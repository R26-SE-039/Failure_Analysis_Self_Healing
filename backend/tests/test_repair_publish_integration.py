import unittest
import json
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.repair_attempt import RepairAttempt
from app.models.repair_publish_audit import RepairPublishAudit
from app.routers.repairs import publish_approved_repair
from app.schemas.repair import (
    PublishConfirmationRequest,
    RepairPublishResult,
)
from app.services.repair_agent_client import RepairPublishError
from tests.test_repair_publish_service import attempt


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.value


class FakeDatabase:
    def __init__(self, repair_attempt):
        self.repair_attempt = repair_attempt
        self.audit = None
        self.commits = 0

    def query(self, model):
        if model is RepairAttempt:
            return FakeQuery(self.repair_attempt)
        if model is RepairPublishAudit:
            return FakeQuery(self.audit)
        raise AssertionError(model)

    def add(self, value):
        if isinstance(value, RepairPublishAudit):
            self.audit = value

    def commit(self):
        self.commits += 1


def result():
    return RepairPublishResult(
        correlation_id="publish-correlation-123",
        attempt_id="REPAIR-4CD693ABC",
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


class RepairPublishIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_frontend_confirmation_rejects_repair_details(self):
        with self.assertRaises(ValidationError):
            PublishConfirmationRequest.model_validate(
                {
                    "confirm_publish": True,
                    "after_excerpt": "must not be trusted",
                }
            )

    async def test_success_stores_sanitized_audit_and_returns_result(self):
        repair_attempt = attempt()
        database = FakeDatabase(repair_attempt)
        with (
            patch.dict(
                "os.environ",
                {
                    "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                    "REPAIR_MAX_FILES": "2",
                },
            ),
            patch(
                "app.routers.repairs.repair_agent_client.publish_plan",
                new=AsyncMock(return_value=result()),
            ),
        ):
            response = await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )

        self.assertEqual(response["publish_status"], "draft_pr_created")
        self.assertEqual(database.audit.commit_sha, "b" * 40)
        self.assertEqual(database.audit.draft_pr_number, 17)
        self.assertTrue(database.audit.github_changes_made)
        self.assertTrue(repair_attempt.github_changes_made)
        self.assertEqual(repair_attempt.status, "awaiting_review")
        self.assertNotIn("token", str(database.audit.__dict__).lower())

    async def test_prewrite_validation_audit_can_retry_after_contract_fix(self):
        repair_attempt = attempt()
        repair_attempt.repair_plan["root_cause_confirmed"] = False
        database = FakeDatabase(repair_attempt)
        database.audit = RepairPublishAudit(
            attempt_id=repair_attempt.attempt_id,
            repository="example/project",
            base_sha="a" * 40,
            failed_branch="main",
            publish_status="manual_review",
            validation_status="failed",
            changed_files=[],
            safety_check_results={"server_validation_passed": False},
            error_code="plan_not_publishable",
            github_changes_made=False,
        )
        with (
            patch.dict(
                "os.environ",
                {
                    "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                    "REPAIR_MAX_FILES": "2",
                },
            ),
            patch(
                "app.routers.repairs.repair_agent_client.publish_plan",
                new=AsyncMock(return_value=result()),
            ),
        ):
            response = await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )

        self.assertEqual(response["publish_status"], "draft_pr_created")
        self.assertIsNone(database.audit.error_code)
        self.assertTrue(database.audit.github_changes_made)

    async def test_commit_created_audit_uses_recovery_only(self):
        repair_attempt = attempt()
        repair_attempt.github_changes_made = True
        database = FakeDatabase(repair_attempt)
        database.audit = RepairPublishAudit(
            attempt_id=repair_attempt.attempt_id,
            repository="example/project",
            base_sha="a" * 40,
            failed_branch="main",
            repair_branch="auto-heal/repair-4cd693-syntaxerror",
            commit_sha="b" * 40,
            publish_status="commit_created",
            validation_status="failed",
            changed_files=["app/user_service.py"],
            safety_check_results={
                "branch_created": True,
                "commit_created": True,
                "pr_created": False,
            },
            error_code="publish_mcp_failed",
            github_changes_made=True,
        )
        publish_mock = AsyncMock(return_value=result())
        with (
            patch.dict(
                "os.environ",
                {
                    "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                    "REPAIR_MAX_FILES": "2",
                },
            ),
            patch(
                "app.routers.repairs.repair_agent_client.publish_plan",
                new=publish_mock,
            ),
        ):
            response = await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )

        sent_request = publish_mock.await_args.args[0]
        self.assertTrue(sent_request.recovery_only)
        self.assertEqual(response["draft_pr_number"], 17)
        self.assertEqual(database.audit.draft_pr_number, 17)
        self.assertIsNone(database.audit.error_code)

    async def test_local_validation_returns_only_safe_diagnostics(self):
        repair_attempt = attempt()
        repair_attempt.repair_plan["proposed_changes"] = []
        database = FakeDatabase(repair_attempt)
        with patch.dict(
            "os.environ",
            {
                "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                "REPAIR_MAX_FILES": "2",
            },
        ):
            response = await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["error_code"], "missing_proposed_changes")
        self.assertEqual(body["failed_check_name"], "proposed_changes_exist")
        self.assertEqual(body["missing_field_names"], [])
        self.assertFalse(body["github_changes_made"])
        self.assertTrue(body["repairable"])
        self.assertFalse(body["has_proposed_changes"])
        self.assertEqual(
            set(body),
            {
                "error_code",
                "failed_check_name",
                "missing_field_names",
                "github_changes_made",
                "repairable",
                "has_proposed_changes",
            },
        )

    async def test_branch_mismatch_is_audited_without_github_change(self):
        repair_attempt = attempt()
        database = FakeDatabase(repair_attempt)
        failure = RepairPublishError(
            "branch_head_mismatch",
            "publish-correlation-123",
            {
                "publish_status": "validating",
                "validation_status": "failed",
                "changed_files": ["app/user_service.py"],
                "github_changes_made": False,
            },
        )
        with (
            patch.dict(
                "os.environ",
                {
                    "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                    "REPAIR_MAX_FILES": "2",
                },
            ),
            patch(
                "app.routers.repairs.repair_agent_client.publish_plan",
                new=AsyncMock(side_effect=failure),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await publish_approved_repair(
                    repair_attempt.attempt_id,
                    PublishConfirmationRequest(confirm_publish=True),
                    db=database,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("failed branch has moved", raised.exception.detail)
        self.assertEqual(database.audit.error_code, "branch_head_mismatch")
        self.assertFalse(
            database.audit.safety_check_results[
                "branch_head_matches_failed_sha"
            ]
        )
        self.assertFalse(repair_attempt.github_changes_made)
        self.assertFalse(database.audit.github_changes_made)

    async def test_partial_publish_returns_safe_status_flags(self):
        repair_attempt = attempt()
        database = FakeDatabase(repair_attempt)
        failure = RepairPublishError(
            "publish_partial_manual_review_required",
            "publish-correlation-123",
            {
                "publish_status": "partial_manual_review",
                "validation_status": "manual_review",
                "repair_branch": "auto-heal/repair-4cd693-syntaxerror",
                "commit_sha": "b" * 40,
                "github_changes_made": True,
                "branch_created": True,
                "commit_created": True,
                "pr_created": False,
            },
        )
        with (
            patch.dict(
                "os.environ",
                {
                    "GITHUB_ALLOWED_REPOSITORIES": "example/project",
                    "REPAIR_MAX_FILES": "2",
                },
            ),
            patch(
                "app.routers.repairs.repair_agent_client.publish_plan",
                new=AsyncMock(side_effect=failure),
            ),
        ):
            response = await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(body["branch_created"])
        self.assertTrue(body["commit_created"])
        self.assertFalse(body["pr_created"])

    async def test_rejects_already_published_audit(self):
        repair_attempt = attempt()
        database = FakeDatabase(repair_attempt)
        database.audit = RepairPublishAudit(
            attempt_id=repair_attempt.attempt_id,
            repository="example/project",
            base_sha="a" * 40,
            failed_branch="main",
            publish_status="draft_pr_created",
            validation_status="pending",
            changed_files=["app/user_service.py"],
            safety_check_results={},
            github_changes_made=True,
        )

        with self.assertRaises(HTTPException) as raised:
            await publish_approved_repair(
                repair_attempt.attempt_id,
                PublishConfirmationRequest(confirm_publish=True),
                db=database,
            )

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
