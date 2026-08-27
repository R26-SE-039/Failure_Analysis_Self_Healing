import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.models.repair_attempt import RepairAttempt
from app.routers.github_actions import MAX_FAILED_JOBS_FOR_EVIDENCE
from app.services.failure_evidence_service import (
    MAX_EVIDENCE_CHARS,
    build_failure_evidence,
    sanitize_log_text,
)
from app.services.github_actions_service import (
    GitHubActionsApiError,
    GitHubActionsService,
    LOG_DOWNLOAD_MAX_BYTES,
)
from app.services.repair_eligibility_service import is_protected_path
from app.services.project_configuration_client import (
    ProjectConfigurationError,
    ProjectGitHubConfiguration,
)


ORG_ID = "11111111-1111-1111-1111-111111111111"
PROJECT_ID = "22222222-2222-2222-2222-222222222222"
HEAD_SHA = "a" * 40
TOKEN = "project-secret-token"
SIGNED_LOG_URL = "https://pipelines.actions.githubusercontent.com/signed-log-url?sig=secret"


def run_payload(
    *,
    repo="example/project",
    run_id=12345,
    status="completed",
    conclusion="failure",
):
    return {
        "id": run_id,
        "run_number": 42,
        "run_attempt": 1,
        "name": "Playwright Tests",
        "display_title": "CI",
        "status": status,
        "conclusion": conclusion,
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "created_at": "2026-08-20T01:00:00Z",
        "updated_at": "2026-08-20T01:05:00Z",
        "html_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        "repository": {"full_name": repo},
        "check_suite_id": 98765,
    }


def normalized_run():
    return {
        "run_id": 12345,
        "run_number": 42,
        "run_attempt": 1,
        "name": "Playwright Tests",
        "display_title": "CI",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "created_at": "2026-08-20T01:00:00Z",
        "updated_at": "2026-08-20T01:05:00Z",
        "html_url": "https://github.com/example/project/actions/runs/12345",
        "repository": {"full_name": "example/project"},
        "check_suite_id": 98765,
    }


def job_payload(job_id, *, conclusion="failure", step_conclusion=None):
    step_conclusion = step_conclusion or conclusion
    return {
        "id": job_id,
        "name": f"job-{job_id}",
        "status": "completed",
        "conclusion": conclusion,
        "started_at": "2026-08-20T01:00:00Z",
        "completed_at": "2026-08-20T01:05:00Z",
        "html_url": f"https://github.com/example/project/actions/runs/12345/job/{job_id}",
        "steps": [
            {
                "number": 1,
                "name": "Install",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "number": 2,
                "name": "Run tests",
                "status": "completed",
                "conclusion": step_conclusion,
            },
        ],
    }


def normalized_job(job_id, *, conclusion="failure", step_conclusion=None):
    raw = job_payload(job_id, conclusion=conclusion, step_conclusion=step_conclusion)
    return {
        "job_id": raw["id"],
        "name": raw["name"],
        "status": raw["status"],
        "conclusion": raw["conclusion"],
        "started_at": raw["started_at"],
        "completed_at": raw["completed_at"],
        "html_url": raw["html_url"],
        "steps": raw["steps"],
    }


class GitHubActionsDiscoveryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_failed_workflow_runs_successfully(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/repos/example/project/actions/runs",
            )
            self.assertEqual(request.url.params["status"], "completed")
            self.assertEqual(request.url.params["per_page"], "20")
            self.assertEqual(request.headers["Authorization"], f"Bearer {TOKEN}")
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        run_payload(run_id=12345, conclusion="failure"),
                        run_payload(run_id=12346, conclusion="success"),
                    ]
                },
            )

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        runs = await service.list_failed_runs(owner="example", repository="project")

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], 12345)
        self.assertEqual(runs[0]["repository"]["full_name"], "example/project")
        self.assertNotIn(TOKEN, str(runs))

    async def test_empty_workflow_run_list_returns_empty(self):
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"workflow_runs": []})
            ),
        )

        runs = await service.list_failed_runs(owner="example", repository="project")

        self.assertEqual(runs, [])

    async def test_no_failed_runs_returns_empty(self):
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"workflow_runs": [run_payload(conclusion="success")]},
                )
            ),
        )

        runs = await service.list_failed_runs(owner="example", repository="project")

        self.assertEqual(runs, [])

    async def test_run_repository_matches_current_project(self):
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=run_payload())
            ),
        )

        run = await service.get_run(owner="example", repository="project", run_id=12345)

        self.assertEqual(run["repository"]["full_name"], "example/project")

    async def test_run_repository_mismatch_is_rejected(self):
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=run_payload(repo="other/project"))
            ),
        )

        with self.assertRaisesRegex(GitHubActionsApiError, "different repository") as ctx:
            await service.get_run(owner="example", repository="project", run_id=12345)

        self.assertEqual(ctx.exception.status_code, 409)

    async def test_jobs_listing_success_and_failed_job_detection(self):
        jobs_response = {
            "jobs": [
                job_payload(1, conclusion="failure"),
                job_payload(2, conclusion="success"),
                job_payload(3, conclusion="failure"),
            ]
        }
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=jobs_response)
            ),
        )

        jobs = await service.list_jobs_for_run(
            owner="example",
            repository="project",
            run_id=12345,
        )
        failed_jobs = [job for job in jobs if job["conclusion"] == "failure"]

        self.assertEqual(len(jobs), 3)
        self.assertEqual(len(failed_jobs), 2)
        self.assertEqual(failed_jobs[0]["steps"][1]["name"], "Run tests")

    async def test_no_failed_jobs_case_is_represented(self):
        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"jobs": [job_payload(1, conclusion="success")]},
                )
            ),
        )

        jobs = await service.list_jobs_for_run(
            owner="example",
            repository="project",
            run_id=12345,
        )

        self.assertEqual([job for job in jobs if job["conclusion"] == "failure"], [])

    async def test_github_http_errors_are_safe(self):
        cases = {
            401: 401,
            403: 403,
            404: 404,
            429: 429,
            500: 502,
        }
        for github_status, expected_status in cases.items():
            with self.subTest(github_status=github_status):
                service = GitHubActionsService(
                    token=TOKEN,
                    allowed_repositories={"example/project"},
                    transport=httpx.MockTransport(
                        lambda request, status=github_status: httpx.Response(status)
                    ),
                )

                with self.assertRaises(GitHubActionsApiError) as ctx:
                    await service.list_failed_runs(owner="example", repository="project")

                self.assertEqual(ctx.exception.status_code, expected_status)
                self.assertNotIn(TOKEN, str(ctx.exception))

    async def test_github_timeout_is_safe(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out")

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaisesRegex(GitHubActionsApiError, "timed out") as ctx:
            await service.list_failed_runs(owner="example", repository="project")

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertNotIn(TOKEN, str(ctx.exception))

    async def test_successful_failed_job_log_retrieval_follows_redirect(self):
        seen_paths = []
        seen_redirect_authorization = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(str(request.url))
            if request.url.host == "api.github.com":
                self.assertEqual(request.headers["Authorization"], f"Bearer {TOKEN}")
                return httpx.Response(302, headers={"Location": SIGNED_LOG_URL})
            seen_redirect_authorization.append(request.headers.get("Authorization"))
            return httpx.Response(200, content=b"ERROR TypeError: broken\nsrc/example.ts:82:4")

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        log_text = await service.download_job_log(
            owner="example",
            repository="project",
            job_id=999,
        )

        self.assertIn("TypeError", log_text)
        self.assertEqual(seen_redirect_authorization, [None])
        self.assertEqual(len(seen_paths), 2)

    async def test_redirect_download_failure_restarts_from_stable_endpoint(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.host == "api.github.com":
                return httpx.Response(302, headers={"Location": SIGNED_LOG_URL})
            if calls.count(SIGNED_LOG_URL) == 1:
                return httpx.Response(503)
            return httpx.Response(200, content=b"AssertionError: retry worked")

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        log_text = await service.download_job_log(
            owner="example",
            repository="project",
            job_id=999,
        )

        stable_endpoint = "https://api.github.com/repos/example/project/actions/jobs/999/logs"
        self.assertEqual(calls.count(stable_endpoint), 2)
        self.assertEqual(calls.count(SIGNED_LOG_URL), 2)
        self.assertIn("retry worked", log_text)

    async def test_bounded_retry_count_for_log_download(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.host == "api.github.com":
                return httpx.Response(302, headers={"Location": SIGNED_LOG_URL})
            return httpx.Response(503)

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaisesRegex(GitHubActionsApiError, "temporarily unavailable") as ctx:
            await service.download_job_log(owner="example", repository="project", job_id=999)

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(
            calls.count("https://api.github.com/repos/example/project/actions/jobs/999/logs"),
            2,
        )

    async def test_log_download_errors_are_safe(self):
        cases = {401: 401, 403: 403, 404: 404, 429: 429, 500: 502}
        for github_status, expected_status in cases.items():
            with self.subTest(github_status=github_status):
                service = GitHubActionsService(
                    token=TOKEN,
                    allowed_repositories={"example/project"},
                    transport=httpx.MockTransport(
                        lambda request, status=github_status: httpx.Response(status)
                    ),
                )

                with self.assertRaises(GitHubActionsApiError) as ctx:
                    await service.download_job_log(owner="example", repository="project", job_id=999)

                self.assertEqual(ctx.exception.status_code, expected_status)
                self.assertNotIn(TOKEN, str(ctx.exception))

    async def test_log_download_timeout_is_safe(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout")

        service = GitHubActionsService(
            token=TOKEN,
            allowed_repositories={"example/project"},
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaisesRegex(GitHubActionsApiError, "timed out") as ctx:
            await service.download_job_log(owner="example", repository="project", job_id=999)

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertNotIn(TOKEN, str(ctx.exception))

    async def test_missing_pat_from_project_configuration_is_safe(self):
        from app.services.project_configuration_client import ProjectConfigurationClient

        client = ProjectConfigurationClient(
            gateway_url="http://gateway.local",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "repo_url": "https://github.com/example/project",
                        "personal_access_token": "",
                    },
                )
            ),
        )

        with self.assertRaisesRegex(ProjectConfigurationError, "not configured") as ctx:
            await client.get_project_github_configuration(
                project_id=PROJECT_ID,
                authorization_header="Bearer user-jwt",
            )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_invalid_repo_url_from_project_configuration_is_safe(self):
        from app.services.project_configuration_client import ProjectConfigurationClient

        client = ProjectConfigurationClient(
            gateway_url="http://gateway.local",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "repo_url": "https://gitlab.example/example/project",
                        "personal_access_token": TOKEN,
                    },
                )
            ),
        )

        with self.assertRaisesRegex(ProjectConfigurationError, "GitHub repository") as ctx:
            await client.get_project_github_configuration(
                project_id=PROJECT_ID,
                authorization_header="Bearer user-jwt",
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertNotIn(TOKEN, str(ctx.exception))


class FailureEvidenceServiceTests(unittest.TestCase):
    def test_ansi_stripping_and_secret_redaction(self):
        text = "\x1b[31mERROR\x1b[0m token=ghp_abcdefghijklmnopqrstuvwxyz123456"

        sanitized = sanitize_log_text(text)

        self.assertIn("ERROR", sanitized)
        self.assertIn("token=[REDACTED]", sanitized)
        self.assertNotIn("ghp_", sanitized)
        self.assertNotIn("\x1b", sanitized)

    def test_error_message_stack_trace_and_candidate_location_extraction(self):
        evidence = build_failure_evidence(
            log_text=(
                "Starting tests\n"
                "Traceback (most recent call last):\n"
                "  File \"src/example.py\", line 82, in test_case\n"
                "TypeError: unsupported operand\n"
            ),
            job_name="pytest",
            failed_steps=[{"number": 2, "name": "Run tests"}],
        )

        self.assertEqual(evidence["error_type"], "TypeError")
        self.assertEqual(evidence["error_message"], "unsupported operand")
        self.assertEqual(evidence["candidate_file"], "src/example.py")
        self.assertEqual(evidence["candidate_line"], 82)
        self.assertIn("Traceback", evidence["stack_trace"])
        self.assertIn("Run tests", evidence["failed_step_names"])

    def test_candidate_location_remains_null_when_unsupported(self):
        evidence = build_failure_evidence(
            log_text="ERROR: Something failed without a source location",
            job_name="tests",
            failed_steps=[],
        )

        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

    def test_oversized_log_is_bounded(self):
        evidence = build_failure_evidence(
            log_text="ERROR: " + ("x" * (MAX_EVIDENCE_CHARS + 1000)),
            job_name="tests",
            failed_steps=[],
        )

        self.assertLessEqual(
            len(evidence["sanitized_log_excerpt"]),
            MAX_EVIDENCE_CHARS + len("\n...[truncated]"),
        )
        self.assertIn("[truncated]", evidence["sanitized_log_excerpt"])

    def test_empty_job_log_has_deterministic_hash(self):
        first = build_failure_evidence(log_text="", job_name="tests", failed_steps=[])
        second = build_failure_evidence(log_text="", job_name="tests", failed_steps=[])

        self.assertEqual(first["sanitized_log_excerpt"], "")
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])
        self.assertIsNone(first["error_type"])

    def test_linux_github_runner_path_normalizes_to_repo_relative(self):
        evidence = build_failure_evidence(
            log_text="TypeError: bad\n/home/runner/work/project/project/app/user_service.py:82:4",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertEqual(evidence["candidate_file"], "app/user_service.py")
        self.assertEqual(evidence["candidate_line"], 82)

    def test_windows_github_runner_path_normalizes_to_repo_relative(self):
        evidence = build_failure_evidence(
            log_text='File "D:\\a\\project\\project\\src\\user_service.ts", line 55, in test',
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertEqual(evidence["candidate_file"], "src/user_service.ts")
        self.assertEqual(evidence["candidate_line"], 55)

    def test_nested_runner_path_normalizes_to_repo_relative(self):
        evidence = build_failure_evidence(
            log_text="AssertionError\n/home/runner/work/project/project/packages/api/src/service.ts:21:9",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertEqual(evidence["candidate_file"], "packages/api/src/service.ts")
        self.assertEqual(evidence["candidate_line"], 21)

    def test_unrelated_absolute_linux_path_is_rejected(self):
        evidence = build_failure_evidence(
            log_text="TypeError\n/tmp/project/app/user_service.py:82",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

    def test_unrelated_absolute_windows_path_is_rejected(self):
        evidence = build_failure_evidence(
            log_text='File "C:\\work\\project\\app\\user_service.py", line 82, in test',
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

    def test_runner_path_traversal_is_rejected(self):
        evidence = build_failure_evidence(
            log_text="TypeError\n/home/runner/work/project/project/../secrets.py:3",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

    def test_already_relative_valid_path_remains_valid(self):
        evidence = build_failure_evidence(
            log_text="TypeError\napp/user_service.py:82:4",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertEqual(evidence["candidate_file"], "app/user_service.py")
        self.assertEqual(evidence["candidate_line"], 82)

    def test_repository_name_mismatch_is_rejected(self):
        evidence = build_failure_evidence(
            log_text="TypeError\n/home/runner/work/other/other/app/user_service.py:82",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

    def test_normalization_does_not_weaken_protected_path_checks(self):
        evidence = build_failure_evidence(
            log_text="TypeError\n/home/runner/work/project/project/auth/login.py:10",
            job_name="tests",
            failed_steps=[],
            repository_name="project",
        )

        self.assertEqual(evidence["candidate_file"], "auth/login.py")
        self.assertTrue(is_protected_path(evidence["candidate_file"]))


    def test_maven_compiler_error_is_prioritized_over_download_noise(self):
        evidence = build_failure_evidence(
            log_text=(
                "[INFO] Scanning for projects...\n"
                "[INFO] Downloading from central: https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.pom\n"
                "[ERROR] /home/runner/work/saucedemo/saucedemo/src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java:[21,53] ';', ')', or '[' expected\n"
                "[ERROR] BUILD FAILURE\n"
            ),
            job_name="maven-test",
            failed_steps=[{"number": 4, "name": "Run Maven tests"}],
            repository_name="saucedemo",
        )

        self.assertEqual(evidence["error_type"], "CompilationError")
        self.assertEqual(evidence["error_message"], "';', ')', or '[' expected")
        self.assertNotIn("Downloading from central", evidence["error_message"])
        self.assertEqual(
            evidence["candidate_file"],
            "src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java",
        )
        self.assertEqual(evidence["candidate_line"], 21)
        self.assertEqual(evidence["failure_stage"], "compile")

    def test_maven_compiler_error_with_relative_java_path_is_extracted(self):
        evidence = build_failure_evidence(
            log_text="[ERROR] src/main/java/app/CheckoutCompletePage.java:[8,12] illegal start of expression",
            job_name="maven-test",
            failed_steps=[],
            repository_name="saucedemo",
        )

        self.assertEqual(evidence["error_type"], "CompilationError")
        self.assertEqual(evidence["error_message"], "illegal start of expression")
        self.assertEqual(evidence["candidate_file"], "src/main/java/app/CheckoutCompletePage.java")
        self.assertEqual(evidence["candidate_line"], 8)

    def test_timestamped_maven_compiler_error_is_prioritized_over_failureaccess_noise(self):
        noise_lines = [
            "2026-08-27T08:30:40.1000000Z [INFO] Downloading from central: "
            "https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.pom"
            for _ in range(80)
        ]
        diagnostic = (
            "2026-08-27T08:30:49.1234567Z [ERROR] "
            "/home/runner/work/saucedemo/saucedemo/src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java:"
            "[21,53] ';', ')', or '[' expected"
        )
        evidence = build_failure_evidence(
            log_text="\n".join([*noise_lines, diagnostic, "2026-08-27T08:30:50.0000000Z [ERROR] BUILD FAILURE"]),
            job_name="maven-test",
            failed_steps=[{"number": 4, "name": "Run Maven tests"}],
            repository_name="saucedemo",
        )

        self.assertEqual(evidence["error_type"], "CompilationError")
        self.assertEqual(evidence["error_message"], "';', ')', or '[' expected")
        self.assertEqual(
            evidence["candidate_file"],
            "src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java",
        )
        self.assertEqual(evidence["candidate_line"], 21)
        self.assertEqual(evidence["failure_stage"], "compile")
        self.assertIn("CheckoutCompletePage.java:[21,53]", evidence["sanitized_log_excerpt"])
        self.assertNotEqual(evidence["error_message"], noise_lines[0])

    def test_late_maven_compiler_diagnostic_survives_bounded_log_decoding(self):
        diagnostic = (
            "2026-08-27T08:30:49.1234567Z [ERROR] "
            "/home/runner/work/saucedemo/saucedemo/src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java:"
            "[21,53] ';', ')', or '[' expected\n"
        )
        long_noise = (
            "2026-08-27T08:30:40.1000000Z [INFO] Downloading from central: "
            "https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.pom\n"
            * 7000
        )
        response = httpx.Response(200, content=(long_noise + diagnostic).encode("utf-8"))

        decoded = GitHubActionsService._decode_log_response(
            response,
            max_bytes=LOG_DOWNLOAD_MAX_BYTES,
        )
        evidence = build_failure_evidence(
            log_text=decoded,
            job_name="maven-test",
            failed_steps=[],
            repository_name="saucedemo",
        )

        self.assertLessEqual(len(decoded.encode("utf-8")), LOG_DOWNLOAD_MAX_BYTES)
        self.assertIn("middle of GitHub job log truncated", decoded)
        self.assertEqual(evidence["error_type"], "CompilationError")
        self.assertEqual(evidence["error_message"], "';', ')', or '[' expected")
        self.assertEqual(
            evidence["candidate_file"],
            "src/main/java/saucedemo/selenium/pages/CheckoutCompletePage.java",
        )
        self.assertEqual(evidence["candidate_line"], 21)
        self.assertIn("CheckoutCompletePage.java:[21,53]", evidence["sanitized_log_excerpt"])

    def test_maven_dependency_download_without_compiler_error_is_not_compilation_error(self):
        evidence = build_failure_evidence(
            log_text=(
                "[INFO] Downloading from central: https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.pom\n"
                "[ERROR] Failed to execute goal on project demo: Could not resolve dependencies\n"
            ),
            job_name="maven-test",
            failed_steps=[],
            repository_name="saucedemo",
        )

        self.assertNotEqual(evidence["error_type"], "CompilationError")
        self.assertIsNone(evidence["failure_stage"])
        self.assertIsNone(evidence["candidate_file"])
        self.assertIsNone(evidence["candidate_line"])

class GitHubActionsDiscoveryRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.config = ProjectGitHubConfiguration(
            repository_url="https://github.com/example/project",
            repository_owner="example",
            repository_name="project",
            repository_full_name="example/project",
            token=TOKEN,
        )

    def scoped_url(self, path):
        return f"{path}?organization_id={ORG_ID}&project_id={PROJECT_ID}"

    def test_failed_runs_endpoint_requires_scope(self):
        response = self.client.get(
            "/api/github/actions/failed-runs",
            headers={"Authorization": "Bearer user-jwt"},
        )

        self.assertEqual(response.status_code, 422)

    def test_failed_runs_endpoint_requires_authorization(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(
                side_effect=ProjectConfigurationError(
                    "Authorization is required to load project GitHub configuration.",
                    status_code=401,
                )
            ),
        ):
            response = self.client.get(self.scoped_url("/api/github/actions/failed-runs"))

        self.assertEqual(response.status_code, 401)

    def test_failed_runs_endpoint_uses_project_configuration(self):
        runs = [normalized_run()]
        config_mock = AsyncMock(return_value=self.config)
        list_mock = AsyncMock(return_value=runs)

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=config_mock,
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_failed_runs",
            new=list_mock,
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/failed-runs"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["repository"], "example/project")
        self.assertEqual(response.json()["runs"][0]["run_id"], 12345)
        self.assertNotIn(TOKEN, response.text)
        config_mock.assert_awaited_once_with(
            project_id=PROJECT_ID,
            authorization_header="Bearer user-jwt",
        )
        self.assertEqual(list_mock.await_args.kwargs["owner"], "example")
        self.assertEqual(list_mock.await_args.kwargs["repository"], "project")

    def test_run_details_endpoint_returns_failed_jobs_separately(self):
        jobs = [
            job_payload(1, conclusion="failure"),
            job_payload(2, conclusion="success"),
            job_payload(3, conclusion="failure"),
        ]

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=jobs),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["repository"], "example/project")
        self.assertEqual(len(body["jobs"]), 3)
        self.assertEqual(len(body["failed_jobs"]), 2)
        self.assertNotIn(TOKEN, response.text)

    def test_run_details_endpoint_preserves_github_error_status(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(
                side_effect=GitHubActionsApiError(
                    "GitHub rate-limited the request. Try again later.",
                    status_code=429,
                )
            ),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertNotIn(TOKEN, response.text)

    def test_project_configuration_missing_returns_safe_error(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(
                side_effect=ProjectConfigurationError(
                    "GitHub configuration is not configured for this project.",
                    status_code=400,
                )
            ),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/failed-runs"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(TOKEN, response.text)

    def test_evidence_endpoint_returns_sanitized_failed_job_evidence(self):
        jobs = [normalized_job(999, conclusion="failure")]

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=jobs),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(
                return_value="\x1b[31mTypeError: bad value\x1b[0m\n/home/runner/work/project/project/src/example.ts:82:4\ntoken=ghp_secretsecretsecretsecret"
            ),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345/evidence"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        evidence = body["failed_jobs"][0]["evidence"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["repository"], "example/project")
        self.assertEqual(body["failed_job_count"], 1)
        self.assertEqual(evidence["error_type"], "TypeError")
        self.assertEqual(evidence["candidate_file"], "src/example.ts")
        self.assertEqual(evidence["candidate_line"], 82)
        self.assertIn("[REDACTED]", evidence["sanitized_log_excerpt"])
        self.assertNotIn("ghp_", response.text)
        self.assertNotIn(TOKEN, response.text)
        self.assertNotIn(SIGNED_LOG_URL, response.text)

    def test_evidence_endpoint_preserves_multiple_failed_jobs_and_bound(self):
        jobs = [normalized_job(index, conclusion="failure") for index in range(1, 8)]
        download_mock = AsyncMock(return_value="AssertionError: failed\nsrc/test.py:10")

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=jobs),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=download_mock,
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345/evidence"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["failed_job_count"], 7)
        self.assertEqual(body["processed_failed_job_count"], MAX_FAILED_JOBS_FOR_EVIDENCE)
        self.assertEqual(len(body["failed_jobs"]), MAX_FAILED_JOBS_FOR_EVIDENCE)
        self.assertEqual(download_mock.await_count, MAX_FAILED_JOBS_FOR_EVIDENCE)

    def test_evidence_endpoint_returns_safe_per_job_log_error(self):
        jobs = [normalized_job(999, conclusion="failure")]

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=jobs),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(
                side_effect=GitHubActionsApiError(
                    "GitHub job log was not found or is no longer available.",
                    status_code=404,
                )
            ),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345/evidence"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["failed_jobs"][0]["evidence"])
        self.assertEqual(body["failed_jobs"][0]["error"]["status_code"], 404)
        self.assertNotIn(TOKEN, response.text)

    def test_evidence_endpoint_does_not_accept_arbitrary_job_id_route(self):
        response = self.client.get(
            self.scoped_url("/api/github/actions/jobs/999/evidence"),
            headers={"Authorization": "Bearer user-jwt"},
        )

        self.assertEqual(response.status_code, 404)




def classifier_result(root_cause="application_defect", *, confidence_percentage=87.0):
    return {
        "detected_error": {
            "error_type": "TypeError",
            "error_message": "bad value",
            "failed_file": "src/example.ts",
            "failed_line": "82",
            "missing_fixture": None,
            "missing_module": None,
        },
        "ml_prediction": root_cause,
        "ml_confidence_percentage": confidence_percentage,
        "final_confidence_percentage": confidence_percentage,
        "probabilities": {
            root_cause: confidence_percentage,
            "application_defect": confidence_percentage if root_cause == "application_defect" else 3.0,
            "test_script_issue": confidence_percentage if root_cause == "test_script_issue" else 2.0,
            "dependency_issue": confidence_percentage if root_cause == "dependency_issue" else 1.0,
        },
        "final_root_cause": root_cause,
        "decision_source": "machine_learning",
        "decision_reason": "Selected by the trained nine-class model.",
        "model_input_sha256": "model-input-hash",
    }


class GitHubActionsClassificationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.config = ProjectGitHubConfiguration(
            repository_url="https://github.com/example/project",
            repository_owner="example",
            repository_name="project",
            repository_full_name="example/project",
            token=TOKEN,
        )

    def scoped_url(self, path):
        return f"{path}?organization_id={ORG_ID}&project_id={PROJECT_ID}"

    def test_successful_github_evidence_classification_preview_reuses_classifier(self):
        classifier_mock = Mock(return_value=classifier_result("application_defect", confidence_percentage=87.0))
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="TypeError: bad value\n/home/runner/work/project/project/src/example.ts:82:4"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=classifier_mock,
        ), patch(
            "app.services.healing_orchestrator.healing_orchestrator.create_plan",
        ) as healing_mock, patch(
            "app.services.repair_eligibility_service.RepairEligibilityService.evaluate",
        ) as eligibility_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["repository"], "example/project")
        self.assertEqual(body["job"]["job_id"], 999)
        self.assertEqual(body["classification"]["root_cause"], "application_defect")
        self.assertEqual(body["classification"]["confidence"], 0.87)
        self.assertEqual(body["classification"]["decision_source"], "machine_learning")
        self.assertEqual(body["saved_to_db"], False)
        self.assertEqual(body["healing_invoked"], False)
        self.assertEqual(body["repair_eligibility_evaluated"], False)
        self.assertEqual(body["repair_agent_invoked"], False)
        self.assertEqual(body["classifier_input_summary"]["candidate_file"], "src/example.ts")
        self.assertEqual(body["classifier_input_summary"]["candidate_line"], 82)
        self.assertNotIn(TOKEN, response.text)
        classifier_mock.assert_called_once()
        classifier_input = classifier_mock.call_args.args[0]
        self.assertIn("FULL LOGS", classifier_input)
        self.assertIn("TypeError", classifier_input)
        healing_mock.assert_not_called()
        eligibility_mock.assert_not_called()

    def test_test_script_issue_preview(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="AssertionError: expected true\ntests/example.spec.ts:12"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(return_value=classifier_result("test_script_issue", confidence_percentage=72.5)),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"]["root_cause"], "test_script_issue")
        self.assertEqual(response.json()["classification"]["confidence"], 0.725)

    def test_non_application_root_cause_preview(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="npm ERR! ERESOLVE unable to resolve dependency tree"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(return_value=classifier_result("dependency_issue", confidence_percentage=91.0)),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"]["root_cause"], "dependency_issue")
        self.assertEqual(response.json()["classification"]["confidence"], 0.91)

    def test_job_does_not_belong_to_run_is_rejected(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(998, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=Mock(),
        ) as download_mock, patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(),
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 404)
        download_mock.assert_not_called()
        classifier_mock.assert_not_called()

    def test_successful_job_is_rejected(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="success")]),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(),
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 400)
        classifier_mock.assert_not_called()

    def test_skipped_job_is_rejected(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="skipped")]),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(),
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 400)
        classifier_mock.assert_not_called()

    def test_missing_authorization_is_rejected(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(
                side_effect=ProjectConfigurationError(
                    "Authorization is required to load project GitHub configuration.",
                    status_code=401,
                )
            ),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify")
            )

        self.assertEqual(response.status_code, 401)

    def test_missing_project_config_is_rejected(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(
                side_effect=ProjectConfigurationError(
                    "GitHub configuration is not configured for this project.",
                    status_code=400,
                )
            ),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 400)

    def test_github_log_acquisition_failure_is_safe(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(
                side_effect=GitHubActionsApiError(
                    "GitHub job log was not found or is no longer available.",
                    status_code=404,
                )
            ),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(),
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(TOKEN, response.text)
        classifier_mock.assert_not_called()

    def test_empty_evidence_is_handled_safely(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value=""),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(),
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 422)
        classifier_mock.assert_not_called()

    def test_candidate_file_and_line_remain_null_when_unknown(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="ERROR: failed without location"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(return_value=classifier_result("other_or_unknown", confidence_percentage=61.0)),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["evidence"]["candidate_file"])
        self.assertIsNone(body["evidence"]["candidate_line"])
        self.assertIsNone(body["classifier_input_summary"]["candidate_file"])
        self.assertIsNone(body["classifier_input_summary"]["candidate_line"])

    def test_no_database_or_repair_side_effect_flags(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="TypeError: bad value\n/home/runner/work/project/project/src/example.ts:82:4"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(return_value=classifier_result("application_defect")),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["saved_to_db"])
        self.assertFalse(body["healing_invoked"])
        self.assertFalse(body["repair_eligibility_evaluated"])
        self.assertFalse(body["repair_agent_invoked"])

    def test_legacy_resolve_requires_scope(self):
        response = self.client.post(
            "/api/github/actions/resolve",
            headers={"Authorization": "Bearer user-jwt"},
            json={
                "project_id": PROJECT_ID,
                "run_url": "https://github.com/example/project/actions/runs/12345",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_legacy_resolve_rejects_project_scope_mismatch(self):
        other_project = "33333333-3333-3333-3333-333333333333"
        response = self.client.post(
            self.scoped_url("/api/github/actions/resolve"),
            headers={"Authorization": "Bearer user-jwt"},
            json={
                "project_id": other_project,
                "run_url": "https://github.com/example/project/actions/runs/12345",
            },
        )

        self.assertEqual(response.status_code, 400)


class GitHubActionsAutoHealBranchGuardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.config = ProjectGitHubConfiguration(
            repository_url="https://github.com/example/project",
            repository_owner="example",
            repository_name="project",
            repository_full_name="example/project",
            token=TOKEN,
        )

    def scoped_url(self, path):
        return f"{path}?organization_id={ORG_ID}&project_id={PROJECT_ID}"

    def test_failed_runs_excludes_only_auto_heal_branches(self):
        main_run = {**normalized_run(), "run_id": 101, "head_branch": "main"}
        feature_run = {**normalized_run(), "run_id": 102, "head_branch": "feature/login-fix"}
        auto_heal_run = {
            **normalized_run(),
            "run_id": 103,
            "head_branch": "auto-heal/repair-c5fe03-syntaxerror",
        }

        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_failed_runs",
            new=AsyncMock(return_value=[main_run, feature_run, auto_heal_run]),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/failed-runs"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        returned_ids = [run["run_id"] for run in response.json()["runs"]]
        self.assertEqual(returned_ids, [101, 102])

    def test_read_only_evidence_allows_auto_heal_branch_for_diagnostics(self):
        auto_heal_run = {
            **normalized_run(),
            "head_branch": "auto-heal/repair-c5fe03-syntaxerror",
        }
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=auto_heal_run),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="TypeError: bad\n/home/runner/work/project/project/app/user_service.py:1:1"),
        ):
            response = self.client.get(
                self.scoped_url("/api/github/actions/runs/12345/evidence"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["failed_jobs"][0]["evidence"]["candidate_file"],
            "app/user_service.py",
        )

    def test_read_only_classify_allows_auto_heal_branch_for_diagnostics(self):
        auto_heal_run = {
            **normalized_run(),
            "head_branch": "auto-heal/repair-c5fe03-syntaxerror",
        }
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=auto_heal_run),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(999, conclusion="failure")]),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value="TypeError: bad\n/home/runner/work/project/project/app/user_service.py:1:1"),
        ), patch(
            "app.routers.github_actions.root_cause_service.analyze",
            new=Mock(return_value=classifier_result("application_defect", confidence_percentage=78.0)),
        ):
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/classify"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"]["root_cause"], "application_defect")
        self.assertFalse(response.json()["saved_to_db"])

