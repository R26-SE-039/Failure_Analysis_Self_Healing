import unittest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.routers.repairs import (
    _validated_plan,
    create_read_only_plan,
)
from app.schemas.repair import (
    ProposedChange,
    ReadOnlyRepairPlan,
    RepairConfirmationRequest,
)
from app.services.repair_agent_client import RepairAgentDownstreamError


def attempt():
    return SimpleNamespace(
        attempt_id="REPAIR-123",
        head_sha="a" * 40,
        candidate_file="app/user_service.py",
        candidate_line=10,
    )


def plan():
    return ReadOnlyRepairPlan(
        correlation_id="safe-correlation-123",
        attempt_id="REPAIR-123",
        status="planned",
        model="mock/tool-model",
        root_cause_confirmed=True,
        repairable=True,
        confirmed_failed_file="app/user_service.py",
        confirmed_failed_line=10,
        base_sha="a" * 40,
        inspected_files=["app/user_service.py"],
        proposed_changes=[
            ProposedChange(
                file_path="app/user_service.py",
                start_line=10,
                end_line=10,
                before_excerpt="return User(name=name",
                after_excerpt="return User(name=name)",
                reason="Close the constructor call.",
            )
        ],
        risks=["Review constructor behavior."],
        suggested_validation_commands=["pytest -q"],
        github_changes_made=False,
    )


def complete_attempt():
    return SimpleNamespace(
        attempt_id="REPAIR-123",
        eligible=True,
        eligibility_reason="Eligible.",
        status="suggested",
        repair_plan=None,
        repository_owner="example",
        repository_name="project",
        run_id=123,
        head_sha="a" * 40,
        head_branch="feature/failure",
        default_branch="main",
        predicted_root_cause="application_defect",
        confidence=0.81,
        decision_source="machine_learning",
        selected_action="start_mcp_code_repair",
        error_type="SyntaxError",
        error_message="A sanitized syntax error.",
        candidate_file="app/user_service.py",
        candidate_line=10,
        sanitized_log_excerpt="Sanitized evidence.",
        inspected_files=None,
        provider_model=None,
        github_changes_made=False,
        failure_reason=None,
    )


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args):
        return self

    def first(self):
        return self.value


class FakeDatabase:
    def __init__(self, value):
        self.value = value
        self.commits = 0

    def query(self, _model):
        return FakeQuery(self.value)

    def commit(self):
        self.commits += 1


class RepairRouterSafetyTests(unittest.TestCase):
    def test_accepts_bounded_read_only_plan(self):
        result = _validated_plan(attempt(), plan())
        self.assertFalse(result.github_changes_made)

    def test_rejects_sha_or_path_mismatch(self):
        bad_sha = plan().model_copy(
            update={"base_sha": "b" * 40}
        )
        protected = plan().model_copy(
            update={"inspected_files": [".env"]}
        )

        with self.assertRaises(ValueError):
            _validated_plan(attempt(), bad_sha)
        with self.assertRaises(ValueError):
            _validated_plan(attempt(), protected)


class RepairConfirmationTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_explicit_confirmation_is_required(self):
        with self.assertRaises(HTTPException) as raised:
            await create_read_only_plan(
                "REPAIR-123",
                RepairConfirmationRequest(
                    confirm_read_only=False,
                ),
                db=SimpleNamespace(),
            )

        self.assertEqual(raised.exception.status_code, 400)

    async def test_successful_plan_is_stored_and_returned(self):
        repair_attempt = complete_attempt()
        database = FakeDatabase(repair_attempt)

        with patch(
            "app.routers.repairs.repair_agent_client.create_plan",
            new=AsyncMock(return_value=plan()),
        ):
            result = await create_read_only_plan(
                repair_attempt.attempt_id,
                RepairConfirmationRequest(
                    confirm_read_only=True,
                ),
                db=database,
            )

        self.assertEqual(result, plan().model_dump())
        self.assertEqual(repair_attempt.repair_plan, result)
        self.assertEqual(repair_attempt.status, "planned")
        self.assertFalse(repair_attempt.github_changes_made)
        self.assertEqual(database.commits, 2)

    async def test_safety_rejection_returns_manual_review_diagnostics(self):
        repair_attempt = complete_attempt()
        database = FakeDatabase(repair_attempt)
        failure = RepairAgentDownstreamError(
            "plan_validation_failed",
            "safe-correlation-123",
            {
                "failed_stage": "plan_safety_validation",
                "failed_check_name": "before_excerpt_mismatch",
                "validation_field_path": [
                    "proposed_changes",
                    0,
                    "before_excerpt",
                ],
                "error_type": "safety_validation_error",
                "proposed_file_path": "app/user_service.py",
                "start_line": 10,
                "end_line": 10,
                "boolean_flags": {
                    "repairable": True,
                    "github_changes_made": False,
                },
            },
        )

        with patch(
            "app.routers.repairs.repair_agent_client.create_plan",
            new=AsyncMock(side_effect=failure),
        ):
            response = await create_read_only_plan(
                repair_attempt.attempt_id,
                RepairConfirmationRequest(confirm_read_only=True),
                db=database,
            )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["error_code"], "plan_validation_failed")
        self.assertEqual(
            body["diagnostics"]["failed_check_name"],
            "before_excerpt_mismatch",
        )
        self.assertEqual(repair_attempt.status, "failed")
        self.assertNotIn("source code", response.body.decode().lower())


if __name__ == "__main__":
    unittest.main()
