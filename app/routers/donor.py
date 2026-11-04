"""Donor endpoints (wireframes 5, 6, 7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth import require
from app.db import get_db
from app.models import (
    AlertStatus,
    Appointment,
    AppointmentStatus,
    AuthSession,
    CircleMember,
    DonationRecord,
    Donor,
    Notification,
    RequestAlert,
    Role,
    User,
)
from app.privacy import donor_view, first_name, patient_view_for_donor
from app.services import eligibility, geo, rotation, scheduling, urgent

router = APIRouter(prefix="/donor", tags=["Donor"])
donor_only = require(Role.donor)


def me(db: Session, user: User) -> Donor:
    d = db.scalar(select(Donor).where(Donor.user_id == user.id))
    if not d:
        raise HTTPException(404, "No donor profile for this account")
    return d


def appt_view(a: Appointment) -> dict:
    return {
        "id": a.id,
        "date": a.transfusion_date,
        "days_until": (a.transfusion_date - clock.today()).days,
        "slot": a.slot.value,
        "status": a.status.value,
        "where": a.patient.blood_bank.name,
        "patient": patient_view_for_donor(a.patient),
        "reminders_on": scheduling.reminder_schedule(a),
    }


@router.get("/home")
def home(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    d = me(db, user)
    upcoming = db.scalars(
        select(Appointment)
        .where(
            Appointment.donor_id == d.id,
            Appointment.status.in_(scheduling.ACTIVE),
            Appointment.transfusion_date >= clock.today(),
        )
        .order_by(Appointment.transfusion_date)
    ).all()

    # "You are next after Priya": where am I in each circle's rotation for the next date?
    turns = []
    for m in db.scalars(select(CircleMember).where(CircleMember.donor_id == d.id)):
        p = m.patient
        nxt = scheduling.next_transfusion_date(p)
        order = rotation.rank_circle(db, p, nxt).order
        ids = [r.donor.id for r in order]
        if d.id in ids:
            i = ids.index(d.id)
            ahead = first_name(order[i - 1].donor.user.name) if i > 0 else None
            turns.append({"position": i + 1, "after": ahead, "for": patient_view_for_donor(p)})
        else:
            turns.append({"position": None, "after": None, "for": patient_view_for_donor(p)})

    elig = eligibility.check(d, clock.today())
    return {
        "me": donor_view(db, d, user),
        "eligible_now": elig.eligible,
        "eligible_from": elig.eligible_from if elig.eligible_from.year > 1 else None,
        "upcoming": [appt_view(a) for a in upcoming],
        "rotation": turns,
        "open_alerts": len(_open_alerts(db, d)),
        "note": "Cancelling early is always fine.",
    }


def _my_appt(db: Session, user: User, appt_id: int) -> Appointment:
    a = db.get(Appointment, appt_id)
    if not a or a.donor_id != me(db, user).id:
        raise HTTPException(404, "Appointment not found")
    if a.status not in scheduling.ACTIVE:
        raise HTTPException(409, f"Appointment is already {a.status.value}")
    return a


@router.post("/appointments/{appt_id}/confirm")
def still_coming(appt_id: int, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    a = _my_appt(db, user, appt_id)
    a.status = AppointmentStatus.confirmed
    db.commit()
    return appt_view(a)


@router.post("/appointments/{appt_id}/cancel")
def cant_make_it(appt_id: int, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    """No penalty: cancelling never counts against the donor's record."""
    a = _my_appt(db, user, appt_id)
    return scheduling.cancel(db, a)


def _open_alerts(db: Session, d: Donor) -> list[RequestAlert]:
    alerts = db.scalars(
        select(RequestAlert).where(RequestAlert.donor_id == d.id, RequestAlert.status == AlertStatus.sent)
    ).all()
    return [a for a in alerts if a.request.status in urgent.OPEN_STATUSES]


