import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.repairs import get_repair_history


NOW = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_models):
        return FakeQuery(self.rows)


def attempt(**overrides):
    values = {
        "attempt_id": "REPAIR-HISTORY-1",
        "predicted_root_cause": "application_defect",
        "confidence": 0.811,
        "repository_owner": "Example",
        "repository_name": "Project",
        "run_id": 123,
        "head_branch": "main",
        "head_sha": "a" * 40,
        "candidate_file": "app/user_service.py",
        "candidate_line": 10,
        "selected_action": "start_mcp_code_repair",
        "status": "planned",
        "github_changes_made": False,
        "created_at": NOW,
        "updated_at": NOW,
        "error_message": "must never appear",
        "sanitized_log_excerpt": "must never appear",
        "repair_plan": {"before_excerpt": "must never appear"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def audit(**overrides):
    values = {
        "publish_status": "draft_pr_created",
        "repair_branch": "auto-heal/repair-history-syntaxerror",
        "commit_sha": "b" * 40,
        "draft_pr_url": "https://github.com/example/project/pull/1",
        "github_changes_made": True,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def notification_audit(**overrides):
    values = {
        "status": "notification_sent",
        "target_module": "Test Script Generation Module",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RepairHistoryTests(unittest.TestCase):
    def test_returns_only_safe_audit_projection(self):
        result = get_repair_history(
            db=FakeDatabase([(attempt(), audit(), None)])
        )

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item.repository, "example/project")
        self.assertEqual(item.publish_status, "draft_pr_created")
        self.assertEqual(
            item.github_run_url,
            "https://github.com/example/project/actions/runs/123",
        )
        self.assertTrue(item.github_changes_made)
        serialized = item.model_dump_json()
        for forbidden in {
            "error_message",
            "sanitized_log_excerpt",
            "repair_plan",
            "before_excerpt",
            "must never appear",
            "token",
            "prompt",
        }:
            self.assertNotIn(forbidden, serialized)

    def test_filters_root_cause_status_and_repository(self):
        rows = [
            (attempt(), audit(), None),
            (
                attempt(
                    attempt_id="REPAIR-HISTORY-2",
                    predicted_root_cause="test_script_issue",
                    repository_name="Other",
                ),
                None,
                notification_audit(),
            ),
        ]
        database = FakeDatabase(rows)

        by_root = get_repair_history(
            root_cause="application_defect",
            db=database,
        )
        by_status = get_repair_history(
            publish_status="notification_sent",
            db=database,
        )
        by_repository = get_repair_history(
            repository="EXAMPLE/PROJECT",
            db=database,
        )

        self.assertEqual([item.attempt_id for item in by_root], ["REPAIR-HISTORY-1"])
        self.assertEqual([item.attempt_id for item in by_status], ["REPAIR-HISTORY-2"])
        self.assertEqual(
            [item.attempt_id for item in by_repository],
            ["REPAIR-HISTORY-1"],
        )

    def test_notification_only_attempt_has_no_github_changes(self):
        result = get_repair_history(
            db=FakeDatabase(
                [
                    (
                        attempt(
                            predicted_root_cause="test_script_issue",
                            selected_action="send_to_test_script_component",
                            status="notification_sent",
                        ),
                        None,
                        notification_audit(),
                    )
                ]
            )
        )[0]

        self.assertIsNone(result.publish_status)
        self.assertEqual(result.action_status, "notification_sent")
        self.assertEqual(
            result.target_module,
            "Test Script Generation Module",
        )
        self.assertFalse(result.github_changes_made)
        self.assertIsNone(result.repair_branch)
        self.assertIsNone(result.commit_sha)
        self.assertIsNone(result.draft_pr_url)


if __name__ == "__main__":
    unittest.main()
