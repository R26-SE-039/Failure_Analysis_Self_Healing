from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.schemas.failure import FailureCreate, FailureResponse, PaginatedFailuresResponse

router = APIRouter(prefix="/failures", tags=["Failures"])


@router.get("/", response_model=PaginatedFailuresResponse)
def get_failures(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(Failure).count()
    failures = db.query(Failure).order_by(Failure.created_at.desc()).offset(offset).limit(limit).all()
    return {"data": failures, "total": total, "page": page, "limit": limit}


@router.get("/{test_id}", response_model=FailureResponse)
def get_failure(test_id: str, db: Session = Depends(get_db)):
    failure = db.query(Failure).filter(Failure.test_id == test_id).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    return failure


@router.post("/", response_model=FailureResponse)
def create_failure(payload: FailureCreate, db: Session = Depends(get_db)):
    failure = Failure(**payload.dict())
    db.add(failure)
    db.commit()
    db.refresh(failure)
    return failure


@router.patch("/{test_id}/heal", response_model=FailureResponse)
def heal_failure(test_id: str, db: Session = Depends(get_db)):
    failure = db.query(Failure).filter(Failure.test_id == test_id).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    
    failure.status = "HEALED"
    failure.healing = "Applied"
    
    # Also update the corresponding healing action
    from app.models.healing import HealingAction
    healing_action = db.query(HealingAction).filter(HealingAction.failure_test_id == test_id).first()
    if healing_action:
        healing_action.status = "Applied"
        
    db.commit()
    db.refresh(failure)
    return failure


@router.delete("/{test_id}")
def delete_failure(test_id: str, db: Session = Depends(get_db)):
    failure = db.query(Failure).filter(Failure.test_id == test_id).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    
    # Optional cascade manually to clean up other tables:
    from app.models.healing import HealingAction
    from app.models.flaky_test import FlakyTest
    from app.models.notification import Notification

    db.query(HealingAction).filter(HealingAction.failure_test_id == test_id).delete()
    db.query(FlakyTest).filter(FlakyTest.test_code == test_id).delete()
    db.query(Notification).filter(Notification.failure_test_id == test_id).delete()
    
    db.delete(failure)
    db.commit()
    return {"status": "success", "message": "Failure and related records deleted"}