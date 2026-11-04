"""Simulated notifications. The prototype stores messages; it never sends SMS."""
from sqlalchemy.orm import Session

from app import clock
from app.models import Notification


def notify(db: Session, user_id: int, text: str) -> None:
    db.add(Notification(user_id=user_id, text=f"[DEMO] {text}", created_at=clock.now()))
