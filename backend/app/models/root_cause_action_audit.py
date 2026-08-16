from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RootCauseActionAudit(Base):
    __tablename__ = "root_cause_action_audits"

    id = Column(Integer, primary_key=True, index=True)
    repair_attempt_id = Column(
        Integer,
        ForeignKey("repair_attempts.id"),
        nullable=True,
        index=True,
    )
    audit_id = Column(String, unique=True, nullable=False, index=True)
    attempt_id = Column(String, unique=True, nullable=False, index=True)
    root_cause = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    repository = Column(String, nullable=True)
    failed_branch = Column(String, nullable=True)
    failed_sha = Column(String, nullable=True)
    run_url = Column(Text, nullable=True)
    automation_level = Column(String, nullable=False)
    notification_required = Column(Boolean, nullable=False)
    target_team_or_module = Column(String, nullable=False)
    recommended_action = Column(Text, nullable=False)
    validation_guidance = Column(JSON, nullable=False, default=list)
    history_status = Column(String, nullable=False)
    github_changes_made = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
