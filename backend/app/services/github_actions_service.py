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
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
LOG_DOWNLOAD_MAX_BYTES = 512_000
LOG_DOWNLOAD_RETRY_COUNT = 2


class GitHubRunUrlError(ValueError):
    pass


class GitHubActionsApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        token = self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _download_headers(self) -> dict[str, str]:
        return {
            "Accept": "text/plain",
            "User-Agent": "failure-analysis-self-healing",
        }

    def _ensure_repository_allowed(self, owner: str, repository: str) -> str:
        full_name = f"{owner}/{repository}".lower()
        if not self._allowed_repositories or full_name not in self._allowed_repositories:
            raise GitHubActionsApiError(
                "The repository is not enabled for analysis.",
                status_code=403,
            )
        return full_name

    async def _get_json(self, endpoint: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(endpoint)
        except httpx.TimeoutException as error:
            raise GitHubActionsApiError(
                "GitHub timed out while reading workflow metadata.",
                status_code=504,
            ) from error
        except httpx.RequestError as error:
            raise GitHubActionsApiError(
                "GitHub could not be reached while reading workflow metadata.",
                status_code=503,
            ) from error

        if response.status_code == 401:
            raise GitHubActionsApiError(
                "GitHub rejected the project GitHub token. Update the project Git configuration.",
                status_code=401,
            )
        if response.status_code == 403:
            raise GitHubActionsApiError(
                "GitHub denied access or rate-limited the request.",
                status_code=403,
            )
        if response.status_code == 404:
            raise GitHubActionsApiError(
                "GitHub workflow metadata was not found or the token cannot access its repository.",
                status_code=404,
            )
        if response.status_code == 429:
            raise GitHubActionsApiError(
                "GitHub rate-limited the request. Try again later.",
                status_code=429,
            )
        if response.status_code >= 500:
            raise GitHubActionsApiError(
                "GitHub is temporarily unavailable while reading workflow metadata.",
                status_code=502,
            )
        if response.status_code >= 400:
            raise GitHubActionsApiError(
                f"GitHub returned HTTP {response.status_code} while reading workflow metadata.",
                status_code=502,
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise GitHubActionsApiError(
                "GitHub returned an invalid workflow metadata response.",
                status_code=502,
            ) from error
        if not isinstance(payload, dict):
            raise GitHubActionsApiError(
                "GitHub returned an unexpected workflow metadata response.",
                status_code=502,
            )
        return payload

    async def _get_log_response(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
    ) -> httpx.Response:
        return await client.get(
            endpoint,
            headers=self._headers(),
            follow_redirects=False,
        )

    async def _get_redirected_log_response(
        self,
        client: httpx.AsyncClient,
        redirect_url: str,
    ) -> httpx.Response:
        return await client.get(
            redirect_url,
            headers=self._download_headers(),
            follow_redirects=False,
        )

    async def _download_log_once(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        *,
        max_bytes: int,
    ) -> str:
        response = await self._get_log_response(client, endpoint)
        if response.status_code in REDIRECT_STATUS_CODES:
            redirect_url = response.headers.get("Location")
            if not redirect_url:
                raise GitHubActionsApiError(
                    "GitHub did not provide a job-log download location.",
                    status_code=502,
                )
            response = await self._get_redirected_log_response(client, redirect_url)

        if response.status_code >= 400:
            self._raise_log_response_error(response)

        return self._decode_log_response(response, max_bytes=max_bytes)

    async def download_job_log(
        self,
        *,
        owner: str,
        repository: str,
        job_id: int,
        max_bytes: int = LOG_DOWNLOAD_MAX_BYTES,
        retry_count: int = LOG_DOWNLOAD_RETRY_COUNT,
    ) -> str:
        self._ensure_repository_allowed(owner, repository)
        if job_id <= 0:
            raise GitHubActionsApiError(
                "GitHub job ID must be positive.",
                status_code=400,
            )

        endpoint = (
            f"https://api.github.com/repos/{owner}/{repository}/actions/jobs/{job_id}/logs"
        )
        attempts = max(1, min(retry_count, 3))
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                for attempt in range(attempts):
                    try:
                        return await self._download_log_once(
                            client,
                            endpoint,
                            max_bytes=max_bytes,
                        )
                    except httpx.TimeoutException as error:
                        if attempt + 1 >= attempts:
                            raise GitHubActionsApiError(
                                "GitHub timed out while downloading the job log.",
                                status_code=504,
                            ) from error
                    except httpx.RequestError as error:
                        if attempt + 1 >= attempts:
                            raise GitHubActionsApiError(
                                "GitHub job log could not be downloaded.",
                                status_code=503,
                            ) from error
                    except GitHubActionsApiError as error:
                        if error.status_code in {502, 503, 504} and attempt + 1 < attempts:
                            continue
                        raise
        except GitHubActionsApiError:
            raise

        raise GitHubActionsApiError(
            "GitHub job log could not be downloaded.",
            status_code=503,
        )

    @staticmethod
    def _decode_log_response(response: httpx.Response, *, max_bytes: int) -> str:
        bounded_max = max(1, max_bytes)
        content = response.content
        if len(content) <= bounded_max:
            return content.decode("utf-8", errors="replace")

        marker = b"\n...[middle of GitHub job log truncated for bounded evidence]...\n"
        if bounded_max <= len(marker) + 2:
            return content[:bounded_max].decode("utf-8", errors="replace")

        remaining_bytes = bounded_max - len(marker)
        head_bytes = max(1, remaining_bytes // 2)
        tail_bytes = max(1, remaining_bytes - head_bytes)
        bounded_content = content[:head_bytes] + marker + content[-tail_bytes:]
        return bounded_content.decode("utf-8", errors="replace")

    @staticmethod
    def _raise_log_response_error(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise GitHubActionsApiError(
                "GitHub rejected the project GitHub token. Update the project Git configuration.",
                status_code=401,
            )
        if response.status_code == 403:
            raise GitHubActionsApiError(
                "GitHub denied access to the job log or rate-limited the request.",
                status_code=403,
            )
        if response.status_code == 404:
            raise GitHubActionsApiError(
                "GitHub job log was not found or is no longer available.",
                status_code=404,
            )
        if response.status_code == 429:
            raise GitHubActionsApiError(
                "GitHub rate-limited the job-log request. Try again later.",
                status_code=429,
            )
        if response.status_code >= 500:
            raise GitHubActionsApiError(
                "GitHub is temporarily unavailable while downloading the job log.",
                status_code=502,
            )
        if response.status_code >= 400:
            raise GitHubActionsApiError(
                f"GitHub returned HTTP {response.status_code} while downloading the job log.",
                status_code=502,
            )

    async def list_failed_runs(
        self,
        *,
        owner: str,
        repository: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self._ensure_repository_allowed(owner, repository)
        bounded_limit = max(1, min(limit, 50))
        endpoint = (
            f"https://api.github.com/repos/{owner}/{repository}/actions/runs"
            f"?status=completed&per_page={bounded_limit}"
        )
        payload = await self._get_json(endpoint)
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            raise GitHubActionsApiError(
                "GitHub returned an invalid workflow-runs response.",
                status_code=502,
            )

        return [
            self._normalize_run_summary(owner, repository, run)
            for run in runs
            if isinstance(run, dict) and self._is_failed_run(run)
        ]

    async def get_run(
        self,
        *,
        owner: str,
        repository: str,
        run_id: int,
    ) -> dict[str, Any]:
        self._ensure_repository_allowed(owner, repository)
        endpoint = (
            f"https://api.github.com/repos/{owner}/{repository}/actions/runs/{run_id}"
        )
        payload = await self._get_json(endpoint)
        return self._normalize_run_summary(owner, repository, payload)

    async def list_jobs_for_run(
        self,
        *,
        owner: str,
        repository: str,
        run_id: int,
    ) -> list[dict[str, Any]]:
        self._ensure_repository_allowed(owner, repository)
        endpoint = (
            f"https://api.github.com/repos/{owner}/{repository}/actions/runs/{run_id}/jobs"
        )
        payload = await self._get_json(endpoint)
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise GitHubActionsApiError(
                "GitHub returned an invalid workflow-jobs response.",
                status_code=502,
            )
        return [
            self._normalize_job(job)
            for job in jobs
            if isinstance(job, dict)
        ]

    async def resolve_run(self, run_url: str) -> dict[str, Any]:
        reference = parse_github_actions_run_url(run_url)
        self._ensure_repository_allowed(reference.owner, reference.repository)
        endpoint = (
            f"https://api.github.com/repos/{reference.owner}/"
            f"{reference.repository}/actions/runs/{reference.run_id}"
        )
        payload = await self._get_json(endpoint)
        return self._normalize_payload(reference, payload)

    @staticmethod
    def _is_failed_run(payload: dict[str, Any]) -> bool:
        return (
            str(payload.get("status") or "").lower() == "completed"
            and str(payload.get("conclusion") or "").lower() == "failure"
        )

    @staticmethod
    def _normalize_run_summary(
        owner: str,
        repository: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        repository_payload = payload.get("repository") or {}
        full_name = str(repository_payload.get("full_name") or "")
        expected_full_name = f"{owner}/{repository}"

        if full_name.lower() != expected_full_name.lower():
            raise GitHubActionsApiError(
                "GitHub returned metadata for a different repository.",
                status_code=409,
            )

        run_id = payload.get("id")
        if not isinstance(run_id, int) or run_id <= 0:
            raise GitHubActionsApiError(
                "GitHub returned workflow-run metadata without a valid run ID.",
                status_code=502,
            )

        head_sha = payload.get("head_sha")
        if head_sha is not None and not COMMIT_SHA_PATTERN.fullmatch(str(head_sha)):
            raise GitHubActionsApiError(
                "The workflow run does not contain a valid commit SHA.",
                status_code=502,
            )

        return {
            "run_id": run_id,
            "run_number": payload.get("run_number"),
            "run_attempt": payload.get("run_attempt", 1),
            "name": payload.get("name"),
            "display_title": payload.get("display_title"),
            "status": payload.get("status"),
            "conclusion": payload.get("conclusion"),
            "head_branch": payload.get("head_branch"),
            "head_sha": head_sha,
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "html_url": payload.get("html_url"),
            "repository": {"full_name": full_name.lower()},
            "check_suite_id": payload.get("check_suite_id"),
        }

    @staticmethod
    def _normalize_job(payload: dict[str, Any]) -> dict[str, Any]:
        steps = payload.get("steps") or []
        safe_steps = []
        if isinstance(steps, list):
            safe_steps = [
                {
                    "number": step.get("number"),
                    "name": step.get("name"),
                    "status": step.get("status"),
                    "conclusion": step.get("conclusion"),
                }
                for step in steps
                if isinstance(step, dict)
            ]

        return {
            "job_id": payload.get("id"),
            "name": payload.get("name"),
            "status": payload.get("status"),
            "conclusion": payload.get("conclusion"),
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "html_url": payload.get("html_url"),
            "steps": safe_steps,
        }

    @staticmethod
    def _normalize_payload(
        reference: GitHubRunReference,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run = GitHubActionsService._normalize_run_summary(
            reference.owner,
            reference.repository,
            payload,
        )
        repository = payload.get("repository") or {}
        head_branch = run.get("head_branch")
        if not isinstance(head_branch, str) or not head_branch.strip():
            raise GitHubActionsApiError(
                "The workflow run does not contain a source branch.",
                status_code=502,
            )
        head_sha = str(run.get("head_sha") or "")
        if not COMMIT_SHA_PATTERN.fullmatch(head_sha):
            raise GitHubActionsApiError(
                "The workflow run does not contain a valid commit SHA.",
                status_code=502,
            )

        return {
            **asdict(reference),
            "repository_full_name": run["repository"]["full_name"],
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
