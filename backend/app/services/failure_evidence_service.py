from __future__ import annotations

import hashlib
import re
from typing import Any, Optional


ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)[^\s]+"),
    re.compile(r"(?i)((?:token|secret|password|passwd|api[_-]?key)\s*[:=]\s*)[^\s]+"),
]
ERROR_LINE_PATTERN = re.compile(
    r"(?i)\b(error|failed|failure|exception|traceback|assertion|panic|fatal)\b"
)
ERROR_TYPE_PATTERN = re.compile(
    r"\b(?P<type>[A-Za-z_][\w.]*(?:Error|Exception)|AssertionError|Error|panic|fatal):\s*(?P<message>.+)"
)
PYTHON_FILE_PATTERN = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)')
SOURCE_FILE_PATTERN = re.compile(
    r"(?P<file>(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+\.(?:py|js|jsx|ts|tsx|java|cs|go|rb|php|rs|kt|feature)):(?P<line>\d+)(?::\d+)?"
)
MAVEN_COMPILER_DIAGNOSTIC_PATTERN = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}T\S+Z\s+)?(?:\[[A-Z]+\]\s*)?(?P<file>(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+\.java):\[(?P<line>\d+),(?P<column>\d+)\]\s*(?P<message>.+?)\s*$"
)
STACK_LINE_PATTERN = re.compile(
    r"(^\s+at\s+.+:\d+:\d+\)?$|^\s*File \".+\", line \d+|^Traceback \(most recent call last\):|\b[A-Za-z_][\w.]*(?:Error|Exception):)"
)

MAX_EVIDENCE_CHARS = 12000
MAX_STACK_TRACE_CHARS = 6000
CONTEXT_LINES = 4
REDACTION_TEXT = "[REDACTED]"


