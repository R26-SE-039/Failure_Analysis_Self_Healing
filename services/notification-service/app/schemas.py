from pydantic import BaseModel
from typing import Optional


class NotifyRequest(BaseModel):
    failure_test_id: str
    test_name: str
    root_cause: str
    message: str
    target: str = "developer"   # developer | devops | manager


class NotifyResponse(BaseModel):
    notification_id: str
    failure_test_id: str
    test_name: str
    root_cause: str
    message: str
    target: str
    status: str
