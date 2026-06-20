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

    status: Literal["planned", "manual_review"]
    confirmed_failed_file: str
    confirmed_failed_line: int
    proposed_changes: list[ProviderProposedChange]
    risks: list[str]
    suggested_validation_commands: list[str]
    manual_review_reason: str | None = None


class ReadOnlyRepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    status: Literal["planned", "manual_review"]
    mode: Literal["read_only"] = "read_only"
    model: str
    confirmed_failed_file: str
    confirmed_failed_line: int
    base_sha: str
    inspected_files: list[str]
    proposed_changes: list[ProviderProposedChange]
    risks: list[str]
    suggested_validation_commands: list[str]
    manual_review_reason: str | None = None
    github_changes_made: Literal[False] = False
