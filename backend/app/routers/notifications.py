from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationResponse, PaginatedNotificationResponse
from fastapi import HTTPException

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=PaginatedNotificationResponse)
def get_notifications(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    total = db.query(Notification).count()
    notifications = db.query(Notification).order_by(Notification.id.desc()).offset(offset).limit(limit).all()
    return {"data": notifications, "total": total, "page": page, "limit": limit}


@router.post("/", response_model=NotificationResponse)
def create_notification(payload: NotificationCreate, db: Session = Depends(get_db)):
    notification = Notification(**payload.dict())
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


@router.delete("/{notification_id}")
def delete_notification(notification_id: int, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(notification)
    db.commit()
    return {"status": "success"}