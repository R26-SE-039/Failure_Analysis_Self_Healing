import unittest

from app.services.healing_orchestrator import HealingOrchestrator


class HealingOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = HealingOrchestrator()

    def test_required_routes(self):
        expected_routes = {
            "application_defect": "start_mcp_code_repair",
            "test_script_issue": "send_to_test_script_component",
            "workflow_environment_issue": "prepare_workflow_fix",
        }

        for root_cause, expected_action in expected_routes.items():
            with self.subTest(root_cause=root_cause):
                plan = self.orchestrator.create_plan(
                    {
                        "final_root_cause": root_cause,
                        "ml_confidence_percentage": 92,
                        "decision_source": "machine_learning",
                    }
                )
                self.assertEqual(plan["action"], expected_action)
                self.assertFalse(plan["confidence_gate_applied"])

    def test_application_defect_policy_preserves_controlled_repair(self):
        plan = self.orchestrator.create_plan(
            {
                "final_root_cause": "application_defect",
                "ml_confidence_percentage": 81,
                "decision_source": "machine_learning",
            }
        )

        self.assertTrue(plan["allowed_to_plan"])
        self.assertTrue(plan["allowed_to_publish"])
        self.assertEqual(plan["automation_level"], "controlled_draft_pr")

    def test_test_script_policy_is_notification_only(self):
        plan = self.orchestrator.create_plan(
            {
                "final_root_cause": "test_script_issue",
                "ml_confidence_percentage": 92,
                "decision_source": "machine_learning",
            }
        )

        self.assertFalse(plan["allowed_to_plan"])
        self.assertFalse(plan["allowed_to_publish"])
        self.assertFalse(plan["automatic_execution_allowed"])
        self.assertEqual(plan["automation_level"], "notification_only")
        self.assertTrue(plan["notification_required"])
        self.assertEqual(
            plan["target_team_or_module"],
            "Test Script Generation Module",
        )
        self.assertEqual(plan["history_status"], "notification_sent")

    def test_remaining_root_cause_policy_matrix(self):
        expected = {
            "dependency_issue": (
                "diagnostic_only",
                "dependency_review_required",
                "Dependency / Build Owner",
            ),
            "workflow_environment_issue": (
                "notification_only",
                "workflow_environment_review_required",
                "CI/CD Workflow Owner",
            ),
            "network_issue": (
                "diagnostic_only",
                "retry_recommended",
                "External Service / Network Owner",
            ),
            "infrastructure_resource_issue": (
                "notification_only",
                "infrastructure_review_required",
                "Infrastructure / Runner Owner",
            ),
            "deployment_issue": (
                "notification_only",
                "deployment_review_required",
                "Deployment Owner",
            ),
            "security_policy_issue": (
                "manual_review_required",
                "security_review_required",
                "Security / Compliance Owner",
            ),
            "other_or_unknown": (
                "manual_triage_required",
                "manual_triage_required",
                "Developer / Manual Triage",
            ),
        }
        for root_cause, values in expected.items():
            with self.subTest(root_cause=root_cause):
                plan = self.orchestrator.create_plan(
                    {
                        "final_root_cause": root_cause,
                        "ml_confidence_percentage": 90,
                        "decision_source": "machine_learning",
                    }
                )
                automation, history, target = values
                self.assertEqual(plan["automation_level"], automation)
                self.assertEqual(plan["history_status"], history)
                self.assertEqual(plan["target_team_or_module"], target)
                self.assertFalse(plan["allowed_to_plan"])
                self.assertFalse(plan["allowed_to_publish"])
                self.assertFalse(plan["github_changes_made"])
                self.assertTrue(plan["recommended_action"])
                self.assertIsInstance(plan["validation_guidance"], list)

    def test_low_confidence_preserves_class_but_gates_action(self):
        plan = self.orchestrator.create_plan(
            {
                "final_root_cause": "application_defect",
                "ml_confidence_percentage": 52.2,
                "decision_source": "machine_learning",
            }
        )

        self.assertEqual(plan["root_cause"], "application_defect")
        self.assertEqual(plan["action"], "manual_review")
        self.assertTrue(plan["confidence_gate_applied"])
        self.assertFalse(plan["automatic_execution_allowed"])


if __name__ == "__main__":
    unittest.main()
