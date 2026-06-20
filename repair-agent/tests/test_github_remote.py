import unittest

from repair_agent.mcp.github_remote import RemoteGitHubMcpClient
from repair_agent.security import reject_sensitive_content, SecurityError


class RemoteGitHubMcpClientTests(unittest.TestCase):
    def test_headers_include_readonly_and_authorization_and_token_is_protected(self):
        client = RemoteGitHubMcpClient(
            url="http://example.invalid",
            token="secret-token-123",
            timeout_seconds=1,
        )
        headers = client._headers()
        self.assertIn("X-MCP-Readonly", headers)
        self.assertEqual(headers["X-MCP-Readonly"], "true")
        self.assertIn("Authorization", headers)
        # If someone attempted to echo the Authorization header, it should be rejected
        with self.assertRaises(SecurityError):
            reject_sensitive_content(f"authorization: {headers['Authorization']}")


if __name__ == "__main__":
    unittest.main()
