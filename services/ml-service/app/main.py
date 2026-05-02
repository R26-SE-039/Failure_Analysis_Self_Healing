"""
ML Service — main.py
Exposes: POST /classify, GET /health, POST /retrain, GET /metrics
Port: 8001
"""
import os, sys, subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import ClassifyRequest, ClassifyResponse, RetrainResponse, MetricsResponse
from app import classifier as clf_module

app = FastAPI(title="ML Classifier Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    clf_module.load_models()


@app.get("/health")
def health():
    return {
        "service": "ml-service",
        "status":  "ready" if clf_module.is_ready() else "model_not_loaded",
        "model":   clf_module.get_metrics()["model_name"] if clf_module.get_metrics() else None,
    }


@app.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest):
    if not clf_module.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Run POST /retrain first."
        )
    result = clf_module.predict(
        error_message     = req.error_message,
        stack_trace       = req.stack_trace or "",
        failure_stage     = req.failure_stage or "test",
        failure_type      = req.failure_type or "Test Failure",
        severity          = req.severity or "MEDIUM",
        retry_count       = req.retry_count or 0,
        test_duration_sec = req.test_duration_sec or 30,
        cpu_usage_pct     = req.cpu_usage_pct or 50,
        memory_usage_mb   = req.memory_usage_mb or 1024,
        is_flaky_test     = req.is_flaky_test or 0,
    )
    return ClassifyResponse(**result)


# ── background retraining state ────────────────────────────────────────────────
_retrain_status = {"running": False, "last_result": None}

def _run_retrain():
    _retrain_status["running"] = True
    _retrain_status["last_result"] = None
    try:
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "research", "scripts", "train_model.py"
        )
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            clf_module.load_models()          # reload freshly trained model
            _retrain_status["last_result"] = "success"
        else:
            _retrain_status["last_result"] = f"error: {result.stderr[-500:]}"
    except Exception as e:
        _retrain_status["last_result"] = f"exception: {str(e)}"
    finally:
        _retrain_status["running"] = False


@app.post("/retrain", response_model=RetrainResponse)
def retrain(background_tasks: BackgroundTasks):
    if _retrain_status["running"]:
        return RetrainResponse(status="running", message="Retraining already in progress.")
    background_tasks.add_task(_run_retrain)
    return RetrainResponse(status="started", message="Model retraining started in background.")


@app.get("/retrain/status")
def retrain_status():
    return {
        "running":     _retrain_status["running"],
        "last_result": _retrain_status["last_result"],
    }


@app.get("/metrics")
def get_metrics():
    m = clf_module.get_metrics()
    if not m:
        raise HTTPException(status_code=404, detail="No metrics available. Train the model first.")
    return m
