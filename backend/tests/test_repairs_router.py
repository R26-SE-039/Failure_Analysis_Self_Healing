import unittest
from types import SimpleNamespace

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


def attempt():
    return SimpleNamespace(
        attempt_id="REPAIR-123",
        head_sha="a" * 40,
        candidate_file="app/user_service.py",
        candidate_line=10,
    )


def plan():
    return ReadOnlyRepairPlan(
        attempt_id="REPAIR-123",
        status="planned",
        model="mock/tool-model",
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


if __name__ == "__main__":
    unittest.main()
