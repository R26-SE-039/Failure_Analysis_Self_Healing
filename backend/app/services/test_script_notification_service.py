import uuid
from typing import Any, Optional

from app.models.test_script_notification_audit import (
    TestScriptNotificationAudit,
)


TARGET_MODULE = "Test Script Generation Module"
NOTIFICATION_MESSAGE = (
    "Forward this failure to the test script generation owner for "
    "inspection/regeneration."
)


class TestScriptNotificationService:
    def create_audit(
        self,
        *,
        attempt_id: str,
        confidence: float,
        source_run: Optional[dict[str, Any]],
    ) -> TestScriptNotificationAudit:
        repository = None
        if source_run:
            repository = source_run.get("repository_full_name")
        return TestScriptNotificationAudit(
            notification_id=f"TSN-{uuid.uuid4().hex[:12].upper()}",
            attempt_id=attempt_id,
            root_cause="test_script_issue",
            confidence=confidence,
            repository=repository,
            failed_branch=(source_run.get("head_branch") if source_run else None),
            failed_sha=(source_run.get("head_sha") if source_run else None),
            run_id=(source_run.get("run_id") if source_run else None),
            run_url=(source_run.get("run_url") if source_run else None),
            target_module=TARGET_MODULE,
            message=NOTIFICATION_MESSAGE,
            status="notification_sent",
        )


test_script_notification_service = TestScriptNotificationService()
