from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RepairConfirmationRequest(BaseModel):
    confirm_read_only: bool


class ProposedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    before_excerpt: str = Field(max_length=8000)
    after_excerpt: str = Field(max_length=8000)
    reason: str = Field(min_length=1, max_length=2000)


class ReadOnlyRepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    status: Literal["planned", "manual_review"]
    mode: Literal["read_only"] = "read_only"
    model: str
    confirmed_failed_file: str
    confirmed_failed_line: int
    base_sha: str
    inspected_files: list[str] = Field(max_length=20)
    proposed_changes: list[ProposedChange] = Field(
        max_length=10
    )
    risks: list[str] = Field(max_length=20)
    suggested_validation_commands: list[str] = Field(
        max_length=20
    )
    manual_review_reason: Optional[str] = None
    github_changes_made: Literal[False] = False


class RepairAttemptSummary(BaseModel):
    attempt_id: str
    eligible: bool
    reason: str
    status: str
    mode: Literal["read_only"] = "read_only"


class RepairPlanRequest(BaseModel):
    attempt_id: str
    repository_owner: str
    repository_name: str
    run_id: int
    head_sha: str
    head_branch: str
    default_branch: Optional[str]
    root_cause: str
    confidence: float
    decision_source: str
    selected_action: str
    error_type: str
    error_message: str
    candidate_file: str
    candidate_line: int
    sanitized_log_excerpt: str
    read_only: Literal[True] = True
