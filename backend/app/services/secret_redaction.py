from __future__ import annotations

import re


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
            r".*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    (
        "github_token",
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    ),
    (
        "openai_key",
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "aws_access_key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ),
    (
        "bearer_token",
        re.compile(
            r"(?i)(authorization\s*[:=]\s*bearer\s+)"
            r"(?!\[REDACTED:)[^\s]+"
        ),
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?i)((?:password|passwd|api[_-]?key|access[_-]?token|"
            r"client[_-]?secret)\s*[:=]\s*)"
            r"(?!\[REDACTED:)[^\s,;]+"
        ),
    ),
    (
        "jwt",
        re.compile(
            r"eyJ[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}"
        ),
    ),
)


def redact_secrets(text: str) -> str:
    redacted = text
    for category, pattern in SECRET_PATTERNS:
        if category in {"bearer_token", "credential_assignment"}:
            redacted = pattern.sub(
                rf"\1[REDACTED:{category}]",
                redacted,
            )
        else:
            redacted = pattern.sub(
                f"[REDACTED:{category}]",
                redacted,
            )
    return redacted


def contains_secret(text: str) -> bool:
    return any(
        pattern.search(text)
        for _, pattern in SECRET_PATTERNS
    )


def bounded_sanitized_text(
    text: str,
    *,
    max_lines: int,
    max_chars: int,
) -> str:
    redacted = redact_secrets(text)
    lines = redacted.splitlines()
    bounded = "\n".join(lines[-max_lines:])
    if len(bounded) > max_chars:
        bounded = bounded[-max_chars:]
    return bounded
