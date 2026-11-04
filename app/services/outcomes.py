"""Blood bank staff record what actually happened after screening."""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    Appointment,
    AppointmentStatus,
    DonationRecord,
    DonationRequest,
    Donor,
    Outcome,
    RequestStatus,
    SlotRole,
    User,
)
from app.services import eligibility, scheduling
from app.services.notify import notify


def record(
    db: Session,
    staff: User,
    donor: Donor,
    outcome: Outcome,
    appointment: Appointment | None = None,
    request: DonationRequest | None = None,
    reason: str = "",
    deferral_days: int = eligibility.DEFAULT_DEFERRAL_DAYS,
) -> DonationRecord:
    if appointment is None and request is None:
        raise HTTPException(422, "Give an appointment_id or a request_id")
    if appointment and appointment.donor_id != donor.id:
        raise HTTPException(422, "Donor does not match the appointment")
    if request and request.filled_by_donor_id != donor.id:
        raise HTTPException(422, "Donor is not the one confirmed for this request")

    today = clock.today()
    patient_id = appointment.patient_id if appointment else request.patient_id
    rec = DonationRecord(
        donor_id=donor.id,
        patient_id=patient_id,
        appointment_id=appointment.id if appointment else None,
        request_id=request.id if request else None,
        outcome=outcome,
        reason=reason,
        on_date=today,
        recorded_by_user_id=staff.id,
    )
    db.add(rec)

    if outcome == Outcome.donated:
        donor.last_donation_date = today
        donor.deferred_until = None
    elif outcome == Outcome.deferred:
        donor.deferred_until = today + timedelta(days=deferral_days)

    if appointment:
        appointment.status = AppointmentStatus.completed
        if outcome == Outcome.donated and appointment.slot == SlotRole.confirmed:
            # The patient got their transfusion: the next cycle starts from here.
            appointment.patient.last_transfusion_date = appointment.transfusion_date
            # Backup is released for this date.
            for slot, a in scheduling.active_slots(db, patient_id, appointment.transfusion_date).items():
                if slot == SlotRole.backup:
                    a.status = AppointmentStatus.completed
    if request:
        request.status = RequestStatus.closed

    msg = {
        Outcome.donated: "Thank you for donating today!",
        Outcome.deferred: f"You were deferred at screening. You can donate again from {donor.deferred_until}.",
        Outcome.no_show: "You were marked as a no-show. Ask staff if this is wrong.",
        Outcome.excused: "Your absence was excused. It does not affect your record.",
    }[outcome]
    notify(db, donor.user_id, msg)
    db.commit()
    return rec
