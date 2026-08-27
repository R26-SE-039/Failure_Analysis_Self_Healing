from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from repair_agent.config import McpSettings
from repair_agent.mcp.github_remote import (
    RemoteGitHubMcpClient,
)
from repair_agent.mcp.read_broker import READ_CONTENT_TOOL


load_dotenv()


async def main() -> None:
    if os.getenv("RUN_LIVE_GITHUB_MCP_TEST") != "1":
        raise RuntimeError(
            "Set RUN_LIVE_GITHUB_MCP_TEST=1 to run the opt-in live probe."
        )

    settings = McpSettings.from_environment()
    client = RemoteGitHubMcpClient(
        url=settings.github_mcp_url,
        token=settings.github_mcp_token,
        timeout_seconds=settings.timeout_seconds,
    )
    tools = await client.list_tools()
    if READ_CONTENT_TOOL not in tools:
        raise RuntimeError(
            "Required read-only GitHub MCP tool is unavailable."
        )

    print("Remote GitHub MCP read-only probe succeeded.")
    print(f"Required tool available: {READ_CONTENT_TOOL}")


if __name__ == "__main__":
    asyncio.run(main())
