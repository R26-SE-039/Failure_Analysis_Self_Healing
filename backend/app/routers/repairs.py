from __future__ import annotations

import json
import logging
import os
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.repair_attempt import RepairAttempt
from app.schemas.repair import (
    ReadOnlyRepairPlan,
    RepairConfirmationRequest,
    RepairPlanRequest,
)
from app.services.repair_agent_client import (
    RepairAgentDownstreamError,
    RepairAgentError,
    RepairAgentValidationError,
    repair_agent_client,
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

    return {
        "attempt_id": attempt.attempt_id,
        "eligible": attempt.eligible,
        "reason": attempt.eligibility_reason,
        "status": attempt.status,
        "mode": attempt.mode,
        "plan": attempt.repair_plan,
        "github_changes_made": False,
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
            "correlation_id=%s stage=plan_failed error_code=%s",
            error.correlation_id,
            error.code,
        )
        attempt.status = "failed"
        attempt.failure_reason = json.dumps(
            {
                "kind": "planning_failure",
                "error_code": error.code,
            }
        )
        db.commit()
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
