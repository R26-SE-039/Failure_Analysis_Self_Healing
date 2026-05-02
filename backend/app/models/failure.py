from sqlalchemy import Column, Integer, String, Text, Boolean
from app.database import Base


class Failure(Base):
    __tablename__ = "failures"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(String, unique=True, nullable=False)
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