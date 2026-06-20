from __future__ import annotations

import asyncio
import hmac

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from repair_agent.config import (
    ConfigurationError,
    Settings,
)
from repair_agent.mcp.github_remote import (
    RemoteGitHubMcpClient,
)
from repair_agent.openrouter_client import (
    OpenRouterPlanProvider,
)
from repair_agent.planner import RepairPlanner
from repair_agent.schemas import RepairPlanRequest


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
        supplied_token = request.headers.get(
            "X-Repair-Agent-Token",
            "",
        )
        if not hmac.compare_digest(
            supplied_token,
            active_settings.shared_token,
        ):
            return JSONResponse(
                {"detail": "Unauthorized."},
                status_code=401,
            )

        try:
            payload = RepairPlanRequest.model_validate(
                await request.json()
            )
            result = await asyncio.wait_for(
                active_planner.create_plan(payload),
                timeout=active_settings.timeout_seconds,
            )
        except Exception:
            return JSONResponse(
                {
                    "detail": (
                        "Read-only repair planning failed."
                    )
                },
                status_code=422,
            )

        return JSONResponse(result.model_dump())

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/plan", plan, methods=["POST"]),
        ]
    )