def decode_log_content(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def sanitize_log_text(log_text: str) -> str:
    normalized = log_text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = ANSI_ESCAPE_PATTERN.sub("", normalized)
    sanitized = stripped
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(lambda match: _redact_match(match), sanitized)
    return sanitized


def _redact_match(match: re.Match[str]) -> str:
    if match.lastindex:
        return f"{match.group(1)}{REDACTION_TEXT}"
    return REDACTION_TEXT


def build_failure_evidence(
    *,
    log_text: str,
    job_name: Optional[str],
    failed_steps: list[dict[str, Any]],
    repository_name: Optional[str] = None,
) -> dict[str, Any]:
    sanitized = sanitize_log_text(log_text)
    excerpt = _select_failure_excerpt(sanitized)
    stack_trace = _extract_stack_trace(sanitized)
    error_type, error_message = _extract_error(sanitized)
    failure_stage = _extract_failure_stage(sanitized)
    candidate_file, candidate_line = _extract_candidate_location(
        sanitized,
        repository_name=repository_name,
    )

    return {
        "job_name": job_name,
        "failed_step_names": [
            step.get("name") for step in failed_steps if step.get("name")
        ],
        "error_type": error_type,
        "error_message": error_message,
        "candidate_file": candidate_file,
        "candidate_line": candidate_line,
        "failure_stage": failure_stage,
        "stack_trace": stack_trace,
        "sanitized_log_excerpt": excerpt,
        "evidence_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
    }


def _select_failure_excerpt(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return ""

    indexes = [
        index for index, line in enumerate(lines)
        if ERROR_LINE_PATTERN.search(line)
    ]
    if not indexes:
        return _bound_text("\n".join(lines))

    selected_indexes: set[int] = set()
    for index in indexes[:20]:
        start = max(0, index - CONTEXT_LINES)
        end = min(len(lines), index + CONTEXT_LINES + 1)
        selected_indexes.update(range(start, end))

    ordered_lines = [lines[index] for index in sorted(selected_indexes)]
    return _bound_text("\n".join(ordered_lines))


def _extract_stack_trace(text: str) -> Optional[str]:
    lines = text.split("\n")
    selected = [line for line in lines if STACK_LINE_PATTERN.search(line)]
    if not selected:
        return None
    return _bound_text("\n".join(selected), MAX_STACK_TRACE_CHARS)


def _extract_error(text: str) -> tuple[Optional[str], Optional[str]]:
    compiler_error = _extract_maven_compiler_error(text)
    if compiler_error:
        return compiler_error

    for line in text.split("\n"):
        match = ERROR_TYPE_PATTERN.search(line.strip())
        if match:
            message = match.group("message").strip() or None
            return match.group("type"), message
    for line in text.split("\n"):
        if ERROR_LINE_PATTERN.search(line):
            value = line.strip()
            return None, value or None
    return None, None


def _extract_maven_compiler_error(text: str) -> Optional[tuple[str, str]]:
    for line in text.split("\n"):
        match = MAVEN_COMPILER_DIAGNOSTIC_PATTERN.search(line.strip())
        if match:
            message = match.group("message").strip()
            if message:
                return "CompilationError", message
    return None


def _extract_failure_stage(text: str) -> Optional[str]:
    for line in text.split("\n"):
        if MAVEN_COMPILER_DIAGNOSTIC_PATTERN.search(line.strip()):
            return "compile"
    return None


def _extract_candidate_location(
    text: str,
    *,
    repository_name: Optional[str] = None,
) -> tuple[Optional[str], Optional[int]]:
    compiler_location = _extract_maven_compiler_location(
        text,
        repository_name=repository_name,
    )
    if compiler_location:
        return compiler_location

    for pattern in (PYTHON_FILE_PATTERN, SOURCE_FILE_PATTERN):
        for match in pattern.finditer(text):
            candidate_file = _normalize_candidate_file_path(
                match.group("file").strip(),
                repository_name=repository_name,
            )
            line_value = int(match.group("line"))
            if line_value <= 0 or candidate_file is None:
                continue
            if _is_probable_dependency_path(candidate_file):
                continue
            return candidate_file, line_value
    return None, None


def _extract_maven_compiler_location(
    text: str,
    *,
    repository_name: Optional[str] = None,
) -> Optional[tuple[str, int]]:
    for line in text.split("\n"):
        match = MAVEN_COMPILER_DIAGNOSTIC_PATTERN.search(line.strip())
        if not match:
            continue
        candidate_file = _normalize_candidate_file_path(
            match.group("file").strip(),
            repository_name=repository_name,
        )
        line_value = int(match.group("line"))
        if line_value <= 0 or candidate_file is None:
            continue
        if _is_probable_dependency_path(candidate_file):
            continue
        return candidate_file, line_value
    return None


def _normalize_candidate_file_path(
    path: str,
    *,
    repository_name: Optional[str] = None,
) -> Optional[str]:
    normalized = path.replace("\\", "/").strip().strip('"').strip("'")
    if not normalized:
        return None

    relative_path = _github_runner_relative_path(
        normalized,
        repository_name=repository_name,
    )
    if relative_path is None and _is_relative_repository_path(normalized):
        relative_path = normalized

    if relative_path is None:
        return None
    relative_path = relative_path.replace("\\", "/").strip()
    if not _is_relative_repository_path(relative_path):
        return None
    return relative_path


def _github_runner_relative_path(
    path: str,
    *,
    repository_name: Optional[str] = None,
) -> Optional[str]:
    repo = (repository_name or "").strip()
    if not repo or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return None

    escaped_repo = re.escape(repo)
    patterns = (
        rf"^/home/runner/work/{escaped_repo}/{escaped_repo}/(?P<relative>.+)$",
        rf"^[A-Za-z]:/a/{escaped_repo}/{escaped_repo}/(?P<relative>.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, path, flags=re.IGNORECASE)
        if match:
            return match.group("relative")
    return None


def _is_relative_repository_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if (
        not normalized
        or normalized.startswith("/")
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z]:/", normalized)
    ):
        return False
    parts = normalized.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _is_probable_dependency_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return any(
        part in normalized
        for part in (
            "node_modules/",
            "site-packages/",
            ".venv/",
            "venv/",
            "__pycache__/",
        )
    )


def _bound_text(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"
