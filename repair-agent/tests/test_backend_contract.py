import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.schemas.repair import (  # noqa: E402
    ReadOnlyRepairPlan as BackendReadOnlyRepairPlan,
    RepairPlanRequest as BackendRepairPlanRequest,
    RepairPublishRequest as BackendRepairPublishRequest,
    RepairPublishResult as BackendRepairPublishResult,
)
from repair_agent.schemas import (  # noqa: E402
    ReadOnlyRepairPlan as AgentReadOnlyRepairPlan,
    RepairPlanRequest as AgentRepairPlanRequest,
    RepairPublishRequest as AgentRepairPublishRequest,
    RepairPublishResult as AgentRepairPublishResult,
)
from tests.test_publisher import request as publish_request  # noqa: E402


class BackendRepairAgentContractTests(unittest.TestCase):
    def test_real_backend_payload_validates_in_agent_schema(self):
        backend_request = BackendRepairPlanRequest(
            attempt_id="REPAIR-CONTRACT123",
            repository_owner="example",
            repository_name="project",
            run_id=123,
            head_sha="a" * 40,
            head_branch="feature/failure",
            default_branch=None,
            root_cause="application_defect",
            confidence=0.811086427989913,
            decision_source="machine_learning",
            selected_action="start_mcp_code_repair",
            error_type="SyntaxError",
            error_message="'(' was never closed",
            candidate_file="app/user_service.py",
            candidate_line=10,
            sanitized_log_excerpt="SyntaxError at line 10",
        )
        wire_payload = json.loads(
            backend_request.model_dump_json()
        )

        agent_request = AgentRepairPlanRequest.model_validate(
            wire_payload
        )

        self.assertEqual(
            set(BackendRepairPlanRequest.model_fields),
            set(AgentRepairPlanRequest.model_fields),
        )
        self.assertEqual(
            agent_request.model_dump(mode="json"),
            wire_payload,
        )
        self.assertTrue(agent_request.read_only)

    def test_agent_success_envelope_validates_in_backend_schema(self):
        agent_plan = AgentReadOnlyRepairPlan(
            attempt_id="REPAIR-CONTRACT123",
            status="planned",
            model="mock/tool-model",
            root_cause_confirmed=True,
            repairable=True,
            confirmed_failed_file="app/user_service.py",
            confirmed_failed_line=10,
            base_sha="a" * 40,
            inspected_files=["app/user_service.py"],
            proposed_changes=[],
            risks=[],
            suggested_validation_commands=["pytest -q"],
            github_changes_made=False,
        )
        wire_payload = {
            **agent_plan.model_dump(mode="json"),
            "correlation_id": "safe-correlation-123",
        }

        backend_plan = BackendReadOnlyRepairPlan.model_validate(
            wire_payload
        )

        self.assertEqual(
            backend_plan.model_dump(mode="json"),
            wire_payload,
        )
        self.assertFalse(backend_plan.github_changes_made)

    def test_publish_request_and_response_contracts_match(self):
        agent_request = publish_request()
        backend_request = BackendRepairPublishRequest.model_validate(
            agent_request.model_dump(mode="json")
        )
        self.assertEqual(
            set(BackendRepairPublishRequest.model_fields),
            set(AgentRepairPublishRequest.model_fields),
        )
        self.assertEqual(
            backend_request.model_dump(mode="json"),
            agent_request.model_dump(mode="json"),
        )

        agent_result = AgentRepairPublishResult(
            attempt_id=agent_request.attempt_id,
            publish_status="draft_pr_created",
            validation_status="pending",
            repair_branch="auto-heal/repair-4cd693-syntaxerror",
            commit_sha="b" * 40,
            draft_pr_number=17,
            draft_pr_url="https://github.com/example/project/pull/17",
            changed_files=["app/user_service.py"],
            github_changes_made=True,
            automatic_merge_performed=False,
            message="Draft PR created — awaiting developer review",
            merge_message="No automatic merge performed",
        )
        envelope = {
            **agent_result.model_dump(mode="json"),
            "correlation_id": "publish-correlation-123",
        }
        backend_result = BackendRepairPublishResult.model_validate(envelope)
        self.assertEqual(backend_result.model_dump(mode="json"), envelope)


if __name__ == "__main__":
    unittest.main()
