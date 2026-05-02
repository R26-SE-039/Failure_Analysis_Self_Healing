from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.schemas.failure import FailureCreate, FailureResponse

router = APIRouter(prefix="/failures", tags=["Failures"])


@router.get("/", response_model=List[FailureResponse])
def get_failures(db: Session = Depends(get_db)):
    return db.query(Failure).all()


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