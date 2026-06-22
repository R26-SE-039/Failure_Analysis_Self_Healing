from __future__ import annotations

import json
import logging
import os
from pathlib import PurePosixPath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.repair_attempt import RepairAttempt
from app.models.repair_publish_audit import RepairPublishAudit
from app.models.test_script_notification_audit import (
    TestScriptNotificationAudit,
)
from app.models.root_cause_action_audit import RootCauseActionAudit
from app.schemas.repair import (
    PublishConfirmationRequest,
    ReadOnlyRepairPlan,
    RepairConfirmationRequest,
    RepairHistoryItem,
    RepairPlanRequest,
)
from app.services.repair_agent_client import (
    RepairAgentDownstreamError,
    RepairAgentError,
    RepairAgentValidationError,
    RepairPublishError,
    repair_agent_client,
)
from app.services.healing_orchestrator import healing_orchestrator
from app.services.repair_publish_service import (
    BRANCH_HEAD_MISMATCH_MESSAGE,
    PublishSafetyError,
    prepare_publish_request,
)
from app.services.repair_eligibility_service import (
    is_protected_path,
)
from app.services.secret_redaction import contains_secret


router = APIRouter(
    prefix="/api/repairs",
    tags=["Controlled Repair"],
)
logger = logging.getLogger(__name__)

PREWRITE_VALIDATION_ERROR_CODES = {
    "plan_not_publishable",
    "stored_plan_invalid",
    "legacy_plan_schema",
    "missing_proposed_changes",
    "missing_before_excerpt",
    "missing_after_excerpt",
    "protected_or_invalid_path",
    "changed_file_mismatch",
    "changed_file_limit_exceeded",
}
PUBLISH_RECOVERY_ERROR_CODES = {
    "draft_pr_identity_missing",
    "publish_partial_manual_review_required",
}


def _repository_name(attempt: RepairAttempt) -> Optional[str]:
    if not attempt.repository_owner or not attempt.repository_name:
        return None
    return f"{attempt.repository_owner}/{attempt.repository_name}".lower()


@router.get("/history", response_model=list[RepairHistoryItem])
def get_repair_history(
    root_cause: Optional[str] = None,
    publish_status: Optional[str] = None,
    repository: Optional[str] = None,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            RepairAttempt,
            RepairPublishAudit,
            TestScriptNotificationAudit,
            RootCauseActionAudit,
        )
        .outerjoin(
            RepairPublishAudit,
            RepairPublishAudit.attempt_id == RepairAttempt.attempt_id,
        )
        .outerjoin(
            TestScriptNotificationAudit,
            TestScriptNotificationAudit.attempt_id == RepairAttempt.attempt_id,
        )
        .outerjoin(
            RootCauseActionAudit,
            RootCauseActionAudit.attempt_id == RepairAttempt.attempt_id,
        )
        .order_by(RepairAttempt.created_at.desc())
        .all()
    )
    repository_filter = repository.strip().lower() if repository else None
    history: list[RepairHistoryItem] = []
    for attempt, audit, notification_audit, action_audit in rows:
        repository_name = _repository_name(attempt)
        current_publish_status = audit.publish_status if audit else None
        if root_cause and attempt.predicted_root_cause != root_cause:
            continue
        action_status = (
            notification_audit.status
            if notification_audit
            else action_audit.history_status
            if action_audit
            else None
        )
        policy = healing_orchestrator.create_plan(
            {
                "final_root_cause": attempt.predicted_root_cause,
                "confidence": attempt.confidence,
                "decision_source": attempt.decision_source,
            }
        )
        if (
            publish_status
            and current_publish_status != publish_status
            and action_status != publish_status
        ):
            continue
        if repository_filter and repository_name != repository_filter:
            continue
        run_url = (
            f"https://github.com/{repository_name}/actions/runs/{attempt.run_id}"
            if repository_name and attempt.run_id
            else None
        )
        history.append(
            RepairHistoryItem(
                attempt_id=attempt.attempt_id,
                root_cause=attempt.predicted_root_cause,
                confidence=attempt.confidence,
                repository=repository_name,
                failed_branch=attempt.head_branch,
                failed_sha=attempt.head_sha,
                github_run_url=run_url,
                candidate_file=attempt.candidate_file,
                candidate_line=attempt.candidate_line,
                healing_action=attempt.selected_action,
                plan_status=attempt.status,
                publish_status=current_publish_status,
                action_status=action_status,
                target_module=(
                    notification_audit.target_module
                    if notification_audit
                    else action_audit.target_team_or_module
                    if action_audit
                    else policy["target_team_or_module"]
                ),
                automation_level=(
                    action_audit.automation_level
                    if action_audit
                    else policy["automation_level"]
                ),
                recommended_action=(
                    action_audit.recommended_action
                    if action_audit
                    else policy["recommended_action"]
                ),
                validation_guidance=(
                    action_audit.validation_guidance
                    if action_audit
                    else policy["validation_guidance"]
                ),
                history_status=(
                    action_audit.history_status
                    if action_audit
                    else action_status or attempt.status
                ),
                repair_branch=(
                    audit.repair_branch
                    if audit
                    and attempt.predicted_root_cause == "application_defect"
                    else None
                ),
                commit_sha=(
                    audit.commit_sha
                    if audit
                    and attempt.predicted_root_cause == "application_defect"
                    else None
                ),
                draft_pr_url=(
                    audit.draft_pr_url
                    if audit
                    and attempt.predicted_root_cause == "application_defect"
                    else None
                ),
                github_changes_made=bool(
                    attempt.predicted_root_cause == "application_defect"
                    and (
                        attempt.github_changes_made
                        or (audit and audit.github_changes_made)
                    )
                ),
                created_at=attempt.created_at,
                updated_at=(
                    max(attempt.updated_at, audit.updated_at)
                    if audit and audit.updated_at
                    else attempt.updated_at
                ),
            )
        )
    return history


