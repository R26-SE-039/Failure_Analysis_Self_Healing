from __future__ import annotations

import os
from typing import Any

import httpx

from app.schemas.repair import (
    ReadOnlyRepairPlan,
    RepairPlanRequest,
)


class RepairAgentError(RuntimeError):
    pass


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
                os.getenv("REPAIR_TIMEOUT_SECONDS", "90")
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

        if response.status_code >= 400:
            raise RepairAgentError(
                "The read-only repair planner rejected the request."
            )

        try:
            return ReadOnlyRepairPlan.model_validate(
                response.json()
            )
        except (ValueError, TypeError) as error:
            raise RepairAgentError(
                "The repair planner returned an invalid response."
            ) from error


repair_agent_client = RepairAgentClient()
