from __future__ import annotations

from typing import Any, Protocol


class McpToolClient(Protocol):
    async def list_tools(self) -> set[str]:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        ...


class RepositoryReader(Protocol):
    @property
    def inspected_files(self) -> list[str]:
        ...

    @property
    def read_contents(self) -> dict[str, str]:
        ...

    async def read_file(self, path: str) -> str:
        ...

    async def list_directory(self, path: str) -> str:
        ...
