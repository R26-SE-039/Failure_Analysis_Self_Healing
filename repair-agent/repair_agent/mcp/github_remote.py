from __future__ import annotations

import base64
import json
from typing import Any

from repair_agent.diagnostics import log_stage

# Defer importing the `mcp` package until methods that need it are called.


class RemoteGitHubMcpError(RuntimeError):
    pass


class McpDecodeError(RemoteGitHubMcpError):
    pass


def extract_embedded_resource(blocks: list[object]) -> str | None:
    for block in blocks:
        if getattr(block, "type", None) != "resource":
            continue
        resource = getattr(block, "resource", None)
        text = getattr(resource, "text", None)
        if isinstance(text, str):
            return text
        blob = getattr(resource, "blob", None)
        if isinstance(blob, str):
            try:
                return base64.b64decode(
                    blob,
                    validate=True,
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                raise McpDecodeError(
                    "Remote GitHub MCP returned invalid resource content."
                ) from error
    return None


def extract_repository_content(value: object) -> str:
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            if value.get("encoding") == "base64":
                try:
                    return base64.b64decode(
                        content,
                        validate=True,
                    ).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as error:
                    raise McpDecodeError(
                        "Remote GitHub MCP returned invalid file content."
                    ) from error
            return content
        for key in ("data", "result", "file"):
            if key in value:
                try:
                    return extract_repository_content(value[key])
                except RemoteGitHubMcpError:
                    pass
        raise McpDecodeError(
            "Remote GitHub MCP returned no file content."
        )
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[", '"')):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, str):
                return parsed
            if (
                isinstance(parsed, dict)
                and set(parsed)
                & {"content", "data", "result", "file", "encoding"}
            ):
                return extract_repository_content(parsed)
        return value
    raise McpDecodeError(
        "Remote GitHub MCP returned no file content."
    )


class RemoteGitHubMcpClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        timeout_seconds: int,
        read_only: bool = True,
    ) -> None:
        self.url = url
        self._token = token
        self.timeout_seconds = timeout_seconds
        self.read_only = read_only

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "X-MCP-Readonly": (
                "true" if self.read_only else "false"
            ),
        }

    async def list_tools(self) -> set[str]:
        from mcp import ClientSession
        from mcp.client.streamable_http import (
            streamablehttp_client,
        )

        async with streamablehttp_client(
            self.url,
            headers=self._headers(),
            timeout=self.timeout_seconds,
            sse_read_timeout=self.timeout_seconds,
        ) as streams:
            async with ClientSession(
                streams[0],
                streams[1],
            ) as session:
                await session.initialize()
                result = await session.list_tools()
        return {tool.name for tool in result.tools}

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import (
                streamablehttp_client,
            )

            async with streamablehttp_client(
                self.url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                sse_read_timeout=self.timeout_seconds,
            ) as streams:
                async with ClientSession(
                    streams[0],
                    streams[1],
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        name,
                        arguments,
                    )
        except Exception as error:
            raise RemoteGitHubMcpError(
                "Remote GitHub MCP operation failed."
            ) from error

        if result.isError:
            raise RemoteGitHubMcpError(
                "Remote GitHub MCP rejected the operation."
            )

        text_parts = [
            str(content.text)
            for content in result.content
            if getattr(content, "type", None) == "text"
            and getattr(content, "text", None) is not None
        ]
        embedded_content = extract_embedded_resource(
            list(result.content)
        )
        if name == "get_file_contents" and embedded_content is not None:
            raw_content = embedded_content
        elif name == "get_file_contents" and result.structuredContent:
            raw_content = result.structuredContent
        elif text_parts:
            raw_content: object = "\n".join(text_parts)
        elif result.structuredContent:
            raw_content = result.structuredContent
        else:
            raise RemoteGitHubMcpError(
                "Remote GitHub MCP returned no readable content."
            )
        if name == "get_file_contents":
            try:
                decoded = extract_repository_content(raw_content)
            except McpDecodeError as error:
                log_stage(
                    "mcp_envelope_decoded",
                    "failed",
                    exception_class=type(error).__name__,
                    error_code="mcp_decode_failed",
                )
                raise
            log_stage("mcp_envelope_decoded", "completed")
            return decoded
        if isinstance(raw_content, str):
            return raw_content
        return json.dumps(raw_content)
