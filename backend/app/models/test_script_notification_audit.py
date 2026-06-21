from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class TestScriptNotificationAudit(Base):
    __tablename__ = "test_script_notification_audits"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(String, unique=True, nullable=False, index=True)
    attempt_id = Column(String, unique=True, nullable=False, index=True)
    root_cause = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    repository = Column(String, nullable=True)
    failed_branch = Column(String, nullable=True)
    failed_sha = Column(String, nullable=True)
    run_id = Column(BigInteger, nullable=True)
    run_url = Column(Text, nullable=True)
    target_module = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="notification_sent")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
