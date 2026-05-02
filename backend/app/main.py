from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Failure Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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