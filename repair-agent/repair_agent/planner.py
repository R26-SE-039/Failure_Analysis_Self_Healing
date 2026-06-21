from __future__ import annotations

import json
from collections.abc import Callable

from repair_agent.config import Settings
from repair_agent.diagnostics import log_stage
from repair_agent.mcp.interface import McpToolClient
from repair_agent.mcp.github_remote import McpDecodeError
from repair_agent.mcp.read_broker import GitHubReadBroker
from repair_agent.openrouter_client import PlanProvider
from repair_agent.schemas import (
    EvidenceExcerpt,
    PlanEvidence,
    ReadOnlyRepairPlan,
    RepairPlanRequest,
)
from repair_agent.security import (
    SecurityError,
    normalize_repository_path,
    reject_sensitive_content,
)


class PlanValidationError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class McpReadFailed(RuntimeError):
    def __init__(self, code: str = "mcp_read_failed") -> None:
        super().__init__(code)
        self.code = code


class RepairPlanner:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: PlanProvider,
        mcp_client_factory: Callable[[], McpToolClient],
        allow_search_fallback: bool = True,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.mcp_client_factory = mcp_client_factory
        self.allow_search_fallback = allow_search_fallback

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

        candidate = normalize_repository_path(
            request.candidate_file
        )
        log_stage("mcp_candidate_read_started", "started")
        try:
            try:
                candidate_content = await reader.read_file(candidate)
            except Exception:
                if not self.allow_search_fallback:
                    raise
                resolved = await reader.find_candidate_path(
                    candidate
                )
                if not resolved:
                    raise
                candidate = resolved
                candidate_content = await reader.read_file(
                    candidate
                )
        except McpDecodeError as error:
            log_stage(
                "mcp_candidate_read_completed",
                "failed",
                exception_class=type(error).__name__,
                error_code="mcp_decode_failed",
            )
            raise McpReadFailed("mcp_decode_failed") from error
        except Exception as error:
            log_stage(
                "mcp_candidate_read_completed",
                "failed",
                exception_class=type(error).__name__,
                error_code="mcp_read_failed",
            )
            raise McpReadFailed() from error
        log_stage("mcp_candidate_read_completed", "completed")

        try:
            candidate_excerpt = self._bounded_excerpt(
                candidate,
                candidate_content,
                request.candidate_line,
            )
            related_excerpts = []
            for path in request.related_test_files:
                normalized = normalize_repository_path(path)
                content = await reader.read_file(normalized)
                related_excerpts.append(
                    self._bounded_excerpt(
                        normalized,
                        content,
                        1,
                    )
                )
        except Exception as error:
            log_stage(
                "bounded_evidence_created",
                "failed",
                exception_class=type(error).__name__,
                error_code="mcp_decode_failed",
            )
            raise McpReadFailed("mcp_decode_failed") from error

        evidence = PlanEvidence(
            candidate=candidate_excerpt,
            related_tests=related_excerpts,
        )
        log_stage("bounded_evidence_created", "completed")
        provider_plan = await self.provider.create_plan(
            request,
            evidence,
        )
        if provider_plan.confirmed_failed_file != candidate:
            raise PlanValidationError("confirmed_file_mismatch")
        if (
            provider_plan.confirmed_failed_line
            != request.candidate_line
        ):
            raise PlanValidationError("confirmed_line_mismatch")
        if candidate not in reader.inspected_files:
            raise PlanValidationError("candidate_not_inspected")
        if len(reader.inspected_files) > self.settings.max_files:
            raise PlanValidationError("file_limit_exceeded")
        if set(provider_plan.inspected_files) != set(
            reader.inspected_files
        ):
            raise PlanValidationError("inspected_files_mismatch")
        if provider_plan.github_changes_made is not False:
            raise PlanValidationError("github_changes_reported")
        if (
            provider_plan.repairable
            and not provider_plan.proposed_changes
        ):
            raise PlanValidationError("repairable_change_missing")
        if (
            not provider_plan.repairable
            and provider_plan.proposed_changes
        ):
            raise PlanValidationError("manual_review_change_present")
        if (
            not provider_plan.repairable
            and not provider_plan.manual_review_reason
        ):
            raise PlanValidationError("manual_review_reason_missing")

        for change in provider_plan.proposed_changes:
            path = normalize_repository_path(
                change.file_path
            )
            if path not in reader.inspected_files:
                raise PlanValidationError("uninspected_change_target")
            if change.end_line < change.start_line:
                raise PlanValidationError("invalid_change_line_range")
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
                raise PlanValidationError("proposal_excerpt_limit")
            current_content = reader.read_contents.get(path, "")
            if (
                change.before_excerpt.strip()
                and change.before_excerpt.strip()
                not in current_content
            ):
                raise PlanValidationError("before_excerpt_mismatch")

        serialized = json.dumps(
            provider_plan.model_dump()
        )
        reject_sensitive_content(serialized)

        return ReadOnlyRepairPlan(
            attempt_id=request.attempt_id,
            status=(
                "planned"
                if provider_plan.repairable
                else "manual_review"
            ),
            model=self.provider.model_name,
            root_cause_confirmed=(
                provider_plan.root_cause_confirmed
            ),
            repairable=provider_plan.repairable,
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

    def _bounded_excerpt(
        self,
        path: str,
        content: str,
        line_number: int,
    ) -> EvidenceExcerpt:
        lines = content.splitlines()
        if not lines or line_number > len(lines):
            raise McpReadFailed()

        line_limit = self.settings.max_excerpt_lines
        max_chars = self.settings.max_excerpt_chars
        candidate_index = line_number - 1
        selected = {
            candidate_index: lines[candidate_index][:max_chars]
        }
        distance = 1
        while len(selected) < line_limit:
            added = False
            for index in (
                candidate_index - distance,
                candidate_index + distance,
            ):
                if index < 0 or index >= len(lines):
                    continue
                proposed = dict(selected)
                proposed[index] = lines[index]
                text = "\n".join(
                    proposed[key]
                    for key in sorted(proposed)
                )
                if len(text) <= max_chars:
                    selected = proposed
                    added = True
                if len(selected) >= line_limit:
                    break
            if not added and (
                candidate_index - distance < 0
                and candidate_index + distance >= len(lines)
            ):
                break
            if (
                candidate_index - distance < 0
                and candidate_index + distance >= len(lines)
            ):
                break
            distance += 1
        ordered_indexes = sorted(selected)
        excerpt = "\n".join(
            selected[index]
            for index in ordered_indexes
        )
        reject_sensitive_content(excerpt)
        return EvidenceExcerpt(
            file_path=path,
            start_line=ordered_indexes[0] + 1,
            end_line=ordered_indexes[-1] + 1,
            content=excerpt,
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
        for path in request.related_test_files:
            normalize_repository_path(path)
        reject_sensitive_content(request.error_message)
        reject_sensitive_content(
            request.sanitized_log_excerpt
        )
