import unittest
from types import SimpleNamespace

from app.services.repair_publish_service import (
    PublishSafetyError,
    prepare_publish_request,
)
from tests.test_repairs_router import plan


def attempt():
    return SimpleNamespace(
        attempt_id="REPAIR-4CD693ABC",
        eligible=True,
        predicted_root_cause="application_defect",
        confidence=0.81,
        decision_source="machine_learning",
        selected_action="start_mcp_code_repair",
        repository_owner="example",
        repository_name="project",
        run_id=123,
        head_sha="a" * 40,
        head_branch="main",
        default_branch="main",
        error_type="SyntaxError",
        candidate_file="app/user_service.py",
        candidate_line=10,
        repair_plan=plan().model_dump(mode="json"),
        github_changes_made=False,
    )


class RepairPublishServiceTests(unittest.TestCase):
    def test_builds_request_only_from_stored_attempt(self):
        value = attempt()
        value.repair_plan["root_cause_confirmed"] = False
        publish_request, checks = prepare_publish_request(
            value,
            allowed_repositories_value="example/project",
            max_files=2,
        )

        self.assertEqual(publish_request.base_sha, "a" * 40)
        self.assertEqual(publish_request.failed_branch, "main")
        self.assertEqual(
            publish_request.proposed_changes[0].after_excerpt,
            "return User(name=name)",
        )
        self.assertEqual(
            checks["branch_head_matches_failed_sha"],
            "pending_mcp_verification",
        )

    def test_legacy_plan_has_clear_schema_error(self):
        value = attempt()
        del value.repair_plan["repairable"]

        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )

        self.assertEqual(raised.exception.code, "legacy_plan_schema")
        self.assertIn("repairable", raised.exception.missing_field_names)
        self.assertEqual(
            raised.exception.safe_message,
            "This repair plan was created with an older schema. "
            "Please rerun Start Controlled Repair.",
        )

    def test_rejects_missing_proposed_changes(self):
        value = attempt()
        value.repair_plan["proposed_changes"] = []
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "missing_proposed_changes")
        self.assertFalse(raised.exception.flags["has_proposed_changes"])

    def test_rejects_plan_that_reports_github_changes(self):
        value = attempt()
        value.repair_plan["github_changes_made"] = True
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "already_published")
        self.assertTrue(raised.exception.flags["github_changes_made"])

    def test_rejects_missing_before_excerpt(self):
        value = attempt()
        del value.repair_plan["proposed_changes"][0]["before_excerpt"]
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "legacy_plan_schema")
        self.assertIn(
            "before_excerpt",
            raised.exception.missing_field_names,
        )

    def test_rejects_missing_after_excerpt(self):
        value = attempt()
        value.repair_plan["proposed_changes"][0]["after_excerpt"] = ""
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "missing_after_excerpt")
        self.assertIn(
            "after_excerpt",
            raised.exception.missing_field_names,
        )

    def test_rejects_protected_and_traversal_paths(self):
        for unsafe in (".env", "../app/user_service.py"):
            value = attempt()
            value.candidate_file = unsafe
            with self.assertRaises(PublishSafetyError):
                prepare_publish_request(
                    value,
                    allowed_repositories_value="example/project",
                    max_files=2,
                )

    def test_rejects_changed_file_mismatch(self):
        value = attempt()
        value.candidate_file = "app/other.py"
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "changed_file_mismatch")

    def test_rejects_more_than_max_files(self):
        value = attempt()
        stored = plan().model_dump(mode="json")
        second = dict(stored["proposed_changes"][0])
        second["file_path"] = "app/second.py"
        stored["proposed_changes"].append(second)
        stored["inspected_files"].append("app/second.py")
        value.repair_plan = stored
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=1,
            )
        self.assertEqual(
            raised.exception.code,
            "changed_file_limit_exceeded",
        )

    def test_rejects_already_published_attempt(self):
        value = attempt()
        value.github_changes_made = True
        with self.assertRaises(PublishSafetyError) as raised:
            prepare_publish_request(
                value,
                allowed_repositories_value="example/project",
                max_files=2,
            )
        self.assertEqual(raised.exception.code, "already_published")


if __name__ == "__main__":
    unittest.main()
