"""Planned mode: next date, confirmed + backup, reminders, backup promotion."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    Appointment,
    AppointmentStatus,
    DonationRequest,
    Patient,
    RequestStatus,
    RequestType,
    SlotRole,
    User,
)
from app.services import rotation
from app.services.notify import notify


def first_name(full: str) -> str:
    return full.split()[0]

ACTIVE = (AppointmentStatus.scheduled, AppointmentStatus.confirmed)
REMINDER_DAYS_BEFORE = (2, 1, 0)  # "2 days before, next morning, 3 hours before"


def next_transfusion_date(patient: Patient, today: date | None = None) -> date:
    """last transfusion + cycle; if that is already past, roll forward whole cycles."""
    today = today or clock.today()
    nxt = patient.last_transfusion_date + timedelta(days=patient.cycle_days)
    while nxt < today:
        nxt += timedelta(days=patient.cycle_days)
    return nxt


def booked_on(db: Session, on_date: date) -> set[int]:
    """Donors already holding a confirmed or backup slot (for any patient) on this date."""
    return set(
        db.scalars(
            select(Appointment.donor_id).where(
                Appointment.transfusion_date == on_date, Appointment.status.in_(ACTIVE)
            )
        ).all()
    )


def active_slots(db: Session, patient_id: int, on_date: date) -> dict[SlotRole, Appointment]:
    appts = db.scalars(
        select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.transfusion_date == on_date,
            Appointment.status.in_(ACTIVE),
        )
    ).all()
    return {a.slot: a for a in appts}


def _assign(db: Session, patient: Patient, on_date: date, slot: SlotRole, exclude: set[int]) -> Appointment | None:
    ranked = rotation.rank_circle(db, patient, on_date, exclude_donor_ids=exclude | booked_on(db, on_date))
    if not ranked.order:
        return None
    donor = ranked.order[0].donor
    appt = Appointment(
        patient_id=patient.id,
        donor_id=donor.id,
        transfusion_date=on_date,
        slot=slot,
        status=AppointmentStatus.scheduled,
        created_at=clock.now(),
    )
    db.add(appt)
    db.flush()
    label = "confirmed donor" if slot == SlotRole.confirmed else "backup donor"
    notify(
        db,
        donor.user_id,
        f"You are the {label} on {on_date:%a %d %b}. Please reply 'Yes, I'll come' or 'I can't make it'.",
    )
    return appt


def ensure_plan(db: Session, patient: Patient) -> dict[SlotRole, Appointment]:
    """Make sure the next transfusion has a confirmed donor and a backup."""
    on_date = next_transfusion_date(patient)
    slots = active_slots(db, patient.id, on_date)
    taken = {a.donor_id for a in slots.values()}
    for slot in (SlotRole.confirmed, SlotRole.backup):
        if slot not in slots:
            appt = _assign(db, patient, on_date, slot, exclude=taken)
            if appt:
                slots[slot] = appt
                taken.add(appt.donor_id)
    db.commit()
    return slots


def replan(db: Session, patient: Patient) -> dict[SlotRole, Appointment]:
    """Plan settings changed: drop future open slots on other dates and plan again."""
    on_date = next_transfusion_date(patient)
    stale = db.scalars(
        select(Appointment).where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(ACTIVE),
            Appointment.transfusion_date != on_date,
            Appointment.transfusion_date >= clock.today(),
        )
    ).all()
    for a in stale:
        db.delete(a)
    db.flush()
    return ensure_plan(db, patient)


def cancel(db: Session, appt: Appointment) -> dict:
    """Donor says "I can't make it". Promote backup, pick a new backup, tell the family.

    Returns a short summary of what happened, used by the API and the demo.
    """
    patient = appt.patient
    family = db.get(User, patient.family_user_id)
    was = appt.slot
    appt.status = AppointmentStatus.cancelled
    db.flush()

    on_date = appt.transfusion_date
    slots = active_slots(db, patient.id, on_date)
    events: list[str] = [f"{first_name(appt.donor.user.name)} cancelled"]

    if was == SlotRole.confirmed:
        backup = slots.get(SlotRole.backup)
        if backup:
            backup.slot = SlotRole.confirmed
            db.flush()
            events.append(f"{first_name(backup.donor.user.name)} promoted from backup to confirmed")
            notify(db, backup.donor.user_id, f"You are now the confirmed donor on {on_date:%a %d %b}.")
    slots = active_slots(db, patient.id, on_date)
    taken = {a.donor_id for a in slots.values()}
    for slot in (SlotRole.confirmed, SlotRole.backup):
        if slot not in slots:
            new = _assign(db, patient, on_date, slot, exclude=taken)
            if new:
                taken.add(new.donor_id)
                events.append(f"{first_name(new.donor.user.name)} assigned as {slot.value}")
                slots[slot] = new

    urgent_id = None
    if SlotRole.confirmed not in slots:
        # Circle can't cover it any more: hand over to the blood bank.
        req = DonationRequest(
            patient_id=patient.id,
            blood_bank_id=patient.blood_bank_id,
            type=RequestType.planned,
            status=RequestStatus.sent_to_bank,
            needed_by=datetime.combine(on_date, time(10, 0)),
            note=f"{first_name(appt.donor.user.name)} cancelled and no eligible circle donor is left",
            created_at=clock.now(),
        )
        db.add(req)
        db.flush()
        urgent_id = req.id
        events.append("No eligible circle donor left: request sent to blood bank")

    notify(db, family.id, "Plan update for " + f"{on_date:%d %b}: " + "; ".join(events) + ".")
    db.commit()
    return {"events": events, "request_id": urgent_id}


def reminder_schedule(appt: Appointment) -> list[date]:
    return [appt.transfusion_date - timedelta(days=d) for d in REMINDER_DAYS_BEFORE]
