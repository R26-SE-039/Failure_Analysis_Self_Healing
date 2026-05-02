from sqlalchemy import Column, Integer, String
from app.database import Base


class HealingAction(Base):
    __tablename__ = "healing_actions"

    id = Column(Integer, primary_key=True, index=True)
    healing_id = Column(String, unique=True, nullable=False)
    failure_test_id = Column(String, nullable=False)
    test_name = Column(String, nullable=False)
    repair_type = Column(String, nullable=False)
    old_value = Column(String, nullable=False)
    new_value = Column(String, nullable=False)
    status = Column(String, nullable=False)