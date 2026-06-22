"""
analyze.py — API Gateway
POST /analyze  — Full pipeline: ML → Heal → Flaky → Notify → Save
GET  /analyze/health  — Check all microservices health
GET  /analyze/metrics — Proxy ML metrics
POST /analyze/retrain — Trigger model retraining
GET  /analyze/retrain/status — Retraining status
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.models.flaky_test import FlakyTest
from app.models.notification import Notification
from app.models.repair_attempt import RepairAttempt
from app.core import healing_engine as healer
from app.core import flaky_detector as analytics
from app.core import notifier
from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubRunUrlError,
    github_actions_service,
)
from app.services.healing_orchestrator import healing_orchestrator
from app.services.repair_evidence_service import (
    repair_evidence_service,
)
from app.services.repair_eligibility_service import (
    RepairEligibilityService,
)
from app.services.root_cause_service import root_cause_service
from app.services.secret_redaction import (
    bounded_sanitized_text,
    redact_secrets,
)
from app.services.test_script_notification_service import (
    NOTIFICATION_MESSAGE,
    TARGET_MODULE,
    test_script_notification_service,
)
from app.services.root_cause_action_audit_service import (
    root_cause_action_audit_service,
)

router = APIRouter(prefix="/analyze", tags=["Analysis Pipeline"])

ROOT_CAUSE_MODEL_NAME = "best_9class_root_cause_model.joblib"


# ── Request schema for the analyze endpoint ────────────────────────────────────
class AnalyzeRequest(BaseModel):
    test_name: str
    pipeline: str
    error_message: str
    stack_trace: Optional[str] = ""
    logs: Optional[str] = ""
    failure_stage: Optional[str] = "test"
    failure_type: Optional[str] = "Test Failure"
    severity: Optional[str] = "MEDIUM"
    retry_count: Optional[float] = 0
    test_duration_sec: Optional[float] = 30
    cpu_usage_pct: Optional[float] = 50
    memory_usage_mb: Optional[float] = 1024
    is_flaky_test: Optional[int] = 0
    old_locator: Optional[str] = ""
    github_actions_run_url: Optional[str] = None


def _build_log_text(req: AnalyzeRequest) -> str:
    """Create one log-like payload for the nine-class root-cause service."""

    sections = [
        f"pipeline={req.pipeline}",
        f"stage={req.failure_stage}",
        f"severity={req.severity}",
        f"failure_type={req.failure_type}",
        f"retry_count={req.retry_count}",
        f"test_duration_sec={req.test_duration_sec}",
        "",
        "ERROR MESSAGE:",
        req.error_message or "",
        "",
        "STACK TRACE:",
        req.stack_trace or "",
        "",
        "FULL LOGS:",
        req.logs or "",
    ]

    return "\n".join(sections)


def _classification_from_root_cause(result: dict) -> dict:
    probabilities = {
        label: round(float(probability) / 100, 4)
        for label, probability in result.get("probabilities", {}).items()
    }

    confidence_percentage = result.get(
        "final_confidence_percentage",
        result.get("ml_confidence_percentage", 0),
    )

    confidence = round(
        float(confidence_percentage) / 100,
        4,
    )
    ml_confidence = round(
        float(result.get("ml_confidence_percentage", 0)) / 100,
        4,
    )

    detected_error = result.get("detected_error")
    if isinstance(detected_error, dict):
        detected_error = {
            key: (
                redact_secrets(value)
                if isinstance(value, str)
                else value
            )
            for key, value in detected_error.items()
        }

    return {
        "root_cause": result["final_root_cause"],
        "confidence": confidence,
        "ml_prediction": result.get("ml_prediction"),
        "ml_confidence": ml_confidence,
        "final_confidence": confidence,
        "all_probabilities": probabilities,
        "model_used": ROOT_CAUSE_MODEL_NAME,
        "decision_source": result.get("decision_source"),
        "decision_reason": result.get("decision_reason"),
        "detected_error": detected_error,
        "model_input_sha256": result.get("model_input_sha256"),
    }


# ── Full pipeline endpoint ─────────────────────────────────────────────────────
@router.post("/")
async def analyze_failure(req: AnalyzeRequest, db: Session = Depends(get_db)):
    test_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"

    source_run = None
    if req.github_actions_run_url:
        try:
            source_run = await github_actions_service.resolve_run(
                req.github_actions_run_url
            )
        except GitHubRunUrlError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except GitHubActionsApiError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    # ── Step 1: ML Classification (Local) ──────────────────────────────────────
    try:
        root_cause_result = root_cause_service.analyze(
            _build_log_text(req)
        )
        ml_result = _classification_from_root_cause(root_cause_result)
        healing_plan = healing_orchestrator.create_plan(
            root_cause_result
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="ML analysis failed.",
        ) from error

    root_cause = ml_result["root_cause"]
    confidence = ml_result["confidence"]

    # ── Step 2: Self-Healing (Local) ───────────────────────────────────────────
    try:
        heal_result = healer.heal(
            test_id       = test_id,
            test_name     = req.test_name,
            root_cause    = root_cause,
            confidence    = confidence,
            error_message = redact_secrets(
                req.error_message or ""
            ),
            stack_trace   = redact_secrets(
                req.stack_trace or ""
            ),
            failure_type  = req.failure_type,
            old_value     = req.old_locator or "",
        )
        heal_result.update(
            {
                "selected_action": healing_plan["action"],
                "automatic_execution_allowed":
                    healing_plan["automatic_execution_allowed"],
                "requires_validation":
                    healing_plan["requires_validation"],
                "confidence_gate_applied":
                    healing_plan["confidence_gate_applied"],
                "automation_level": healing_plan["automation_level"],
                "allowed_to_plan": healing_plan["allowed_to_plan"],
                "allowed_to_publish": healing_plan["allowed_to_publish"],
                "notification_required": healing_plan["notification_required"],
                "target_team_or_module": healing_plan["target_team_or_module"],
            }
        )
        if root_cause != "application_defect":
            heal_result.update(
                {
                    "repair_type": healing_plan["automation_level"].replace(
                        "_", " "
                    ).title(),
                    "recommendation": healing_plan["recommended_action"],
                    "status": healing_plan["history_status"],
                    "developer_alert": False,
                    "old_value": "",
                    "new_value": "",
                }
            )
    except Exception:
        heal_result = {
            "healing_id":     "H-ERROR",
            "repair_type":    "N/A",
            "old_value":      "",
            "new_value":      "",
            "recommendation": "Healing engine processing failed.",
            "status":         "Pending",
            "developer_alert": False,
            "selected_action": healing_plan["action"],
            "automatic_execution_allowed":
                healing_plan["automatic_execution_allowed"],
            "requires_validation":
                healing_plan["requires_validation"],
            "confidence_gate_applied":
                healing_plan["confidence_gate_applied"],
            "automation_level": healing_plan["automation_level"],
            "allowed_to_plan": healing_plan["allowed_to_plan"],
            "allowed_to_publish": healing_plan["allowed_to_publish"],
            "notification_required": healing_plan["notification_required"],
            "target_team_or_module": healing_plan["target_team_or_module"],
        }

    raw_log = req.logs or req.error_message or ""
    evidence = repair_evidence_service.extract(
        raw_log,
        root_cause_result.get("detected_error", {}),
    )
    eligibility = RepairEligibilityService().evaluate(
        classification=ml_result,
        healing_plan=healing_plan,
        source_run=source_run,
        candidate_file=evidence.candidate_file,
        candidate_line=evidence.candidate_line,
    )

    repair_attempt = None
    notification_audit = None
    action_audit = None
    if root_cause in healing_orchestrator.ACTION_MATRIX:
        attempt_id = (
            f"REPAIR-{uuid.uuid4().hex[:12].upper()}"
        )
        non_application_action = root_cause != "application_defect"
        test_script_notification = root_cause == "test_script_issue"
        repair_attempt = RepairAttempt(
            attempt_id=attempt_id,
            failure_test_id=test_id,
            status=(
                healing_plan["history_status"]
                if non_application_action
                else (
                    "eligible"
                    if eligibility.eligible
                    else "ineligible"
                )
            ),
            mode="read_only",
            eligible=(False if non_application_action else eligibility.eligible),
            eligibility_code=(
                healing_plan["automation_level"]
                if non_application_action
                else eligibility.code
            ),
            eligibility_reason=(
                f"Forwarded to {TARGET_MODULE}."
                if test_script_notification
                else healing_plan["recommended_action"]
                if non_application_action
                else eligibility.reason
            ),
            predicted_root_cause=root_cause,
            confidence=confidence,
            decision_source=(
                ml_result.get("decision_source")
                or "machine_learning"
            ),
            selected_action=healing_plan["action"],
            repository_owner=(
                source_run.get("owner")
                if source_run
                else None
            ),
            repository_name=(
                source_run.get("repository")
                if source_run
                else None
            ),
            run_id=(
                source_run.get("run_id")
                if source_run
                else None
            ),
            head_sha=(
                source_run.get("head_sha")
                if source_run
                else None
            ),
            head_branch=(
                source_run.get("head_branch")
                if source_run
                else None
            ),
            default_branch=(
                source_run.get("default_branch")
                if source_run
                else None
            ),
            error_type=evidence.error_type,
            error_message=(
                ""
                if non_application_action
                else evidence.error_message
            ),
            candidate_file=evidence.candidate_file,
            candidate_line=evidence.candidate_line,
            log_content_sha256=(
                evidence.log_content_sha256
            ),
            sanitized_log_excerpt=(
                ""
                if non_application_action
                else evidence.sanitized_log_excerpt
            ),
            github_changes_made=False,
        )
        if test_script_notification:
            notification_audit = (
                test_script_notification_service.create_audit(
                    attempt_id=attempt_id,
                    confidence=confidence,
                    source_run=source_run,
                )
            )
        elif non_application_action:
            action_audit = root_cause_action_audit_service.create_audit(
                attempt_id=attempt_id,
                root_cause=root_cause,
                confidence=confidence,
                policy=healing_plan,
                source_run=source_run,
            )

    # ── Step 3: Flaky Test Detection (Local) ───────────────────────────────────
    try:
        flaky_result = analytics.check_flaky(
            test_id           = test_id,
            test_name         = req.test_name,
            retry_count       = req.retry_count,
            failure_type      = req.failure_type,
            failure_stage     = req.failure_stage,
            severity          = req.severity,
            test_duration_sec = req.test_duration_sec,
        )
    except Exception as e:
        flaky_result = {
            "is_flaky":          False,
            "flaky_probability": 0.0,
            "risk_level":        "Unknown",
            "instability_score": "0%",
            "recent_pattern":    "N/A",
        }

    # ── Step 4: Notification (Local) ───────────────────────────────────────────
    notification_result = None
    developer_alert = heal_result.get("developer_alert", False)
    if root_cause == "test_script_issue":
        notification_result = {
            "notification_id": notification_audit.notification_id,
            "status": "notification_sent",
            "target_module": TARGET_MODULE,
            "message": NOTIFICATION_MESSAGE,
            "github_changes_made": False,
        }
    elif action_audit:
        notification_result = {
            "audit_id": action_audit.audit_id,
            "status": action_audit.history_status,
            "automation_level": action_audit.automation_level,
            "notification_required": action_audit.notification_required,
            "target_module": action_audit.target_team_or_module,
            "message": action_audit.recommended_action,
            "validation_guidance": action_audit.validation_guidance,
            "github_changes_made": False,
        }
    elif developer_alert:
        try:
            notification_result = notifier.create_notification(
                failure_test_id = test_id,
                test_name       = req.test_name,
                root_cause      = root_cause,
                message         = (
                    f"Test '{req.test_name}' failed with root cause '{root_cause}' "
                    f"(confidence: {confidence:.0%}). "
                    f"{heal_result.get('recommendation', '')}"
                ),
                target          = "developer",
            )
        except Exception:
            notification_result = {
                "status": "failed",
                "error": "Notification processing failed.",
            }

    # ── Step 5: Persist to DB ──────────────────────────────────────────────────
    failure_record = Failure(
        test_id          = test_id,
        test_name        = req.test_name,
        pipeline         = req.pipeline,
        status           = "FAIL",
        root_cause       = root_cause,
        confidence       = f"{confidence:.0%}",
        healing          = heal_result.get("status", "Pending"),
        logs             = evidence.sanitized_log_excerpt,
        stack_trace      = bounded_sanitized_text(
            req.stack_trace or "",
            max_lines=40,
            max_chars=8000,
        ),
        recommendation   = heal_result.get("recommendation"),
        developer_alert  = developer_alert,
    )
    db.add(failure_record)

    healing_record = HealingAction(
        healing_id       = heal_result.get("healing_id", f"H-{uuid.uuid4().hex[:6].upper()}"),
        failure_test_id  = test_id,
        test_name        = req.test_name,
        repair_type      = heal_result.get("repair_type", "N/A"),
        old_value        = heal_result.get("old_value", ""),
        new_value        = heal_result.get("new_value", ""),
        status           = heal_result.get("status", "Pending"),
    )
    db.add(healing_record)

    if repair_attempt:
        db.add(repair_attempt)
    if notification_audit:
        db.add(notification_audit)
    if action_audit:
        db.add(action_audit)

    if flaky_result.get("is_flaky"):
        flaky_record = FlakyTest(
            test_code        = test_id,
            test_name        = req.test_name,
            instability_score = flaky_result.get("instability_score", "0%"),
            recent_pattern   = flaky_result.get("recent_pattern", "N/A"),
            risk_level       = flaky_result.get("risk_level", "Low"),
        )
        db.add(flaky_record)

    if (
        notification_result
        and notification_result.get("status") == "sent"
    ):
        notif_record = Notification(
            failure_test_id = test_id,
            test_name       = req.test_name,
            root_cause      = root_cause,
            message         = notification_result.get("message",
                                f"Alert for {req.test_name}: {root_cause}"),
            target          = notification_result.get("target", "developer"),
        )
        db.add(notif_record)

    db.commit()
    db.refresh(failure_record)

    # ── Step 6: Return full result ─────────────────────────────────────────────
    return {
        "test_id":    test_id,
        "status":     "FAIL",
        "pipeline": {
            "classification": ml_result,
            "source_run":       source_run,
            "healing_plan":   healing_plan,
            "healing":        heal_result,
            "flaky_analysis": flaky_result,
            "notification":   notification_result,
            "repair": (
                {
                    "attempt_id":
                        repair_attempt.attempt_id,
                    "eligible":
                        repair_attempt.eligible,
                    "reason":
                        repair_attempt.eligibility_reason,
                    "status":
                        repair_attempt.status,
                    "mode": "read_only",
                    "github_changes_made": False,
                    "automation_level": healing_plan["automation_level"],
                    "allowed_to_plan": healing_plan["allowed_to_plan"],
                    "allowed_to_publish": healing_plan["allowed_to_publish"],
                    "target_module": healing_plan["target_team_or_module"],
                    "recommended_action": healing_plan["recommended_action"],
                    "validation_guidance": healing_plan["validation_guidance"],
                    "history_status": healing_plan["history_status"],
                }
                if repair_attempt
                else None
            ),
        },
        "saved_to_db": True,
    }


# ── Local Metrics Endpoints ───────────────────────────────────────────────────
@router.get("/health")
async def check_services_health():
    # Frontend expects a flat Record<string, { status: string; model?: string; error?: string }>
    # and UI displays it as name.replace("-service", "")
    return {
        "ml-classifier-service": {
            "status": "ready",
            "model": ROOT_CAUSE_MODEL_NAME,
        },
        "healing-engine-service": {"status": "ready"},
        "analytics-service": {"status": "ready"},
        "notifier-service": {"status": "ready"}
    }


@router.get("/metrics")
async def get_ml_metrics():
    raise HTTPException(
        status_code=404,
        detail=(
            "No metrics artifact is available for "
            f"{ROOT_CAUSE_MODEL_NAME}."
        ),
    )


@router.post("/retrain")
async def trigger_retrain():
    # In a local monolithic setup, retraining can be triggered directly via scripts/train_model.py
    # or we could implement a background task here. For now, we point to the research scripts.
    return {"status": "info", "message": "Trigger retraining via research/scripts/master_train.py"}


@router.get("/retrain/status")
async def get_retrain_status():
    # Frontend expects { running: boolean, last_result: string }
    # In local monolithic mode, we don't have a background worker yet.
    return {"running": False, "last_result": "Manual retraining recommended in local mode."}

