from __future__ import annotations

import re
import json
from pathlib import PurePosixPath

from repair_agent.mcp.interface import McpToolClient
from repair_agent.security import (
    SecurityError,
    normalize_repository_path,
    reject_sensitive_content,
)


READ_CONTENT_TOOL = "get_file_contents"
SEARCH_CODE_TOOL = "search_code"
READ_TOOL_ALLOWLIST = {
    READ_CONTENT_TOOL,
    SEARCH_CODE_TOOL,
}


class ReadLimitError(RuntimeError):
    pass


class GitHubReadBroker:
    def __init__(
        self,
        *,
        client: McpToolClient,
        owner: str,
        repository: str,
        head_sha: str,
        allowed_repositories: frozenset[str],
        max_tool_calls: int,
        max_files: int,
        max_bytes: int,
    ) -> None:
        full_name = f"{owner}/{repository}".lower()
        if full_name not in allowed_repositories:
            raise SecurityError(
                "Repository is not enabled for MCP reads."
            )
        if not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
            raise SecurityError(
                "An exact failed commit SHA is required."
            )
        self.client = client
        self.owner = owner
        self.repository = repository
        self.head_sha = head_sha
        self.max_tool_calls = max_tool_calls
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._tool_calls = 0
        self._bytes = 0
        self._inspected_files: list[str] = []
        self._read_contents: dict[str, str] = {}
        self._tools_verified = False
        self._available_tools: set[str] = set()

    @property
    def inspected_files(self) -> list[str]:
        return list(self._inspected_files)

    @property
    def read_contents(self) -> dict[str, str]:
        return dict(self._read_contents)

    async def _verify_tools(self) -> None:
        if self._tools_verified:
            return
        available = await self.client.list_tools()
        if READ_CONTENT_TOOL not in available:
            raise ReadLimitError(
                "Required read-only GitHub MCP tool is unavailable."
            )
        self._available_tools = (
            set(available) & READ_TOOL_ALLOWLIST
        )
        self._tools_verified = True

    async def _read(self, path: str) -> str:
        await self._verify_tools()
        if self._tool_calls >= self.max_tool_calls:
            raise ReadLimitError("MCP tool-call limit reached.")

        normalized = normalize_repository_path(path)
        self._tool_calls += 1
        content = await self.client.call_tool(
            READ_CONTENT_TOOL,
            {
                "owner": self.owner,
                "repo": self.repository,
                "path": normalized,
                "ref": self.head_sha,
            },
        )

        encoded_size = len(content.encode("utf-8"))
        if self._bytes + encoded_size > self.max_bytes:
            raise ReadLimitError("MCP byte limit reached.")
        reject_sensitive_content(content)
        self._bytes += encoded_size
        return content

    async def read_file(self, path: str) -> str:
        normalized = normalize_repository_path(path)
        if (
            normalized not in self._inspected_files
            and len(self._inspected_files) >= self.max_files
        ):
            raise ReadLimitError("MCP file-count limit reached.")

        content = await self._read(normalized)
        if normalized not in self._inspected_files:
            self._inspected_files.append(normalized)
        self._read_contents[normalized] = content
        return content

    async def list_directory(self, path: str) -> str:
        return await self._read(path)

    async def find_candidate_path(
        self,
        candidate_path: str,
    ) -> str | None:
        await self._verify_tools()
        if SEARCH_CODE_TOOL not in self._available_tools:
            return None
        if self._tool_calls >= self.max_tool_calls:
            raise ReadLimitError("MCP tool-call limit reached.")

        normalized = normalize_repository_path(candidate_path)
        filename = PurePosixPath(normalized).name
        self._tool_calls += 1
        result = await self.client.call_tool(
            SEARCH_CODE_TOOL,
            {
                "query": (
                    f"repo:{self.owner}/{self.repository} "
                    f"filename:{filename}"
                ),
                "page": 1,
                "perPage": 10,
            },
        )
        encoded_size = len(result.encode("utf-8"))
        if self._bytes + encoded_size > self.max_bytes:
            raise ReadLimitError("MCP byte limit reached.")
        reject_sensitive_content(result)
        self._bytes += encoded_size

        paths = self._paths_from_search(result)
        matching = sorted(
            {
                path
                for path in paths
                if PurePosixPath(path).name == filename
            }
        )
        return matching[0] if len(matching) == 1 else None

    @staticmethod
    def _paths_from_search(result: str) -> set[str]:
        paths: set[str] = set()
        try:
            payload = json.loads(result)
        except ValueError:
            payload = None

        def collect(value: object) -> None:
            if isinstance(value, dict):
                path = value.get("path")
                if isinstance(path, str):
                    try:
                        paths.add(normalize_repository_path(path))
                    except SecurityError:
                        pass
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(payload)
        if not paths:
            for match in re.finditer(
                r'"path"\s*:\s*"([^"]+)"',
                result,
            ):
                try:
                    paths.add(
                        normalize_repository_path(match.group(1))
                    )
                except SecurityError:
                    pass
        return paths
