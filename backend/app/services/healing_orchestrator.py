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
            "validation_guidance": [],
            "github_changes_made": False,
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
            "validation_guidance": [],
            "github_changes_made": False,
        },
        "network_issue": {
            "action": "retry_pipeline",
            "automation_level": "diagnostic_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Treat as possible transient failure. Retry workflow and "
                "check DNS, timeout, external API availability, and rate limits."
            ),
            "notification_required": False,
            "target_team_or_module": "External Service / Network Owner",
            "history_status": "retry_recommended",
            "validation_guidance": [
                "Retry the failed workflow once.",
                "Check DNS, timeout, API availability, and rate limits.",
            ],
            "github_changes_made": False,
        },
        "dependency_issue": {
            "action": "prepare_dependency_fix",
            "automation_level": "diagnostic_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Review missing dependency, version conflict, lockfile "
                "mismatch, or package installation failure."
            ),
            "notification_required": True,
            "target_team_or_module": "Dependency / Build Owner",
            "history_status": "dependency_review_required",
            "validation_guidance": [
                "pip install -r requirements.txt",
                "npm install",
                "npm test",
            ],
            "github_changes_made": False,
        },
        "workflow_environment_issue": {
            "action": "prepare_workflow_fix",
            "automation_level": "notification_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Review GitHub Actions runner, workflow YAML, runtime version, "
                "working directory, cache path, and environment configuration."
            ),
            "notification_required": True,
            "target_team_or_module": "CI/CD Workflow Owner",
            "history_status": "workflow_environment_review_required",
            "validation_guidance": [
                "Review workflow syntax and runner/runtime configuration.",
                "Verify working directory, cache paths, and environment names.",
            ],
            "github_changes_made": False,
        },
        "infrastructure_resource_issue": {
            "action": "retry_or_resource_review",
            "automation_level": "notification_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Review CI runner memory, disk, CPU, timeout, job parallelism, "
                "and cache usage."
            ),
            "notification_required": True,
            "target_team_or_module": "Infrastructure / Runner Owner",
            "history_status": "infrastructure_review_required",
            "validation_guidance": [
                "Review runner resource metrics and job timeout settings.",
            ],
            "github_changes_made": False,
        },
        "deployment_issue": {
            "action": "rollback_or_manual_review",
            "automation_level": "notification_only",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Review deployment configuration, target environment, cloud "
                "CLI authentication, permissions, and deployment variables."
            ),
            "notification_required": True,
            "target_team_or_module": "Deployment Owner",
            "history_status": "deployment_review_required",
            "validation_guidance": [
                "Verify deployment target, credentials, permissions, and variables.",
            ],
            "github_changes_made": False,
        },
        "security_policy_issue": {
            "action": "block_and_security_review",
            "automation_level": "manual_review_required",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Review policy violation, permission restriction, secret "
                "scanning result, dependency vulnerability, or compliance "
                "rule. Do not auto-fix."
            ),
            "notification_required": True,
            "target_team_or_module": "Security / Compliance Owner",
            "history_status": "security_review_required",
            "validation_guidance": [
                "Require security or compliance owner review before rerun.",
            ],
            "github_changes_made": False,
        },
        "other_or_unknown": {
            "action": "manual_review",
            "automation_level": "manual_triage_required",
            "allowed_to_plan": False,
            "allowed_to_publish": False,
            "recommended_action": (
                "Manual inspection required because the root cause is unknown "
                "or confidence is insufficient."
            ),
            "notification_required": False,
            "target_team_or_module": "Developer / Manual Triage",
            "history_status": "manual_triage_required",
            "validation_guidance": [
                "Inspect sanitized failure evidence and assign an owner manually.",
            ],
            "github_changes_made": False,
        },
    }

    AUTOMATIC_ACTIONS = set()

    VALIDATION_REQUIRED_ACTIONS = {
        "start_mcp_code_repair",
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
