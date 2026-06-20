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
