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
    ) -> None:
        super().__init__(
            "The repair agent could not complete planning."
        )
        self.code = code
        self.correlation_id = correlation_id


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
}


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
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    response_fields = set(ReadOnlyRepairPlan.model_fields)
    nested_fields = set(ProposedChange.model_fields)
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
) -> list[dict[str, Any]]:
    fields, missing, diagnostics = _safe_response_diagnostics(
        body,
        error,
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
                code = response.json().get("error_code")
            except ValueError:
                code = None
            safe_code = (
                code
                if code in ALLOWED_ERROR_CODES
                else "planner_internal_error"
            )
            raise RepairAgentDownstreamError(
                safe_code,
                _safe_correlation_id(response),
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


repair_agent_client = RepairAgentClient()
