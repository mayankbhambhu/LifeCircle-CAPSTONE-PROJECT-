"""Urgent mode: circle first, then nearby eligible donors ranked by distance.

Flow
  1. Family presses "Request urgent help"  -> request goes to the blood bank (not to donors)
  2. Staff approves                         -> every eligible donor in the patient's circle is alerted
  3. No acceptance within 15 minutes        -> nearby eligible donors (not in the circle) are alerted,
     (or staff presses "Escalate now")         ranked by distance from the blood bank
  4. The first donor to accept is confirmed; everyone else's alert closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    AlertStatus,
    AlertTier,
    Donor,
    DonationRequest,
    Patient,
    RequestAlert,
    RequestStatus,
    RequestType,
    User,
)
from app.services import eligibility, geo, scheduling
from app.services.notify import notify

ESCALATE_AFTER = timedelta(minutes=15)
OPEN_STATUSES = (RequestStatus.sent_to_bank, RequestStatus.circle_alerted, RequestStatus.nearby_alerted)


@dataclass
class Candidate:
    donor: Donor
    distance_km: float
    tier: AlertTier
    exact_match: bool


def create(db: Session, patient: Patient, needed_by: datetime, note: str = "") -> DonationRequest:
    req = DonationRequest(
        patient_id=patient.id,
        blood_bank_id=patient.blood_bank_id,
        type=RequestType.urgent,
        status=RequestStatus.sent_to_bank,
        needed_by=needed_by,
        note=note,
        created_at=clock.now(),
    )
    db.add(req)
    db.flush()
    for staff in db.scalars(select(User).where(User.blood_bank_id == patient.blood_bank_id)):
        notify(db, staff.id, f"Urgent request #{req.id}: {patient.blood_group} needed by {needed_by:%d %b %H:%M}.")
    db.commit()
    return req


def _circle_ids(patient: Patient) -> set[int]:
    return {m.donor_id for m in patient.circle}


def circle_candidates(db: Session, req: DonationRequest) -> list[Candidate]:
    patient, bank = req.patient, req.patient.blood_bank
    out = []
    for m in patient.circle:
        d = m.donor
        if not d.urgent_alerts_enabled:
            continue
        if not eligibility.check(d, req.needed_by.date(), patient.blood_group).eligible:
            continue
        out.append(
            Candidate(
                donor=d,
                distance_km=geo.haversine_km(d.lat, d.lng, bank.lat, bank.lng),
                tier=AlertTier.circle,
                exact_match=d.blood_group == patient.blood_group,
            )
        )
    out.sort(key=lambda c: c.distance_km)
    return out


def nearby_candidates(
    db: Session, req: DonationRequest, radius_km: float = geo.DEFAULT_RADIUS_KM, limit: int = 10
) -> list[Candidate]:
    """Verified, eligible, compatible donors outside the circle who opted in to
    urgent alerts and location sharing, within `radius_km` of the blood bank,
    nearest first (exact blood-group match breaks ties)."""
    patient, bank = req.patient, req.patient.blood_bank
    # skip the circle (alerted in tier 1) and anyone already booked to donate that day
    skip = _circle_ids(patient) | scheduling.booked_on(db, req.needed_by.date())
    out = []
    for d in db.scalars(select(Donor)):
        if d.id in skip or not (d.urgent_alerts_enabled and d.share_location_for_urgent):
            continue
        if not eligibility.check(d, req.needed_by.date(), patient.blood_group).eligible:
            continue
        km = geo.haversine_km(d.lat, d.lng, bank.lat, bank.lng)
        if km > radius_km:
            continue
        out.append(Candidate(d, km, AlertTier.nearby, d.blood_group == patient.blood_group))
    out.sort(key=lambda c: (round(c.distance_km, 1), not c.exact_match, c.donor.id))
    return out[:limit]


def _send(db: Session, req: DonationRequest, cands: list[Candidate]) -> int:
    existing = {a.donor_id for a in req.alerts}
    start = len(req.alerts)
    sent = 0
    for i, c in enumerate(cands):
        if c.donor.id in existing:
            continue
        db.add(
            RequestAlert(
                request_id=req.id,
                donor_id=c.donor.id,
                tier=c.tier,
                distance_km=round(c.distance_km, 2),
                rank=start + i + 1,
                status=AlertStatus.sent,
                sent_at=clock.now(),
            )
        )
        notify(
            db,
            c.donor.user_id,
            f"Urgent: {req.patient.blood_group} needed at {req.patient.blood_bank.name}, "
            f"{geo.format_km(c.distance_km)} from you. Can you donate?",
        )
        sent += 1
    db.flush()
    db.refresh(req)
    return sent


def approve(db: Session, req: DonationRequest, staff: User) -> dict:
    if req.status != RequestStatus.sent_to_bank:
        raise HTTPException(409, f"Request is already {req.status.value}")
    req.approved_by_user_id = staff.id
    sent = _send(db, req, circle_candidates(db, req))
    req.status = RequestStatus.circle_alerted
    req.circle_alerted_at = clock.now()
    notify(db, req.patient.family_user_id, "Blood bank approved your request. Your donor circle has been alerted.")
    result = {"circle_alerted": sent, "nearby_alerted": 0}
    if sent == 0:
        # Nobody in the circle can help on this date: skip straight to nearby donors.
        result["nearby_alerted"] = escalate(db, req)["nearby_alerted"]
    db.commit()
    return result


def escalate(db: Session, req: DonationRequest) -> dict:
    if req.status not in (RequestStatus.circle_alerted, RequestStatus.nearby_alerted):
        raise HTTPException(409, f"Cannot escalate a request that is {req.status.value}")
    sent = _send(db, req, nearby_candidates(db, req))
    req.status = RequestStatus.nearby_alerted
    req.nearby_alerted_at = clock.now()
    notify(db, req.patient.family_user_id, "Circle has not filled the request yet. Nearby donors are being alerted.")
    db.commit()
    return {"nearby_alerted": sent}


def escalate_if_due(db: Session, req: DonationRequest) -> bool:
    """Lazy 15-minute timer: called whenever a request is read."""
    if (
        req.status == RequestStatus.circle_alerted
        and req.circle_alerted_at
        and clock.now() - req.circle_alerted_at >= ESCALATE_AFTER
    ):
        escalate(db, req)
        return True
    return False


def fill(db: Session, req: DonationRequest, donor: Donor) -> None:
    """First acceptance wins. Everyone else's alert is closed."""
    if req.status not in OPEN_STATUSES or req.filled_by_donor_id:
        raise HTTPException(409, "This request has already been filled. Thank you for responding!")
    if not eligibility.check(donor, req.needed_by.date(), req.patient.blood_group).eligible:
        raise HTTPException(409, "Donor does not pass the eligibility pre-check for this request")
    # Atomic "first one wins": only succeeds if nobody filled it in the meantime.
    won = db.execute(
        update(DonationRequest)
        .where(DonationRequest.id == req.id, DonationRequest.filled_by_donor_id.is_(None))
        .values(filled_by_donor_id=donor.id, status=RequestStatus.filled)
    ).rowcount
    if not won:
        db.rollback()
        raise HTTPException(409, "This request has already been filled. Thank you for responding!")
    db.refresh(req)
    now = clock.now()
    for a in req.alerts:
        if a.donor_id == donor.id:
            a.status, a.responded_at = AlertStatus.accepted, now
        elif a.status == AlertStatus.sent:
            a.status = AlertStatus.expired
    notify(db, req.patient.family_user_id, f"A donor ({donor.user.name.split()[0]}) is confirmed for your request.")
    notify(db, donor.user_id, f"You're confirmed. Please go to {req.patient.blood_bank.name} by {req.needed_by:%d %b %H:%M}.")
    db.commit()


def respond(db: Session, alert: RequestAlert, accept: bool) -> None:
    if alert.status != AlertStatus.sent:
        raise HTTPException(409, f"Alert is already {alert.status.value}")
    if accept:
        fill(db, alert.request, alert.donor)
    else:
        alert.status, alert.responded_at = AlertStatus.declined, clock.now()
        db.commit()
