from sqlalchemy import Column, Integer, String, UniqueConstraint
from app.database import Base
from app.db_types import GUID


class FlakyTest(Base):
    __tablename__ = "flaky_tests"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "test_code",
            name="uq_flaky_tests_project_test_code",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(GUID(), nullable=True, index=True)
    project_id = Column(GUID(), nullable=True, index=True)
    suite_id = Column(GUID(), nullable=True, index=True)
    latest_test_run_id = Column(GUID(), nullable=True, index=True)
    test_code = Column(String, nullable=False, index=True)
    test_name = Column(String, nullable=False)
    instability_score = Column(String, nullable=False)
    recent_pattern = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
