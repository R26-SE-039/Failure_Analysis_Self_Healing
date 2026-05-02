from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.models.flaky_test import FlakyTest
from app.models.notification import Notification

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_failures = db.query(Failure).count()
    total_healing_actions = db.query(HealingAction).count()
    total_flaky_tests = db.query(FlakyTest).count()
    total_notifications = db.query(Notification).count()

    recent_failures = (
        db.query(Failure)
        .order_by(Failure.id.desc())
        .limit(5)
        .all()
    )

    return {
        "total_failures": total_failures,
        "total_healing_actions": total_healing_actions,
        "total_flaky_tests": total_flaky_tests,
        "total_notifications": total_notifications,
        "recent_failures": [
            {
                "id": item.id,
                "test_id": item.test_id,
                "test_name": item.test_name,
                "pipeline": item.pipeline,
                "status": item.status,
                "root_cause": item.root_cause,
                "healing": item.healing,
            }
            for item in recent_failures
        ],
    }