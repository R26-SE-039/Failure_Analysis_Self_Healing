from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.schemas.failure import FailureCreate, FailureResponse, PaginatedFailuresResponse
from app.services.project_scope import (
    ProjectScope,
    apply_failure_scope,
    ensure_failure_in_scope,
    get_project_scope,
)

router = APIRouter(prefix="/failures", tags=["Failures"])


@router.get("/", response_model=PaginatedFailuresResponse)
def get_failures(
    page: int = 1,
    limit: int = 10,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    offset = (page - 1) * limit
    base_query = apply_failure_scope(db.query(Failure), Failure, scope)
    total = base_query.count()
    failures = base_query.order_by(Failure.created_at.desc()).offset(offset).limit(limit).all()
    return {"data": failures, "total": total, "page": page, "limit": limit}


@router.get("/{test_id}", response_model=FailureResponse)
def get_failure(
    test_id: str,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    failure = apply_failure_scope(
        db.query(Failure).filter(Failure.test_id == test_id),
        Failure,
        scope,
    ).first()
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
def heal_failure(
    test_id: str,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    failure = apply_failure_scope(
        db.query(Failure).filter(Failure.test_id == test_id),
        Failure,
        scope,
    ).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    
    failure.status = "HEALED"
    failure.healing = "Applied"
    
    # Also update the corresponding healing action
    from app.models.healing import HealingAction
    healing_action = db.query(HealingAction).filter(HealingAction.failure_test_id == test_id).first()
    if healing_action:
        ensure_failure_in_scope(db, Failure, healing_action.failure_id, scope)
    if healing_action:
        healing_action.status = "Applied"
        
    db.commit()
    db.refresh(failure)
    return failure


@router.delete("/{test_id}")
def delete_failure(
    test_id: str,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    failure = apply_failure_scope(
        db.query(Failure).filter(Failure.test_id == test_id),
        Failure,
        scope,
    ).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    
    # Optional cascade manually to clean up other tables:
    from app.models.healing import HealingAction
    from app.models.flaky_test import FlakyTest
    from app.models.notification import Notification

    db.query(HealingAction).filter(HealingAction.failure_id == failure.id).delete()
    db.query(HealingAction).filter(HealingAction.failure_test_id == test_id).delete()
    flaky_query = db.query(FlakyTest).filter(FlakyTest.test_code == test_id)
    if scope.is_scoped:
        flaky_query = flaky_query.filter(
            FlakyTest.organization_id == scope.organization_id,
            FlakyTest.project_id == scope.project_id,
        )
    flaky_query.delete()
    db.query(Notification).filter(Notification.failure_id == failure.id).delete()
    db.query(Notification).filter(Notification.failure_test_id == test_id).delete()
    
    db.delete(failure)
    db.commit()
    return {"status": "success", "message": "Failure and related records deleted"}
