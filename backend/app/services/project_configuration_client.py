from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


class ProjectConfigurationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ProjectGitHubConfiguration:
    repository_url: str
    repository_owner: str
    repository_name: str
    repository_full_name: str
    token: str


def _safe_bearer_header(value: str | None) -> str:
    header = (value or "").strip()
    if not header.lower().startswith("bearer ") or len(header) <= 7:
        raise ProjectConfigurationError(
            "Authorization is required to load project GitHub configuration.",
            status_code=401,
        )
    return header


def _parse_github_repository(repository_url: str) -> tuple[str, str, str]:
    value = repository_url.strip()
    if not value:
        raise ProjectConfigurationError(
            "GitHub configuration is not configured for this project.",
            status_code=400,
        )
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value):
        value = f"https://github.com/{value}"
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() != "github.com":
        raise ProjectConfigurationError(
            "Configured repository must be an HTTPS GitHub repository URL.",
            status_code=400,
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ProjectConfigurationError(
            "Configured repository URL must include owner and repository.",
            status_code=400,
        )
    owner = parts[0]
    repository = re.sub(r"\.git$", "", parts[1], flags=re.IGNORECASE)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise ProjectConfigurationError(
            "Configured GitHub repository owner or name is invalid.",
            status_code=400,
        )
    return owner, repository, f"{owner}/{repository}".lower()


class ProjectConfigurationClient:
    def __init__(
        self,
        *,
        gateway_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.gateway_url = (
            gateway_url
            if gateway_url is not None
            else os.getenv("API_GATEWAY_URL", "")
        ).rstrip("/")
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    async def get_project_github_configuration(
        self,
        *,
        project_id: str,
        authorization_header: str | None,
    ) -> ProjectGitHubConfiguration:
        if not self.gateway_url:
            raise ProjectConfigurationError(
                "API gateway URL is not configured for project GitHub configuration lookup.",
                status_code=503,
            )
        auth_header = _safe_bearer_header(authorization_header)
        url = f"{self.gateway_url}/api/auth-service/projects/{project_id}/configuration"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": auth_header},
                )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise ProjectConfigurationError(
                "Project GitHub configuration could not be reached.",
                status_code=503,
            ) from error

        if response.status_code == 404:
            raise ProjectConfigurationError(
                "GitHub configuration is not configured for this project.",
                status_code=400,
            )
        if response.status_code in {401, 403}:
            raise ProjectConfigurationError(
                "Not authorized to load GitHub configuration for this project.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProjectConfigurationError(
                "Project GitHub configuration could not be loaded.",
                status_code=502,
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as error:
            raise ProjectConfigurationError(
                "Project GitHub configuration response was invalid.",
                status_code=502,
            ) from error

        repository_url = str(payload.get("repo_url") or "")
        token = str(payload.get("personal_access_token") or "")
        if not token.strip():
            raise ProjectConfigurationError(
                "GitHub configuration is not configured for this project.",
                status_code=400,
            )
        owner, repository, full_name = _parse_github_repository(repository_url)
        return ProjectGitHubConfiguration(
            repository_url=repository_url,
            repository_owner=owner,
            repository_name=repository,
            repository_full_name=full_name,
            token=token,
        )


project_configuration_client = ProjectConfigurationClient()
