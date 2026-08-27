from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class FailureBase(BaseModel):
    organization_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    iteration_id: Optional[UUID] = None
    user_story_id: Optional[UUID] = None
    suite_id: Optional[UUID] = None
    execution_id: Optional[UUID] = None
    test_run_id: Optional[UUID] = None
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

class PaginatedFailuresResponse(BaseModel):
    data: list[FailureResponse]
    total: int
    page: int
    limit: int
