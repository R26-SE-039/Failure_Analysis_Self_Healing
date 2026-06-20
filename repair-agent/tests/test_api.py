import unittest

import httpx

from repair_agent.api import create_app
from repair_agent.config import Settings
from repair_agent.schemas import ReadOnlyRepairPlan

from test_planner import request, settings


class FakePlanner:
    async def create_plan(self, payload):
        return ReadOnlyRepairPlan(
            attempt_id=payload.attempt_id,
            status="planned",
            model="mock/tool-model",
            confirmed_failed_file=payload.candidate_file,
            confirmed_failed_line=payload.candidate_line,
            base_sha=payload.head_sha,
            inspected_files=[payload.candidate_file],
            proposed_changes=[],
            risks=[],
            suggested_validation_commands=["pytest -q"],
            github_changes_made=False,
        )


class RepairAgentApiTests(
    unittest.IsolatedAsyncioTestCase
):
    async def asyncSetUp(self):
        app = create_app(
            settings=settings(),
            planner=FakePlanner(),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://repair-agent.test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_requires_internal_authentication(self):
        response = await self.client.post(
            "/plan",
            json=request().model_dump(),
        )
        self.assertEqual(response.status_code, 401)

    async def test_returns_no_github_changes(self):
        response = await self.client.post(
            "/plan",
            headers={
                "X-Repair-Agent-Token": "test-shared-token",
            },
            json=request().model_dump(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.json()["github_changes_made"]
        )


if __name__ == "__main__":
    unittest.main()
