from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class RepairAttempt(Base):
    __tablename__ = "repair_attempts"

    id = Column(Integer, primary_key=True, index=True)
    failure_id = Column(Integer, ForeignKey("failures.id"), nullable=True, index=True)
    attempt_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )
    failure_test_id = Column(
        String,
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False)
    mode = Column(
        String,
        nullable=False,
        default="read_only",
    )
    eligible = Column(Boolean, nullable=False, default=False)
    eligibility_code = Column(String, nullable=False)
    eligibility_reason = Column(Text, nullable=False)
    predicted_root_cause = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    decision_source = Column(String, nullable=False)
    selected_action = Column(String, nullable=False)
    repository_owner = Column(String, nullable=True)
    repository_name = Column(String, nullable=True)
    run_id = Column(BigInteger, nullable=True)
    head_sha = Column(String, nullable=True)
    head_branch = Column(String, nullable=True)
    default_branch = Column(String, nullable=True)
    error_type = Column(String, nullable=False)
    error_message = Column(Text, nullable=False)
    candidate_file = Column(String, nullable=False)
    candidate_line = Column(Integer, nullable=True)
    log_content_sha256 = Column(String, nullable=False)
    sanitized_log_excerpt = Column(Text, nullable=False)
    inspected_files = Column(JSON, nullable=True)
    repair_plan = Column(JSON, nullable=True)
    provider_model = Column(String, nullable=True)
    github_changes_made = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    failure_reason = Column(Text, nullable=True)
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