def _validated_plan(
    attempt: RepairAttempt,
    plan: ReadOnlyRepairPlan,
) -> ReadOnlyRepairPlan:
    max_files = int(os.getenv("REPAIR_MAX_FILES", "4"))
    max_excerpt_lines = int(
        os.getenv("REPAIR_MAX_EXCERPT_LINES", "12")
    )
    max_excerpt_chars = int(
        os.getenv("REPAIR_MAX_EXCERPT_CHARS", "2000")
    )

    if plan.attempt_id != attempt.attempt_id:
        raise ValueError("Repair attempt identity mismatch.")
    if plan.base_sha.lower() != (attempt.head_sha or "").lower():
        raise ValueError("Repair plan SHA mismatch.")
    if plan.confirmed_failed_file != attempt.candidate_file:
        if (
            is_protected_path(plan.confirmed_failed_file)
            or PurePosixPath(plan.confirmed_failed_file).name
            != PurePosixPath(attempt.candidate_file).name
        ):
            raise ValueError("Repair plan failed-file mismatch.")
    if plan.confirmed_failed_line != attempt.candidate_line:
        raise ValueError("Repair plan failed-line mismatch.")
    if plan.github_changes_made is not False:
        raise ValueError("Read-only plan reported GitHub changes.")
    if len(set(plan.inspected_files)) > max_files:
        raise ValueError("Repair plan inspected too many files.")

    for path in plan.inspected_files:
        if is_protected_path(path):
            raise ValueError("Repair plan inspected a protected path.")

    for change in plan.proposed_changes:
        if is_protected_path(change.file_path):
            raise ValueError("Repair plan targets a protected path.")
        if change.end_line < change.start_line:
            raise ValueError("Repair plan line range is invalid.")
        if (
            len(change.before_excerpt.splitlines())
            > max_excerpt_lines
            or len(change.after_excerpt.splitlines())
            > max_excerpt_lines
            or len(change.before_excerpt) > max_excerpt_chars
            or len(change.after_excerpt) > max_excerpt_chars
        ):
            raise ValueError("Repair plan excerpt is too large.")

    serialized = json.dumps(plan.model_dump())
    if contains_secret(serialized):
        raise ValueError("Repair plan contains sensitive content.")
    return plan


