import unittest

from repair_agent.config import PublishSettings
from repair_agent.publisher import (
    BRANCH_HEAD_MISMATCH_MESSAGE,
    RepairPublishFailure,
    RepairPublisher,
    apply_approved_changes,
    safe_branch_name,
)
from repair_agent.schemas import (
    ProviderProposedChange,
    RepairPublishRequest,
)
from tests.test_publish_broker import (
    BASE_SHA,
    FakePublishMcpClient,
)


def settings() -> PublishSettings:
    return PublishSettings(
        github_mcp_url="https://api.githubcopilot.com/mcp/",
        github_write_mcp_token="private-write-token",
        allowed_repositories=frozenset({"example/project"}),
        max_tool_calls=10,
        max_files=2,
        max_bytes=5000,
        timeout_seconds=30,
    )


def request() -> RepairPublishRequest:
    return RepairPublishRequest(
        attempt_id="REPAIR-4CD693ABC",
        repository_owner="example",
        repository_name="project",
        run_id=123,
        run_url="https://github.com/example/project/actions/runs/123",
        base_sha=BASE_SHA,
        failed_branch="main",
        default_branch="main",
        root_cause="application_defect",
        confidence=0.81,
        decision_source="machine_learning",
        selected_action="start_mcp_code_repair",
        error_type="SyntaxError",
        confirmed_failed_file="app/user_service.py",
        confirmed_failed_line=2,
        inspected_files=["app/user_service.py"],
        proposed_changes=[
            ProviderProposedChange(
                file_path="app/user_service.py",
                start_line=2,
                end_line=2,
                before_excerpt="return User(name=name",
                after_excerpt="return User(name=name)",
                reason="Close the constructor call.",
            )
        ],
        risks=["Review constructor behavior."],
        suggested_validation_commands=["pytest -q"],
        phase1_correlation_id="phase1-correlation",
    )


class RepairPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_publishes_stored_plan_without_merge(self):
        client = FakePublishMcpClient()
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        result = await publisher.publish(request())

        self.assertEqual(result.publish_status, "draft_pr_created")
        self.assertTrue(result.repair_branch.startswith("auto-heal/"))
        self.assertFalse(result.automatic_merge_performed)
        names = [name for name, _ in client.calls]
        self.assertEqual(names.count("push_files"), 1)
        self.assertNotIn("merge_pull_request", names)
        serialized_calls = str(client.calls)
        self.assertNotIn(settings().github_write_mcp_token, serialized_calls)
        push = next(args for name, args in client.calls if name == "push_files")
        self.assertIn(
            "fix: auto-heal application defect in app/user_service.py",
            push["message"],
        )
        self.assertIn("Repair attempt: REPAIR-4CD693ABC", push["message"])
        self.assertIn("Developer review is required", push["message"])
        pull_request = next(
            args for name, args in client.calls if name == "create_pull_request"
        )
        self.assertEqual(
            pull_request["title"],
            "[Auto-Heal] Fix application defect in app/user_service.py",
        )
        self.assertIn(
            "must be reviewed by a developer before merge",
            pull_request["body"],
        )

    async def test_existing_draft_pr_is_recovered_without_writes(self):
        client = FakePublishMcpClient(existing_pr=True)
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        result = await publisher.publish(
            request().model_copy(update={"recovery_only": True})
        )

        self.assertEqual(result.draft_pr_number, 17)
        self.assertEqual(result.commit_sha, "b" * 40)
        names = [name for name, _ in client.calls]
        for forbidden in {
            "create_branch",
            "push_files",
            "create_pull_request",
            "merge_pull_request",
        }:
            self.assertNotIn(forbidden, names)

    async def test_recovery_without_pr_requires_manual_review(self):
        client = FakePublishMcpClient(existing_pr=False)
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        with self.assertRaises(RepairPublishFailure) as raised:
            await publisher.publish(
                request().model_copy(update={"recovery_only": True})
            )

        self.assertEqual(
            raised.exception.code,
            "publish_partial_manual_review_required",
        )
        self.assertTrue(raised.exception.state["branch_created"])
        self.assertTrue(raised.exception.state["commit_created"])
        self.assertFalse(raised.exception.state["pr_created"])
        names = [name for name, _ in client.calls]
        self.assertNotIn("create_pull_request", names)
        self.assertNotIn("create_branch", names)
        self.assertNotIn("push_files", names)

    async def test_branch_mismatch_has_no_github_writes(self):
        client = FakePublishMcpClient("c" * 40)
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        with self.assertRaises(RepairPublishFailure) as raised:
            await publisher.publish(request())

        self.assertEqual(raised.exception.code, "branch_head_mismatch")
        self.assertEqual(raised.exception.safe_message, BRANCH_HEAD_MISMATCH_MESSAGE)
        self.assertEqual(
            [name for name, _ in client.calls],
            ["list_pull_requests", "get_commit"],
        )
        self.assertNotIn(
            "create_branch",
            [name for name, _ in client.calls],
        )

    async def test_before_excerpt_mismatch_stops_before_branch(self):
        client = FakePublishMcpClient()
        client_content = "line 1\nchanged line\nline 3\n"

        async def call_tool(name, arguments):
            if name == "get_file_contents":
                client.calls.append((name, arguments))
                return client_content
            return await FakePublishMcpClient.call_tool(client, name, arguments)

        client.call_tool = call_tool
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        with self.assertRaises(RepairPublishFailure) as raised:
            await publisher.publish(request())

        self.assertEqual(raised.exception.code, "before_excerpt_mismatch")
        self.assertNotIn("create_branch", [name for name, _ in client.calls])

    def test_branch_name_is_safe_and_bounded(self):
        branch = safe_branch_name(
            "REPAIR-4CD693ABC",
            "SyntaxError: unsafe / description",
        )
        self.assertRegex(branch, r"^auto-heal/[a-z0-9-]+$")
        self.assertLessEqual(len(branch), 100)

    def test_applies_only_approved_line_range(self):
        content = "line 1\nreturn User(name=name\nline 3\n"
        updated = apply_approved_changes(
            content,
            request().proposed_changes,
        )
        self.assertEqual(
            updated,
            "line 1\nreturn User(name=name)\nline 3\n",
        )

    async def test_rejects_confidence_below_sixty_percent_before_github_write(self):
        client = FakePublishMcpClient()
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        with self.assertRaises(RepairPublishFailure) as raised:
            await publisher.publish(
                request().model_copy(update={"confidence": 0.5999})
            )

        self.assertEqual(raised.exception.code, "publish_safety_failed")
        self.assertEqual(client.calls, [])

    async def test_accepts_confidence_at_sixty_percent_gate(self):
        client = FakePublishMcpClient()
        publisher = RepairPublisher(
            settings=settings(),
            mcp_client_factory=lambda: client,
        )

        result = await publisher.publish(
            request().model_copy(update={"confidence": 0.6000})
        )

        self.assertEqual(result.publish_status, "draft_pr_created")
        self.assertFalse(result.automatic_merge_performed)
        self.assertEqual(
            [name for name, _ in client.calls].count("push_files"),
            1,
        )

if __name__ == "__main__":
    unittest.main()
