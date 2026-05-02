from pydantic import BaseModel
from typing import Optional


class HealRequest(BaseModel):
    test_id: str
    test_name: str
    root_cause: str
    confidence: float
    error_message: str
    stack_trace: Optional[str] = ""
    failure_type: Optional[str] = "Test Failure"
    old_value: Optional[str] = ""


class HealResponse(BaseModel):
    test_id: str
    healing_id: str
    repair_type: str
    old_value: str
    new_value: str
    recommendation: str
    status: str
    developer_alert: bool