@router.get("/alerts")
def urgent_alerts(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    d = me(db, user)
    out = []
    for a in _open_alerts(db, d):
        r = a.request
        out.append(
            {
                "id": a.id,
                "distance": geo.format_km(geo.haversine_km(d.lat, d.lng, r.patient.blood_bank.lat, r.patient.blood_bank.lng)),
                "blood_group": r.patient.blood_group,
                "needed_by": r.needed_by,
                "where": r.patient.blood_bank.name,
                "patient": patient_view_for_donor(r.patient),
                "from_your_circle": a.tier.value == "circle",
                "privacy": "Your number is shared only with the blood bank, never the family.",
            }
        )
    return out


def _my_alert(db: Session, user: User, alert_id: int) -> RequestAlert:
    a = db.get(RequestAlert, alert_id)
    if not a or a.donor_id != me(db, user).id:
        raise HTTPException(404, "Alert not found")
    return a


@router.post("/alerts/{alert_id}/accept")
def accept(alert_id: int, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    a = _my_alert(db, user, alert_id)
    urgent.respond(db, a, accept=True)
    return {"status": "confirmed", "message": f"You're confirmed. Go to {a.request.patient.blood_bank.name}."}


@router.post("/alerts/{alert_id}/decline")
def not_today(alert_id: int, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    urgent.respond(db, _my_alert(db, user, alert_id), accept=False)
    return {"status": "declined"}


class PrivacyIn(BaseModel):
    show_next_eligible_to_staff: bool | None = None
    share_location_for_urgent: bool | None = None
    urgent_alerts_enabled: bool | None = None


def _privacy(d: Donor) -> dict:
    return {
        "show_next_eligible_to_staff": d.show_next_eligible_to_staff,
        "share_location_for_urgent": d.share_location_for_urgent,
        "urgent_alerts_enabled": d.urgent_alerts_enabled,
    }


@router.get("/privacy")
def get_privacy(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    return _privacy(me(db, user))


@router.put("/privacy")
def set_privacy(body: PrivacyIn, user: User = Depends(donor_only), db: Session = Depends(get_db)):
    d = me(db, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    db.commit()
    return _privacy(d)


@router.get("/record")
def my_record(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    d = me(db, user)
    rel = rotation.reliability(db, d.id)
    rows = db.scalars(
        select(DonationRecord).where(DonationRecord.donor_id == d.id).order_by(DonationRecord.on_date.desc())
    ).all()
    return {
        "showed_up": rel.label,
        "rule": "Only a no-show counts. Excused and deferred never count against you.",
        "history": [{"date": r.on_date, "outcome": r.outcome.value, "reason": r.reason} for r in rows],
    }


@router.delete("/account")
def delete_my_account(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    """"Delete my account and number" (wireframe 7).

    Upcoming slots are cancelled first, so backups are promoted as usual. The
    donor leaves every circle, their phone number and name are erased and they
    can no longer sign in. Past donation outcomes stay, without the name, because
    the blood bank must keep its records.
    """
    d = me(db, user)
    upcoming = db.scalars(
        select(Appointment).where(Appointment.donor_id == d.id, Appointment.status.in_(scheduling.ACTIVE))
    ).all()
    for a in upcoming:
        scheduling.cancel(db, a)
    for m in db.scalars(select(CircleMember).where(CircleMember.donor_id == d.id)).all():
        db.delete(m)
    for a in _open_alerts(db, d):
        a.status = AlertStatus.declined
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all():
        db.delete(s)
    user.name = "Deleted donor"
    user.phone = f"deleted-{user.id}"
    d.lat = d.lng = 0.0
    d.verified = False
    d.urgent_alerts_enabled = d.share_location_for_urgent = d.show_next_eligible_to_staff = False
    db.commit()
    return {"deleted": True, "cancelled_appointments": len(upcoming)}


@router.get("/notifications")
def notifications(user: User = Depends(donor_only), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(20)
    ).all()
    return [{"text": n.text, "at": n.created_at} for n in rows]
