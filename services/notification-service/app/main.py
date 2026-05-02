"""
Notification Service — main.py
Exposes: POST /notify, GET /health
Port: 8004
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import NotifyRequest, NotifyResponse
from app import alert_router

app = FastAPI(title="Notification Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"service": "notification-service", "status": "ready"}


@app.post("/notify", response_model=NotifyResponse)
def notify(req: NotifyRequest):
    result = alert_router.create_notification(
        failure_test_id = req.failure_test_id,
        test_name       = req.test_name,
        root_cause      = req.root_cause,
        message         = req.message,
        target          = req.target,
    )
    return NotifyResponse(**result)
