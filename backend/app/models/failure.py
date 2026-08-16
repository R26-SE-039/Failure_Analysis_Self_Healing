from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base
from app.db_types import GUID


class Failure(Base):
    __tablename__ = "failures"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "test_id",
            name="uq_failures_project_test_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(GUID(), nullable=True, index=True)
    project_id = Column(GUID(), nullable=True, index=True)
    iteration_id = Column(GUID(), nullable=True, index=True)
    user_story_id = Column(GUID(), nullable=True, index=True)
    suite_id = Column(GUID(), nullable=True, index=True)
    execution_id = Column(GUID(), nullable=True, index=True)
    test_run_id = Column(GUID(), nullable=True, index=True)
    test_id = Column(String, nullable=False, index=True)
    test_name = Column(String, nullable=False)
    pipeline = Column(String, nullable=False)
    status = Column(String, nullable=False)
    root_cause = Column(String, nullable=False)
    confidence = Column(String, nullable=True)
    healing = Column(String, nullable=True)
    logs = Column(Text, nullable=True)
    stack_trace = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    developer_alert = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
