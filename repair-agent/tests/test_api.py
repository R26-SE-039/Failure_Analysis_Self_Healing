import unittest
from unittest.mock import patch

import httpx

from repair_agent.api import create_app
from repair_agent.config import Settings
from repair_agent.planner import PlanValidationError
from repair_agent.publisher import RepairPublishFailure
from repair_agent.schemas import (
    ReadOnlyRepairPlan,
    RepairPublishResult,
)

from tests.test_planner import request, settings
from tests.test_publisher import request as publish_request


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


class SafetyFailingPlanner:
    async def create_plan(self, payload):
        raise PlanValidationError(
            "before_excerpt_mismatch",
            field_path=["proposed_changes", 0, "before_excerpt"],
            proposed_file_path=payload.candidate_file,
            start_line=payload.candidate_line,
            end_line=payload.candidate_line,
            flags={
                "repairable": True,
                "github_changes_made": False,
            },
            before_excerpt_hash="a" * 64,
            after_excerpt_hash="b" * 64,
        )


class FakePublisher:
    async def publish(self, payload):
        return RepairPublishResult(
            attempt_id=payload.attempt_id,
            publish_status="draft_pr_created",
            validation_status="pending",
            repair_branch="auto-heal/repair-4cd693-syntaxerror",
            commit_sha="b" * 40,
            draft_pr_number=17,
            draft_pr_url="https://github.com/example/project/pull/17",
            changed_files=["app/user_service.py"],
            github_changes_made=True,
            automatic_merge_performed=False,
            message="Draft PR created — awaiting developer review",
            merge_message="No automatic merge performed",
        )


class BranchMismatchPublisher:
    async def publish(self, _payload):
        raise RepairPublishFailure(
            "branch_head_mismatch",
            safe_message=(
                "Cannot auto-publish because the failed branch has moved "
                "since the failed workflow run. Please rerun diagnosis on "
                "the latest failing commit or review manually."
            ),
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

    async def test_safety_failure_returns_sanitized_manual_review(self):
        app = create_app(
            settings=settings(),
            planner=SafetyFailingPlanner(),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://repair-agent.test",
        ) as client:
            response = await client.post(
                "/plan",
                headers={
                    "X-Repair-Agent-Token": "test-shared-token",
                },
                json=request().model_dump(),
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error_code"], "plan_validation_failed")
        self.assertEqual(
            body["diagnostics"]["failed_check_name"],
            "before_excerpt_mismatch",
        )
        self.assertEqual(
            body["diagnostics"]["proposed_file_path"],
            "app/user_service.py",
        )
        self.assertNotIn("source code", response.text.lower())

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

    async def test_publish_returns_draft_only_result(self):
        app = create_app(
            settings=settings(),
            planner=FakePlanner(),
            publisher=FakePublisher(),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://repair-agent.test",
        ) as client:
            response = await client.post(
                "/publish",
                headers={"X-Repair-Agent-Token": "test-shared-token"},
                json=publish_request().model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["github_changes_made"])
        self.assertFalse(response.json()["automatic_merge_performed"])

    async def test_publish_branch_mismatch_is_safe(self):
        app = create_app(
            settings=settings(),
            planner=FakePlanner(),
            publisher=BranchMismatchPublisher(),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://repair-agent.test",
        ) as client:
            response = await client.post(
                "/publish",
                headers={"X-Repair-Agent-Token": "test-shared-token"},
                json=publish_request().model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "branch_head_mismatch")

    async def test_publish_rejects_missing_write_token(self):
        app = create_app(
            settings=settings(),
            planner=FakePlanner(),
        )
        with patch.dict("os.environ", {}, clear=True):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://repair-agent.test",
            ) as client:
                response = await client.post(
                    "/publish",
                    headers={"X-Repair-Agent-Token": "test-shared-token"},
                    json=publish_request().model_dump(mode="json"),
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "write_token_missing")


if __name__ == "__main__":
    unittest.main()
