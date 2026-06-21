from typing import Any


class HealingOrchestrator:
    ACTION_MATRIX = {
        "application_defect": {
            "action": "start_mcp_code_repair",
            "automation_level": "controlled_draft_pr",
            "allowed_to_plan": True,
            "allowed_to_publish": True,
            "recommended_action": "Start a controlled read-only repair plan.",
            "notification_required": False,
            "target_team_or_module": "Application Development Team",
            "history_status": "eligible",
        },
        "test_script_issue": {
            "action": "send_to_test_script_component",
            "automation_level": "notification_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Forward this failure to the test script generation owner "
                "for inspection/regeneration."
            ),
            "notification_required": True,
            "target_team_or_module": "Test Script Generation Module",
            "history_status": "notification_sent",
        },
        "network_issue": {
            "action": "retry_pipeline",
            "automation_level": "controlled_retry",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Apply the bounded pipeline retry policy.",
            "notification_required": True,
            "target_team_or_module": "DevOps Team",
            "history_status": "suggested",
        },
        "dependency_issue": {
            "action": "prepare_dependency_fix",
            "automation_level": "recommendation_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Review dependency and lockfile evidence.",
            "notification_required": True,
            "target_team_or_module": "Application Development Team",
            "history_status": "suggested",
        },
        "workflow_environment_issue": {
            "action": "prepare_workflow_fix",
            "automation_level": "recommendation_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Review workflow environment configuration.",
            "notification_required": True,
            "target_team_or_module": "DevOps Team",
            "history_status": "suggested",
        },
        "infrastructure_resource_issue": {
            "action": "retry_or_resource_review",
            "automation_level": "manual_review",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Review runner resources and capacity.",
            "notification_required": True,
            "target_team_or_module": "Infrastructure Team",
            "history_status": "manual_review",
        },
        "deployment_issue": {
            "action": "rollback_or_manual_review",
            "automation_level": "manual_review",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Review deployment and rollback safety.",
            "notification_required": True,
            "target_team_or_module": "DevOps Team",
            "history_status": "manual_review",
        },
        "security_policy_issue": {
            "action": "block_and_security_review",
            "automation_level": "blocked",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Block release and request security review.",
            "notification_required": True,
            "target_team_or_module": "Security Team",
            "history_status": "manual_review",
        },
        "other_or_unknown": {
            "action": "manual_review",
            "automation_level": "manual_review",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": "Route this failure for manual review.",
            "notification_required": True,
            "target_team_or_module": "Failure Triage Team",
            "history_status": "manual_review",
        },
    }

    AUTOMATIC_ACTIONS = {
        "retry_pipeline",
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

        policy = dict(
            self.ACTION_MATRIX.get(
                root_cause,
                self.ACTION_MATRIX["other_or_unknown"],
            )
        )
        action = policy["action"]

        confidence_gate_applied = (
            decision_source == "machine_learning"
            and confidence < self.MINIMUM_AUTOMATIC_CONFIDENCE
        )

        if confidence_gate_applied and policy["allowed_to_plan"]:
            action = "manual_review"

        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "decision_source": decision_source,
            "decision_reason": classification.get(
                "decision_reason",
            ),
            "action": action,
            **{
                key: value
                for key, value in policy.items()
                if key != "action"
            },
            "automatic_healing_allowed": (
                policy["allowed_to_plan"] and action != "manual_review"
            ),
            "automatic_execution_allowed":
                action in self.AUTOMATIC_ACTIONS,
            "requires_validation":
                action in self.VALIDATION_REQUIRED_ACTIONS,
            "confidence_gate_applied": confidence_gate_applied,
        }


healing_orchestrator = HealingOrchestrator()
