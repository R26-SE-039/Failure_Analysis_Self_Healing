"""
Analytics Service — main.py
Exposes: POST /check-flaky, GET /health
Port: 8003
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import FlakyCheckRequest, FlakyCheckResponse
from app import flaky_detector

app = FastAPI(title="Analytics Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"service": "analytics-service", "status": "ready"}


@app.post("/check-flaky", response_model=FlakyCheckResponse)
def check_flaky(req: FlakyCheckRequest):
    result = flaky_detector.check_flaky(
        test_id           = req.test_id,
        test_name         = req.test_name,
        retry_count       = req.retry_count,
        failure_type      = req.failure_type,
        failure_stage     = req.failure_stage,
        severity          = req.severity,
        test_duration_sec = req.test_duration_sec,
    )
    return FlakyCheckResponse(**result)
