import uuid
from typing import Any, Optional

from app.models.root_cause_action_audit import RootCauseActionAudit


class RootCauseActionAuditService:
    def create_audit(
        self,
        *,
        attempt_id: str,
        root_cause: str,
        confidence: float,
        policy: dict[str, Any],
        source_run: Optional[dict[str, Any]],
    ) -> RootCauseActionAudit:
        return RootCauseActionAudit(
            audit_id=f"RCA-{uuid.uuid4().hex[:12].upper()}",
            attempt_id=attempt_id,
            root_cause=root_cause,
            confidence=confidence,
            repository=(
                source_run.get("repository_full_name") if source_run else None
            ),
            failed_branch=(source_run.get("head_branch") if source_run else None),
            failed_sha=(source_run.get("head_sha") if source_run else None),
            run_url=(source_run.get("run_url") if source_run else None),
            automation_level=policy["automation_level"],
            notification_required=policy["notification_required"],
            target_team_or_module=policy["target_team_or_module"],
            recommended_action=policy["recommended_action"],
            validation_guidance=list(policy["validation_guidance"]),
            history_status=policy["history_status"],
            github_changes_made=False,
        )


root_cause_action_audit_service = RootCauseActionAuditService()
