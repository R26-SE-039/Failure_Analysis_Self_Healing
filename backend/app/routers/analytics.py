from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flaky_test import FlakyTest
from app.schemas.flaky_test import FlakyTestCreate, FlakyTestResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/flaky-tests", response_model=List[FlakyTestResponse])
def get_flaky_tests(db: Session = Depends(get_db)):
    return db.query(FlakyTest).all()


@router.post("/flaky-tests", response_model=FlakyTestResponse)
def create_flaky_test(payload: FlakyTestCreate, db: Session = Depends(get_db)):
    test = FlakyTest(**payload.dict())
    db.add(test)
    db.commit()
    db.refresh(test)
    return test