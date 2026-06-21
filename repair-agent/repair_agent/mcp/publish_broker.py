from __future__ import annotations

import json
import logging
import re
from typing import Any

from repair_agent.mcp.interface import McpToolClient
from repair_agent.security import (
    SecurityError,
    normalize_repository_path,
)


GET_COMMIT = "get_commit"
GET_FILE_CONTENTS = "get_file_contents"
CREATE_BRANCH = "create_branch"
PUSH_FILES = "push_files"
CREATE_PULL_REQUEST = "create_pull_request"
PULL_REQUEST_READ = "pull_request_read"
LIST_PULL_REQUESTS = "list_pull_requests"

PUBLISH_TOOL_ALLOWLIST = {
    GET_COMMIT,
    GET_FILE_CONTENTS,
    CREATE_BRANCH,
    PUSH_FILES,
    CREATE_PULL_REQUEST,
    PULL_REQUEST_READ,
    LIST_PULL_REQUESTS,
}

logger = logging.getLogger("repair_agent.publish")


class PublishBrokerError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostics = diagnostics or {}


def _json_object(value: str) -> object:
    try:
        return json.loads(value)
    except ValueError as error:
        raise PublishBrokerError("publish_mcp_decode_failed") from error


def _find_value(value: object, keys: set[str]) -> object | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in keys and child not in (None, ""):
                return child
        for child in value.values():
            found = _find_value(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found is not None:
                return found
    return None


def _decode_nested_json(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[", '"')):
            try:
                return _decode_nested_json(json.loads(stripped))
            except ValueError:
                return value
        return value
    if isinstance(value, dict):
        return {
            key: _decode_nested_json(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_decode_nested_json(child) for child in value]
    return value


def _response_shape_metadata(payload: object) -> dict[str, object]:
    keys: set[str] = set()
    value_types: dict[str, str] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = re.sub(r"[^A-Za-z0-9_]", "", str(raw_key))[:80]
                if key:
                    keys.add(key)
                    value_types.setdefault(key, type(child).__name__)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return {
        "response_key_names": sorted(keys)[:80],
        "response_value_types": {
            key: value_types[key] for key in sorted(value_types)[:80]
        },
        "number_exists": _find_value(payload, {"number", "pull_number"})
        is not None,
        "url_exists": _find_value(payload, {"html_url", "url"}) is not None,
        "draft_exists": _find_value(payload, {"draft", "is_draft"})
        is not None,
    }


def _iter_pr_candidates(value: object):
    if isinstance(value, dict):
        if _find_value(value, {"number", "pull_number"}) is not None:
            yield value
        for child in value.values():
            yield from _iter_pr_candidates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_pr_candidates(child)


def _ref_name(value: object) -> str | None:
    if isinstance(value, dict):
        ref = value.get("ref")
        if isinstance(ref, str):
            return ref
        label = value.get("label")
        if isinstance(label, str):
            return label.split(":", 1)[-1]
    if isinstance(value, str):
        return value.split(":", 1)[-1]
    return None


def parse_pull_request_identity(
    payload: object,
    *,
    owner: str,
    repository: str,
) -> tuple[int, str] | None:
    decoded = _decode_nested_json(payload)
    number = _find_value(decoded, {"number", "pull_number"})
    if isinstance(number, str) and number.isdigit():
        number = int(number)
    if not isinstance(number, int) or number <= 0:
        return None
    raw_url = _find_value(decoded, {"html_url"})
    if raw_url is None:
        raw_url = _find_value(decoded, {"url"})
    if not isinstance(raw_url, str):
        return None
    web_url = f"https://github.com/{owner}/{repository}/pull/{number}"
    api_url = f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}"
    if raw_url.rstrip("/") not in {web_url, api_url}:
        return None
    return number, web_url


class GitHubPublishBroker:
    def __init__(
        self,
        *,
        client: McpToolClient,
        owner: str,
        repository: str,
        base_sha: str,
        failed_branch: str,
        repair_branch: str,
        approved_paths: set[str],
        allowed_repositories: frozenset[str],
        max_tool_calls: int,
        max_files: int,
        max_bytes: int,
    ) -> None:
        full_name = f"{owner}/{repository}".lower()
        if full_name not in allowed_repositories:
            raise SecurityError("Repository is not enabled for publishing.")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
            raise SecurityError("An exact failed commit SHA is required.")
        if (
            not re.fullmatch(r"[A-Za-z0-9._/-]{1,255}", failed_branch)
            or ".." in failed_branch
            or "//" in failed_branch
            or failed_branch.startswith("/")
            or failed_branch.endswith("/")
        ):
            raise SecurityError("Failed branch is invalid.")
        if not repair_branch.startswith("auto-heal/"):
            raise SecurityError("Repair branch must use auto-heal prefix.")
        if repair_branch in {failed_branch, "main", "master"}:
            raise SecurityError("Direct branch modification is forbidden.")
        normalized_paths = {
            normalize_repository_path(path) for path in approved_paths
        }
        if not normalized_paths or len(normalized_paths) > max_files:
            raise SecurityError("Approved file count is invalid.")

        self.client = client
        self.owner = owner
        self.repository = repository
        self.base_sha = base_sha.lower()
        self.failed_branch = failed_branch
        self.repair_branch = repair_branch
        self.approved_paths = normalized_paths
        self.max_tool_calls = max_tool_calls
        self.max_bytes = max_bytes
        self._tool_calls = 0
        self._bytes = 0
        self._tools_verified = False
        self._branch_head_verified = False
        self._branch_created = False
        self._commit_pushed = False
        self._pull_request_created = False

    async def _verify_tools(self) -> None:
        if self._tools_verified:
            return
        available = await self.client.list_tools()
        missing = PUBLISH_TOOL_ALLOWLIST - set(available)
        if missing:
            raise PublishBrokerError("publish_tools_unavailable")
        self._tools_verified = True

    async def _call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        await self._verify_tools()
        if name not in PUBLISH_TOOL_ALLOWLIST:
            raise PublishBrokerError("publish_tool_forbidden")
        if self._tool_calls >= self.max_tool_calls:
            raise PublishBrokerError("publish_tool_limit_reached")
        self._tool_calls += 1
        return await self.client.call_tool(name, arguments)

    async def verify_failed_branch_head(self) -> None:
        result = await self._call(
            GET_COMMIT,
            {
                "owner": self.owner,
                "repo": self.repository,
                "sha": self.failed_branch,
                "detail": "none",
            },
        )
        sha = _find_value(_json_object(result), {"sha"})
        if not isinstance(sha, str) or sha.lower() != self.base_sha:
            raise PublishBrokerError("branch_head_mismatch")
        self._branch_head_verified = True

    async def read_approved_file(self, path: str) -> str:
        if not self._branch_head_verified:
            raise PublishBrokerError("branch_head_not_verified")
        normalized = normalize_repository_path(path)
        if normalized not in self.approved_paths:
            raise PublishBrokerError("changed_file_mismatch")
        content = await self._call(
            GET_FILE_CONTENTS,
            {
                "owner": self.owner,
                "repo": self.repository,
                "path": normalized,
                "sha": self.base_sha,
            },
        )
        content_size = len(content.encode("utf-8"))
        if self._bytes + content_size > self.max_bytes:
            raise PublishBrokerError("publish_byte_limit_reached")
        self._bytes += content_size
        return content

    async def create_repair_branch(self) -> None:
        if not self._branch_head_verified:
            raise PublishBrokerError("branch_head_not_verified")
        if self._branch_created:
            raise PublishBrokerError("single_branch_limit_reached")
        result = await self._call(
            CREATE_BRANCH,
            {
                "owner": self.owner,
                "repo": self.repository,
                "branch": self.repair_branch,
                "from_branch": self.failed_branch,
            },
        )
        sha = _find_value(_json_object(result), {"sha"})
        if not isinstance(sha, str) or sha.lower() != self.base_sha:
            raise PublishBrokerError("created_branch_sha_mismatch")
        self._branch_created = True

    async def push_approved_files(
        self,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        if not self._branch_created:
            raise PublishBrokerError("repair_branch_not_created")
        if self._commit_pushed:
            raise PublishBrokerError("single_commit_limit_reached")
        paths = {
            normalize_repository_path(item.get("path", ""))
            for item in files
        }
        if paths != self.approved_paths:
            raise PublishBrokerError("changed_file_mismatch")
        output_size = sum(
            len(item.get("content", "").encode("utf-8"))
            for item in files
        )
        if output_size > self.max_bytes:
            raise PublishBrokerError("publish_byte_limit_reached")
        result = await self._call(
            PUSH_FILES,
            {
                "owner": self.owner,
                "repo": self.repository,
                "branch": self.repair_branch,
                "files": files,
                "message": message,
            },
        )
        sha = _find_value(
            _json_object(result),
            {"sha", "commit_sha"},
        )
        if not isinstance(sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}",
            sha,
        ):
            raise PublishBrokerError("commit_sha_missing")
        self._commit_pushed = True
        return sha

    async def create_draft_pull_request(
        self,
        *,
        title: str,
        body: str,
    ) -> tuple[int, str]:
        if not self._commit_pushed:
            raise PublishBrokerError("commit_not_created")
        if self._pull_request_created:
            raise PublishBrokerError("single_pull_request_limit_reached")
        result = await self._call(
            CREATE_PULL_REQUEST,
            {
                "owner": self.owner,
                "repo": self.repository,
                "title": title,
                "body": body,
                "head": self.repair_branch,
                "base": self.failed_branch,
                "draft": True,
                "maintainer_can_modify": True,
                "show_ui": False,
            },
        )
        payload = _decode_nested_json(_json_object(result))
        identity = parse_pull_request_identity(
            payload,
            owner=self.owner,
            repository=self.repository,
        )
        if identity is None:
            diagnostics = _response_shape_metadata(payload)
            logger.warning(
                "stage=draft_pr_identity_parse_failed diagnostics=%s",
                diagnostics,
            )
            recovered = await self.find_existing_draft_pull_request()
            if recovered is None:
                raise PublishBrokerError(
                    "draft_pr_identity_missing",
                    diagnostics=diagnostics,
                )
            identity = recovered
        number, url = identity
        self._pull_request_created = True
        return number, url

    async def find_existing_draft_pull_request(
        self,
    ) -> tuple[int, str] | None:
        result = await self._call(
            LIST_PULL_REQUESTS,
            {
                "owner": self.owner,
                "repo": self.repository,
                "state": "open",
                "head": f"{self.owner}:{self.repair_branch}",
                "base": self.failed_branch,
                "perPage": 10,
            },
        )
        payload = _decode_nested_json(_json_object(result))
        for candidate in _iter_pr_candidates(payload):
            state = candidate.get("state")
            draft = candidate.get("draft", candidate.get("is_draft"))
            head = _ref_name(candidate.get("head"))
            base = _ref_name(candidate.get("base"))
            if state not in (None, "open"):
                continue
            if draft is not True:
                continue
            if head != self.repair_branch or base != self.failed_branch:
                continue
            identity = parse_pull_request_identity(
                candidate,
                owner=self.owner,
                repository=self.repository,
            )
            if identity is not None:
                return identity
        return None

    async def read_repair_branch_head(self) -> str:
        result = await self._call(
            GET_COMMIT,
            {
                "owner": self.owner,
                "repo": self.repository,
                "sha": self.repair_branch,
                "detail": "none",
            },
        )
        sha = _find_value(_decode_nested_json(_json_object(result)), {"sha"})
        if not isinstance(sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", sha
        ):
            raise PublishBrokerError("recovery_commit_identity_missing")
        return sha

    async def recover_existing_publish(
        self,
    ) -> tuple[str, int, str, str] | None:
        identity = await self.find_existing_draft_pull_request()
        if identity is None:
            return None
        commit_sha = await self.read_repair_branch_head()
        number, url = identity
        validation_status = await self.verify_draft_pull_request(number)
        return commit_sha, number, url, validation_status

    async def verify_draft_pull_request(self, number: int) -> str:
        result = await self._call(
            PULL_REQUEST_READ,
            {
                "method": "get",
                "owner": self.owner,
                "repo": self.repository,
                "pullNumber": number,
            },
        )
        payload = _json_object(result)
        draft = _find_value(payload, {"draft", "is_draft"})
        if draft is not True:
            raise PublishBrokerError("pull_request_not_draft")

        try:
            status_result = await self._call(
                PULL_REQUEST_READ,
                {
                    "method": "get_status",
                    "owner": self.owner,
                    "repo": self.repository,
                    "pullNumber": number,
                },
            )
            status = _find_value(
                _json_object(status_result),
                {"state", "status"},
            )
        except PublishBrokerError:
            return "pending"
        return str(status)[:100] if status else "pending"