class FakePipelineDatabase:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, _value):
        return None


class GitHubActionsAnalyzeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.database = FakePipelineDatabase()
        app.dependency_overrides[get_db] = lambda: self.database
        self.config = ProjectGitHubConfiguration(
            repository_url="https://github.com/example/project",
            repository_owner="example",
            repository_name="project",
            repository_full_name="example/project",
            token=TOKEN,
        )

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)

    def scoped_url(self, path):
        return f"{path}?organization_id={ORG_ID}&project_id={PROJECT_ID}"

    def _run_analyze(self, *, classification=None, log_text=None, run=None, jobs=None):
        classification = classification or classifier_result("application_defect", confidence_percentage=75.8)
        log_text = log_text or (
            "TypeError: bad value\n"
            "/home/runner/work/project/project/app/user_service.py:1:1\n"
            f"temporary={SIGNED_LOG_URL}\n"
            f"token={TOKEN}"
        )
        run = run or normalized_run()
        jobs = jobs or [normalized_job(999, conclusion="failure")]
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=run),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=jobs),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(return_value=log_text),
        ), patch(
            "app.routers.analyze.root_cause_service.analyze",
            return_value=classification,
        ) as classifier_mock, patch(
            "app.services.repair_agent_client.repair_agent_client.create_plan",
            new=AsyncMock(),
        ) as plan_mock, patch(
            "app.services.repair_agent_client.repair_agent_client.publish_plan",
            new=AsyncMock(),
        ) as publish_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/analyze"),
                headers={"Authorization": "Bearer user-jwt"},
            )
        return response, classifier_mock, plan_mock, publish_mock

    def test_successful_github_failed_job_runs_full_c3_analysis(self):
        response, classifier_mock, plan_mock, publish_mock = self._run_analyze()

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["source"], "github_actions")
        self.assertEqual(body["github"]["repository"], "example/project")
        self.assertEqual(body["evidence"]["candidate_file"], "app/user_service.py")
        self.assertEqual(body["evidence"]["candidate_line"], 1)
        self.assertEqual(body["classification"]["root_cause"], "application_defect")
        self.assertEqual(body["repair"]["mode"], "read_only")
        self.assertTrue(body["repair"]["eligible"])
        self.assertTrue(body["analysis"]["saved_to_db"])
        self.assertEqual(self.database.commits, 1)
        self.assertTrue(any(isinstance(item, Failure) for item in self.database.added))
        self.assertTrue(any(isinstance(item, HealingAction) for item in self.database.added))
        attempt = next(item for item in self.database.added if isinstance(item, RepairAttempt))
        self.assertEqual(attempt.candidate_file, "app/user_service.py")
        self.assertEqual(attempt.candidate_line, 1)
        self.assertTrue(attempt.eligible)
        self.assertNotIn("/home/runner/work", attempt.candidate_file)
        self.assertNotIn("/home/runner/work", str(body["evidence"]["candidate_file"]))
        self.assertNotIn(TOKEN, response.text)
        self.assertNotIn(SIGNED_LOG_URL, response.text)
        classifier_mock.assert_called_once()
        plan_mock.assert_not_called()
        publish_mock.assert_not_called()

    def test_low_confidence_application_defect_uses_existing_manual_review_gate(self):
        response, _, plan_mock, publish_mock = self._run_analyze(
            classification=classifier_result("application_defect", confidence_percentage=55.0)
        )

        self.assertEqual(response.status_code, 200)
        repair = response.json()["repair"]
        self.assertFalse(repair["eligible"])
        self.assertEqual(repair["status"], "ineligible")
        self.assertEqual(repair["status"], "ineligible")
        self.assertEqual(response.json()["analysis"]["pipeline"]["healing_plan"]["action"], "manual_review")
        plan_mock.assert_not_called()
        publish_mock.assert_not_called()

    def test_existing_non_code_repair_policy_paths_are_reused(self):
        cases = {
            "test_script_issue": "send_to_test_script_component",
            "dependency_issue": "prepare_dependency_fix",
            "network_issue": "retry_pipeline",
            "security_policy_issue": "block_and_security_review",
        }
        for root_cause, expected_action in cases.items():
            with self.subTest(root_cause=root_cause):
                self.database = FakePipelineDatabase()
                app.dependency_overrides[get_db] = lambda db=self.database: db
                response, _, _, _ = self._run_analyze(
                    classification=classifier_result(root_cause, confidence_percentage=88.0)
                )

                self.assertEqual(response.status_code, 200)
                repair = response.json()["repair"]
                self.assertFalse(repair["eligible"])
                self.assertEqual(repair["recommended_action"], response.json()["analysis"]["pipeline"]["healing_plan"]["recommended_action"])
                self.assertEqual(response.json()["analysis"]["pipeline"]["healing_plan"]["action"], expected_action)

    def test_full_analyze_feature_branch_still_works(self):
        run = {**normalized_run(), "head_branch": "feature/login-fix"}
        response, _, plan_mock, publish_mock = self._run_analyze(run=run)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["github"]["head_branch"], "feature/login-fix")
        self.assertTrue(response.json()["repair"]["eligible"])
        plan_mock.assert_not_called()
        publish_mock.assert_not_called()

    def test_full_analyze_auto_heal_branch_is_rejected_without_persistence(self):
        auto_heal_run = {
            **normalized_run(),
            "head_branch": "auto-heal/repair-c5fe03-syntaxerror",
        }
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=auto_heal_run),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(),
        ) as jobs_mock, patch(
            "app.routers.github_actions.GitHubActionsService.download_job_log",
            new=AsyncMock(),
        ) as log_mock, patch(
            "app.routers.analyze.root_cause_service.analyze",
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/analyze"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("repair branch", response.json()["detail"])
        self.assertEqual(self.database.added, [])
        self.assertEqual(self.database.commits, 0)
        jobs_mock.assert_not_called()
        log_mock.assert_not_called()
        classifier_mock.assert_not_called()
    def test_invalid_sha_remains_ineligible(self):
        run = {**normalized_run(), "head_sha": "not-a-sha"}
        response, _, _, _ = self._run_analyze(run=run)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["repair"]["eligible"])
        self.assertIn("SHA", response.json()["repair"]["reason"])

    def test_missing_branch_remains_ineligible(self):
        run = {**normalized_run(), "head_branch": None}
        response, _, _, _ = self._run_analyze(run=run)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["repair"]["eligible"])
        self.assertIn("branch", response.json()["repair"]["reason"].lower())

    def test_protected_source_path_remains_ineligible(self):
        response, _, _, _ = self._run_analyze(
            log_text="TypeError: bad\n/home/runner/work/project/project/auth/login.py:1:1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evidence"]["candidate_file"], "auth/login.py")
        self.assertFalse(response.json()["repair"]["eligible"])
        self.assertIn("protected", response.json()["repair"]["reason"].lower())

    def test_missing_candidate_line_remains_ineligible(self):
        response, _, _, _ = self._run_analyze(log_text="TypeError: bad value without location")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["evidence"]["candidate_line"])
        self.assertFalse(response.json()["repair"]["eligible"])

    def test_wrong_job_or_run_is_rejected_before_analysis(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(return_value=normalized_run()),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.list_jobs_for_run",
            new=AsyncMock(return_value=[normalized_job(998, conclusion="failure")]),
        ), patch(
            "app.routers.analyze.root_cause_service.analyze",
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/analyze"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 404)
        classifier_mock.assert_not_called()

    def test_repository_mismatch_is_rejected_before_analysis(self):
        with patch(
            "app.routers.github_actions.project_configuration_client.get_project_github_configuration",
            new=AsyncMock(return_value=self.config),
        ), patch(
            "app.routers.github_actions.GitHubActionsService.get_run",
            new=AsyncMock(
                side_effect=GitHubActionsApiError(
                    "GitHub returned metadata for a different repository.",
                    status_code=409,
                )
            ),
        ), patch(
            "app.routers.analyze.root_cause_service.analyze",
        ) as classifier_mock:
            response = self.client.post(
                self.scoped_url("/api/github/actions/runs/12345/jobs/999/analyze"),
                headers={"Authorization": "Bearer user-jwt"},
            )

        self.assertEqual(response.status_code, 409)
        classifier_mock.assert_not_called()

    def test_repeated_analysis_creates_separate_safe_analysis_records(self):
        first, _, _, _ = self._run_analyze()
        second, _, _, _ = self._run_analyze()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        attempts = [item for item in self.database.added if isinstance(item, RepairAttempt)]
        self.assertEqual(len(attempts), 2)
        self.assertNotEqual(attempts[0].attempt_id, attempts[1].attempt_id)
        self.assertFalse(attempts[0].github_changes_made)
        self.assertFalse(attempts[1].github_changes_made)

if __name__ == "__main__":
    unittest.main()




