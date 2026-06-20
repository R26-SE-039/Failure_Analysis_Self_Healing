from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


GITHUB_API_VERSION = "2022-11-28"
GITHUB_HOSTS = {"github.com", "www.github.com"}
REPOSITORY_PART_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


class GitHubRunUrlError(ValueError):
    pass


class GitHubActionsApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubRunReference:
    owner: str
    repository: str
    run_id: int
    run_url: str


def parse_github_actions_run_url(run_url: str) -> GitHubRunReference:
    value = run_url.strip()
    if not value:
        raise GitHubRunUrlError("GitHub Actions run URL is required.")

    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in GITHUB_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise GitHubRunUrlError(
            "Use an HTTPS GitHub Actions run URL from github.com."
        )

    parts = [part for part in parsed.path.split("/") if part]
    if (
        len(parts) < 5
        or parts[2] != "actions"
        or parts[3] != "runs"
        or not parts[4].isdigit()
    ):
        raise GitHubRunUrlError(
            "Expected https://github.com/{owner}/{repo}/actions/runs/{run_id}."
        )

    owner, repository = parts[0], parts[1]
    if not all(
        REPOSITORY_PART_PATTERN.fullmatch(part)
        for part in (owner, repository)
    ):
        raise GitHubRunUrlError("The GitHub owner or repository name is invalid.")

    run_id = int(parts[4])
    if run_id <= 0:
        raise GitHubRunUrlError("The GitHub Actions run ID must be positive.")

    canonical_url = (
        f"https://github.com/{owner}/{repository}/actions/runs/{run_id}"
    )
    return GitHubRunReference(owner, repository, run_id, canonical_url)


class GitHubActionsService:
    def __init__(
        self,
        *,
        token: str | None = None,
        allowed_repositories: set[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._token = token
        self._allowed_repositories = (
            {
                repository.lower()
                for repository in allowed_repositories
            }
            if allowed_repositories is not None
            else {
                repository.strip().lower()
                for repository in os.getenv(
                    "GITHUB_ALLOWED_REPOSITORIES",
                    "",
                ).split(",")
                if repository.strip()
            }
        )
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "failure-analysis-self-healing",
        }
        token = (
            self._token
            or os.getenv("GITHUB_ACTIONS_TOKEN")
            or os.getenv("GITHUB_PAT_TOKEN")
        )
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def resolve_run(self, run_url: str) -> dict[str, Any]:
        reference = parse_github_actions_run_url(run_url)
        requested_repository = (
            f"{reference.owner}/{reference.repository}".lower()
        )
        if (
            not self._allowed_repositories
            or requested_repository
            not in self._allowed_repositories
        ):
            raise GitHubActionsApiError(
                "The repository is not enabled for analysis."
            )
        endpoint = (
            f"https://api.github.com/repos/{reference.owner}/"
            f"{reference.repository}/actions/runs/{reference.run_id}"
        )

        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(endpoint)
        except httpx.TimeoutException as error:
            raise GitHubActionsApiError(
                "GitHub timed out while resolving the workflow run."
            ) from error
        except httpx.RequestError as error:
            raise GitHubActionsApiError(
                "GitHub could not be reached while resolving the workflow run."
            ) from error

        if response.status_code == 401:
            raise GitHubActionsApiError(
                "GitHub rejected the token. Check GITHUB_PAT_TOKEN."
            )
        if response.status_code == 403:
            raise GitHubActionsApiError(
                "GitHub denied access or rate-limited the request."
            )
        if response.status_code == 404:
            raise GitHubActionsApiError(
                "Workflow run not found or the token cannot access its repository."
            )
        if response.status_code >= 400:
            raise GitHubActionsApiError(
                f"GitHub returned HTTP {response.status_code} for the workflow run."
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise GitHubActionsApiError(
                "GitHub returned an invalid workflow-run response."
            ) from error

        return self._normalize_payload(reference, payload)

    @staticmethod
    def _normalize_payload(
        reference: GitHubRunReference,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        repository = payload.get("repository") or {}
        full_name = str(repository.get("full_name") or "")
        expected_full_name = f"{reference.owner}/{reference.repository}"

        if full_name.lower() != expected_full_name.lower():
            raise GitHubActionsApiError(
                "GitHub returned metadata for a different repository."
            )

        if payload.get("id") != reference.run_id:
            raise GitHubActionsApiError(
                "GitHub returned metadata for a different workflow run."
            )

        head_sha = str(payload.get("head_sha") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
            raise GitHubActionsApiError(
                "The workflow run does not contain a valid commit SHA."
            )

        head_branch = payload.get("head_branch")
        if not isinstance(head_branch, str) or not head_branch.strip():
            raise GitHubActionsApiError(
                "The workflow run does not contain a source branch."
            )

        return {
            **asdict(reference),
            "repository_full_name": full_name,
            "default_branch": repository.get("default_branch"),
            "head_sha": head_sha,
            "head_branch": head_branch,
            "workflow_name": payload.get("name"),
            "workflow_path": payload.get("path"),
            "event": payload.get("event"),
            "status": payload.get("status"),
            "conclusion": payload.get("conclusion"),
            "run_attempt": payload.get("run_attempt", 1),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }


github_actions_service = GitHubActionsService()
