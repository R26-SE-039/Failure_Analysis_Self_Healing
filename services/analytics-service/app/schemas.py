from pydantic import BaseModel
from typing import Optional


class FlakyCheckRequest(BaseModel):
    test_id: str
    test_name: str
    retry_count: float = 0
    failure_type: str = "Test Failure"
    failure_stage: str = "test"
    severity: str = "MEDIUM"
    test_duration_sec: float = 30


class FlakyCheckResponse(BaseModel):
    test_id: str
    test_name: str
    is_flaky: bool
    flaky_probability: float
    risk_level: str
    instability_score: str
    recent_pattern: str
