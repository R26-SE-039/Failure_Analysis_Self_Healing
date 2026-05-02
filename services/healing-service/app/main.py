"""
Healing Service — main.py
Exposes: POST /heal, GET /health
Port: 8002
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import HealRequest, HealResponse
from app import healing_engine

app = FastAPI(title="Self-Healing Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"service": "healing-service", "status": "ready"}


@app.post("/heal", response_model=HealResponse)
def heal(req: HealRequest):
    result = healing_engine.heal(
        test_id       = req.test_id,
        test_name     = req.test_name,
        root_cause    = req.root_cause,
        confidence    = req.confidence,
        error_message = req.error_message,
        stack_trace   = req.stack_trace or "",
        failure_type  = req.failure_type or "Test Failure",
        old_value     = req.old_value or "",
    )
    return HealResponse(**result)
