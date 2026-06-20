from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any


PROTECTED_PATH_PARTS = {
    ".env",
    ".git",
    "auth",
    "authentication",
    "credentials",
    "migrations",
    "secrets",
}
PROTECTED_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
}


@dataclass(frozen=True)
class RepairEligibility:
    eligible: bool
    code: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_allowed_repositories(value: str | None) -> set[str]:
    return {
        item.strip().lower()
        for item in (value or "").split(",")
        if item.strip()
    }


def is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or normalized == "unknown"
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        return True

    lower_parts = {part.lower() for part in candidate.parts}
    if lower_parts & PROTECTED_PATH_PARTS:
        return True
    if candidate.suffix.lower() in PROTECTED_SUFFIXES:
        return True
    return False


class RepairEligibilityService:
    def __init__(
        self,
        allowed_repositories: set[str] | None = None,
    ) -> None:
        self.allowed_repositories = (
            allowed_repositories
            if allowed_repositories is not None
            else parse_allowed_repositories(
                os.getenv("GITHUB_ALLOWED_REPOSITORIES")
            )
        )

    def evaluate(
        self,
        *,
        classification: dict[str, Any],
        healing_plan: dict[str, Any],
        source_run: dict[str, Any] | None,
        candidate_file: str,
        candidate_line: int | None = None,
    ) -> RepairEligibility:
        if classification.get("root_cause") != "application_defect":
            return RepairEligibility(
                False,
                "wrong_root_cause",
                "Controlled code repair is only available for application defects.",
            )
        if healing_plan.get("action") != "start_mcp_code_repair":
            return RepairEligibility(
                False,
                "route_not_selected",
                "The healing orchestrator did not select controlled code repair.",
            )
        if healing_plan.get("confidence_gate_applied"):
            return RepairEligibility(
                False,
                "confidence_gate",
                "The model confidence did not pass the repair safety threshold.",
            )
        if not source_run:
            return RepairEligibility(
                False,
                "missing_run_metadata",
                "Verified GitHub Actions run metadata is required.",
            )

        repository = str(
            source_run.get("repository_full_name") or ""
        ).lower()
        if (
            not self.allowed_repositories
            or repository not in self.allowed_repositories
        ):
            return RepairEligibility(
                False,
                "repository_not_allowed",
                "The repository is not enabled for controlled repair.",
            )

        head_sha = str(source_run.get("head_sha") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
            return RepairEligibility(
                False,
                "invalid_failed_sha",
                "An exact 40-character failed commit SHA is required.",
            )
        if not source_run.get("head_branch"):
            return RepairEligibility(
                False,
                "missing_branch",
                "The failed branch is missing from the workflow metadata.",
            )
        if is_protected_path(candidate_file):
            return RepairEligibility(
                False,
                "protected_or_missing_path",
                "The failed source path is missing or protected.",
            )
        if candidate_line is None or candidate_line < 1:
            return RepairEligibility(
                False,
                "missing_failed_line",
                "A confirmed positive failed line is required.",
            )

        return RepairEligibility(
            True,
            "eligible",
            "Read-only controlled repair planning is available.",
        )
