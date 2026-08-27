from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FlakyTestBase(BaseModel):
    organization_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    suite_id: Optional[UUID] = None
    latest_test_run_id: Optional[UUID] = None
    test_code: str
    test_name: str
    instability_score: str
    recent_pattern: str
    risk_level: str


class FlakyTestCreate(FlakyTestBase):
    pass


class FlakyTestResponse(FlakyTestBase):
    id: int

    class Config:
        orm_mode = True

class PaginatedFlakyTestResponse(BaseModel):
    data: list[FlakyTestResponse]
    total: int
    page: int
    limit: int
