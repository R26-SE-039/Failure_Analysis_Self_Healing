import unittest

from repair_agent.config import Settings
from repair_agent.planner import (
    PlanValidationError,
    RepairPlanner,
)
from repair_agent.schemas import (
    ProviderProposedChange,
    ProviderRepairPlan,
    RepairPlanRequest,
)
from repair_agent.security import SecurityError


def settings() -> Settings:
    return Settings(
        openrouter_api_key="test-provider-key",
        openrouter_model="provider/tool-model",
        openrouter_provider=None,
        openrouter_base_url="https://openrouter.ai/api/v1",
        github_mcp_url="https://api.githubcopilot.com/mcp/",
        github_mcp_token="test-github-token",
        allowed_repositories=frozenset(
            {"example/project"}
        ),
        shared_token="test-shared-token",
        max_tool_calls=5,
        max_files=3,
        max_bytes=5000,
        max_excerpt_lines=4,
        max_excerpt_chars=500,
        timeout_seconds=30,
        openrouter_request_timeout_seconds=180,
        planning_timeout_seconds=240,
    )


def request() -> RepairPlanRequest:
    return RepairPlanRequest(
        attempt_id="REPAIR-123",
        repository_owner="example",
        repository_name="project",
        run_id=123,
        head_sha="a" * 40,
        head_branch="main",
        default_branch="main",
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


class FakeMcpClient:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return {"get_file_contents"}

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return (
            "line 1\nline 2\nline 3\nline 4\nline 5\n"
            "line 6\nline 7\nline 8\nline 9\n"
            "    return User(name=name\n"
            "line 11\nline 12\n"
        )


class FakeProvider:
    model_name = "mock/tool-model"

    def __init__(
        self,
        after_excerpt: str = "    return User(name=name)",
        before_excerpt: str = "    return User(name=name",
    ):
        self.after_excerpt = after_excerpt
        self.before_excerpt = before_excerpt
        self.calls = 0
        self.last_evidence = None

    async def create_plan(self, repair_request, evidence):
        self.calls += 1
        self.last_evidence = evidence
        return ProviderRepairPlan(
            root_cause_confirmed=True,
            repairable=True,
            confirmed_failed_file=(
                evidence.candidate.file_path
            ),
            confirmed_failed_line=(
                repair_request.candidate_line
            ),
            inspected_files=[evidence.candidate.file_path],
            proposed_changes=[
                ProviderProposedChange(
                    file_path="app/user_service.py",
                    start_line=10,
                    end_line=10,
                    before_excerpt=self.before_excerpt,
                    after_excerpt=self.after_excerpt,
                    reason="Close the constructor call.",
                )
            ],
            risks=["Constructor behavior should be reviewed."],
            suggested_validation_commands=["pytest -q"],
            manual_review_reason=None,
            github_changes_made=False,
        )


class RepairPlannerTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_returns_bounded_read_only_plan(self):
        mcp = FakeMcpClient()
        provider = FakeProvider()
        planner = RepairPlanner(
            settings=settings(),
            provider=provider,
            mcp_client_factory=lambda: mcp,
        )

        result = await planner.create_plan(request())

        self.assertEqual(result.status, "planned")
        self.assertEqual(
            result.inspected_files,
            ["app/user_service.py"],
        )
        self.assertFalse(result.github_changes_made)
        self.assertEqual(
            result.suggested_validation_commands,
            ["pytest -q"],
        )
        self.assertTrue(result.root_cause_confirmed)
        self.assertTrue(result.repairable)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            mcp.calls,
            [
                (
                    "get_file_contents",
                    {
                        "owner": "example",
                        "repo": "project",
                        "path": "app/user_service.py",
                        "ref": "a" * 40,
                    },
                )
            ],
        )
        self.assertEqual(
            provider.last_evidence.candidate.start_line,
            8,
        )

    async def test_rejects_oversized_excerpt(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(
                "one\ntwo\nthree\nfour\nfive"
            ),
            mcp_client_factory=FakeMcpClient,
        )

        with self.assertRaises(PlanValidationError):
            await planner.create_plan(request())

    async def test_rejects_before_excerpt_not_in_exact_sha_content(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(before_excerpt="different source line"),
            mcp_client_factory=FakeMcpClient,
        )

        with self.assertRaises(PlanValidationError) as raised:
            await planner.create_plan(request())

        diagnostics = raised.exception.safe_diagnostics()
        self.assertEqual(
            diagnostics["failed_check_name"],
            "before_excerpt_mismatch",
        )
        self.assertEqual(
            diagnostics["validation_field_path"],
            ["proposed_changes", 0, "before_excerpt"],
        )
        self.assertEqual(
            diagnostics["proposed_file_path"],
            "app/user_service.py",
        )
        self.assertNotIn("different source line", str(diagnostics))

    async def test_rejects_empty_after_excerpt_safely(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(after_excerpt=""),
            mcp_client_factory=FakeMcpClient,
        )

        with self.assertRaises(PlanValidationError) as raised:
            await planner.create_plan(request())

        diagnostics = raised.exception.safe_diagnostics()
        self.assertEqual(
            diagnostics["failed_check_name"],
            "after_excerpt_missing",
        )
        self.assertFalse(
            diagnostics["boolean_flags"]["after_excerpt_present"]
        )

    async def test_rejects_confidence_below_sixty_percent_gate(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(),
            mcp_client_factory=FakeMcpClient,
        )

        with self.assertRaises(SecurityError) as raised:
            await planner.create_plan(
                request().model_copy(update={"confidence": 0.5999})
            )

        self.assertEqual(str(raised.exception), "Confidence gate did not pass.")

    async def test_accepts_confidence_at_sixty_percent_gate(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(),
            mcp_client_factory=FakeMcpClient,
        )

        result = await planner.create_plan(
            request().model_copy(update={"confidence": 0.6000})
        )

        self.assertEqual(result.status, "planned")
        self.assertFalse(result.github_changes_made)

if __name__ == "__main__":
    unittest.main()
