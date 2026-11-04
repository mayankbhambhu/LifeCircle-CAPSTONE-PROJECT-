"""Patient family endpoints (wireframes 2, 3, 4)."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth import require
from app.db import get_db
from app.models import DonationRequest, Notification, Patient, Role, SlotRole, User
from app.privacy import donor_view
from app.services import eligibility, rotation, scheduling, urgent

router = APIRouter(prefix="/family", tags=["Patient family"])
family_only = require(Role.family)


def my_patient(db: Session, user: User) -> Patient:
    p = db.scalar(select(Patient).where(Patient.family_user_id == user.id))
    if not p:
        raise HTTPException(404, "No patient linked to this account")
    return p


def request_view(req: DonationRequest) -> dict:
    """Status timeline for the family. Says how many donors were alerted, never who."""
    steps = [
        {"label": f"Sent to {req.patient.blood_bank.name}", "at": req.created_at, "done": True},
        {"label": "Blood bank approved, circle alerted", "at": req.circle_alerted_at, "done": bool(req.circle_alerted_at)},
        {"label": "Nearby donors alerted", "at": req.nearby_alerted_at, "done": bool(req.nearby_alerted_at)},
        {"label": "Donor confirmed", "at": None, "done": bool(req.filled_by_donor_id)},
    ]
    return {
        "id": req.id,
        "type": req.type.value,
        "status": req.status.value,
        "needed_by": req.needed_by,
        "note": req.note,
        "donors_alerted": len(req.alerts),
        "steps": steps,
        "message": "You don't need to call anyone. This screen updates itself.",
    }


@router.get("/home")
def home(user: User = Depends(family_only), db: Session = Depends(get_db)):
    patient = my_patient(db, user)
    slots = scheduling.ensure_plan(db, patient)
    nxt = scheduling.next_transfusion_date(patient)
    order = rotation.rank_circle(db, patient, nxt)
    on_slot = {a.donor_id: a.slot.value for a in slots.values()}

    open_reqs = db.scalars(
        select(DonationRequest).where(
            DonationRequest.patient_id == patient.id, DonationRequest.status.in_(urgent.OPEN_STATUSES + (urgent.RequestStatus.filled,))
        )
    ).all()
    for r in open_reqs:
        urgent.escalate_if_due(db, r)

    circle = []
    for m in patient.circle:
        v = donor_view(db, m.donor, user)
        v["slot"] = on_slot.get(m.donor_id)
        v["eligible_for_next"] = m.donor_id not in order.ineligible
        circle.append(v)

    confirmed = slots.get(SlotRole.confirmed)
    backup = slots.get(SlotRole.backup)
    return {
        "patient": {"name": patient.name, "blood_group": patient.blood_group, "cycle_days": patient.cycle_days},
        "next_transfusion": nxt,
        "days_until": (nxt - clock.today()).days,
        "confirmed": donor_view(db, confirmed.donor, user) | {"status": confirmed.status.value} if confirmed else None,
        "backup": donor_view(db, backup.donor, user) | {"status": backup.status.value} if backup else None,
        "covered": confirmed is not None,
        "circle": circle,
        "circle_health": rotation.circle_health(patient),
        "requests": [request_view(r) for r in open_reqs],
    }


class PlanIn(BaseModel):
    blood_group: str
    cycle_days: int = Field(ge=7, le=90)
    last_transfusion_date: date

    @field_validator("blood_group")
    @classmethod
    def valid_group(cls, v: str) -> str:
        if v not in eligibility.BLOOD_GROUPS:
            raise ValueError(f"blood_group must be one of {eligibility.BLOOD_GROUPS}")
        return v


@router.get("/plan")
def get_plan(user: User = Depends(family_only), db: Session = Depends(get_db)):
    p = my_patient(db, user)
    return {
        "blood_group": p.blood_group,
        "cycle_days": p.cycle_days,
        "last_transfusion_date": p.last_transfusion_date,
        "next_transfusion": scheduling.next_transfusion_date(p),
    }


@router.put("/plan")
def save_plan(body: PlanIn, user: User = Depends(family_only), db: Session = Depends(get_db)):
    p = my_patient(db, user)
    if body.last_transfusion_date > clock.today():
        raise HTTPException(422, "Last transfusion date cannot be in the future")
    p.blood_group, p.cycle_days, p.last_transfusion_date = body.blood_group, body.cycle_days, body.last_transfusion_date
    scheduling.replan(db, p)
    return get_plan(user, db)


class UrgentIn(BaseModel):
    needed_by: datetime | None = None
    note: str = ""


@router.post("/urgent", status_code=201)
def request_urgent_help(body: UrgentIn, user: User = Depends(family_only), db: Session = Depends(get_db)):
    """Goes to the blood bank, not to donors."""
    p = my_patient(db, user)
    needed_by = body.needed_by or clock.now().replace(hour=18, minute=0)
    req = urgent.create(db, p, needed_by, body.note)
    return request_view(req)


@router.get("/requests/{request_id}")
def request_status(request_id: int, user: User = Depends(family_only), db: Session = Depends(get_db)):
    p = my_patient(db, user)
    req = db.get(DonationRequest, request_id)
    if not req or req.patient_id != p.id:
        raise HTTPException(404, "Request not found")
    urgent.escalate_if_due(db, req)
    return request_view(req)


@router.get("/notifications")
def notifications(user: User = Depends(family_only), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(20)
    ).all()
    return [{"text": n.text, "at": n.created_at} for n in rows]
