from __future__ import annotations

import argparse
import asyncio
import json
import os

import httpx
from dotenv import load_dotenv


load_dotenv()


async def resolve_run(run_url: str) -> dict:
    backend_url = os.getenv(
        "BACKEND_API_URL",
        "http://127.0.0.1:8000",
    ).rstrip("/")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{backend_url}/api/github/actions/resolve",
            json={"run_url": run_url},
        )

    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"Run resolution failed ({response.status_code}): {detail}"
        )

    return response.json()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a GitHub Actions run URL through the analysis backend."
        )
    )
    parser.add_argument("run_url")
    args = parser.parse_args()

    metadata = await resolve_run(args.run_url)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
