from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    pass


def _required(
    environment: Mapping[str, str],
    name: str,
) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"Required environment variable is missing: {name}"
        )
    return value


def _positive_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    raw = environment.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(
            f"{name} must be an integer."
        ) from error
    if value <= 0:
        raise ConfigurationError(
            f"{name} must be greater than zero."
        )
    return value


@dataclass(frozen=True)
class McpSettings:
    github_mcp_url: str
    github_mcp_token: str
    allowed_repositories: frozenset[str]
    max_tool_calls: int
    max_files: int
    max_bytes: int
    max_excerpt_lines: int
    max_excerpt_chars: int
    timeout_seconds: int

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "McpSettings":
        env = environment if environment is not None else os.environ
        github_mcp_url = _required(env, "GITHUB_MCP_URL")
        if urlsplit(github_mcp_url).scheme != "https":
            raise ConfigurationError(
                "GITHUB_MCP_URL must use HTTPS."
            )
        if github_mcp_url.rstrip("/") != (
            "https://api.githubcopilot.com/mcp"
        ):
            raise ConfigurationError(
                "GITHUB_MCP_URL must use the official remote endpoint."
            )

        repositories = frozenset(
            item.strip().lower()
            for item in _required(
                env,
                "GITHUB_ALLOWED_REPOSITORIES",
            ).split(",")
            if item.strip()
        )
        if not repositories:
            raise ConfigurationError(
                "At least one allowed repository is required."
            )

        return cls(
            github_mcp_url=github_mcp_url,
            github_mcp_token=_required(
                env,
                "GITHUB_MCP_TOKEN",
            ),
            allowed_repositories=repositories,
            max_tool_calls=_positive_int(
                env,
                "REPAIR_MAX_TOOL_CALLS",
                12,
            ),
            max_files=_positive_int(
                env,
                "REPAIR_MAX_FILES",
                4,
            ),
            max_bytes=_positive_int(
                env,
                "REPAIR_MAX_BYTES",
                80000,
            ),
            max_excerpt_lines=_positive_int(
                env,
                "REPAIR_MAX_EXCERPT_LINES",
                12,
            ),
            max_excerpt_chars=_positive_int(
                env,
                "REPAIR_MAX_EXCERPT_CHARS",
                2000,
            ),
            timeout_seconds=_positive_int(
                env,
                "REPAIR_TIMEOUT_SECONDS",
                90,
            ),
        )


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str
    github_mcp_url: str
    github_mcp_token: str
    allowed_repositories: frozenset[str]
    shared_token: str
    max_tool_calls: int
    max_files: int
    max_bytes: int
    max_excerpt_lines: int
    max_excerpt_chars: int
    timeout_seconds: int

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "Settings":
        env = environment if environment is not None else os.environ
        openrouter_model = _required(
            env,
            "OPENROUTER_MODEL",
        )
        if openrouter_model in {
            "openrouter/free",
            "openrouter/auto",
        }:
            raise ConfigurationError(
                "OPENROUTER_MODEL must name one fixed model."
            )

        openrouter_base_url = _required(
            env,
            "OPENROUTER_BASE_URL",
        )
        if urlsplit(openrouter_base_url).scheme != "https":
            raise ConfigurationError(
                "OPENROUTER_BASE_URL must use HTTPS."
            )

        if (
            urlsplit(openrouter_base_url).hostname
            != "openrouter.ai"
        ):
            raise ConfigurationError(
                "OPENROUTER_BASE_URL must use openrouter.ai."
            )
        mcp = McpSettings.from_environment(env)

        return cls(
            openrouter_api_key=_required(
                env,
                "OPENROUTER_API_KEY",
            ),
            openrouter_model=openrouter_model,
            openrouter_base_url=openrouter_base_url.rstrip("/"),
            github_mcp_url=mcp.github_mcp_url,
            github_mcp_token=mcp.github_mcp_token,
            allowed_repositories=mcp.allowed_repositories,
            shared_token=_required(
                env,
                "REPAIR_AGENT_SHARED_TOKEN",
            ),
            max_tool_calls=mcp.max_tool_calls,
            max_files=mcp.max_files,
            max_bytes=mcp.max_bytes,
            max_excerpt_lines=mcp.max_excerpt_lines,
            max_excerpt_chars=mcp.max_excerpt_chars,
            timeout_seconds=mcp.timeout_seconds,
        )
