import unittest

import httpx

from app.services.project_configuration_client import (
    ProjectConfigurationClient,
    ProjectConfigurationError,
)


class ProjectConfigurationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_existing_project_configuration_through_gateway(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("Authorization")
            return httpx.Response(
                200,
                json={
                    "id": "config-1",
                    "project_id": "project-a",
                    "repo_url": "https://github.com/example/project-a.git",
                    "personal_access_token": "project-token",
                    "created_at": "2026-08-16T00:00:00Z",
                    "updated_at": "2026-08-16T00:00:00Z",
                },
            )

        client = ProjectConfigurationClient(
            gateway_url="http://gateway.local",
            transport=httpx.MockTransport(handler),
        )

        config = await client.get_project_github_configuration(
            project_id="project-a",
            authorization_header="Bearer user-jwt",
        )

        self.assertEqual(
            seen["url"],
            "http://gateway.local/api/auth-service/projects/project-a/configuration",
        )
        self.assertEqual(seen["authorization"], "Bearer user-jwt")
        self.assertEqual(config.repository_full_name, "example/project-a")
        self.assertEqual(config.repository_owner, "example")
        self.assertEqual(config.repository_name, "project-a")
        self.assertEqual(config.token, "project-token")

    async def test_requires_authorization_header(self):
        client = ProjectConfigurationClient(gateway_url="http://gateway.local")

        with self.assertRaisesRegex(ProjectConfigurationError, "Authorization") as ctx:
            await client.get_project_github_configuration(
                project_id="project-a",
                authorization_header=None,
            )

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_missing_project_configuration_is_safe_error(self):
        client = ProjectConfigurationClient(
            gateway_url="http://gateway.local",
            transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        )

        with self.assertRaisesRegex(
            ProjectConfigurationError,
            "GitHub configuration is not configured",
        ) as ctx:
            await client.get_project_github_configuration(
                project_id="project-a",
                authorization_header="Bearer user-jwt",
            )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_auth_service_denial_is_safe_error(self):
        client = ProjectConfigurationClient(
            gateway_url="http://gateway.local",
            transport=httpx.MockTransport(lambda request: httpx.Response(403)),
        )

        with self.assertRaisesRegex(ProjectConfigurationError, "Not authorized") as ctx:
            await client.get_project_github_configuration(
                project_id="project-a",
                authorization_header="Bearer user-jwt",
            )

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
