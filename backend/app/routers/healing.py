from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.healing import HealingAction
from app.schemas.healing import HealingCreate, HealingResponse

router = APIRouter(prefix="/healing", tags=["Healing"])


@router.get("/", response_model=List[HealingResponse])
def get_healing_actions(db: Session = Depends(get_db)):
    return db.query(HealingAction).all()


@router.post("/", response_model=HealingResponse)
def create_healing_action(payload: HealingCreate, db: Session = Depends(get_db)):
    action = HealingAction(**payload.dict())
    db.add(action)
    db.commit()
    db.refresh(action)
    return action