@router.get("/{attempt_id}")
def get_repair_attempt(
    attempt_id: str,
    db: Session = Depends(get_db),
):
    attempt = (
        db.query(RepairAttempt)
        .filter(RepairAttempt.attempt_id == attempt_id)
        .first()
    )
    if not attempt:
        raise HTTPException(
            status_code=404,
            detail="Repair attempt not found.",
        )

    publish_audit = (
        db.query(RepairPublishAudit)
        .filter(RepairPublishAudit.attempt_id == attempt_id)
        .first()
    )
    return {
        "attempt_id": attempt.attempt_id,
        "eligible": attempt.eligible,
        "reason": attempt.eligibility_reason,
        "status": attempt.status,
        "mode": attempt.mode,
        "plan": attempt.repair_plan,
        "github_changes_made": bool(
            attempt.github_changes_made
            or (
                publish_audit
                and publish_audit.github_changes_made
            )
        ),
        "publish": (
            {
                "publish_status": publish_audit.publish_status,
                "validation_status": publish_audit.validation_status,
                "repair_branch": publish_audit.repair_branch,
                "commit_sha": publish_audit.commit_sha,
                "draft_pr_number": publish_audit.draft_pr_number,
                "draft_pr_url": publish_audit.draft_pr_url,
                "error_code": publish_audit.error_code,
            }
            if publish_audit
            else None
        ),
    }


@router.post("/{attempt_id}/plan")
async def create_read_only_plan(
    attempt_id: str,
    confirmation: RepairConfirmationRequest,
    db: Session = Depends(get_db),
):
    if confirmation.confirm_read_only is not True:
        raise HTTPException(
            status_code=400,
            detail="Explicit read-only confirmation is required.",
        )

    attempt = (
        db.query(RepairAttempt)
        .filter(RepairAttempt.attempt_id == attempt_id)
        .first()
    )
    if not attempt:
        raise HTTPException(
            status_code=404,
            detail="Repair attempt not found.",
        )
    action_policy = healing_orchestrator.create_plan(
        {
            "final_root_cause": attempt.predicted_root_cause,
            "confidence": attempt.confidence,
            "decision_source": attempt.decision_source,
        }
    )
    if not action_policy["allowed_to_plan"]:
        raise HTTPException(
            status_code=409,
            detail="This root cause is not eligible for repair planning.",
        )
    if not attempt.eligible:
        raise HTTPException(
            status_code=409,
            detail=attempt.eligibility_reason,
        )
    if attempt.repair_plan:
        return attempt.repair_plan
    if attempt.status == "planning":
        raise HTTPException(
            status_code=409,
            detail="Repair planning is already in progress.",
        )

    attempt.status = "planning"
    attempt.failure_reason = None
    db.commit()

    request = RepairPlanRequest(
        attempt_id=attempt.attempt_id,
        repository_owner=attempt.repository_owner or "",
        repository_name=attempt.repository_name or "",
        run_id=int(attempt.run_id or 0),
        head_sha=attempt.head_sha or "",
        head_branch=attempt.head_branch or "",
        default_branch=attempt.default_branch,
        root_cause=attempt.predicted_root_cause,
        confidence=attempt.confidence,
        decision_source=attempt.decision_source,
        selected_action=attempt.selected_action,
        error_type=attempt.error_type,
        error_message=attempt.error_message,
        candidate_file=attempt.candidate_file,
        candidate_line=attempt.candidate_line,
        sanitized_log_excerpt=(
            attempt.sanitized_log_excerpt
        ),
    )

    try:
        result = await repair_agent_client.create_plan(request)
        result = _validated_plan(attempt, result)
    except RepairAgentValidationError as error:
        logger.warning(
            "correlation_id=%s stage=plan_failed "
            "error_code=plan_validation_failed",
            error.correlation_id,
        )
        attempt.status = "failed"
        attempt.failure_reason = json.dumps(
            {
                "kind": "request_validation",
                "errors": error.diagnostics,
            }
        )
        db.commit()
        raise HTTPException(
            status_code=502,
            detail=(
                "Read-only repair planning could not be completed."
            ),
        )
    except RepairAgentDownstreamError as error:
        logger.warning(
            "correlation_id=%s stage=plan_failed error_code=%s "
            "diagnostics=%s",
            error.correlation_id,
            error.code,
            error.diagnostics,
        )
        attempt.status = "failed"
        attempt.failure_reason = json.dumps(
            {
                "kind": "planning_failure",
                "error_code": error.code,
                "diagnostics": error.diagnostics,
            }
        )
        db.commit()
        if error.code == "plan_validation_failed":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        "The generated repair plan failed safety "
                        "validation. Please retry or review manually."
                    ),
                    "error_code": error.code,
                    "correlation_id": error.correlation_id,
                    "diagnostics": error.diagnostics,
                },
            )
        raise HTTPException(
            status_code=502,
            detail=(
                "Read-only repair planning could not be completed."
            ),
        )
    except (RepairAgentError, ValueError):
        attempt.status = "failed"
        attempt.failure_reason = (
            "Read-only repair planning failed safety validation."
        )
        db.commit()
        raise HTTPException(
            status_code=502,
            detail=(
                "Read-only repair planning could not be completed."
            ),
        )

    attempt.status = result.status
    attempt.inspected_files = result.inspected_files
    attempt.repair_plan = result.model_dump()
    attempt.provider_model = result.model
    attempt.github_changes_made = False
    db.commit()

    return result.model_dump()


