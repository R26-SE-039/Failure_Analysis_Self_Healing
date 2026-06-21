import unittest

from repair_agent.mcp.read_broker import (
    GitHubReadBroker,
    ReadLimitError,
)
from repair_agent.security import SecurityError


class FakeMcpClient:
    def __init__(self, content: str = "def broken():\n    return 1\n"):
        self.content = content
        self.calls = []

    async def list_tools(self):
        return {"get_file_contents", "create_branch"}

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.content


class SearchMcpClient(FakeMcpClient):
    async def list_tools(self):
        return {
            "get_file_contents",
            "search_code",
            "create_branch",
        }

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "search_code":
            return (
                '{"items":[{"path":"src/user_service.py"}]}'
            )
        return self.content


class GitHubReadBrokerTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_forces_repository_and_exact_sha(self):
        client = FakeMcpClient()
        broker = GitHubReadBroker(
            client=client,
            owner="example",
            repository="project",
            head_sha="a" * 40,
            allowed_repositories=frozenset(
                {"example/project"}
            ),
            max_tool_calls=2,
            max_files=1,
            max_bytes=1000,
        )

        await broker.read_file("app/user_service.py")

        self.assertEqual(
            client.calls,
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
        self.assertNotIn(
            "create_branch",
            [call[0] for call in client.calls],
        )

    async def test_enforces_file_and_byte_limits(self):
        broker = GitHubReadBroker(
            client=FakeMcpClient("x" * 20),
            owner="example",
            repository="project",
            head_sha="a" * 40,
            allowed_repositories=frozenset(
                {"example/project"}
            ),
            max_tool_calls=3,
            max_files=1,
            max_bytes=30,
        )
        await broker.read_file("app/one.py")

        with self.assertRaises(ReadLimitError):
            await broker.read_file("app/two.py")

    async def test_rejects_protected_path_before_call(self):
        client = FakeMcpClient()
        broker = GitHubReadBroker(
            client=client,
            owner="example",
            repository="project",
            head_sha="a" * 40,
            allowed_repositories=frozenset(
                {"example/project"}
            ),
            max_tool_calls=2,
            max_files=2,
            max_bytes=1000,
        )

        with self.assertRaises(SecurityError):
            await broker.read_file("../secret.txt")
        self.assertEqual(client.calls, [])

    async def test_rejects_non_exact_sha(self):
        with self.assertRaises(SecurityError):
            GitHubReadBroker(
                client=FakeMcpClient(),
                owner="example",
                repository="project",
                head_sha="main",
                allowed_repositories=frozenset(
                    {"example/project"}
                ),
                max_tool_calls=2,
                max_files=2,
                max_bytes=1000,
            )

    async def test_search_only_locates_then_exact_sha_read(self):
        client = SearchMcpClient()
        broker = GitHubReadBroker(
            client=client,
            owner="example",
            repository="project",
            head_sha="a" * 40,
            allowed_repositories=frozenset(
                {"example/project"}
            ),
            max_tool_calls=3,
            max_files=1,
            max_bytes=2000,
        )

        resolved = await broker.find_candidate_path(
            "app/user_service.py"
        )
        await broker.read_file(resolved)

        self.assertEqual(resolved, "src/user_service.py")
        self.assertEqual(
            client.calls[-1],
            (
                "get_file_contents",
                {
                    "owner": "example",
                    "repo": "project",
                    "path": "src/user_service.py",
                    "ref": "a" * 40,
                },
            ),
        )
        self.assertNotIn(
            "create_branch",
            [name for name, _arguments in client.calls],
        )


if __name__ == "__main__":
    unittest.main()
