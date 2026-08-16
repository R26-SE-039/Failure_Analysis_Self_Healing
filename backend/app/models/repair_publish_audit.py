from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class RepairPublishAudit(Base):
    __tablename__ = "repair_publish_audits"

    id = Column(Integer, primary_key=True, index=True)
    repair_attempt_id = Column(
        Integer,
        ForeignKey("repair_attempts.id"),
        nullable=True,
        index=True,
    )
    attempt_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )
    correlation_id = Column(String, nullable=True, index=True)
    repository = Column(String, nullable=False)
    base_sha = Column(String, nullable=False)
    failed_branch = Column(String, nullable=False)
    repair_branch = Column(String, nullable=True)
    commit_sha = Column(String, nullable=True)
    draft_pr_number = Column(Integer, nullable=True)
    draft_pr_url = Column(Text, nullable=True)
    publish_status = Column(String, nullable=False)
    validation_status = Column(String, nullable=False)
    changed_files = Column(JSON, nullable=False, default=list)
    safety_check_results = Column(JSON, nullable=False, default=dict)
    error_code = Column(String, nullable=True)
    github_changes_made = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
