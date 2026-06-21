from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import Base, engine

# Import database models so SQLAlchemy can create their tables
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.models.flaky_test import FlakyTest
from app.models.notification import Notification
from app.models.repair_attempt import RepairAttempt
from app.models.repair_publish_audit import RepairPublishAudit
from app.models.test_script_notification_audit import TestScriptNotificationAudit

# Existing routers
from app.routers.failures import router as failures_router
from app.routers.healing import router as healing_router
from app.routers.analytics import router as analytics_router
from app.routers.notifications import router as notifications_router
from app.routers.dashboard import router as dashboard_router
from app.routers.analyze import router as analyze_router
from app.routers.repairs import router as repairs_router

# New nine-class root-cause router
from app.routers.root_cause import router as root_cause_router



# ── Create database tables that do not exist yet ──────────────────────────────
Base.metadata.create_all(bind=engine)


# ── Safe database migration ───────────────────────────────────────────────────
def _run_migrations() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(
                text(
                    """
                    ALTER TABLE failures
                    ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()
                    """
                )
            )
            conn.commit()
            print(
                "[Migration] Added created_at column "
                "to failures table."
            )
        except Exception:
            # The column probably already exists.
            # This is expected after the first successful migration.
            pass


_run_migrations()


# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(
    title="Failure Analysis and Self-Healing API",
    description=(
        "API for CI/CD failure analysis, root-cause classification, "
        "self-healing actions, analytics and notifications."
    ),
    version="1.0.0",
)


# ── Startup tasks ─────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event() -> None:
    """
    The new nine-class model is loaded by RootCauseService when the
    root-cause router/service is imported.
    """
    print("[Startup] Nine-class root-cause service is available.")


# ── CORS configuration ────────────────────────────────────────────────────────
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


# ── Existing API routers ──────────────────────────────────────────────────────
app.include_router(failures_router)
app.include_router(healing_router)
app.include_router(analytics_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(analyze_router)
app.include_router(repairs_router)


# ── New nine-class root-cause analysis router ─────────────────────────────────
app.include_router(root_cause_router)


# ── Basic health endpoint ─────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Backend is running",
        "service": "Failure Analysis and Self-Healing API",
        "root_cause_endpoint": "/api/root-cause/analyze",
        "documentation": "/docs",
    }
