import unittest

from app.services.repair_eligibility_service import (
    RepairEligibilityService,
    is_protected_path,
)


def classification():
    return {
        "root_cause": "application_defect",
        "confidence": 0.811086427989913,
        "decision_source": "machine_learning",
    }


def healing_plan():
    return {
        "action": "start_mcp_code_repair",
        "confidence_gate_applied": False,
    }


def source_run():
    return {
        "repository_full_name": "example/project",
        "head_sha": "a" * 40,
        "head_branch": "main",
    }


class RepairEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.service = RepairEligibilityService(
            {"example/project"}
        )

    def test_allows_verified_application_defect(self):
        result = self.service.evaluate(
            classification=classification(),
            healing_plan=healing_plan(),
            source_run=source_run(),
            candidate_file="app/user_service.py",
            candidate_line=10,
        )
        self.assertTrue(result.eligible)


    def test_allows_project_configured_repository_without_env_allowlist(self):
        service = RepairEligibilityService({"example/project"})

        result = service.evaluate(
            classification=classification(),
            healing_plan=healing_plan(),
            source_run=source_run(),
            candidate_file="app/user_service.py",
            candidate_line=10,
        )

        self.assertTrue(result.eligible)

    def test_non_application_defect_remains_blocked_even_when_repo_matches(self):
        service = RepairEligibilityService({"example/project"})
        cls = classification()
        cls["root_cause"] = "dependency_issue"

        result = service.evaluate(
            classification=cls,
            healing_plan=healing_plan(),
            source_run=source_run(),
            candidate_file="app/user_service.py",
            candidate_line=10,
        )

        self.assertFalse(result.eligible)
        self.assertEqual(result.code, "wrong_root_cause")

    def test_rejects_missing_metadata_and_protected_path(self):
        missing = self.service.evaluate(
            classification=classification(),
            healing_plan=healing_plan(),
            source_run=None,
            candidate_file="app/user_service.py",
            candidate_line=10,
        )
        protected = self.service.evaluate(
            classification=classification(),
            healing_plan=healing_plan(),
            source_run=source_run(),
            candidate_file="auth/login.py",
            candidate_line=10,
        )
        missing_line = self.service.evaluate(
            classification=classification(),
            healing_plan=healing_plan(),
            source_run=source_run(),
            candidate_file="app/user_service.py",
            candidate_line=None,
        )

        self.assertFalse(missing.eligible)
        self.assertFalse(protected.eligible)
        self.assertFalse(missing_line.eligible)
        self.assertTrue(is_protected_path("../secret.py"))

    def test_rejects_disallowed_repository_and_bad_sha(self):
        disallowed_run = source_run()
        disallowed_run["repository_full_name"] = (
            "other/project"
        )
        bad_sha_run = source_run()
        bad_sha_run["head_sha"] = "abc123"

        self.assertFalse(
            self.service.evaluate(
                classification=classification(),
                healing_plan=healing_plan(),
                source_run=disallowed_run,
                candidate_file="app/user_service.py",
                candidate_line=10,
            ).eligible
        )
        self.assertFalse(
            self.service.evaluate(
                classification=classification(),
                healing_plan=healing_plan(),
                source_run=bad_sha_run,
                candidate_file="app/user_service.py",
                candidate_line=10,
            ).eligible
        )


if __name__ == "__main__":
    unittest.main()
