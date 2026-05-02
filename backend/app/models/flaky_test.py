from sqlalchemy import Column, Integer, String
from app.database import Base


class FlakyTest(Base):
    __tablename__ = "flaky_tests"

    id = Column(Integer, primary_key=True, index=True)
    test_code = Column(String, unique=True, nullable=False)
    test_name = Column(String, nullable=False)
    instability_score = Column(String, nullable=False)
    recent_pattern = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)