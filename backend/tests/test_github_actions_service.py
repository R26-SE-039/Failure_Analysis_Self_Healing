import unittest

import httpx

from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubActionsService,
    GitHubRunUrlError,
    parse_github_actions_run_url,
)


RUN_URL = "https://github.com/example/project/actions/runs/12345"
HEAD_SHA = "a" * 40


class GitHubRunUrlTests(unittest.TestCase):
    def test_parses_run_url_without_hardcoded_repository(self):
        reference = parse_github_actions_run_url(
            f"{RUN_URL}/job/99?check_suite_focus=true"
        )

        self.assertEqual(reference.owner, "example")
        self.assertEqual(reference.repository, "project")
        self.assertEqual(reference.run_id, 12345)
        self.assertEqual(reference.run_url, RUN_URL)

    def test_rejects_non_github_url(self):
        with self.assertRaises(GitHubRunUrlError):
            parse_github_actions_run_url(
                "https://example.com/example/project/actions/runs/12345"
            )


class GitHubActionsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_dynamic_run_metadata(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/repos/example/project/actions/runs/12345",
            )
            self.assertEqual(
                request.headers["Authorization"],
                "Bearer test-token",
            )
            return httpx.Response(
                200,
                json={
                    "id": 12345,
                    "name": "CI",
                    "path": ".github/workflows/ci.yml",
                    "head_sha": HEAD_SHA,
                    "head_branch": "feature/fix",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "failure",
                    "run_attempt": 2,
                    "created_at": "2026-06-20T01:00:00Z",
                    "updated_at": "2026-06-20T01:05:00Z",
                    "repository": {
                        "full_name": "example/project",
                        "clone_url": "https://github.com/example/project.git",
                        "default_branch": "main",
                    },
                },
            )

        service = GitHubActionsService(
            token="test-token",
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        result = await service.resolve_run(RUN_URL)

        self.assertEqual(result["repository_full_name"], "example/project")
        self.assertEqual(result["run_id"], 12345)
        self.assertEqual(result["head_sha"], HEAD_SHA)
        self.assertEqual(result["head_branch"], "feature/fix")
        self.assertEqual(result["default_branch"], "main")

    async def test_reports_missing_actions_permission(self):
        service = GitHubActionsService(
            token="test-token",
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(403)
            ),
        )

        with self.assertRaisesRegex(
            GitHubActionsApiError,
            "denied access",
        ):
            await service.resolve_run(RUN_URL)


if __name__ == "__main__":
    unittest.main()
