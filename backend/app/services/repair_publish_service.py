from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from pydantic import ValidationError

from app.models.repair_attempt import RepairAttempt
from app.schemas.repair import (
    ReadOnlyRepairPlan,
    RepairPublishRequest,
)
from app.services.healing_orchestrator import healing_orchestrator
from app.services.repair_eligibility_service import (
    is_protected_path,
    parse_allowed_repositories,
)
from app.services.secret_redaction import contains_secret


BRANCH_HEAD_MISMATCH_MESSAGE = (
    "Cannot auto-publish because the failed branch has moved since "
    "the failed workflow run. Please rerun diagnosis on the latest "
    "failing commit or review manually."
)


class PublishSafetyError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        failed_check_name: str | None = None,
        missing_field_names: list[str] | None = None,
        flags: dict[str, bool] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.failed_check_name = failed_check_name or code
        self.missing_field_names = sorted(
            set(missing_field_names or [])
        )
        self.flags = flags or {
            "github_changes_made": False,
            "repairable": False,
            "has_proposed_changes": False,
        }

    def safe_diagnostics(self) -> dict[str, object]:
        return {
            "error_code": self.code,
            "failed_check_name": self.failed_check_name,
            "missing_field_names": self.missing_field_names,
            **self.flags,
        }


PLAN_REQUIRED_FIELDS = {
    "attempt_id",
    "base_sha",
    "confirmed_failed_file",
    "confirmed_failed_line",
    "correlation_id",
    "github_changes_made",
    "inspected_files",
    "mode",
    "model",
    "proposed_changes",
    "repairable",
    "risks",
    "root_cause_confirmed",
    "status",
    "suggested_validation_commands",
}
CHANGE_REQUIRED_FIELDS = {
    "file_path",
    "start_line",
    "end_line",
    "before_excerpt",
    "after_excerpt",
    "reason",
}


def _plan_flags(raw_plan: object) -> dict[str, bool]:
    plan = raw_plan if isinstance(raw_plan, dict) else {}
    changes = plan.get("proposed_changes")
    return {
        "github_changes_made": plan.get("github_changes_made") is True,
        "repairable": plan.get("repairable") is True,
        "has_proposed_changes": isinstance(changes, list) and bool(changes),
    }


