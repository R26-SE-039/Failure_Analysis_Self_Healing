import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.models.failure import Failure
from app.models.repair_attempt import RepairAttempt
from app.models.test_script_notification_audit import (
    TestScriptNotificationAudit,
)
from app.models.root_cause_action_audit import RootCauseActionAudit
from app.routers.analyze import analyze_failure
from tests.test_classifier_regression import _frontend_request


FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "0_test.txt"
)


class FakeDatabase:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def refresh(self, _value):
        return None


class AnalysisRepairIntegrationTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_existing_analysis_creates_read_only_attempt(self):
        raw_log = FIXTURE_PATH.read_text(encoding="utf-8")
        request = _frontend_request(raw_log)
        request.github_actions_run_url = (
            "https://github.com/example/demo/actions/runs/123"
        )
        source_run = {
            "owner": "example",
            "repository": "demo",
            "repository_full_name": "example/demo",
            "run_id": 123,
            "run_url": request.github_actions_run_url,
            "head_sha": "a" * 40,
            "head_branch": "feature/failure",
            "default_branch": "main",
            "workflow_name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "run_attempt": 1,
        }
        database = FakeDatabase()

        with (
            patch.dict(
                os.environ,
                {"GITHUB_ALLOWED_REPOSITORIES": "example/demo"},
            ),
            patch(
                "app.routers.analyze.github_actions_service.resolve_run",
                new=AsyncMock(return_value=source_run),
            ),
        ):
            result = await analyze_failure(request, database)

        self.assertEqual(
            result["pipeline"]["classification"]["root_cause"],
            "application_defect",
        )
        self.assertTrue(result["pipeline"]["repair"]["eligible"])
        self.assertEqual(
            result["pipeline"]["repair"]["mode"],
            "read_only",
        )
        self.assertFalse(
            result["pipeline"]["repair"]["github_changes_made"]
        )

        attempt = next(
            item
            for item in database.added
            if isinstance(item, RepairAttempt)
        )
        failure = next(
            item
            for item in database.added
            if isinstance(item, Failure)
        )
        self.assertEqual(
            attempt.log_content_sha256,
            hashlib.sha256(raw_log.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(attempt.candidate_file, "app/user_service.py")
        self.assertEqual(attempt.candidate_line, 10)
        self.assertLess(len(attempt.sanitized_log_excerpt), len(raw_log))
        self.assertNotEqual(failure.logs, raw_log)
        self.assertFalse(attempt.github_changes_made)

    async def test_test_script_issue_records_notification_only(self):
        raw_log = FIXTURE_PATH.read_text(encoding="utf-8")
        request = _frontend_request(raw_log)
        request.github_actions_run_url = (
            "https://github.com/example/demo/actions/runs/456"
        )
        source_run = {
            "owner": "example",
            "repository": "demo",
            "repository_full_name": "example/demo",
            "run_id": 456,
            "run_url": request.github_actions_run_url,
            "head_sha": "c" * 40,
            "head_branch": "main",
            "default_branch": "main",
        }
        classification = {
            "final_root_cause": "test_script_issue",
            "final_confidence_percentage": 88.0,
            "ml_confidence_percentage": 88.0,
            "ml_prediction": "test_script_issue",
            "decision_source": "machine_learning",
            "decision_reason": "Selected by the trained model.",
            "probabilities": {"test_script_issue": 88.0},
            "detected_error": {
                "error_type": "FixtureError",
                "error_message": "fixture missing",
                "failed_file": "tests/test_user_service.py",
                "failed_line": "6",
            },
            "model_input_sha256": "d" * 64,
        }
        database = FakeDatabase()

        with (
            patch(
                "app.routers.analyze.github_actions_service.resolve_run",
                new=AsyncMock(return_value=source_run),
            ),
            patch(
                "app.routers.analyze.root_cause_service.analyze",
                return_value=classification,
            ),
        ):
            result = await analyze_failure(request, database)

        attempt = next(
            item for item in database.added if isinstance(item, RepairAttempt)
        )
        notification = next(
            item
            for item in database.added
            if isinstance(item, TestScriptNotificationAudit)
        )
        self.assertFalse(attempt.eligible)
        self.assertEqual(attempt.status, "notification_sent")
        self.assertFalse(attempt.github_changes_made)
        self.assertIsNone(attempt.repair_plan)
        self.assertEqual(notification.status, "notification_sent")
        self.assertEqual(
            notification.target_module,
            "Test Script Generation Module",
        )
        self.assertEqual(
            result["pipeline"]["notification"]["status"],
            "notification_sent",
        )
        self.assertFalse(
            result["pipeline"]["repair"]["allowed_to_plan"]
        )
        self.assertFalse(
            result["pipeline"]["repair"]["allowed_to_publish"]
        )
        serialized = str(result["pipeline"]["notification"])
        self.assertNotIn(raw_log, serialized)
        self.assertNotIn("token", serialized.lower())

    async def test_remaining_root_causes_record_safe_action_statuses(self):
        expected = {
            "dependency_issue": "dependency_review_required",
            "workflow_environment_issue": (
                "workflow_environment_review_required"
            ),
            "network_issue": "retry_recommended",
            "infrastructure_resource_issue": (
                "infrastructure_review_required"
            ),
            "deployment_issue": "deployment_review_required",
            "security_policy_issue": "security_review_required",
            "other_or_unknown": "manual_triage_required",
        }
        for root_cause, expected_status in expected.items():
            with self.subTest(root_cause=root_cause):
                request = _frontend_request("sanitized test evidence")
                classification = {
                    "final_root_cause": root_cause,
                    "final_confidence_percentage": 84.0,
                    "ml_confidence_percentage": 84.0,
                    "ml_prediction": root_cause,
                    "decision_source": "machine_learning",
                    "probabilities": {root_cause: 84.0},
                    "detected_error": {
                        "error_type": "BuildError",
                        "error_message": "sanitized failure",
                        "failed_file": "unknown",
                        "failed_line": "unknown",
                    },
                    "model_input_sha256": "e" * 64,
                }
                database = FakeDatabase()
                with patch(
                    "app.routers.analyze.root_cause_service.analyze",
                    return_value=classification,
                ):
                    result = await analyze_failure(request, database)

                attempt = next(
                    item
                    for item in database.added
                    if isinstance(item, RepairAttempt)
                )
                action = next(
                    item
                    for item in database.added
                    if isinstance(item, RootCauseActionAudit)
                )
                self.assertEqual(attempt.status, expected_status)
                self.assertFalse(attempt.eligible)
                self.assertFalse(attempt.github_changes_made)
                self.assertIsNone(attempt.repair_plan)
                self.assertEqual(action.history_status, expected_status)
                self.assertFalse(action.github_changes_made)
                self.assertEqual(
                    result["pipeline"]["notification"]["status"],
                    expected_status,
                )
                safe_result = str(result["pipeline"]["notification"])
                self.assertNotIn("sanitized test evidence", safe_result)
                self.assertNotIn("token", safe_result.lower())


if __name__ == "__main__":
    unittest.main()
