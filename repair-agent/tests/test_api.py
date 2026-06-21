import unittest

import httpx

from repair_agent.api import create_app
from repair_agent.config import Settings
from repair_agent.schemas import ReadOnlyRepairPlan

from tests.test_planner import request, settings


class FakePlanner:
    async def create_plan(self, payload):
        return ReadOnlyRepairPlan(
            attempt_id=payload.attempt_id,
            status="planned",
            model="mock/tool-model",
            root_cause_confirmed=True,
            repairable=True,
            confirmed_failed_file=payload.candidate_file,
            confirmed_failed_line=payload.candidate_line,
            base_sha=payload.head_sha,
            inspected_files=[payload.candidate_file],
            proposed_changes=[],
            risks=[],
            suggested_validation_commands=["pytest -q"],
            github_changes_made=False,
        )


class FailingPlanner:
    async def create_plan(self, payload):
        raise RuntimeError("provider detail must stay private")


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
        self.assertEqual(
            response.headers["X-Correlation-ID"],
            response.json()["correlation_id"],
        )
        self.assertFalse(
            response.json()["github_changes_made"]
        )

    async def test_422_contains_only_safe_validation_metadata(self):
        invalid = request().model_dump()
        rejected_value = "not-a-valid-sha-private-value"
        invalid["head_sha"] = rejected_value

        response = await self.client.post(
            "/plan",
            headers={
                "X-Repair-Agent-Token": "test-shared-token",
            },
            json=invalid,
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(
            body["validation_errors"],
            [
                {
                    "field": "head_sha",
                    "location": ["head_sha"],
                    "type": "string_pattern_mismatch",
                }
            ],
        )
        self.assertNotIn(rejected_value, response.text)
        self.assertNotIn("input", response.text)

    async def test_planner_failure_is_not_reported_as_422(self):
        app = create_app(
            settings=settings(),
            planner=FailingPlanner(),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://repair-agent.test",
        ) as client:
            response = await client.post(
                "/plan",
                headers={
                    "X-Repair-Agent-Token":
                        "test-shared-token",
                },
                json=request().model_dump(),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["error_code"],
            "planner_internal_error",
        )
        self.assertNotIn("provider detail", response.text)

    async def test_unknown_field_name_is_not_echoed(self):
        invalid = request().model_dump()
        private_field = "private-value-as-field-name"
        private_value = "private-value-as-input"
        invalid[private_field] = private_value

        response = await self.client.post(
            "/plan",
            headers={
                "X-Repair-Agent-Token": "test-shared-token",
            },
            json=invalid,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["validation_errors"][0]["location"],
            ["unknown_field"],
        )
        self.assertNotIn(private_field, response.text)
        self.assertNotIn(private_value, response.text)


if __name__ == "__main__":
    unittest.main()
