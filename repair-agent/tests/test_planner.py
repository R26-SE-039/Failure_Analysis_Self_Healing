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


def settings() -> Settings:
    return Settings(
        openrouter_api_key="test-provider-key",
        openrouter_model="provider/tool-model",
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
    async def list_tools(self):
        return {"get_file_contents"}

    async def call_tool(self, name, arguments):
        return (
            "def create_user(name):\n"
            "    return User(name=name\n"
        )


class FakeProvider:
    model_name = "mock/tool-model"

    def __init__(self, after_excerpt: str = "    return User(name=name)"):
        self.after_excerpt = after_excerpt

    async def create_plan(self, repair_request, reader):
        await reader.read_file(repair_request.candidate_file)
        return ProviderRepairPlan(
            status="planned",
            confirmed_failed_file=(
                repair_request.candidate_file
            ),
            confirmed_failed_line=(
                repair_request.candidate_line
            ),
            proposed_changes=[
                ProviderProposedChange(
                    file_path="app/user_service.py",
                    start_line=2,
                    end_line=2,
                    before_excerpt=(
                        "    return User(name=name"
                    ),
                    after_excerpt=self.after_excerpt,
                    reason="Close the constructor call.",
                )
            ],
            risks=["Constructor behavior should be reviewed."],
            suggested_validation_commands=["pytest -q"],
        )


class RepairPlannerTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_returns_bounded_read_only_plan(self):
        planner = RepairPlanner(
            settings=settings(),
            provider=FakeProvider(),
            mcp_client_factory=FakeMcpClient,
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


if __name__ == "__main__":
    unittest.main()
