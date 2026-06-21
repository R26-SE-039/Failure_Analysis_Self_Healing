from __future__ import annotations

import asyncio
import hmac
import json

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from repair_agent.config import (
    Settings,
)
from repair_agent.diagnostics import begin_correlation, log_stage
from repair_agent.mcp.github_remote import (
    RemoteGitHubMcpClient,
)
from repair_agent.openrouter_client import (
    OpenRouterPlanProvider,
    PlanProviderError,
)
from repair_agent.planner import (
    McpReadFailed,
    PlanValidationError,
    RepairPlanner,
)
from repair_agent.schemas import RepairPlanRequest


def _safe_validation_errors(
    error: ValidationError,
) -> list[dict[str, object]]:
    known_fields = set(RepairPlanRequest.model_fields)
    diagnostics = []
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
            char
            for char in str(
                item.get("type", "validation_error")
            )
            if char.isalnum() or char in {"_", "."}
        )[:100]
        diagnostics.append(
            {
                "field": ".".join(str(part) for part in location),
                "location": location,
                "type": error_type or "validation_error",
            }
        )
    return diagnostics


def _default_planner(settings: Settings) -> RepairPlanner:
    provider = OpenRouterPlanProvider(settings)
    return RepairPlanner(
        settings=settings,
        provider=provider,
        mcp_client_factory=lambda: RemoteGitHubMcpClient(
            url=settings.github_mcp_url,
            token=settings.github_mcp_token,
            timeout_seconds=settings.timeout_seconds,
        ),
    )


def create_app(
    *,
    settings: Settings | None = None,
    planner: RepairPlanner | None = None,
) -> Starlette:
    active_settings = settings or Settings.from_environment()
    active_planner = planner or _default_planner(
        active_settings
    )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ready",
                "mode": "read_only",
                "model": active_settings.openrouter_model,
                "github_changes_enabled": False,
            }
        )

    async def plan(request: Request) -> JSONResponse:
        correlation_id, _token = begin_correlation()
        log_stage("plan_request_received", "received")

        def response(
            payload: dict[str, object],
            status_code: int,
        ) -> JSONResponse:
            return JSONResponse(
                {
                    **payload,
                    "correlation_id": correlation_id,
                },
                status_code=status_code,
                headers={"X-Correlation-ID": correlation_id},
            )

        supplied_token = request.headers.get(
            "X-Repair-Agent-Token",
            "",
        )
        if not hmac.compare_digest(
            supplied_token,
            active_settings.shared_token,
        ):
            log_stage(
                "plan_failed",
                "failed",
                exception_class="AuthenticationError",
                error_code="planner_internal_error",
            )
            return response(
                {"detail": "Unauthorized."},
                401,
            )

        try:
            request_body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            log_stage(
                "plan_failed",
                "failed",
                exception_class="JSONDecodeError",
                error_code="plan_validation_failed",
            )
            return response(
                {"detail": "Invalid JSON request."},
                400,
            )

        try:
            payload = RepairPlanRequest.model_validate(request_body)
        except ValidationError as error:
            diagnostics = _safe_validation_errors(error)
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code="plan_validation_failed",
                validation_errors=diagnostics,
            )
            return response(
                {
                    "detail": "Invalid repair-plan request.",
                    "validation_errors": diagnostics,
                },
                422,
            )

        try:
            result = await asyncio.wait_for(
                active_planner.create_plan(payload),
                timeout=active_settings.planning_timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code="openrouter_timeout",
            )
            return response(
                {
                    "detail": "Read-only repair planning timed out.",
                    "error_code": "openrouter_timeout",
                },
                504,
            )
        except McpReadFailed as error:
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code=error.code,
            )
            return response(
                {
                    "detail": "Read-only repair planning failed.",
                    "error_code": error.code,
                },
                502,
            )
        except PlanProviderError as error:
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code=error.code,
                upstream_http_status=(
                    error.upstream_http_status
                ),
                retry_after=error.retry_after,
                validation_errors=error.validation_errors,
            )
            return response(
                {
                    "detail": "Read-only repair planning failed.",
                    "error_code": error.code,
                },
                502,
            )
        except PlanValidationError as error:
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code="plan_validation_failed",
                validation_errors=[
                    {
                        "location": [],
                        "type": error.reason_code,
                    }
                ],
            )
            return response(
                {
                    "detail": "Read-only repair planning failed.",
                    "error_code": "plan_validation_failed",
                },
                502,
            )
        except Exception as error:
            log_stage(
                "plan_failed",
                "failed",
                exception_class=type(error).__name__,
                error_code="planner_internal_error",
            )
            return response(
                {
                    "detail": (
                        "Read-only repair planning failed."
                    ),
                    "error_code": "planner_internal_error",
                },
                502,
            )

        log_stage("plan_completed", "completed")
        return response(result.model_dump(), 200)

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/plan", plan, methods=["POST"]),
        ]
    )
