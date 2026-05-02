from pydantic import BaseModel


class FlakyTestBase(BaseModel):
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