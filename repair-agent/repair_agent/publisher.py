from __future__ import annotations

import re
from collections import defaultdict
from typing import Callable

from repair_agent.config import PublishSettings
from repair_agent.mcp.interface import McpToolClient
from repair_agent.mcp.publish_broker import (
    GitHubPublishBroker,
    PublishBrokerError,
)
from repair_agent.schemas import (
    ProviderProposedChange,
    RepairPublishRequest,
    RepairPublishResult,
)
from repair_agent.security import reject_sensitive_content


BRANCH_HEAD_MISMATCH_MESSAGE = (
    "Cannot auto-publish because the failed branch has moved since "
    "the failed workflow run. Please rerun diagnosis on the latest "
    "failing commit or review manually."
)


class RepairPublishFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        safe_message: str = "Controlled repair publishing failed.",
        state: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.safe_message = safe_message
        self.state = state or {}


def safe_branch_name(attempt_id: str, description: str) -> str:
    attempt = re.sub(r"[^a-z0-9]", "", attempt_id.lower())
    attempt = re.sub(r"^repair", "", attempt)[:6] or "repair"
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")
    slug = slug[:40].strip("-") or "application-defect"
    return f"auto-heal/repair-{attempt}-{slug}"


def apply_approved_changes(
    content: str,
    changes: list[ProviderProposedChange],
) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    trailing_newline = content.endswith(("\n", "\r"))
    lines = content.splitlines()
    for change in sorted(
        changes,
        key=lambda item: item.start_line,
        reverse=True,
    ):
        start = change.start_line - 1
        end = change.end_line
        if start < 0 or end > len(lines) or end <= start:
            raise RepairPublishFailure("approved_change_range_invalid")
        before_lines = change.before_excerpt.splitlines()
        if lines[start:end] != before_lines:
            raise RepairPublishFailure(
                "before_excerpt_mismatch",
                safe_message=(
                    "The approved source excerpt no longer matches the "
                    "failed commit. Manual review is required."
                ),
            )
        lines[start:end] = change.after_excerpt.splitlines()
    result = newline.join(lines)
    if trailing_newline:
        result += newline
    reject_sensitive_content(result)
    return result


