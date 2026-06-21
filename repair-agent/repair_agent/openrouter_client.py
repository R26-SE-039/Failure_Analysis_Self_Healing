from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, Protocol

import httpx
from pydantic import ValidationError

from repair_agent.config import Settings
from repair_agent.diagnostics import log_stage
from repair_agent.schemas import (
    PlanEvidence,
    ProviderRepairPlan,
    RepairPlanRequest,
)
from repair_agent.security import (
    SYSTEM_INSTRUCTIONS,
    reject_sensitive_content,
)


class PlanProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        upstream_http_status: int | None = None,
        retry_after: str | None = None,
        validation_errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.upstream_http_status = upstream_http_status
        self.retry_after = retry_after
        self.validation_errors = validation_errors or []


class StructuredOutputError(PlanProviderError):
    def __init__(
        self,
        validation_errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(
            "structured_output_invalid",
            validation_errors=validation_errors,
        )


class StructuredOutputMissing(PlanProviderError):
    def __init__(
        self,
        validation_errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(
            "structured_output_missing",
            validation_errors=validation_errors,
        )


class PlanProvider(Protocol):
    @property
    def model_name(self) -> str:
        ...

    async def create_plan(
        self,
        request: RepairPlanRequest,
        evidence: PlanEvidence,
    ) -> ProviderRepairPlan:
        ...


def _retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (retry_at - datetime.now(timezone.utc)).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _safe_provider_validation_errors(
    error: ValidationError,
) -> list[dict[str, object]]:
    known_fields = set(ProviderRepairPlan.model_fields)
    diagnostics = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = []
        for part in item.get("loc", ()):
            if isinstance(part, int):
                location.append(part)
            elif isinstance(part, str):
                location.append(
                    part if part in known_fields else "nested_field"
                )
        diagnostics.append(
            {
                "location": location,
                "type": str(item.get("type", "validation_error"))[:100],
            }
        )
    return diagnostics


def _normalize_json_content(content: str) -> object:
    stripped = content.strip()
    if not stripped:
        raise StructuredOutputMissing()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) < 3 or not lines[-1].strip() == "```":
            raise StructuredOutputError(
                [{"location": [], "type": "fence_invalid"}]
            )
        opening = lines[0].strip().lower()
        if opening not in {"```", "```json"}:
            raise StructuredOutputError(
                [{"location": [], "type": "fence_invalid"}]
            )
        stripped = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as error:
        if "```json" in stripped.lower():
            error_type = "prose_wrapped_json_fence"
        elif stripped.startswith("<|"):
            error_type = "provider_channel_markup"
        elif not stripped.startswith(("{", "[")):
            error_type = (
                "json_leading_content"
                if "{" in stripped or "[" in stripped
                else "json_non_json_content"
            )
        else:
            try:
                _, end = json.JSONDecoder().raw_decode(stripped)
            except json.JSONDecodeError:
                error_type = (
                    "json_truncated"
                    if error.pos >= max(0, len(stripped) - 2)
                    or error.msg.startswith("Unterminated")
                    else "json_syntax_invalid"
                )
            else:
                error_type = (
                    "json_trailing_content"
                    if stripped[end:].strip()
                    else "json_syntax_invalid"
                )
        raise StructuredOutputError(
            [{"location": [], "type": error_type}]
        ) from error


def _missing_output_diagnostics(
    message: dict[str, object],
) -> list[dict[str, object]]:
    if message.get("refusal"):
        error_type = "provider_refusal"
    else:
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            try:
                candidate = _normalize_json_content(reasoning)
                ProviderRepairPlan.model_validate(candidate)
            except (PlanProviderError, ValidationError):
                error_type = "reasoning_only_output"
            else:
                error_type = "structured_json_in_reasoning"
        elif message.get("reasoning_details"):
            error_type = "reasoning_only_output"
        else:
            error_type = "final_content_missing"
    return [{"location": [], "type": error_type}]


class OpenRouterPlanProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 2,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.sleep = sleep
        self.max_attempts = max(1, min(max_attempts, 2))

    @property
    def model_name(self) -> str:
        return self.settings.openrouter_model

    async def create_plan(
        self,
        request: RepairPlanRequest,
        evidence: PlanEvidence,
    ) -> ProviderRepairPlan:
        context = {
            "repository": {
                "owner": request.repository_owner,
                "name": request.repository_name,
                "failed_sha": request.head_sha,
                "failed_branch": request.head_branch,
            },
            "root_cause": request.root_cause,
            "error_type": request.error_type,
            "error_message": request.error_message,
            "candidate_file": evidence.candidate.file_path,
            "candidate_line": request.candidate_line,
            "candidate_source_excerpt": (
                evidence.candidate.model_dump()
            ),
            "related_test_excerpts": [
                item.model_dump()
                for item in evidence.related_tests
            ],
            "task": (
                "Propose the smallest safe read-only change. "
                "Use only inspected file paths and exact bounded excerpts."
            ),
        }
        prompt = json.dumps(context, separators=(",", ":"))
        reject_sensitive_content(prompt)

        provider_routing: dict[str, object] = {
            "require_parameters": True,
        }
        if self.settings.openrouter_provider:
            provider_routing["only"] = [
                self.settings.openrouter_provider
            ]

        body = {
            "model": self.settings.openrouter_model,
            "provider": provider_routing,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_INSTRUCTIONS,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0,
            "max_tokens": 8192,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "read_only_repair_plan",
                    "strict": True,
                    "schema": (
                        ProviderRepairPlan.model_json_schema()
                    ),
                },
            },
        }

        response = await self._request_with_one_retry(body)
        log_stage("structured_output_received", "completed")
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise StructuredOutputMissing() from error

        if choice.get("finish_reason") == "length":
            raise StructuredOutputError(
                [{"location": [], "type": "output_truncated"}]
            )

        structured = message.get("parsed")
        if structured is None:
            structured = payload.get("parsed")
        if structured is None:
            content = message.get("content")
            if not isinstance(content, str):
                raise StructuredOutputMissing(
                    _missing_output_diagnostics(message)
                )
            if not content.strip():
                raise StructuredOutputMissing(
                    _missing_output_diagnostics(message)
                )
            structured = _normalize_json_content(content)
        if not isinstance(structured, dict):
            raise StructuredOutputError(
                [{"location": [], "type": "object_type_required"}]
            )

        log_stage(
            "structured_output_validation_started",
            "started",
        )
        try:
            result = ProviderRepairPlan.model_validate(structured)
        except ValidationError as error:
            raise StructuredOutputError(
                _safe_provider_validation_errors(error)
            ) from error

        log_stage("structured_output_validated", "completed")
        return result

    async def _request_with_one_retry(
        self,
        body: dict[str, object],
    ) -> httpx.Response:
        endpoint = (
            f"{self.settings.openrouter_base_url}"
            "/chat/completions"
        )
        headers = {
            "Authorization": (
                f"Bearer {self.settings.openrouter_api_key}"
            ),
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=self.settings.openrouter_request_timeout_seconds,
            transport=self.transport,
        ) as client:
            for attempt in range(self.max_attempts):
                log_stage("openrouter_request_started", "started")
                try:
                    response = await client.post(
                        endpoint,
                        headers=headers,
                        json=body,
                    )
                except httpx.TimeoutException as error:
                    if attempt + 1 < self.max_attempts:
                        await self.sleep(0)
                        continue
                    raise PlanProviderError(
                        "openrouter_timeout"
                    ) from error
                except httpx.RequestError as error:
                    raise PlanProviderError(
                        "openrouter_provider_error"
                    ) from error

                retry_after = response.headers.get("Retry-After")
                log_stage(
                    "openrouter_http_response_received",
                    "received",
                    upstream_http_status=response.status_code,
                    retry_after=retry_after,
                )
                if response.status_code == 200:
                    return response

                retryable = response.status_code in {429, 503}
                if retryable and attempt + 1 < self.max_attempts:
                    await self.sleep(
                        _retry_after_seconds(
                            retry_after
                        )
                    )
                    continue
                if response.status_code == 429:
                    raise PlanProviderError(
                        "openrouter_rate_limited",
                        upstream_http_status=response.status_code,
                        retry_after=retry_after,
                    )
                raise PlanProviderError(
                    "openrouter_provider_error",
                    upstream_http_status=response.status_code,
                    retry_after=retry_after,
                )

        raise PlanProviderError("openrouter_provider_error")
