from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class FailureBase(BaseModel):
    test_id: str
    test_name: str
    pipeline: str
    status: str
    root_cause: str
    confidence: Optional[str] = None
    healing: Optional[str] = None
    logs: Optional[str] = None
    stack_trace: Optional[str] = None
    recommendation: Optional[str] = None
    developer_alert: bool = False


class FailureCreate(FailureBase):
    pass


class FailureResponse(FailureBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True