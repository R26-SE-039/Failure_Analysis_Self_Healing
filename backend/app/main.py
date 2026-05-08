from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import Base, engine
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.models.flaky_test import FlakyTest
from app.models.notification import Notification
from app.routers.failures import router as failures_router
from app.routers.healing import router as healing_router
from app.routers.analytics import router as analytics_router
from app.routers.notifications import router as notifications_router
from app.routers.dashboard import router as dashboard_router
from app.routers.analyze import router as analyze_router
from app.core import ml_classifier

# ── Create all tables that don't exist yet ─────────────────────────────────────
Base.metadata.create_all(bind=engine)




# ── Safe migration: add created_at column if it doesn't exist ─────────────────
def _run_migrations():
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE failures ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()"
            ))
            conn.commit()
            print("[Migration] Added created_at column to failures table.")
        except Exception:
            # Column already exists — this is expected on subsequent restarts
            pass

_run_migrations()

app = FastAPI(title="Failure Analysis API")

@app.on_event("startup")
def startup_event():
    ml_classifier.load_models()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(failures_router)
app.include_router(healing_router)
app.include_router(analytics_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(analyze_router)


@app.get("/")
def root():
    return {"message": "Backend is running"}