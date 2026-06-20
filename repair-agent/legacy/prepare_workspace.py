from __future__ import annotations

import argparse
import asyncio
import json

from resolve_run import resolve_run
from workspace_manager import WorkspaceManager


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a failed GitHub Actions run, prepare its exact commit, "
            "and index the workspace with Serena."
        )
    )
    parser.add_argument("run_url")
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Prepare the Git workspace without running Serena.",
    )
    args = parser.parse_args()

    metadata = await resolve_run(args.run_url)
    result = WorkspaceManager().prepare(
        metadata,
        index_with_serena=not args.skip_index,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
