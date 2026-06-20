from __future__ import annotations

import json
from collections.abc import Callable

from repair_agent.config import Settings
from repair_agent.mcp.interface import McpToolClient
from repair_agent.mcp.read_broker import GitHubReadBroker
from repair_agent.openrouter_client import PlanProvider
from repair_agent.schemas import (
    ReadOnlyRepairPlan,
    RepairPlanRequest,
)
from repair_agent.security import (
    SecurityError,
    normalize_repository_path,
    reject_sensitive_content,
)


class PlanValidationError(RuntimeError):
    pass


class RepairPlanner:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: PlanProvider,
        mcp_client_factory: Callable[[], McpToolClient],
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.mcp_client_factory = mcp_client_factory

    async def create_plan(
        self,
        request: RepairPlanRequest,
    ) -> ReadOnlyRepairPlan:
        self._validate_request(request)
        reader = GitHubReadBroker(
            client=self.mcp_client_factory(),
            owner=request.repository_owner,
            repository=request.repository_name,
            head_sha=request.head_sha,
            allowed_repositories=(
                self.settings.allowed_repositories
            ),
            max_tool_calls=self.settings.max_tool_calls,
            max_files=self.settings.max_files,
            max_bytes=self.settings.max_bytes,
        )

        provider_plan = await self.provider.create_plan(
            request,
            reader,
        )
        candidate = normalize_repository_path(
            request.candidate_file
        )
        if provider_plan.confirmed_failed_file != candidate:
            raise PlanValidationError(
                "Provider changed the confirmed failed file."
            )
        if (
            provider_plan.confirmed_failed_line
            != request.candidate_line
        ):
            raise PlanValidationError(
                "Provider changed the confirmed failed line."
            )
        if candidate not in reader.inspected_files:
            raise PlanValidationError(
                "Provider did not inspect the failed file."
            )
        if len(reader.inspected_files) > self.settings.max_files:
            raise PlanValidationError(
                "Provider inspected too many files."
            )

        for change in provider_plan.proposed_changes:
            path = normalize_repository_path(
                change.file_path
            )
            if path not in reader.inspected_files:
                raise PlanValidationError(
                    "Proposal targets an uninspected file."
                )
            if change.end_line < change.start_line:
                raise PlanValidationError(
                    "Proposal contains an invalid line range."
                )
            if (
                len(change.before_excerpt.splitlines())
                > self.settings.max_excerpt_lines
                or len(change.after_excerpt.splitlines())
                > self.settings.max_excerpt_lines
                or len(change.before_excerpt)
                > self.settings.max_excerpt_chars
                or len(change.after_excerpt)
                > self.settings.max_excerpt_chars
            ):
                raise PlanValidationError(
                    "Proposal excerpt exceeds the configured limit."
                )
            current_content = reader.read_contents.get(path, "")
            if (
                change.before_excerpt.strip()
                and change.before_excerpt.strip()
                not in current_content
            ):
                raise PlanValidationError(
                    "Before excerpt was not found in the inspected file."
                )

        serialized = json.dumps(
            provider_plan.model_dump()
        )
        reject_sensitive_content(serialized)

        return ReadOnlyRepairPlan(
            attempt_id=request.attempt_id,
            status=provider_plan.status,
            model=self.provider.model_name,
            confirmed_failed_file=candidate,
            confirmed_failed_line=request.candidate_line,
            base_sha=request.head_sha,
            inspected_files=reader.inspected_files,
            proposed_changes=provider_plan.proposed_changes,
            risks=provider_plan.risks,
            suggested_validation_commands=(
                provider_plan.suggested_validation_commands
            ),
            manual_review_reason=(
                provider_plan.manual_review_reason
            ),
            github_changes_made=False,
        )

    def _validate_request(
        self,
        request: RepairPlanRequest,
    ) -> None:
        repository = (
            f"{request.repository_owner}/"
            f"{request.repository_name}"
        ).lower()
        if repository not in self.settings.allowed_repositories:
            raise SecurityError("Repository is not allowed.")
        if request.root_cause != "application_defect":
            raise SecurityError("Root cause is not eligible.")
        if request.selected_action != "start_mcp_code_repair":
            raise SecurityError("Repair route is not eligible.")
        if request.confidence < 0.60:
            raise SecurityError("Confidence gate did not pass.")
        normalize_repository_path(request.candidate_file)
        reject_sensitive_content(request.error_message)
        reject_sensitive_content(
            request.sanitized_log_excerpt
        )