@router.post("/{attempt_id}/publish")
async def publish_approved_repair(
    attempt_id: str,
    confirmation: PublishConfirmationRequest,
    db: Session = Depends(get_db),
):
    if confirmation.confirm_publish is not True:
        raise HTTPException(
            status_code=400,
            detail="Explicit publish confirmation is required.",
        )

    attempt_query = db.query(RepairAttempt).filter(
        RepairAttempt.attempt_id == attempt_id
    )
    if hasattr(attempt_query, "with_for_update"):
        attempt_query = attempt_query.with_for_update()
    attempt = attempt_query.first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Repair attempt not found.")

    action_policy = healing_orchestrator.create_plan(
        {
            "final_root_cause": attempt.predicted_root_cause,
            "confidence": attempt.confidence,
            "decision_source": attempt.decision_source,
        }
    )
    if not action_policy["allowed_to_publish"]:
        raise HTTPException(
            status_code=409,
            detail="This root cause is not eligible for GitHub publishing.",
        )

    existing = (
        db.query(RepairPublishAudit)
        .filter(RepairPublishAudit.attempt_id == attempt_id)
        .first()
    )
    reusable_validation_audit = bool(
        existing
        and not existing.github_changes_made
        and existing.error_code in PREWRITE_VALIDATION_ERROR_CODES
    )
    recovery_audit = bool(
        existing
        and (
            existing.error_code in PUBLISH_RECOVERY_ERROR_CODES
            or (
                existing.error_code == "publish_mcp_failed"
                and existing.publish_status == "commit_created"
            )
        )
        and existing.github_changes_made
        and existing.repair_branch
        and existing.commit_sha
        and not existing.draft_pr_number
        and not existing.draft_pr_url
    )
    if (
        (existing and not reusable_validation_audit and not recovery_audit)
        or (attempt.github_changes_made and not recovery_audit)
    ):
        raise HTTPException(
            status_code=409,
            detail="This repair attempt has already entered publishing.",
        )

    repository = (
        f"{attempt.repository_owner or ''}/"
        f"{attempt.repository_name or ''}"
    ).lower()
    try:
        publish_request, safety_checks = prepare_publish_request(
            attempt,
            allowed_repositories_value=os.getenv(
                "GITHUB_ALLOWED_REPOSITORIES"
            ),
            max_files=int(os.getenv("REPAIR_MAX_FILES", "4")),
            recovery_only=recovery_audit,
        )
    except PublishSafetyError as error:
        audit = existing or RepairPublishAudit(
            attempt_id=attempt.attempt_id,
            repository=repository,
            base_sha=attempt.head_sha or "unknown",
            failed_branch=attempt.head_branch or "unknown",
        )
        audit.publish_status = "manual_review"
        audit.validation_status = "failed"
        audit.changed_files = []
        audit.safety_check_results = {
            "server_validation_passed": False,
            **error.safe_diagnostics(),
        }
        audit.error_code = error.code
        audit.github_changes_made = False
        if existing is None:
            db.add(audit)
        db.commit()
        return JSONResponse(
            status_code=409,
            content=error.safe_diagnostics(),
        )

    changed_files = sorted(
        {change.file_path for change in publish_request.proposed_changes}
    )
    audit = existing or RepairPublishAudit(
        attempt_id=attempt.attempt_id,
        repository=repository,
        base_sha=publish_request.base_sha,
        failed_branch=publish_request.failed_branch,
    )
    audit.correlation_id = None
    if not recovery_audit:
        audit.repair_branch = None
        audit.commit_sha = None
        audit.draft_pr_number = None
        audit.draft_pr_url = None
    audit.publish_status = "in_progress"
    audit.validation_status = "pending"
    audit.changed_files = changed_files
    audit.safety_check_results = safety_checks
    audit.error_code = None
    audit.github_changes_made = False
    if existing is None:
        db.add(audit)
    db.commit()

    try:
        result = await repair_agent_client.publish_plan(publish_request)
    except RepairPublishError as error:
        state = error.state
        audit.correlation_id = error.correlation_id
        audit.repair_branch = state.get("repair_branch")
        audit.commit_sha = state.get("commit_sha")
        audit.draft_pr_number = state.get("draft_pr_number")
        audit.draft_pr_url = state.get("draft_pr_url")
        audit.publish_status = (
            "manual_review"
            if error.code == "branch_head_mismatch"
            else state.get("publish_status", "failed")
        )
        audit.validation_status = state.get(
            "validation_status",
            "failed",
        )
        audit.error_code = error.code
        audit.github_changes_made = bool(
            state.get("github_changes_made", False)
        )
        if audit.github_changes_made:
            attempt.github_changes_made = True
        checks = dict(audit.safety_check_results or {})
        for flag in ("branch_created", "commit_created", "pr_created"):
            if flag in state and isinstance(state[flag], bool):
                checks[flag] = state[flag]
        if error.code == "branch_head_mismatch":
            checks["branch_head_matches_failed_sha"] = False
        audit.safety_check_results = checks
        db.commit()
        if error.code == "publish_partial_manual_review_required":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        "The repair branch and commit exist, but the draft "
                        "pull request could not be recovered. Manual review "
                        "is required."
                    ),
                    "error_code": error.code,
                    "branch_created": bool(state.get("branch_created")),
                    "commit_created": bool(state.get("commit_created")),
                    "pr_created": bool(state.get("pr_created")),
                },
            )
        detail = (
            BRANCH_HEAD_MISMATCH_MESSAGE
            if error.code == "branch_head_mismatch"
            else "Controlled repair publishing could not be completed."
        )
        raise HTTPException(
            status_code=(409 if error.code == "branch_head_mismatch" else 502),
            detail=detail,
        )

    audit.correlation_id = result.correlation_id
    audit.repair_branch = result.repair_branch
    audit.commit_sha = result.commit_sha
    audit.draft_pr_number = result.draft_pr_number
    audit.draft_pr_url = result.draft_pr_url
    audit.publish_status = result.publish_status
    audit.validation_status = result.validation_status
    audit.changed_files = result.changed_files
    audit.github_changes_made = True
    checks = dict(audit.safety_check_results or {})
    checks["branch_head_matches_failed_sha"] = True
    checks["draft_pull_request_verified"] = True
    checks["automatic_merge_performed"] = False
    audit.safety_check_results = checks

    attempt.github_changes_made = True
    attempt.status = "awaiting_review"
    db.commit()
    return result.model_dump(mode="json")
