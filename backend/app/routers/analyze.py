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
from app.services import gateway_client as gc

router = APIRouter(prefix="/analyze", tags=["Analysis Pipeline"])


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


# ── Full pipeline endpoint ─────────────────────────────────────────────────────
@router.post("/")
async def analyze_failure(req: AnalyzeRequest, db: Session = Depends(get_db)):
    test_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"

    # ── Step 1: ML Classification ──────────────────────────────────────────────
    try:
        ml_result = await gc.classify({
            "error_message":    req.error_message,
            "stack_trace":      req.stack_trace or "",
            "failure_stage":    req.failure_stage,
            "failure_type":     req.failure_type,
            "severity":         req.severity,
            "retry_count":      req.retry_count,
            "test_duration_sec": req.test_duration_sec,
            "cpu_usage_pct":    req.cpu_usage_pct,
            "memory_usage_mb":  req.memory_usage_mb,
            "is_flaky_test":    req.is_flaky_test,
        })
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ML Service unavailable: {e}")

    root_cause = ml_result["root_cause"]
    confidence = ml_result["confidence"]

    # ── Step 2: Self-Healing ───────────────────────────────────────────────────
    try:
        heal_result = await gc.heal({
            "test_id":       test_id,
            "test_name":     req.test_name,
            "root_cause":    root_cause,
            "confidence":    confidence,
            "error_message": req.error_message,
            "stack_trace":   req.stack_trace or "",
            "failure_type":  req.failure_type,
            "old_value":     req.old_locator or "",
        })
    except Exception as e:
        heal_result = {
            "healing_id":     f"H-UNAVAIL",
            "repair_type":    "N/A",
            "old_value":      "",
            "new_value":      "",
            "recommendation": f"Healing service unavailable: {e}",
            "status":         "Pending",
            "developer_alert": False,
        }

    # ── Step 3: Flaky Test Detection ───────────────────────────────────────────
    try:
        flaky_result = await gc.check_flaky({
            "test_id":          test_id,
            "test_name":        req.test_name,
            "retry_count":      req.retry_count,
            "failure_type":     req.failure_type,
            "failure_stage":    req.failure_stage,
            "severity":         req.severity,
            "test_duration_sec": req.test_duration_sec,
        })
    except Exception as e:
        flaky_result = {
            "is_flaky":          False,
            "flaky_probability": 0.0,
            "risk_level":        "Unknown",
            "instability_score": "0%",
            "recent_pattern":    "N/A",
        }

    # ── Step 4: Notification (if developer alert needed) ───────────────────────
    notification_result = None
    developer_alert = heal_result.get("developer_alert", False)
    if developer_alert:
        try:
            notification_result = await gc.notify({
                "failure_test_id": test_id,
                "test_name":       req.test_name,
                "root_cause":      root_cause,
                "message":         (
                    f"Test '{req.test_name}' failed with root cause '{root_cause}' "
                    f"(confidence: {confidence:.0%}). "
                    f"{heal_result.get('recommendation', '')}"
                ),
                "target":          "developer",
            })
        except Exception as e:
            notification_result = {"status": "failed", "error": str(e)}

    # ── Step 5: Persist to DB ──────────────────────────────────────────────────
    failure_record = Failure(
        test_id          = test_id,
        test_name        = req.test_name,
        pipeline         = req.pipeline,
        status           = "FAIL",
        root_cause       = root_cause,
        confidence       = f"{confidence:.0%}",
        healing          = heal_result.get("status", "Pending"),
        logs             = req.logs or req.error_message,
        stack_trace      = req.stack_trace,
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

    if flaky_result.get("is_flaky"):
        flaky_record = FlakyTest(
            test_code        = test_id,
            test_name        = req.test_name,
            instability_score = flaky_result.get("instability_score", "0%"),
            recent_pattern   = flaky_result.get("recent_pattern", "N/A"),
            risk_level       = flaky_result.get("risk_level", "Low"),
        )
        db.add(flaky_record)

    if notification_result and notification_result.get("status") == "sent":
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
            "healing":        heal_result,
            "flaky_analysis": flaky_result,
            "notification":   notification_result,
        },
        "saved_to_db": True,
    }


# ── Proxy endpoints ────────────────────────────────────────────────────────────
@router.get("/health")
async def check_services_health():
    return await gc.services_health()


@router.get("/metrics")
async def get_ml_metrics():
    try:
        return await gc.get_ml_metrics()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ML Service unavailable: {e}")


@router.post("/retrain")
async def trigger_retrain():
    try:
        return await gc.trigger_retrain()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ML Service unavailable: {e}")


@router.get("/retrain/status")
async def get_retrain_status():
    try:
        return await gc.get_retrain_status()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ML Service unavailable: {e}")
