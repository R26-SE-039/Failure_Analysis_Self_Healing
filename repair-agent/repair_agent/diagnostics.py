from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from uuid import uuid4


logger = logging.getLogger("repair_agent.planning")

_correlation_id: ContextVar[str] = ContextVar(
    "repair_plan_correlation_id",
    default="unassigned",
)

ALLOWED_STAGES = {
    "plan_request_received",
    "mcp_candidate_read_started",
    "mcp_candidate_read_completed",
    "mcp_envelope_decoded",
    "bounded_evidence_created",
    "openrouter_request_started",
    "openrouter_http_response_received",
    "structured_output_received",
    "structured_output_validation_started",
    "structured_output_validated",
    "plan_completed",
    "plan_failed",
}


def begin_correlation() -> tuple[str, Token[str]]:
    correlation_id = uuid4().hex
    return correlation_id, _correlation_id.set(correlation_id)


def set_correlation(correlation_id: str) -> Token[str]:
    safe = "".join(
        character
        for character in correlation_id
        if character.isalnum() or character == "-"
    )[:64]
    return _correlation_id.set(safe or uuid4().hex)


def reset_correlation(token: Token[str]) -> None:
    _correlation_id.reset(token)


def current_correlation_id() -> str:
    return _correlation_id.get()


def log_stage(
    stage: str,
    status: str,
    *,
    exception_class: str | None = None,
    error_code: str | None = None,
    upstream_http_status: int | None = None,
    retry_after: str | None = None,
    validation_errors: list[dict[str, object]] | None = None,
    safety_diagnostics: dict[str, object] | None = None,
) -> None:
    if stage not in ALLOWED_STAGES:
        stage = "plan_failed"
    safe_status = "".join(
        character
        for character in str(status)
        if character.isalnum() or character in {"_", "-"}
    )[:64]
    fields = [
        f"correlation_id={current_correlation_id()}",
        f"stage={stage}",
        f"status={safe_status or 'unknown'}",
    ]
    if exception_class:
        safe_exception = "".join(
            character
            for character in exception_class
            if character.isalnum() or character in {"_", "."}
        )[:100]
        fields.append(f"exception_class={safe_exception}")
    if error_code:
        safe_code = "".join(
            character
            for character in error_code
            if character.isalnum() or character == "_"
        )[:100]
        fields.append(f"error_code={safe_code}")
    if upstream_http_status is not None:
        fields.append(
            f"upstream_http_status={int(upstream_http_status)}"
        )
    if retry_after:
        safe_retry = "".join(
            character
            for character in retry_after
            if character.isalnum() or character in {"-", ":", ",", " "}
        )[:100]
        fields.append(f"retry_after={safe_retry}")
    if validation_errors:
        safe_validation = [
            {
                "location": item.get("location", []),
                "type": item.get("type", "validation_error"),
            }
            for item in validation_errors
        ]
        fields.append(f"validation_errors={safe_validation}")
    if safety_diagnostics:
        fields.append(f"safety_diagnostics={safety_diagnostics}")
    logger.info(" ".join(fields))
