"""Blood bank staff endpoints (wireframes 8, 9, 10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth import require
from app.db import get_db
from app.models import (
    Appointment,
    DonationRequest,
    Donor,
    Outcome,
    PhoneViewLog,
    RequestStatus,
    Role,
    SlotRole,
    User,
)
from app.privacy import donor_view
from app.services import geo, outcomes, scheduling, urgent

router = APIRouter(prefix="/staff", tags=["Blood bank staff"])
staff_only = require(Role.staff)


def _req(db: Session, user: User, request_id: int) -> DonationRequest:
    r = db.get(DonationRequest, request_id)
    if not r or r.blood_bank_id != user.blood_bank_id:
        raise HTTPException(404, "Request not found")
    return r


def _suggestion(db: Session, r: DonationRequest) -> str:
    if r.status == RequestStatus.sent_to_bank:
        n = len(urgent.circle_candidates(db, r))
        return f"Approve: alert {n} eligible circle donor(s)" if n else "Approve: circle has no eligible donor, go straight to nearby donors"
    if r.status == RequestStatus.circle_alerted:
        left = urgent.ESCALATE_AFTER - (clock.now() - r.circle_alerted_at)
        mins = max(0, int(left.total_seconds() // 60))
        return f"Waiting on circle. Escalates to nearby donors in {mins} min"
    if r.status == RequestStatus.nearby_alerted:
        return f"{len(r.alerts)} donors alerted. Confirm the first to accept"
    if r.status == RequestStatus.filled:
        return "Call the confirmed donor, then record the outcome"
    return "No action"


@router.get("/queue")
def request_queue(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    reqs = db.scalars(
        select(DonationRequest)
        .where(DonationRequest.blood_bank_id == user.blood_bank_id, DonationRequest.status != RequestStatus.closed)
        .order_by(DonationRequest.type.desc(), DonationRequest.needed_by)
    ).all()
    out = []
    for r in reqs:
        urgent.escalate_if_due(db, r)
        filled = db.get(Donor, r.filled_by_donor_id) if r.filled_by_donor_id else None
        out.append(
            {
                "id": r.id,
                "patient": r.patient.name,
                "blood_group": r.patient.blood_group,
                "type": r.type.value,
                "status": r.status.value,
                "needed_by": r.needed_by,
                "note": r.note,
                "alerts_sent": len(r.alerts),
                "suggested_action": _suggestion(db, r),
                "confirmed_donor": donor_view(db, filled, user, f"queue #{r.id}") if filled else None,
            }
        )
    db.commit()
    return out


@router.post("/requests/{request_id}/approve")
def approve(request_id: int, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    return urgent.approve(db, _req(db, user, request_id), user)


@router.post("/requests/{request_id}/escalate")
def escalate_now(request_id: int, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    return urgent.escalate(db, _req(db, user, request_id))


@router.get("/requests/{request_id}/candidates")
def choose_a_donor(request_id: int, radius_km: float = geo.DEFAULT_RADIUS_KM, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Wireframe 9: circle donors first, then nearby donors, each ranked by distance."""
    r = _req(db, user, request_id)
    cands = urgent.circle_candidates(db, r) + urgent.nearby_candidates(db, r, radius_km=radius_km)
    alert_status = {a.donor_id: a.status.value for a in r.alerts}
    out = []
    for i, c in enumerate(cands, 1):
        v = donor_view(db, c.donor, user, f"candidates #{r.id}")
        v |= {
            "rank": i,
            "tier": c.tier.value,
            "distance_km": round(c.distance_km, 1),
            "distance": geo.format_km(c.distance_km),
            "exact_match": c.exact_match,
            "alert": alert_status.get(c.donor.id, "not alerted"),
        }
        out.append(v)
    db.commit()
    return {"request_id": r.id, "status": r.status.value, "candidates": out, "note": "Numbers are visible to staff only. Every view is logged."}


class ConfirmIn(BaseModel):
    donor_id: int


@router.post("/requests/{request_id}/confirm")
def confirm_donor(request_id: int, body: ConfirmIn, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Staff phoned a donor who agreed: confirm them directly."""
    r = _req(db, user, request_id)
    d = db.get(Donor, body.donor_id)
    if not d:
        raise HTTPException(404, "Donor not found")
    urgent.fill(db, r, d)
    return {"status": r.status.value, "donor": d.user.name}


@router.get("/donors")
def all_donors(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    out = [donor_view(db, d, user, "donor list") for d in db.scalars(select(Donor).order_by(Donor.id))]
    db.commit()
    return out


@router.post("/donors/{donor_id}/verify")
def verify(donor_id: int, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    d = db.get(Donor, donor_id)
    if not d:
        raise HTTPException(404, "Donor not found")
    d.verified = True
    db.commit()
    return {"id": d.id, "verified": True}


@router.get("/today")
def todays_donations(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Wireframe 10: everyone expected today, to mark Donated / Deferred / No-show / Excused."""
    today = clock.today()
    appts = db.scalars(
        select(Appointment).where(
            Appointment.transfusion_date == today,
            Appointment.slot == SlotRole.confirmed,
            Appointment.status.in_(scheduling.ACTIVE),
        )
    ).all()
    reqs = db.scalars(
        select(DonationRequest).where(
            DonationRequest.blood_bank_id == user.blood_bank_id, DonationRequest.status == RequestStatus.filled
        )
    ).all()
    rows = []
    for a in appts:
        if a.patient.blood_bank_id != user.blood_bank_id:
            continue
        rows.append({"kind": "planned", "appointment_id": a.id, "request_id": None, "for": a.patient.name,
                     "donor": donor_view(db, a.donor, user, "today")})
    for r in reqs:
        d = db.get(Donor, r.filled_by_donor_id)
        rows.append({"kind": r.type.value, "appointment_id": None, "request_id": r.id, "for": r.patient.name,
                     "donor": donor_view(db, d, user, "today")})
    db.commit()
    return {"date": today, "rows": rows, "rule": "Only a no-show counts against a record. Deferred and excused do not."}


class OutcomeIn(BaseModel):
    donor_id: int
    outcome: Outcome
    appointment_id: int | None = None
    request_id: int | None = None
    reason: str = ""
    deferral_days: int = 30


@router.post("/outcomes", status_code=201)
def record_outcome(body: OutcomeIn, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    d = db.get(Donor, body.donor_id)
    if not d:
        raise HTTPException(404, "Donor not found")
    appt = db.get(Appointment, body.appointment_id) if body.appointment_id else None
    req = _req(db, user, body.request_id) if body.request_id else None
    rec = outcomes.record(db, user, d, body.outcome, appt, req, body.reason, body.deferral_days)
    return {"id": rec.id, "outcome": rec.outcome.value, "date": rec.on_date}


@router.get("/audit/phone-views")
def phone_view_audit(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(PhoneViewLog).order_by(PhoneViewLog.id.desc()).limit(100)).all()
    return [
        {"staff": db.get(User, r.staff_user_id).name, "donor_id": r.donor_id, "context": r.context, "at": r.viewed_at}
        for r in rows
    ]
