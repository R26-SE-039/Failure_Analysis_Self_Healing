from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flaky_test import FlakyTest
from app.schemas.flaky_test import FlakyTestCreate, FlakyTestResponse, PaginatedFlakyTestResponse
from fastapi import HTTPException

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/flaky-tests", response_model=PaginatedFlakyTestResponse)
def get_flaky_tests(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(FlakyTest).count()
    tests = db.query(FlakyTest).order_by(FlakyTest.id.desc()).offset(offset).limit(limit).all()
    return {"data": tests, "total": total, "page": page, "limit": limit}


@router.post("/flaky-tests", response_model=FlakyTestResponse)
def create_flaky_test(payload: FlakyTestCreate, db: Session = Depends(get_db)):
    test = FlakyTest(**payload.dict())
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.delete("/flaky-tests/{test_code}")
def delete_flaky_test(test_code: str, db: Session = Depends(get_db)):
    test = db.query(FlakyTest).filter(FlakyTest.test_code == test_code).first()
    if not test:
        raise HTTPException(status_code=404, detail="Flaky test not found")
    db.delete(test)
    db.commit()
    return {"status": "success"}