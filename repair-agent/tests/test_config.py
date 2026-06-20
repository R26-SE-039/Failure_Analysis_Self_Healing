import unittest

from repair_agent.config import (
    ConfigurationError,
    McpSettings,
    Settings,
)


def valid_environment() -> dict[str, str]:
    return {
        "OPENROUTER_API_KEY": "test-provider-key",
        "OPENROUTER_MODEL": "provider/tool-model",
        "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "GITHUB_MCP_URL": "https://api.githubcopilot.com/mcp/",
        "GITHUB_MCP_TOKEN": "test-github-token",
        "GITHUB_ALLOWED_REPOSITORIES": "example/project",
        "REPAIR_AGENT_SHARED_TOKEN": "test-shared-token",
    }


def valid_mcp_environment() -> dict[str, str]:
    return {
        "GITHUB_MCP_URL": "https://api.githubcopilot.com/mcp/",
        "GITHUB_MCP_TOKEN": "test-github-token",
        "GITHUB_ALLOWED_REPOSITORIES": "example/project",
        "REPAIR_TIMEOUT_SECONDS": "15",
    }


class SettingsTests(unittest.TestCase):
    def test_loads_mcp_settings_without_openrouter(self):
        environment = valid_mcp_environment()

        settings = McpSettings.from_environment(environment)

        self.assertEqual(
            settings.github_mcp_url,
            "https://api.githubcopilot.com/mcp/",
        )
        self.assertEqual(settings.timeout_seconds, 15)
        self.assertEqual(
            settings.allowed_repositories,
            frozenset({"example/project"}),
        )
        self.assertNotIn("OPENROUTER_MODEL", environment)

    def test_loads_required_read_only_configuration(self):
        settings = Settings.from_environment(
            valid_environment()
        )

        self.assertEqual(
            settings.openrouter_model,
            "provider/tool-model",
        )
        self.assertEqual(
            settings.allowed_repositories,
            frozenset({"example/project"}),
        )

    def test_rejects_missing_model(self):
        environment = valid_environment()
        del environment["OPENROUTER_MODEL"]

        with self.assertRaises(ConfigurationError):
            Settings.from_environment(environment)

    def test_rejects_random_model_router(self):
        environment = valid_environment()
        environment["OPENROUTER_MODEL"] = "openrouter/free"

        with self.assertRaises(ConfigurationError):
            Settings.from_environment(environment)

    def test_rejects_non_official_mcp_endpoint(self):
        environment = valid_environment()
        environment["GITHUB_MCP_URL"] = (
            "https://example.com/mcp/"
        )

        with self.assertRaises(ConfigurationError):
            Settings.from_environment(environment)


if __name__ == "__main__":
    unittest.main()
