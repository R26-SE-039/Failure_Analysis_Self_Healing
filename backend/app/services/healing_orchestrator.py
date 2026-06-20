from typing import Any


class HealingOrchestrator:
    ACTIONS = {
        "application_defect": "start_mcp_code_repair",
        "test_script_issue": "send_to_test_script_component",
        "network_issue": "retry_pipeline",
        "dependency_issue": "prepare_dependency_fix",
        "workflow_environment_issue": "prepare_workflow_fix",
        "infrastructure_resource_issue": "retry_or_resource_review",
        "deployment_issue": "rollback_or_manual_review",
        "security_policy_issue": "block_and_security_review",
        "other_or_unknown": "manual_review",
    }

    AUTOMATIC_ACTIONS = {
        "retry_pipeline",
        "send_to_test_script_component",
    }

    VALIDATION_REQUIRED_ACTIONS = {
        "start_mcp_code_repair",
        "prepare_dependency_fix",
        "prepare_workflow_fix",
    }

    MINIMUM_AUTOMATIC_CONFIDENCE = 60.0

    @staticmethod
    def _confidence_percentage(
        classification: dict[str, Any],
    ) -> float:
        confidence = classification.get(
            "final_confidence_percentage",
            classification.get(
                "ml_confidence_percentage",
                classification.get("confidence", 0),
            ),
        )

        confidence = float(confidence or 0)

        if 0 < confidence <= 1:
            return round(confidence * 100, 2)

        return round(confidence, 2)

    def create_plan(
        self,
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        root_cause = classification.get(
            "final_root_cause",
            classification.get("root_cause"),
        )

        if not root_cause:
            raise ValueError(
                "Classification result does not include a root cause."
            )

        confidence = self._confidence_percentage(
            classification
        )

        decision_source = classification.get(
            "decision_source",
            "machine_learning",
        )

        action = self.ACTIONS.get(
            root_cause,
            "manual_review",
        )

        confidence_gate_applied = (
            decision_source == "machine_learning"
            and confidence < self.MINIMUM_AUTOMATIC_CONFIDENCE
        )

        if confidence_gate_applied:
            action = "manual_review"

        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "decision_source": decision_source,
            "decision_reason": classification.get(
                "decision_reason",
            ),
            "action": action,
            "automatic_healing_allowed": action != "manual_review",
            "automatic_execution_allowed":
                action in self.AUTOMATIC_ACTIONS,
            "requires_validation":
                action in self.VALIDATION_REQUIRED_ACTIONS,
            "confidence_gate_applied": confidence_gate_applied,
        }


healing_orchestrator = HealingOrchestrator()
