import unittest
import json

from repair_agent.mcp.publish_broker import (
    GitHubPublishBroker,
    PUBLISH_TOOL_ALLOWLIST,
    PublishBrokerError,
    parse_pull_request_identity,
)
from repair_agent.security import SecurityError


BASE_SHA = "a" * 40
COMMIT_SHA = "b" * 40


class FakePublishMcpClient:
    def __init__(
        self,
        branch_sha: str = BASE_SHA,
        *,
        create_pr_response: str | None = None,
        existing_pr: bool = False,
        recover_after_create: bool = False,
    ):
        self.branch_sha = branch_sha
        self.create_pr_response = create_pr_response
        self.existing_pr = existing_pr
        self.recover_after_create = recover_after_create
        self.pr_create_called = False
        self.calls = []

    async def list_tools(self):
        return {
            "get_commit",
            "get_file_contents",
            "create_branch",
            "push_files",
            "create_pull_request",
            "pull_request_read",
            "list_pull_requests",
            "merge_pull_request",
            "delete_file",
        }

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_commit":
            sha = (
                COMMIT_SHA
                if arguments["sha"].startswith("auto-heal/")
                else self.branch_sha
            )
            return f'{{"sha":"{sha}"}}'
        if name == "get_file_contents":
            return "line 1\nreturn User(name=name\nline 3\n"
        if name == "create_branch":
            return f'{{"object":{{"sha":"{BASE_SHA}"}}}}'
        if name == "push_files":
            return f'{{"commit":{{"sha":"{COMMIT_SHA}"}}}}'
        if name == "create_pull_request":
            self.pr_create_called = True
            return self.create_pr_response or (
                '{"number":17,"html_url":'
                '"https://github.com/example/project/pull/17"}'
            )
        if name == "list_pull_requests":
            available = self.existing_pr or (
                self.recover_after_create and self.pr_create_called
            )
            if not available:
                return "[]"
            head = arguments["head"].split(":", 1)[-1]
            base = arguments["base"]
            return (
                '[{"number":17,"html_url":'
                '"https://github.com/example/project/pull/17",'
                '"state":"open","draft":true,'
                f'"head":{{"ref":"{head}"}},'
                f'"base":{{"ref":"{base}"}}}}]'
            )
        if name == "pull_request_read":
            if arguments["method"] == "get":
                return '{"draft":true}'
            return '{"state":"pending"}'
        raise AssertionError(name)


def broker(client, **overrides):
    values = {
        "client": client,
        "owner": "example",
        "repository": "project",
        "base_sha": BASE_SHA,
        "failed_branch": "main",
        "repair_branch": "auto-heal/repair-123-syntax-error",
        "approved_paths": {"app/user_service.py"},
        "allowed_repositories": frozenset({"example/project"}),
        "max_tool_calls": 10,
        "max_files": 2,
        "max_bytes": 5000,
    }
    values.update(overrides)
    return GitHubPublishBroker(**values)


