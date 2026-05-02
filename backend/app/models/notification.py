from sqlalchemy import Column, Integer, String, Text
from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    failure_test_id = Column(String, nullable=False)
    test_name = Column(String, nullable=False)
    root_cause = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    target = Column(String, nullable=False)