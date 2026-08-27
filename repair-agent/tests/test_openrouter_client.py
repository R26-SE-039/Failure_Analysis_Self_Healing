import json
import unittest
from dataclasses import replace

import httpx

from repair_agent.openrouter_client import (
    OpenRouterPlanProvider,
    PlanProviderError,
    StructuredOutputError,
    StructuredOutputMissing,
)
from repair_agent.schemas import (
    EvidenceExcerpt,
    PlanEvidence,
)
from tests.test_planner import request, settings


def provider_plan() -> dict:
    return {
        "root_cause_confirmed": True,
        "repairable": True,
        "confirmed_failed_file": "app/user_service.py",
        "confirmed_failed_line": 10,
        "inspected_files": ["app/user_service.py"],
        "proposed_changes": [
            {
                "file_path": "app/user_service.py",
                "start_line": 10,
                "end_line": 10,
                "before_excerpt": "return User(name=name",
                "after_excerpt": "return User(name=name)",
                "reason": "Close the constructor call.",
            }
        ],
        "suggested_validation_commands": ["pytest -q"],
        "risks": ["Review constructor behavior."],
        "manual_review_reason": None,
        "github_changes_made": False,
    }


def evidence() -> PlanEvidence:
    return PlanEvidence(
        candidate=EvidenceExcerpt(
            file_path="app/user_service.py",
            start_line=8,
            end_line=11,
            content=(
                "line 8\nline 9\n"
                "return User(name=name\nline 11"
            ),
        ),
        related_tests=[],
    )


def success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(provider_plan())
                    }
                }
            ]
        },
    )


class OpenRouterPlanProviderTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_one_tool_free_structured_request(self):
        captured = []

        async def handler(http_request):
            captured.append(json.loads(http_request.content))
            return success_response()

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertLogs(
            "repair_agent.planning",
            level="INFO",
        ) as logs:
            result = await provider.create_plan(
                request(),
                evidence(),
            )

        self.assertTrue(result.repairable)
        self.assertFalse(result.github_changes_made)
        self.assertEqual(len(captured), 1)
        self.assertNotIn("tools", captured[0])
        self.assertIn(
            "Return exactly one JSON object",
            captured[0]["messages"][0]["content"],
        )
        self.assertEqual(
            captured[0]["provider"],
            {"require_parameters": True},
        )
        self.assertNotIn("reasoning", captured[0])
        self.assertEqual(captured[0]["max_tokens"], 8192)
        self.assertEqual(
            captured[0]["response_format"]["type"],
            "json_schema",
        )
        serialized = json.dumps(captured[0])
        for credential in (
            settings().openrouter_api_key,
            settings().github_mcp_token,
            settings().shared_token,
        ):
            self.assertNotIn(credential, serialized)
            self.assertNotIn(credential, "\n".join(logs.output))

    async def test_pins_configured_structured_output_provider(self):
        captured = []

        async def handler(http_request):
            captured.append(json.loads(http_request.content))
            return success_response()

        provider = OpenRouterPlanProvider(
            replace(
                settings(),
                openrouter_provider="Structured Provider",
            ),
            transport=httpx.MockTransport(handler),
        )

        await provider.create_plan(request(), evidence())

        self.assertEqual(
            captured[0]["provider"],
            {
                "require_parameters": True,
                "only": ["Structured Provider"],
            },
        )

    async def test_rejects_malformed_structured_output(self):
        calls = 0

        async def handler(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "{invalid"}}
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(StructuredOutputError):
            await provider.create_plan(request(), evidence())
        self.assertEqual(calls, 1)

    async def test_rejects_prose_wrapped_json(self):
        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "Here is the plan: "
                                    + json.dumps(provider_plan())
                                )
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(StructuredOutputError) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.validation_errors,
            [{"location": [], "type": "json_leading_content"}],
        )

    async def test_rejects_trailing_content_after_json(self):
        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    json.dumps(provider_plan())
                                    + " trailing prose"
                                )
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(StructuredOutputError) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.validation_errors,
            [{"location": [], "type": "json_trailing_content"}],
        )
    async def test_accepts_fenced_json_only(self):
        fenced = "```json\n" + json.dumps(provider_plan()) + "\n```"

        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": fenced}}
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )
        result = await provider.create_plan(request(), evidence())
        self.assertTrue(result.repairable)

    async def test_accepts_parsed_structured_data(self):
        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "parsed": provider_plan(),
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )
        result = await provider.create_plan(request(), evidence())
        self.assertTrue(result.repairable)

    async def test_empty_content_is_reported_missing(self):
        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning": "not accepted",
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(StructuredOutputMissing) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.validation_errors,
            [{"location": [], "type": "reasoning_only_output"}],
        )

    async def test_does_not_accept_schema_json_from_reasoning(self):
        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning": json.dumps(
                                    provider_plan()
                                ),
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(StructuredOutputMissing) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.validation_errors,
            [
                {
                    "location": [],
                    "type": "structured_json_in_reasoning",
                }
            ],
        )

    async def test_429_respects_retry_after_and_retries_once(self):
        calls = 0
        sleeps = []

        async def handler(_request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "2"},
                )
            return success_response()

        async def sleep(seconds):
            sleeps.append(seconds)

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
            sleep=sleep,
        )
        result = await provider.create_plan(
            request(),
            evidence(),
        )

        self.assertTrue(result.repairable)
        self.assertEqual(calls, 2)
        self.assertEqual(sleeps, [2.0])

    async def test_authentication_error_is_not_retried(self):
        calls = 0

        async def handler(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(401)

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(PlanProviderError) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.code,
            "openrouter_provider_error",
        )
        self.assertEqual(calls, 1)

    async def test_strict_schema_rejection_reports_status(self):
        async def handler(_request):
            return httpx.Response(400)

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(PlanProviderError) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.code,
            "openrouter_provider_error",
        )
        self.assertEqual(raised.exception.upstream_http_status, 400)

    async def test_provider_cannot_report_github_changes(self):
        unsafe = provider_plan()
        unsafe["github_changes_made"] = True

        async def handler(_request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(unsafe)
                            }
                        }
                    ]
                },
            )

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(StructuredOutputError):
            await provider.create_plan(request(), evidence())

    async def test_provider_timeout_retries_once(self):
        calls = 0

        async def handler(http_request):
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout(
                "provider timeout",
                request=http_request,
            )

        async def sleep(_seconds):
            return None

        provider = OpenRouterPlanProvider(
            settings(),
            transport=httpx.MockTransport(handler),
            sleep=sleep,
        )

        with self.assertRaises(PlanProviderError) as raised:
            await provider.create_plan(request(), evidence())

        self.assertEqual(
            raised.exception.code,
            "openrouter_timeout",
        )
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
