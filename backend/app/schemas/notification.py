from pydantic import BaseModel


class NotificationBase(BaseModel):
    failure_test_id: str
    test_name: str
    root_cause: str
    message: str
    target: str


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    id: int

    class Config:
        orm_mode = True