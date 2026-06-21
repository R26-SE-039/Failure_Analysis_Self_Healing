from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import ValidationError

from app.schemas.repair import (
    ProposedChange,
    ReadOnlyRepairPlan,
    RepairPlanRequest,
    RepairPublishRequest,
    RepairPublishResult,
)


logger = logging.getLogger(__name__)


class RepairAgentError(RuntimeError):
    pass


class RepairAgentValidationError(RepairAgentError):
    def __init__(
        self,
        diagnostics: list[dict[str, Any]],
        correlation_id: str = "unavailable",
    ) -> None:
        super().__init__(
            "The repair-agent request contract was rejected."
        )
        self.diagnostics = diagnostics
        self.correlation_id = correlation_id


class RepairAgentDownstreamError(RepairAgentError):
    def __init__(
        self,
        code: str,
        correlation_id: str = "unavailable",
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            "The repair agent could not complete planning."
        )
        self.code = code
        self.correlation_id = correlation_id
        self.diagnostics = diagnostics or {}


class RepairAgentResponseError(RepairAgentError):
    def __init__(
        self,
        diagnostics: list[dict[str, Any]],
        correlation_id: str = "unavailable",
    ) -> None:
        super().__init__(
            "The repair agent returned an invalid response."
        )
        self.diagnostics = diagnostics
        self.correlation_id = correlation_id


