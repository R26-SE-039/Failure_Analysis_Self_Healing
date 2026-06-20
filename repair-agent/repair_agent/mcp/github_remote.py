from __future__ import annotations

from typing import Any

# Defer importing the `mcp` package until methods that need it are called.


class RemoteGitHubMcpError(RuntimeError):
    pass


class RemoteGitHubMcpClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        timeout_seconds: int,
    ) -> None:
        self.url = url
        self._token = token
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "X-MCP-Readonly": "true",
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
                "Remote GitHub MCP read failed."
            ) from error

        if result.isError:
            raise RemoteGitHubMcpError(
                "Remote GitHub MCP rejected the read."
            )

        text_parts = [
            str(content.text)
            for content in result.content
            if getattr(content, "type", None) == "text"
            and getattr(content, "text", None) is not None
        ]
        if not text_parts and result.structuredContent:
            text_parts.append(str(result.structuredContent))
        if not text_parts:
            raise RemoteGitHubMcpError(
                "Remote GitHub MCP returned no readable content."
            )
        return "\n".join(text_parts)
