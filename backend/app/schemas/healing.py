from pydantic import BaseModel


class HealingBase(BaseModel):
    healing_id: str
    failure_test_id: str
    test_name: str
    repair_type: str
    old_value: str
    new_value: str
    status: str


class HealingCreate(HealingBase):
    pass


class HealingResponse(HealingBase):
    id: int

    class Config:
        orm_mode = True

class PaginatedHealingResponse(BaseModel):
    data: list[HealingResponse]
    total: int
    page: int
    limit: int