class RepairPublishError(RepairAgentError):
    def __init__(
        self,
        code: str,
        correlation_id: str = "unavailable",
        state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("Controlled repair publishing failed.")
        self.code = code
        self.correlation_id = correlation_id
        self.state = state or {}


ALLOWED_ERROR_CODES = {
    "openrouter_rate_limited",
    "openrouter_timeout",
    "openrouter_provider_error",
    "structured_output_invalid",
    "structured_output_missing",
    "mcp_read_failed",
    "mcp_decode_failed",
    "plan_validation_failed",
    "planner_internal_error",
    "branch_head_mismatch",
    "write_token_missing",
    "publish_request_invalid",
    "publish_safety_failed",
    "publish_mcp_failed",
    "publish_response_invalid",
    "draft_pr_identity_missing",
    "publish_partial_manual_review_required",
}

PUBLISH_STATE_FIELDS = {
    "publish_status",
    "validation_status",
    "repair_branch",
    "commit_sha",
    "draft_pr_number",
    "draft_pr_url",
    "changed_files",
    "github_changes_made",
    "branch_created",
    "commit_created",
    "pr_created",
}

PLAN_SAFETY_CHECKS = {
    "confirmed_file_mismatch",
    "confirmed_line_mismatch",
    "candidate_not_inspected",
    "file_limit_exceeded",
    "inspected_files_mismatch",
    "github_changes_reported",
    "repairable_change_missing",
    "manual_review_change_present",
    "manual_review_reason_missing",
    "uninspected_change_target",
    "invalid_change_line_range",
    "proposal_excerpt_limit",
    "before_excerpt_missing",
    "after_excerpt_missing",
    "before_excerpt_mismatch",
}
PLAN_DIAGNOSTIC_FIELDS = {
    "confirmed_failed_file",
    "confirmed_failed_line",
    "inspected_files",
    "github_changes_made",
    "proposed_changes",
    "manual_review_reason",
    "file_path",
    "start_line",
    "end_line",
    "before_excerpt",
    "after_excerpt",
}
PLAN_BOOLEAN_FLAGS = {
    "root_cause_confirmed",
    "repairable",
    "github_changes_made",
    "has_proposed_changes",
    "before_excerpt_present",
    "after_excerpt_present",
}


def _safe_plan_failure_diagnostics(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    raw = body.get("diagnostics")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    if raw.get("failed_stage") == "plan_safety_validation":
        result["failed_stage"] = "plan_safety_validation"
    check = raw.get("failed_check_name")
    if check in PLAN_SAFETY_CHECKS:
        result["failed_check_name"] = check
    if raw.get("error_type") == "safety_validation_error":
        result["error_type"] = "safety_validation_error"

    path = raw.get("validation_field_path")
    if isinstance(path, list):
        safe_path = []
        for part in path:
            if isinstance(part, int) and 0 <= part <= 100:
                safe_path.append(part)
            elif isinstance(part, str) and part in PLAN_DIAGNOSTIC_FIELDS:
                safe_path.append(part)
        result["validation_field_path"] = safe_path

    proposed_path = raw.get("proposed_file_path")
    if (
        isinstance(proposed_path, str)
        and 0 < len(proposed_path) <= 500
        and ".." not in proposed_path
        and all(
            char.isalnum() or char in "._-/"
            for char in proposed_path
        )
    ):
        result["proposed_file_path"] = proposed_path
    for field in ("start_line", "end_line"):
        value = raw.get(field)
        if isinstance(value, int) and 1 <= value <= 10_000_000:
            result[field] = value
    for field in (
        "before_excerpt_sha256",
        "after_excerpt_sha256",
    ):
        value = raw.get(field)
        if (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        ):
            result[field] = value

    flags = raw.get("boolean_flags")
    if isinstance(flags, dict):
        result["boolean_flags"] = {
            key: value
            for key, value in flags.items()
            if key in PLAN_BOOLEAN_FLAGS and isinstance(value, bool)
        }
    return result


def _safe_correlation_id(response: httpx.Response) -> str:
    raw = response.headers.get("X-Correlation-ID", "")
    safe = "".join(
        character
        for character in raw
        if character.isalnum() or character == "-"
    )[:64]
    return safe or "unavailable"


def _safe_validation_diagnostics(
    response: httpx.Response,
) -> list[dict[str, Any]]:
    try:
        body = response.json()
    except ValueError:
        return []

    known_fields = set(RepairPlanRequest.model_fields)
    diagnostics = []
    for item in body.get("validation_errors", []):
        if not isinstance(item, dict):
            continue
        location = []
        for part in item.get("location", []):
            if isinstance(part, int):
                location.append(part)
            elif isinstance(part, str):
                location.append(
                    part
                    if part in known_fields
                    else "unknown_field"
                )
        error_type = item.get("type")
        if not isinstance(error_type, str):
            continue
        safe_type = "".join(
            char
            for char in error_type
            if char.isalnum() or char in {"_", "."}
        )[:100]
        diagnostics.append(
            {
                "field": ".".join(str(part) for part in location),
                "location": location,
                "type": safe_type or "validation_error",
            }
        )
    return diagnostics


def _safe_response_diagnostics(
    body: object,
    error: ValidationError | None,
    response_fields: set[str] | None = None,
    nested_fields: set[str] | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    response_fields = response_fields or set(
        ReadOnlyRepairPlan.model_fields
    )
    nested_fields = nested_fields or set(ProposedChange.model_fields)
    known_fields = response_fields | nested_fields

    if isinstance(body, dict):
        field_names = sorted(
            {
                key if key in response_fields else "unknown_field"
                for key in body
                if isinstance(key, str)
            }
        )
    else:
        field_names = []

    missing_fields: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    if error is not None:
        for item in error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        ):
            location = []
            for part in item.get("loc", ()):
                if isinstance(part, int):
                    location.append(part)
                elif isinstance(part, str):
                    location.append(
                        part
                        if part in known_fields
                        else "unknown_field"
                    )
            error_type = "".join(
                character
                for character in str(
                    item.get("type", "validation_error")
                )
                if character.isalnum()
                or character in {"_", "."}
            )[:100] or "validation_error"
            diagnostics.append(
                {
                    "location": location,
                    "type": error_type,
                }
            )
            if error_type == "missing" and location:
                field = location[-1]
                if isinstance(field, str) and field != "unknown_field":
                    missing_fields.append(field)

    return (
        field_names,
        sorted(set(missing_fields)),
        diagnostics,
    )


def _log_invalid_success_response(
    *,
    body: object,
    error: ValidationError | None,
    correlation_id: str,
    response_fields: set[str] | None = None,
    nested_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    fields, missing, diagnostics = _safe_response_diagnostics(
        body,
        error,
        response_fields,
        nested_fields,
    )
    logger.warning(
        "correlation_id=%s stage=response_validation_failed "
        "response_fields=%s missing_fields=%s validation_errors=%s",
        correlation_id,
        fields,
        missing,
        diagnostics,
    )
    return diagnostics


class RepairAgentClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        shared_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "REPAIR_AGENT_URL",
                "http://127.0.0.1:8010",
            )
        ).rstrip("/")
        self.shared_token = (
            shared_token
            if shared_token is not None
            else os.getenv("REPAIR_AGENT_SHARED_TOKEN")
        )
        self.transport = transport
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(
                os.getenv(
                    "REPAIR_AGENT_TIMEOUT_SECONDS",
                    "270",
                )
            )
        )

    async def create_plan(
        self,
        request: RepairPlanRequest,
    ) -> ReadOnlyRepairPlan:
        if not self.shared_token:
            raise RepairAgentError(
                "Repair-agent authentication is not configured."
            )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/plan",
                    headers={
                        "X-Repair-Agent-Token":
                            self.shared_token,
                    },
                    json=request.model_dump(),
                )
        except httpx.TimeoutException as error:
            raise RepairAgentError(
                "The read-only repair planner timed out."
            ) from error
        except httpx.RequestError as error:
            raise RepairAgentError(
                "The read-only repair planner is unavailable."
            ) from error

        if response.status_code == 422:
            raise RepairAgentValidationError(
                _safe_validation_diagnostics(response),
                _safe_correlation_id(response),
            )
        if response.status_code >= 400:
            try:
                error_body = response.json()
                code = error_body.get("error_code")
            except ValueError:
                error_body = None
                code = None
            safe_code = (
                code
                if code in ALLOWED_ERROR_CODES
                else "planner_internal_error"
            )
            raise RepairAgentDownstreamError(
                safe_code,
                _safe_correlation_id(response),
                _safe_plan_failure_diagnostics(error_body),
            )

        correlation_id = _safe_correlation_id(response)
        try:
            body = response.json()
        except ValueError as error:
            diagnostics = _log_invalid_success_response(
                body=None,
                error=None,
                correlation_id=correlation_id,
            )
            raise RepairAgentResponseError(
                diagnostics,
                correlation_id,
            ) from error

        try:
            return ReadOnlyRepairPlan.model_validate(body)
        except ValidationError as error:
            diagnostics = _log_invalid_success_response(
                body=body,
                error=error,
                correlation_id=correlation_id,
            )
            raise RepairAgentResponseError(
                diagnostics,
                correlation_id,
            ) from error

    async def publish_plan(
        self,
        request: RepairPublishRequest,
    ) -> RepairPublishResult:
        if not self.shared_token:
            raise RepairAgentError(
                "Repair-agent authentication is not configured."
            )
        timeout = float(
            os.getenv("REPAIR_PUBLISH_TIMEOUT_SECONDS", "180")
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/publish",
                    headers={
                        "X-Repair-Agent-Token": self.shared_token,
                    },
                    json=request.model_dump(mode="json"),
                )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise RepairPublishError("publish_mcp_failed") from error

        correlation_id = _safe_correlation_id(response)
        try:
            body = response.json()
        except ValueError as error:
            raise RepairPublishError(
                "publish_response_invalid",
                correlation_id,
            ) from error

        if response.status_code >= 400:
            raw_code = body.get("error_code") if isinstance(body, dict) else None
            code = (
                raw_code
                if raw_code in ALLOWED_ERROR_CODES
                else "publish_mcp_failed"
            )
            state = {
                key: body[key]
                for key in PUBLISH_STATE_FIELDS
                if isinstance(body, dict) and key in body
            }
            raise RepairPublishError(code, correlation_id, state)

        try:
            return RepairPublishResult.model_validate(body)
        except ValidationError as error:
            diagnostics = _log_invalid_success_response(
                body=body,
                error=error,
                correlation_id=correlation_id,
                response_fields=set(RepairPublishResult.model_fields),
                nested_fields=set(),
            )
            raise RepairPublishError(
                "publish_response_invalid",
                correlation_id,
                {"validation_errors": diagnostics},
            ) from error

repair_agent_client = RepairAgentClient()
