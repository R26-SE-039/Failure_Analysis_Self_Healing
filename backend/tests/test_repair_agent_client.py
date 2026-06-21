import unittest
from unittest.mock import patch

import httpx

from app.schemas.repair import RepairPlanRequest
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
