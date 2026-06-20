from __future__ import annotations

import json
from typing import Protocol

from agents import (
    Agent,
    AsyncOpenAI,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)

from repair_agent.config import Settings
from repair_agent.mcp.interface import RepositoryReader
from repair_agent.schemas import (
    ProviderRepairPlan,
    RepairPlanRequest,
)
from repair_agent.security import (
    SYSTEM_INSTRUCTIONS,
    reject_sensitive_content,
)


class PlanProvider(Protocol):
    @property
    def model_name(self) -> str:
        ...

    async def create_plan(
        self,
        request: RepairPlanRequest,
        reader: RepositoryReader,
    ) -> ProviderRepairPlan:
        ...


class OpenRouterPlanProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.timeout_seconds,
        )
        self._model = OpenAIChatCompletionsModel(
            model=settings.openrouter_model,
            openai_client=self._client,
            strict_feature_validation=False,
        )
        set_tracing_disabled(True)

    @property
    def model_name(self) -> str:
        return self.settings.openrouter_model

    async def create_plan(
        self,
        request: RepairPlanRequest,
        reader: RepositoryReader,
    ) -> ProviderRepairPlan:
        @function_tool
        async def read_repository_file(path: str) -> str:
            """Read one safe repository file at the verified failed SHA."""
            return await reader.read_file(path)

        @function_tool
        async def list_repository_directory(path: str) -> str:
            """List one safe repository directory at the failed SHA."""
            return await reader.list_directory(path)

        request_payload = {
            "attempt_id": request.attempt_id,
            "root_cause": request.root_cause,
            "confidence": request.confidence,
            "error_type": request.error_type,
            "error_message": request.error_message,
            "candidate_file": request.candidate_file,
            "candidate_line": request.candidate_line,
            "sanitized_log_excerpt":
                request.sanitized_log_excerpt,
        }
        prompt = (
            "Investigate this failure using the read-only tools and "
            "return the smallest concrete repair proposal.\n"
            + json.dumps(request_payload)
        )
        reject_sensitive_content(prompt)

        agent = Agent(
            name="Read-Only Application Repair Planner",
            instructions=SYSTEM_INSTRUCTIONS,
            model=self._model,
            tools=[
                read_repository_file,
                list_repository_directory,
            ],
            output_type=ProviderRepairPlan,
        )
        result = await Runner.run(
            agent,
            prompt,
            max_turns=self.settings.max_tool_calls + 2,
        )
        return ProviderRepairPlan.model_validate(
            result.final_output
        )
