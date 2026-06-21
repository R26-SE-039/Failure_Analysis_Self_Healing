import base64
import json
import unittest
from types import SimpleNamespace

from repair_agent.mcp.github_remote import (
    RemoteGitHubMcpClient,
    extract_embedded_resource,
    extract_repository_content,
)
from repair_agent.security import reject_sensitive_content, SecurityError


class RemoteGitHubMcpClientTests(unittest.TestCase):
    def test_write_client_disables_readonly_header(self):
        client = RemoteGitHubMcpClient(
            url="https://api.githubcopilot.com/mcp/",
            token="private-write-token",
            timeout_seconds=30,
            read_only=False,
        )

        headers = client._headers()

        self.assertEqual(headers["X-MCP-Readonly"], "false")
        self.assertNotIn("private-write-token", str(client.__dict__.keys()))

    def test_extracts_embedded_text_resource(self):
        blocks = [
            SimpleNamespace(type="text", text="summary only"),
            SimpleNamespace(
                type="resource",
                resource=SimpleNamespace(
                    text="line 1\nline 2",
                ),
            ),
        ]

        self.assertEqual(
            extract_embedded_resource(blocks),
            "line 1\nline 2",
        )

    def test_decodes_embedded_blob_resource(self):
        blocks = [
            SimpleNamespace(
                type="resource",
                resource=SimpleNamespace(
                    blob=base64.b64encode(
                        b"line 1\nline 2"
                    ).decode("ascii"),
                ),
            )
        ]

        self.assertEqual(
            extract_embedded_resource(blocks),
            "line 1\nline 2",
        )

    def test_structured_file_content_is_preferred_contract(self):
        structured = {
            "encoding": "base64",
            "content": base64.b64encode(
                b"line 1\nline 2"
            ).decode("ascii"),
        }
        summary = "File retrieved successfully."

        self.assertNotEqual(
            extract_repository_content(structured),
            summary,
        )
        self.assertEqual(
            extract_repository_content(structured),
            "line 1\nline 2",
        )

    def test_decodes_base64_file_envelope(self):
        source = "line 1\nline 2\nline 3"
        envelope = json.dumps(
            {
                "encoding": "base64",
                "content": base64.b64encode(
                    source.encode("utf-8")
                ).decode("ascii"),
            }
        )

        self.assertEqual(
            extract_repository_content(envelope),
            source,
        )

    def test_extracts_plain_file_envelope(self):
        self.assertEqual(
            extract_repository_content(
                {"content": "line 1\nline 2"}
            ),
            "line 1\nline 2",
        )

    def test_decodes_json_string_content(self):
        self.assertEqual(
            extract_repository_content(
                json.dumps("line 1\nline 2")
            ),
            "line 1\nline 2",
        )

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
