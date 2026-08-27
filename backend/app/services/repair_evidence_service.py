from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from app.services.secret_redaction import redact_secrets


@dataclass(frozen=True)
class RepairEvidence:
    log_content_sha256: str
    sanitized_log_excerpt: str
    error_type: str
    error_message: str
    candidate_file: str
    candidate_line: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepairEvidenceService:
    def __init__(
        self,
        *,
        max_excerpt_lines: int = 40,
        max_excerpt_chars: int = 8000,
    ) -> None:
        self.max_excerpt_lines = max_excerpt_lines
        self.max_excerpt_chars = max_excerpt_chars

    def extract(
        self,
        raw_log: str,
        detected_error: dict[str, Any],
    ) -> RepairEvidence:
        error_type = redact_secrets(
            str(
                detected_error.get("error_type")
                or "UnknownError"
            )
        )
        error_message = redact_secrets(
            str(detected_error.get("error_message") or "")
        )[:1000]
        candidate_file = redact_secrets(
            str(
                detected_error.get("failed_file")
                or "unknown"
            )
        ).replace("\\", "/")
        candidate_line = self._line_number(
            detected_error.get("failed_line")
        )

        redacted_lines = [
            redact_secrets(line)
            for line in raw_log.splitlines()
        ]
        needles = [
            value.lower()
            for value in (
                error_type,
                candidate_file
                if candidate_file != "unknown"
                else "",
            )
            if value
        ]
        selected_indexes: set[int] = set()
        for index, line in enumerate(redacted_lines):
            lower_line = line.lower()
            if any(needle in lower_line for needle in needles):
                selected_indexes.update(
                    range(
                        max(0, index - 3),
                        min(len(redacted_lines), index + 4),
                    )
                )

        if selected_indexes:
            excerpt_lines = [
                redacted_lines[index]
                for index in sorted(selected_indexes)
            ]
        else:
            excerpt_lines = redacted_lines[
                -self.max_excerpt_lines:
            ]

        excerpt = "\n".join(
            excerpt_lines[-self.max_excerpt_lines:]
        )
        if len(excerpt) > self.max_excerpt_chars:
            excerpt = excerpt[-self.max_excerpt_chars:]

        return RepairEvidence(
            log_content_sha256=hashlib.sha256(
                raw_log.encode("utf-8")
            ).hexdigest(),
            sanitized_log_excerpt=excerpt,
            error_type=error_type,
            error_message=error_message,
            candidate_file=candidate_file,
            candidate_line=candidate_line,
        )

    @staticmethod
    def _line_number(value: Any) -> int | None:
        try:
            line = int(value)
        except (TypeError, ValueError):
            return None
        return line if line > 0 else None


repair_evidence_service = RepairEvidenceService()
