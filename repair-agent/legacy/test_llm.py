from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)


load_dotenv()


def configure_local_llm() -> str:
    """
    Configure the OpenAI Agents SDK to use local Ollama
    instead of the paid OpenAI API.
    """

    base_url = os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434/v1",
    )

    model_name = os.getenv(
        "OLLAMA_MODEL",
        "qwen2.5-coder:3b",
    )

    # Ollama requires a non-empty API-key value for OpenAI
    # client compatibility, but the value is ignored locally.
    local_client = AsyncOpenAI(
        base_url=base_url,
        api_key="ollama",
    )

    set_default_openai_client(
        local_client,
        use_for_tracing=False,
    )

    # Ollama supports the OpenAI-compatible Chat Completions API.
    set_default_openai_api("chat_completions")

    # Prevent the Agents SDK from trying to send traces
    # to OpenAI's servers.
    set_tracing_disabled(True)

    return model_name


async def main() -> None:
    model_name = configure_local_llm()

    print("Using local model:", model_name)

    agent = Agent(
        name="Local Connection Test",
        model=model_name,
        instructions=(
            "You are a software repair assistant. "
            "Reply using one short sentence."
        ),
    )

    result = await Runner.run(
        agent,
        "What does a Python SyntaxError mean?",
    )

    print("\nLLM response:")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())