def _missing_plan_fields(raw_plan: object) -> list[str]:
    if not isinstance(raw_plan, dict):
        return sorted(PLAN_REQUIRED_FIELDS)
    missing = set(PLAN_REQUIRED_FIELDS) - set(raw_plan)
    changes = raw_plan.get("proposed_changes")
    if isinstance(changes, list):
        for change in changes:
            if isinstance(change, dict):
                missing.update(CHANGE_REQUIRED_FIELDS - set(change))
            else:
                missing.update(CHANGE_REQUIRED_FIELDS)
    return sorted(missing)


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    candidate = PurePosixPath(normalized)
    if (
        normalized != path
        or is_protected_path(path)
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise PublishSafetyError(
            "protected_or_invalid_path",
            "The stored repair plan contains an unsafe file path.",
        )
    return candidate.as_posix()


def prepare_publish_request(
    attempt: RepairAttempt,
    *,
    allowed_repositories_value: str | None,
    max_files: int,
    recovery_only: bool = False,
) -> tuple[RepairPublishRequest, dict[str, object]]:
    if not attempt.repair_plan:
        raise PublishSafetyError(
            "missing_repair_plan",
            "A successful read-only repair plan is required.",
            failed_check_name="stored_plan_exists",
        )
    raw_plan = attempt.repair_plan
    plan_flags = _plan_flags(raw_plan)
    missing_fields = _missing_plan_fields(raw_plan)
    if missing_fields:
        raise PublishSafetyError(
            "legacy_plan_schema",
            (
                "This repair plan was created with an older schema. "
                "Please rerun Start Controlled Repair."
            ),
            failed_check_name="stored_plan_schema",
            missing_field_names=missing_fields,
            flags=plan_flags,
        )
    if plan_flags["github_changes_made"]:
        raise PublishSafetyError(
            "already_published",
            "This repair attempt has already changed GitHub.",
            failed_check_name="github_changes_made_is_false",
            flags=plan_flags,
        )
    try:
        plan = ReadOnlyRepairPlan.model_validate(raw_plan)
    except ValidationError as error:
        missing_from_validation = sorted(
            {
                str(item["loc"][-1])
                for item in error.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                )
                if item.get("type") == "missing" and item.get("loc")
            }
        )
        raise PublishSafetyError(
            "stored_plan_invalid",
            "The stored read-only repair plan is invalid.",
            failed_check_name="stored_plan_schema",
            missing_field_names=missing_from_validation,
            flags=plan_flags,
        ) from error

    classification = {
        "final_root_cause": attempt.predicted_root_cause,
        "confidence": attempt.confidence,
        "decision_source": attempt.decision_source,
    }
    route = healing_orchestrator.create_plan(classification)
    if attempt.predicted_root_cause != "application_defect":
        raise PublishSafetyError(
            "wrong_root_cause",
            "Only application defects can be published automatically.",
        )
    if (
        attempt.selected_action != "start_mcp_code_repair"
        or route["action"] != "start_mcp_code_repair"
        or route["confidence_gate_applied"]
    ):
        raise PublishSafetyError(
            "publish_confidence_or_route_failed",
            "The repair no longer passes the controlled-publish gate.",
        )
    if not attempt.eligible:
        raise PublishSafetyError(
            "attempt_not_eligible",
            "The repair attempt is not eligible for publishing.",
        )

    repository = (
        f"{attempt.repository_owner or ''}/"
        f"{attempt.repository_name or ''}"
    ).lower()
    allowed = parse_allowed_repositories(
        allowed_repositories_value
    )
    if not allowed or repository not in allowed:
        raise PublishSafetyError(
            "repository_not_allowed",
            "The repository is not enabled for controlled publishing.",
        )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", attempt.head_sha or ""):
        raise PublishSafetyError(
            "invalid_failed_sha",
            "The stored failed commit SHA is invalid.",
        )
    if not attempt.head_branch:
        raise PublishSafetyError(
            "missing_failed_branch",
            "The stored failed branch is missing.",
        )
    if (
        not re.fullmatch(r"[A-Za-z0-9._/-]{1,255}", attempt.head_branch)
        or ".." in attempt.head_branch
        or "//" in attempt.head_branch
        or attempt.head_branch.startswith("/")
        or attempt.head_branch.endswith("/")
    ):
        raise PublishSafetyError(
            "invalid_failed_branch",
            "The stored failed branch is invalid.",
        )
    if not attempt.run_id or int(attempt.run_id) <= 0:
        raise PublishSafetyError(
            "invalid_workflow_run",
            "The stored workflow run is invalid.",
        )
    if not attempt.candidate_line or int(attempt.candidate_line) <= 0:
        raise PublishSafetyError(
            "invalid_failed_line",
            "The stored failed line is invalid.",
        )
    if attempt.github_changes_made and not recovery_only:
        raise PublishSafetyError(
            "already_published",
            "This repair attempt has already changed GitHub.",
            failed_check_name="attempt_github_changes_made_is_false",
            flags=plan_flags,
        )
    if (
        plan.status != "planned"
        or not plan.repairable
    ):
        raise PublishSafetyError(
            "plan_not_publishable",
            "The stored repair plan is not publishable.",
            failed_check_name=(
                "plan_status_is_planned"
                if plan.status != "planned"
                else "plan_repairable_is_true"
            ),
            flags=plan_flags,
        )
    if plan.base_sha.lower() != attempt.head_sha.lower():
        raise PublishSafetyError(
            "base_sha_mismatch",
            "The stored repair plan does not match the failed commit.",
        )

    candidate = _normalized_path(attempt.candidate_file)
    if plan.confirmed_failed_file != candidate:
        raise PublishSafetyError(
            "changed_file_mismatch",
            "The stored repair plan targets a different failed file.",
        )
    inspected = [_normalized_path(path) for path in plan.inspected_files]
    if candidate not in inspected:
        raise PublishSafetyError(
            "changed_file_mismatch",
            "The failed file was not inspected by the repair plan.",
        )

    changed_files = sorted(
        {_normalized_path(change.file_path) for change in plan.proposed_changes}
    )
    if not changed_files:
        raise PublishSafetyError(
            "missing_proposed_changes",
            "The stored repair plan contains no approved changes.",
            failed_check_name="proposed_changes_exist",
            flags=plan_flags,
        )
    if len(changed_files) > max_files:
        raise PublishSafetyError(
            "changed_file_limit_exceeded",
            "The stored repair plan changes too many files.",
        )
    if any(path not in inspected for path in changed_files):
        raise PublishSafetyError(
            "changed_file_mismatch",
            "The stored repair plan changes an uninspected file.",
        )

    ranges: dict[str, list[tuple[int, int]]] = {}
    for change in plan.proposed_changes:
        path = _normalized_path(change.file_path)
        if not change.before_excerpt.strip():
            raise PublishSafetyError(
                "missing_before_excerpt",
                "The stored repair plan is missing its before excerpt.",
                failed_check_name="before_excerpt_exists",
                missing_field_names=["before_excerpt"],
                flags=plan_flags,
            )
        if not change.after_excerpt.strip():
            raise PublishSafetyError(
                "missing_after_excerpt",
                "The stored repair plan is missing its after excerpt.",
                failed_check_name="after_excerpt_exists",
                missing_field_names=["after_excerpt"],
                flags=plan_flags,
            )
        if change.end_line < change.start_line:
            raise PublishSafetyError(
                "invalid_change_range",
                "The stored repair plan contains an invalid line range.",
            )
        for start, end in ranges.setdefault(path, []):
            if change.start_line <= end and change.end_line >= start:
                raise PublishSafetyError(
                    "overlapping_changes",
                    "The stored repair plan contains overlapping changes.",
                )
        ranges[path].append((change.start_line, change.end_line))

    serialized = json.dumps(plan.model_dump(mode="json"))
    if contains_secret(serialized):
        raise PublishSafetyError(
            "sensitive_plan_content",
            "The stored repair plan contains sensitive content.",
        )

    safety_checks: dict[str, object] = {
        "server_plan_reloaded": True,
        "root_cause_and_route_valid": True,
        "confidence_gate_passed": True,
        "repository_allowed": True,
        "base_sha_valid": True,
        "paths_protected": False,
        "path_traversal_detected": False,
        "changed_file_limit_passed": True,
        "stored_plan_only": True,
        "branch_head_matches_failed_sha": "pending_mcp_verification",
    }
    return (
        RepairPublishRequest(
            attempt_id=attempt.attempt_id,
            repository_owner=attempt.repository_owner or "",
            repository_name=attempt.repository_name or "",
            run_id=int(attempt.run_id or 0),
            run_url=(
                f"https://github.com/{repository}/actions/runs/"
                f"{int(attempt.run_id or 0)}"
            ),
            base_sha=attempt.head_sha,
            failed_branch=attempt.head_branch,
            default_branch=attempt.default_branch,
            root_cause="application_defect",
            confidence=attempt.confidence,
            decision_source=attempt.decision_source,
            selected_action="start_mcp_code_repair",
            error_type=attempt.error_type,
            confirmed_failed_file=candidate,
            confirmed_failed_line=int(attempt.candidate_line or 0),
            inspected_files=inspected,
            proposed_changes=plan.proposed_changes,
            risks=plan.risks,
            suggested_validation_commands=(
                plan.suggested_validation_commands
            ),
            phase1_correlation_id=plan.correlation_id,
            recovery_only=recovery_only,
        ),
        safety_checks,
    )
