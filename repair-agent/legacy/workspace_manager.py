from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{7,64}")


class WorkspaceError(RuntimeError):
    pass


class WorkspaceManager:
    def __init__(self, workspace_root: Path | None = None) -> None:
        root = workspace_root or Path(__file__).parent / "workspaces"
        self.workspace_root = root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def workspace_path_for(self, repository_full_name: str) -> Path:
        if not REPOSITORY_PATTERN.fullmatch(repository_full_name):
            raise WorkspaceError("Invalid GitHub repository name.")

        owner, repository = repository_full_name.split("/", maxsplit=1)
        if owner in {".", ".."} or repository in {".", ".."}:
            raise WorkspaceError("Invalid GitHub repository name.")

        target = (self.workspace_root / f"{owner}__{repository}").resolve()
        if target.parent != self.workspace_root:
            raise WorkspaceError("Workspace path escaped the configured root.")
        return target

    def prepare(
        self,
        run_metadata: dict[str, Any],
        *,
        index_with_serena: bool = True,
    ) -> dict[str, Any]:
        repository_full_name = str(
            run_metadata.get("repository_full_name") or ""
        )
        head_sha = str(run_metadata.get("head_sha") or "")
        clone_url = str(run_metadata.get("repository_clone_url") or "")

        if not SHA_PATTERN.fullmatch(head_sha):
            raise WorkspaceError("Workflow metadata contains an invalid SHA.")

        expected_clone_url = (
            f"https://github.com/{repository_full_name}.git"
        )
        if clone_url.lower() != expected_clone_url.lower():
            raise WorkspaceError(
                "Workflow metadata contains an unexpected clone URL."
            )

        workspace = self.workspace_path_for(repository_full_name)
        if workspace.exists():
            self._verify_existing_workspace(workspace, expected_clone_url)
        else:
            self._clone_repository(expected_clone_url, workspace)

        self._run_git(
            ["fetch", "--no-tags", "origin", head_sha],
            cwd=workspace,
        )
        self._run_git(
            ["checkout", "--detach", head_sha],
            cwd=workspace,
        )

        indexed = False
        if index_with_serena:
            self._index_with_serena(workspace)
            indexed = True

        return {
            "repository_full_name": repository_full_name,
            "workspace_path": str(workspace),
            "head_sha": head_sha,
            "head_branch": run_metadata.get("head_branch"),
            "serena_indexed": indexed,
        }

    def _clone_repository(self, clone_url: str, workspace: Path) -> None:
        try:
            self._run_git(
                [
                    "clone",
                    "--no-checkout",
                    "--filter=blob:none",
                    clone_url,
                    str(workspace),
                ],
                cwd=self.workspace_root,
            )
        except Exception:
            if workspace.exists():
                shutil.rmtree(workspace)
            raise

    def _verify_existing_workspace(
        self,
        workspace: Path,
        expected_clone_url: str,
    ) -> None:
        if not (workspace / ".git").is_dir():
            raise WorkspaceError(
                f"Workspace exists but is not a Git repository: {workspace}"
            )

        status = self._run_git(
            ["status", "--porcelain"],
            cwd=workspace,
        )
        if status.strip():
            raise WorkspaceError(
                "Workspace contains uncommitted changes; repair preparation stopped."
            )

        origin = self._run_git(
            ["remote", "get-url", "origin"],
            cwd=workspace,
        ).strip()
        if origin.lower() != expected_clone_url.lower():
            raise WorkspaceError(
                "Existing workspace points to a different GitHub repository."
            )

    @staticmethod
    def _git_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"

        token = os.getenv("GITHUB_PAT_TOKEN")
        if token:
            credential = base64.b64encode(
                f"x-access-token:{token}".encode("utf-8")
            ).decode("ascii")
            environment["GIT_CONFIG_COUNT"] = "1"
            environment["GIT_CONFIG_KEY_0"] = (
                "http.https://github.com/.extraheader"
            )
            environment["GIT_CONFIG_VALUE_0"] = (
                f"AUTHORIZATION: basic {credential}"
            )

        return environment

    def _run_git(self, arguments: list[str], *, cwd: Path) -> str:
        return self._run_command(
            ["git", *arguments],
            cwd=cwd,
            environment=self._git_environment(),
        )

    def _index_with_serena(self, workspace: Path) -> None:
        executable = shutil.which("serena")
        if not executable:
            fallback = Path.home() / ".local" / "bin" / "serena.exe"
            if fallback.is_file():
                executable = str(fallback)

        if not executable:
            raise WorkspaceError(
                "Serena executable was not found on PATH or in ~/.local/bin."
            )

        self._run_command(
            [
                executable,
                "project",
                "index",
                "--log-level",
                "ERROR",
                str(workspace),
            ],
            cwd=workspace,
            environment=os.environ.copy(),
            timeout_seconds=300,
        )

    @staticmethod
    def _run_command(
        command: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
        timeout_seconds: int = 120,
    ) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise WorkspaceError(
                f"Command could not complete: {command[0]}"
            ) from error

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise WorkspaceError(
                f"{command[0]} failed: {detail or 'unknown error'}"
            )

        return result.stdout
