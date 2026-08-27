from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.failure import Failure
from app.models.healing import HealingAction
from app.schemas.healing import HealingCreate, HealingResponse, PaginatedHealingResponse
from fastapi import HTTPException
from app.services.project_scope import (
    ProjectScope,
    apply_child_failure_scope,
    ensure_failure_in_scope,
    get_project_scope,
)

router = APIRouter(prefix="/healing", tags=["Healing"])


@router.get("/", response_model=PaginatedHealingResponse)
def get_healing_actions(
    page: int = 1,
    limit: int = 10,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    offset = (page - 1) * limit
    base_query = apply_child_failure_scope(
        db.query(HealingAction), HealingAction, Failure, scope
    )
    total = base_query.count()
    actions = base_query.order_by(HealingAction.id.desc()).offset(offset).limit(limit).all()
    return {"data": actions, "total": total, "page": page, "limit": limit}


@router.post("/", response_model=HealingResponse)
def create_healing_action(payload: HealingCreate, db: Session = Depends(get_db)):
    action = HealingAction(**payload.dict())
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.delete("/{healing_id}")
def delete_healing_action(
    healing_id: str,
    scope: ProjectScope = Depends(get_project_scope),
    db: Session = Depends(get_db),
):
    action = db.query(HealingAction).filter(HealingAction.healing_id == healing_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Healing action not found")
    ensure_failure_in_scope(db, Failure, action.failure_id, scope)
    db.delete(action)
    db.commit()
    return {"status": "success"}