class RepairPublisher:
    def __init__(
        self,
        *,
        settings: PublishSettings,
        mcp_client_factory: Callable[[], McpToolClient],
    ) -> None:
        self.settings = settings
        self.mcp_client_factory = mcp_client_factory

    async def publish(
        self,
        request: RepairPublishRequest,
    ) -> RepairPublishResult:
        if request.root_cause != "application_defect":
            raise RepairPublishFailure("publish_safety_failed")
        if request.selected_action != "start_mcp_code_repair":
            raise RepairPublishFailure("publish_safety_failed")
        if (
            request.decision_source == "machine_learning"
            and request.confidence < 0.60
        ):
            raise RepairPublishFailure("publish_safety_failed")

        changes_by_file: dict[str, list[ProviderProposedChange]] = defaultdict(list)
        for change in request.proposed_changes:
            changes_by_file[change.file_path].append(change)
        approved_paths = set(changes_by_file)
        if len(approved_paths) > self.settings.max_files:
            raise RepairPublishFailure("changed_file_limit_exceeded")
        if request.confirmed_failed_file not in request.inspected_files:
            raise RepairPublishFailure("changed_file_mismatch")
        if any(path not in request.inspected_files for path in approved_paths):
            raise RepairPublishFailure("changed_file_mismatch")

        branch = safe_branch_name(request.attempt_id, request.error_type)
        state: dict[str, object] = {
            "publish_status": "validating",
            "validation_status": "pending",
            "repair_branch": None,
            "commit_sha": None,
            "draft_pr_number": None,
            "draft_pr_url": None,
            "changed_files": sorted(approved_paths),
            "github_changes_made": False,
            "branch_created": False,
            "commit_created": False,
            "pr_created": False,
        }
        broker = GitHubPublishBroker(
            client=self.mcp_client_factory(),
            owner=request.repository_owner,
            repository=request.repository_name,
            base_sha=request.base_sha,
            failed_branch=request.failed_branch,
            repair_branch=branch,
            approved_paths=approved_paths,
            allowed_repositories=self.settings.allowed_repositories,
            max_tool_calls=self.settings.max_tool_calls,
            max_files=self.settings.max_files,
            max_bytes=self.settings.max_bytes,
        )

        try:
            recovered = await broker.recover_existing_publish()
            if recovered is not None:
                commit_sha, pr_number, pr_url, validation_status = recovered
                return RepairPublishResult(
                    attempt_id=request.attempt_id,
                    publish_status="draft_pr_created",
                    validation_status=validation_status,
                    repair_branch=branch,
                    commit_sha=commit_sha,
                    draft_pr_number=pr_number,
                    draft_pr_url=pr_url,
                    changed_files=sorted(approved_paths),
                    github_changes_made=True,
                    automatic_merge_performed=False,
                    message="Draft PR created — awaiting developer review",
                    merge_message="No automatic merge performed",
                )
            if request.recovery_only:
                commit_sha = await broker.read_repair_branch_head()
                state.update(
                    {
                        "repair_branch": branch,
                        "commit_sha": commit_sha,
                        "publish_status": "partial_manual_review",
                        "validation_status": "manual_review",
                        "github_changes_made": True,
                        "branch_created": True,
                        "commit_created": True,
                        "pr_created": False,
                    }
                )
                raise RepairPublishFailure(
                    "publish_partial_manual_review_required",
                    safe_message=(
                        "The repair branch and commit exist, but the draft "
                        "pull request could not be recovered. Manual review "
                        "is required."
                    ),
                    state=state,
                )

            await broker.verify_failed_branch_head()
            files = []
            for path in sorted(approved_paths):
                source = await broker.read_approved_file(path)
                updated = apply_approved_changes(
                    source,
                    changes_by_file[path],
                )
                files.append({"path": path, "content": updated})

            await broker.create_repair_branch()
            state["repair_branch"] = branch
            state["github_changes_made"] = True
            state["branch_created"] = True
            state["publish_status"] = "branch_created"

            commit_message = self._commit_message(request)
            commit_sha = await broker.push_approved_files(
                files,
                commit_message,
            )
            state["commit_sha"] = commit_sha
            state["publish_status"] = "commit_created"
            state["commit_created"] = True

            pr_number, pr_url = await broker.create_draft_pull_request(
                title=(
                    "[Auto-Heal] Fix application defect in "
                    f"{request.confirmed_failed_file}"
                ),
                body=self._pull_request_body(request, sorted(approved_paths)),
            )
            state["draft_pr_number"] = pr_number
            state["draft_pr_url"] = pr_url
            state["publish_status"] = "draft_pr_created"
            state["pr_created"] = True
            validation_status = await broker.verify_draft_pull_request(
                pr_number
            )
            state["validation_status"] = validation_status
        except PublishBrokerError as error:
            if error.code == "created_branch_sha_mismatch":
                state["repair_branch"] = branch
                state["publish_status"] = "branch_created_sha_mismatch"
                state["github_changes_made"] = True
                state["branch_created"] = True
            error_code = error.code
            if error.code == "draft_pr_identity_missing":
                error_code = "publish_partial_manual_review_required"
                state.update(
                    {
                        "publish_status": "partial_manual_review",
                        "validation_status": "manual_review",
                        "branch_created": True,
                        "commit_created": True,
                        "pr_created": False,
                        "github_changes_made": True,
                    }
                )
            message = (
                BRANCH_HEAD_MISMATCH_MESSAGE
                if error.code == "branch_head_mismatch"
                else "Controlled repair publishing failed."
            )
            raise RepairPublishFailure(
                error_code,
                safe_message=message,
                state=state,
            ) from error
        except RepairPublishFailure as error:
            error.state.update(state)
            raise

        return RepairPublishResult(
            attempt_id=request.attempt_id,
            publish_status="draft_pr_created",
            validation_status=str(state["validation_status"]),
            repair_branch=branch,
            commit_sha=str(state["commit_sha"]),
            draft_pr_number=int(state["draft_pr_number"]),
            draft_pr_url=str(state["draft_pr_url"]),
            changed_files=sorted(approved_paths),
            github_changes_made=True,
            automatic_merge_performed=False,
            message="Draft PR created — awaiting developer review",
            merge_message="No automatic merge performed",
        )

    @staticmethod
    def _commit_message(request: RepairPublishRequest) -> str:
        return (
            "fix: auto-heal application defect in "
            f"{request.confirmed_failed_file}\n\n"
            f"Repair attempt: {request.attempt_id}\n"
            f"Original GitHub Actions run: {request.run_id}\n"
            f"Original failed SHA: {request.base_sha}\n"
            f"Root cause: {request.root_cause}\n"
            "Generated-by: failure-analysis-self-healing\n"
            "Developer review is required before merge."
        )

    @staticmethod
    def _pull_request_body(
        request: RepairPublishRequest,
        changed_files: list[str],
    ) -> str:
        inspected = "\n".join(f"- `{path}`" for path in request.inspected_files)
        changed = "\n".join(f"- `{path}`" for path in changed_files)
        summaries = "\n".join(
            f"- `{change.file_path}:{change.start_line}-{change.end_line}`: "
            f"{change.reason}"
            for change in request.proposed_changes
        )
        commands = "\n".join(
            f"- `{command}`"
            for command in request.suggested_validation_commands
        ) or "- None supplied"
        return (
            "## Controlled Repair\n"
            f"Root cause: `{request.root_cause}`\n\n"
            f"Confidence: `{request.confidence * 100:.2f}%`\n\n"
            f"Failed workflow run: {request.run_url}\n\n"
            f"Failed SHA: `{request.base_sha}`\n\n"
            "### Inspected files\n"
            f"{inspected}\n\n"
            "### Changed files\n"
            f"{changed}\n\n"
            "### Approved before/after summary\n"
            f"{summaries}\n\n"
            "### Suggested validation commands\n"
            f"{commands}\n\n"
            "### Safety checks passed\n"
            "- Stored Phase 1 plan revalidated server-side\n"
            "- Failed branch head matched the failed SHA\n"
            "- Protected paths and direct branch writes rejected\n"
            "- One commit created on an `auto-heal/` branch\n\n"
            "This PR was generated as a draft and must be reviewed by a "
            "developer before merge."
        )
