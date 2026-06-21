from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

from repair_agent.config import Settings
from repair_agent.diagnostics import begin_correlation, log_stage
from repair_agent.mcp.github_remote import RemoteGitHubMcpClient
from repair_agent.openrouter_client import (
    OpenRouterPlanProvider,
    PlanProviderError,
)
from repair_agent.planner import (
    McpReadFailed,
    PlanValidationError,
    RepairPlanner,
)
from repair_agent.schemas import RepairPlanRequest


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing diagnostic setting: {name}")
    return value


async def main() -> None:
    if os.getenv("RUN_LIVE_PHASE1_DIAGNOSTIC") != "1":
        raise RuntimeError(
            "Set RUN_LIVE_PHASE1_DIAGNOSTIC=1 to run this live test."
        )

    settings = Settings.from_environment()
    correlation_id, _token = begin_correlation()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for logger_name in ("httpx", "httpcore", "mcp", "anyio"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    print(f"model_id={settings.openrouter_model}")

    request = RepairPlanRequest(
        attempt_id="LIVE-DIAGNOSTIC",
        repository_owner=required("LIVE_REPOSITORY_OWNER"),
        repository_name=required("LIVE_REPOSITORY_NAME"),
        run_id=1,
        head_sha=required("LIVE_FAILED_SHA"),
        head_branch=os.getenv("LIVE_HEAD_BRANCH", "diagnostic"),
        default_branch=None,
        root_cause="application_defect",
        confidence=1.0,
        decision_source="live_diagnostic",
        selected_action="start_mcp_code_repair",
        error_type=required("LIVE_ERROR_TYPE"),
        error_message=required("LIVE_ERROR_MESSAGE"),
        candidate_file=required("LIVE_CANDIDATE_FILE"),
        candidate_line=int(required("LIVE_CANDIDATE_LINE")),
        sanitized_log_excerpt="Live diagnostic evidence omitted.",
    )
    provider = OpenRouterPlanProvider(
        settings,
        max_attempts=1,
    )
    planner = RepairPlanner(
        settings=settings,
        provider=provider,
        mcp_client_factory=lambda: RemoteGitHubMcpClient(
            url=settings.github_mcp_url,
            token=settings.github_mcp_token,
            timeout_seconds=settings.timeout_seconds,
        ),
        allow_search_fallback=False,
    )

    try:
        result = await asyncio.wait_for(
            planner.create_plan(request),
            timeout=settings.planning_timeout_seconds,
        )
    except McpReadFailed as error:
        log_stage(
            "plan_failed",
            "failed",
            exception_class=type(error).__name__,
            error_code=error.code,
        )
        print(f"diagnostic_status=failed error_code={error.code}")
        return
    except PlanProviderError as error:
        log_stage(
            "plan_failed",
            "failed",
            exception_class=type(error).__name__,
            error_code=error.code,
            upstream_http_status=error.upstream_http_status,
            retry_after=error.retry_after,
            validation_errors=error.validation_errors,
        )
        print(f"diagnostic_status=failed error_code={error.code}")
        return
    except PlanValidationError as error:
        log_stage(
            "plan_failed",
            "failed",
            exception_class=type(error).__name__,
            error_code="plan_validation_failed",
            validation_errors=[
                {"location": [], "type": error.reason_code}
            ],
        )
        print(
            "diagnostic_status=failed "
            "error_code=plan_validation_failed"
        )
        return
    except asyncio.TimeoutError as error:
        log_stage(
            "plan_failed",
            "failed",
            exception_class=type(error).__name__,
            error_code="openrouter_timeout",
        )
        print("diagnostic_status=failed error_code=openrouter_timeout")
        return
    except Exception as error:
        log_stage(
            "plan_failed",
            "failed",
            exception_class=type(error).__name__,
            error_code="planner_internal_error",
        )
        print("diagnostic_status=failed error_code=planner_internal_error")
        return

    log_stage("plan_completed", "completed")
    status = "completed" if not result.github_changes_made else "failed"
    print(
        f"diagnostic_status={status} "
        f"correlation_id={correlation_id}"
    )


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
