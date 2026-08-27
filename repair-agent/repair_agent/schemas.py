from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepairPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    repository_owner: str
    repository_name: str
    run_id: int = Field(gt=0)
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    head_branch: str
    default_branch: str | None = None
    root_cause: str
    confidence: float = Field(ge=0, le=1)
    decision_source: str
    selected_action: str
    error_type: str
    error_message: str = Field(max_length=1000)
    candidate_file: str
    candidate_line: int = Field(ge=1)
    related_test_files: list[str] = Field(
        default_factory=list,
        max_length=3,
    )
    sanitized_log_excerpt: str = Field(max_length=12000)
    read_only: Literal[True] = True


class ProviderProposedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    before_excerpt: str = Field(max_length=8000)
    after_excerpt: str = Field(max_length=8000)
    reason: str = Field(min_length=1, max_length=2000)


class ProviderRepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause_confirmed: bool
    repairable: bool
    confirmed_failed_file: str
    confirmed_failed_line: int
    inspected_files: list[str] = Field(max_length=4)
    proposed_changes: list[ProviderProposedChange]
    risks: list[str]
    suggested_validation_commands: list[str]
    manual_review_reason: str | None
    github_changes_made: Literal[False]


class ReadOnlyRepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    status: Literal["planned", "manual_review"]
    mode: Literal["read_only"] = "read_only"
    model: str
    root_cause_confirmed: bool
    repairable: bool
    confirmed_failed_file: str
    confirmed_failed_line: int
    base_sha: str
    inspected_files: list[str]
    proposed_changes: list[ProviderProposedChange]
    risks: list[str]
    suggested_validation_commands: list[str]
    manual_review_reason: str | None = None
    github_changes_made: Literal[False] = False


class EvidenceExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str


class PlanEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: EvidenceExcerpt
    related_tests: list[EvidenceExcerpt] = Field(max_length=3)


class RepairPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    repository_owner: str
    repository_name: str
    run_id: int = Field(gt=0)
    run_url: str = Field(max_length=1000)
    base_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    failed_branch: str = Field(min_length=1, max_length=255)
    default_branch: str | None = None
    root_cause: Literal["application_defect"]
    confidence: float = Field(ge=0, le=1)
    decision_source: str
    selected_action: Literal["start_mcp_code_repair"]
    error_type: str = Field(min_length=1, max_length=200)
    confirmed_failed_file: str
    confirmed_failed_line: int = Field(ge=1)
    inspected_files: list[str] = Field(max_length=20)
    proposed_changes: list[ProviderProposedChange] = Field(
        min_length=1,
        max_length=10,
    )
    risks: list[str] = Field(max_length=20)
    suggested_validation_commands: list[str] = Field(max_length=20)
    phase1_correlation_id: str = Field(min_length=1, max_length=64)
    recovery_only: bool = False


class RepairPublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    publish_status: Literal["draft_pr_created"]
    validation_status: str
    repair_branch: str = Field(pattern=r"^auto-heal/[a-z0-9-]+$")
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    draft_pr_number: int = Field(gt=0)
    draft_pr_url: str = Field(min_length=1, max_length=1000)
    changed_files: list[str] = Field(min_length=1, max_length=10)
    github_changes_made: Literal[True]
    automatic_merge_performed: Literal[False]
    message: Literal["Draft PR created — awaiting developer review"]
    merge_message: Literal["No automatic merge performed"]