class GitHubPublishBrokerTests(unittest.IsolatedAsyncioTestCase):
    def test_parses_top_level_nested_and_api_url_identities(self):
        cases = [
            {
                "number": 17,
                "html_url": "https://github.com/example/project/pull/17",
            },
            {
                "pull_request": {
                    "number": 17,
                    "html_url": "https://github.com/example/project/pull/17",
                }
            },
            {
                "content": {
                    "text": (
                        '{"pull_request":{"number":"17","url":'
                        '"https://api.github.com/repos/example/project/pulls/17"}}'
                    )
                }
            },
        ]
        for payload in cases:
            self.assertEqual(
                parse_pull_request_identity(
                    payload,
                    owner="example",
                    repository="project",
                ),
                (17, "https://github.com/example/project/pull/17"),
            )

    def test_allowlist_excludes_merge_delete_and_workflow_writes(self):
        for forbidden in {
            "merge_pull_request",
            "delete_file",
            "delete_branch",
            "actions_run_trigger",
            "update_pull_request",
        }:
            self.assertNotIn(forbidden, PUBLISH_TOOL_ALLOWLIST)

    async def test_branch_head_mismatch_stops_before_creation(self):
        client = FakePublishMcpClient("c" * 40)
        instance = broker(client)

        with self.assertRaises(PublishBrokerError) as raised:
            await instance.verify_failed_branch_head()

        self.assertEqual(raised.exception.code, "branch_head_mismatch")
        self.assertEqual([name for name, _ in client.calls], ["get_commit"])

    async def test_one_commit_and_draft_pr_only(self):
        client = FakePublishMcpClient()
        instance = broker(client)

        await instance.verify_failed_branch_head()
        await instance.read_approved_file("app/user_service.py")
        await instance.create_repair_branch()
        sha = await instance.push_approved_files(
            [
                {
                    "path": "app/user_service.py",
                    "content": "fixed",
                }
            ],
            "fix: test",
        )
        number, _url = await instance.create_draft_pull_request(
            title="Draft repair",
            body="Review required.",
        )
        status = await instance.verify_draft_pull_request(number)

        self.assertEqual(sha, COMMIT_SHA)
        self.assertEqual(status, "pending")
        names = [name for name, _ in client.calls]
        self.assertEqual(names.count("push_files"), 1)
        self.assertNotIn("merge_pull_request", names)
        pr_call = next(args for name, args in client.calls if name == "create_pull_request")
        self.assertTrue(pr_call["draft"])
        self.assertFalse(pr_call["show_ui"])
        self.assertEqual(pr_call["base"], "main")
        self.assertTrue(pr_call["head"].startswith("auto-heal/"))

    async def test_missing_create_identity_recovers_existing_draft(self):
        private_response_value = "private-source-code-must-not-be-logged"
        client = FakePublishMcpClient(
            create_pr_response=json.dumps(
                {
                    "result": {
                        "created": True,
                        "message": private_response_value,
                    }
                }
            ),
            recover_after_create=True,
        )
        instance = broker(client)
        await instance.verify_failed_branch_head()
        await instance.create_repair_branch()
        await instance.push_approved_files(
            [{"path": "app/user_service.py", "content": "fixed"}],
            "fix: test",
        )

        with self.assertLogs("repair_agent.publish", level="WARNING") as logs:
            number, url = await instance.create_draft_pull_request(
                title="Draft repair",
                body="Review required.",
            )

        self.assertEqual(number, 17)
        self.assertEqual(url, "https://github.com/example/project/pull/17")
        names = [name for name, _ in client.calls]
        self.assertEqual(names.count("create_pull_request"), 1)
        self.assertEqual(names.count("list_pull_requests"), 1)
        self.assertNotIn(private_response_value, "\n".join(logs.output))

    async def test_rejects_second_commit(self):
        client = FakePublishMcpClient()
        instance = broker(client)
        await instance.verify_failed_branch_head()
        await instance.create_repair_branch()
        files = [{"path": "app/user_service.py", "content": "fixed"}]
        await instance.push_approved_files(files, "fix: test")

        with self.assertRaises(PublishBrokerError) as raised:
            await instance.push_approved_files(files, "fix: test again")

        self.assertEqual(raised.exception.code, "single_commit_limit_reached")

    def test_rejects_direct_main_and_path_traversal(self):
        with self.assertRaises(SecurityError):
            broker(
                FakePublishMcpClient(),
                repair_branch="main",
            )
        with self.assertRaises(SecurityError):
            broker(
                FakePublishMcpClient(),
                approved_paths={"../secret.py"},
            )

    def test_rejects_more_than_max_files(self):
        with self.assertRaises(SecurityError):
            broker(
                FakePublishMcpClient(),
                approved_paths={"app/a.py", "app/b.py"},
                max_files=1,
            )


if __name__ == "__main__":
    unittest.main()
