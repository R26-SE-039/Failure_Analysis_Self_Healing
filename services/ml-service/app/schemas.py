from pydantic import BaseModel
from typing import Optional


class ClassifyRequest(BaseModel):
    error_message: str
    stack_trace: Optional[str] = ""
    failure_stage: Optional[str] = "test"
    failure_type: Optional[str] = "Test Failure"
    severity: Optional[str] = "MEDIUM"
    retry_count: Optional[float] = 0
    test_duration_sec: Optional[float] = 30
    cpu_usage_pct: Optional[float] = 50
    memory_usage_mb: Optional[float] = 1024
    is_flaky_test: Optional[int] = 0


class ClassifyResponse(BaseModel):
    root_cause: str
    confidence: float
    all_probabilities: dict
    model_used: str


class RetrainResponse(BaseModel):
    status: str
    message: str


class MetricsResponse(BaseModel):
    model_name: str
    accuracy: float
    macro_f1: float
    weighted_f1: float
    macro_precision: float
    macro_recall: float
    train_samples: int
    test_samples: int
    classes: list
    per_class: dict
    all_models: dict
