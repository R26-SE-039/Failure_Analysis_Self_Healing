"""Deprecated local-stdio GitHub MCP connection probe.

Retained for rollback only. The active Phase 1 runtime uses the official
remote streamable-HTTP endpoint through repair_agent.mcp.github_remote.
"""
from __future__ import annotations

import asyncio
import os
import shlex

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


load_dotenv()


async def main() -> None:
    token = os.getenv("GITHUB_PAT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_PAT_TOKEN is required.")

    command = os.getenv(
        "GITHUB_MCP_COMMAND",
        "github-mcp-server",
    )
    args = shlex.split(
        os.getenv("GITHUB_MCP_ARGS", "stdio")
    )
    environment = os.environ.copy()
    environment["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
    environment["GITHUB_READ_ONLY"] = "1"

    server = StdioServerParameters(
        command=command,
        args=args,
        env=environment,
    )
    async with stdio_client(server) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()

    print("Legacy local GitHub MCP tools:")
    for tool in tools.tools:
        print(tool.name)


if __name__ == "__main__":
    asyncio.run(main())
