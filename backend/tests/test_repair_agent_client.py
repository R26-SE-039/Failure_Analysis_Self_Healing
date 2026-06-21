import unittest
from unittest.mock import patch

import httpx

from app.schemas.repair import (
    RepairPlanRequest,
    RepairPublishRequest,
)
from app.services.repair_agent_client import (
    RepairAgentClient,
    RepairAgentDownstreamError,
    RepairAgentResponseError,
    RepairAgentValidationError,
)


def successful_plan() -> dict:
    return {
        "correlation_id": "safe-correlation-123",
        "attempt_id": "REPAIR-CONTRACT123",
        "status": "planned",
        "mode": "read_only",
        "model": "mock/tool-model",
        "root_cause_confirmed": True,
        "repairable": True,
        "confirmed_failed_file": "app/user_service.py",
        "confirmed_failed_line": 10,
        "base_sha": "a" * 40,
        "inspected_files": ["app/user_service.py"],
        "proposed_changes": [
            {
                "file_path": "app/user_service.py",
                "start_line": 10,
                "end_line": 10,
                "before_excerpt": "return User(name=name",
                "after_excerpt": "return User(name=name)",
                "reason": "Close the constructor call.",
            }
        ],
        "risks": ["Review constructor behavior."],
        "suggested_validation_commands": ["pytest -q"],
        "manual_review_reason": None,
        "github_changes_made": False,
    }


def publish_request() -> RepairPublishRequest:
    plan = successful_plan()
    return RepairPublishRequest(
        attempt_id=plan["attempt_id"],
        repository_owner="example",
        repository_name="project",
        run_id=123,
        run_url="https://github.com/example/project/actions/runs/123",
        base_sha="a" * 40,
        failed_branch="main",
        default_branch="main",
        root_cause="application_defect",
        confidence=0.81,
        decision_source="machine_learning",
        selected_action="start_mcp_code_repair",
        error_type="SyntaxError",
        confirmed_failed_file="app/user_service.py",
        confirmed_failed_line=10,
        inspected_files=plan["inspected_files"],
        proposed_changes=plan["proposed_changes"],
        risks=plan["risks"],
        suggested_validation_commands=plan[
            "suggested_validation_commands"
        ],
        phase1_correlation_id="safe-correlation-123",
    )


def request() -> RepairPlanRequest:
    return RepairPlanRequest(
        attempt_id="REPAIR-CONTRACT123",
        repository_owner="example",
        repository_name="project",
        run_id=123,
        head_sha="a" * 40,
        head_branch="feature/failure",
        default_branch=None,
        root_cause="application_defect",
        confidence=0.811086427989913,
        decision_source="machine_learning",
        selected_action="start_mcp_code_repair",
        error_type="SyntaxError",
        error_message="'(' was never closed",
        candidate_file="app/user_service.py",
        candidate_line=10,
        sanitized_log_excerpt="SyntaxError at line 10",
    )


class RepairAgentClientTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_accepts_successful_repair_agent_response(self):
        async def handler(_request):
            return httpx.Response(
                200,
                headers={
                    "X-Correlation-ID": "safe-correlation-123"
                },
                json=successful_plan(),
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )

        result = await client.create_plan(request())

        self.assertEqual(
            result.correlation_id,
            "safe-correlation-123",
        )
        self.assertFalse(result.github_changes_made)

    async def test_publish_sends_no_write_token_or_frontend_details(self):
        captured = []

        async def handler(http_request):
            captured.append(http_request)
            return httpx.Response(
                200,
                headers={"X-Correlation-ID": "publish-correlation-123"},
                json={
                    "correlation_id": "publish-correlation-123",
                    "attempt_id": "REPAIR-CONTRACT123",
                    "publish_status": "draft_pr_created",
                    "validation_status": "pending",
                    "repair_branch": "auto-heal/repair-123-syntaxerror",
                    "commit_sha": "b" * 40,
                    "draft_pr_number": 17,
                    "draft_pr_url": "https://github.com/example/project/pull/17",
                    "changed_files": ["app/user_service.py"],
                    "github_changes_made": True,
                    "automatic_merge_performed": False,
                    "message": "Draft PR created — awaiting developer review",
                    "merge_message": "No automatic merge performed",
                },
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )
        response = await client.publish_plan(publish_request())

        self.assertEqual(response.publish_status, "draft_pr_created")
        wire = captured[0].content.decode("utf-8")
        self.assertNotIn("GITHUB_WRITE_MCP_TOKEN", wire)
        self.assertNotIn("private-write-token", wire)

    async def test_malformed_success_response_is_sanitized(self):
        private_value = "private-source-and-secret-value"
        malformed = successful_plan()
        del malformed["base_sha"]
        malformed["private-source-field"] = private_value

        async def handler(_request):
            return httpx.Response(
                200,
                headers={
                    "X-Correlation-ID": "safe-correlation-123"
                },
                json=malformed,
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )

        with self.assertLogs(
            "app.services.repair_agent_client",
            level="WARNING",
        ) as logs:
            with self.assertRaises(RepairAgentResponseError) as raised:
                await client.create_plan(request())

        output = "\n".join(logs.output)
        self.assertIn("base_sha", output)
        self.assertIn("'type': 'missing'", output)
        self.assertIn("unknown_field", output)
        self.assertNotIn(private_value, output)
        self.assertNotIn("private-source-field", output)
        self.assertNotIn(private_value, str(raised.exception))

    async def test_422_retains_only_safe_diagnostics(self):
        private_value = "private-input-must-not-be-retained"

        async def handler(_request):
            return httpx.Response(
                422,
                json={
                    "detail": "Invalid repair-plan request.",
                    "validation_errors": [
                        {
                            "field": "head_sha",
                            "location": ["head_sha"],
                            "type": "string_pattern_mismatch",
                            "input": private_value,
                            "message": private_value,
                        }
                    ],
                },
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(
            RepairAgentValidationError
        ) as raised:
            await client.create_plan(request())

        self.assertEqual(
            raised.exception.diagnostics,
            [
                {
                    "field": "head_sha",
                    "location": ["head_sha"],
                    "type": "string_pattern_mismatch",
                }
            ],
        )
        self.assertNotIn(private_value, str(raised.exception))
        self.assertNotIn(
            private_value,
            str(raised.exception.diagnostics),
        )

    async def test_safe_downstream_error_code(self):
        async def handler(_request):
            return httpx.Response(
                502,
                headers={"X-Correlation-ID": "safe-correlation-123"},
                json={
                    "detail": "Read-only repair planning failed.",
                    "error_code": "structured_output_invalid",
                    "private": "must-not-be-retained",
                },
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(
            RepairAgentDownstreamError
        ) as raised:
            await client.create_plan(request())

        self.assertEqual(
            raised.exception.code,
            "structured_output_invalid",
        )
        self.assertEqual(
            raised.exception.correlation_id,
            "safe-correlation-123",
        )
        self.assertNotIn(
            "must-not-be-retained",
            str(raised.exception),
        )

    async def test_plan_safety_diagnostics_are_allowlisted(self):
        private_value = "private-source-content-must-not-survive"

        async def handler(_request):
            return httpx.Response(
                409,
                headers={"X-Correlation-ID": "safe-correlation-123"},
                json={
                    "error_code": "plan_validation_failed",
                    "diagnostics": {
                        "failed_stage": "plan_safety_validation",
                        "failed_check_name": "before_excerpt_mismatch",
                        "validation_field_path": [
                            "proposed_changes",
                            0,
                            "before_excerpt",
                        ],
                        "error_type": "safety_validation_error",
                        "proposed_file_path": "app/user_service.py",
                        "start_line": 10,
                        "end_line": 10,
                        "before_excerpt_sha256": "a" * 64,
                        "after_excerpt_sha256": "b" * 64,
                        "boolean_flags": {
                            "repairable": True,
                            "github_changes_made": False,
                        },
                        "raw_source": private_value,
                    },
                },
            )

        client = RepairAgentClient(
            base_url="http://repair-agent.test",
            shared_token="test-shared-token",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(RepairAgentDownstreamError) as raised:
            await client.create_plan(request())

        diagnostics = raised.exception.diagnostics
        self.assertEqual(
            diagnostics["failed_check_name"],
            "before_excerpt_mismatch",
        )
        self.assertEqual(
            diagnostics["proposed_file_path"],
            "app/user_service.py",
        )
        self.assertNotIn(private_value, str(diagnostics))
        self.assertNotIn("raw_source", diagnostics)

    def test_backend_timeout_exceeds_planning_timeout(self):
        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            client = RepairAgentClient(
                base_url="http://repair-agent.test",
                shared_token="test-shared-token",
            )

        self.assertEqual(client.timeout_seconds, 270)
        self.assertGreater(client.timeout_seconds, 240)


if __name__ == "__main__":
    unittest.main()
