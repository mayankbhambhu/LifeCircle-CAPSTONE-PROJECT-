"""Fair rotation of a patient's donor circle.

For a given transfusion date we:
  1. keep only circle donors who pass the eligibility pre-check on that date
     and have not already said they can't make it,
  2. sort them so the load is spread out:
       a. fewest donations to this patient in the last 12 months,
       b. then the donor whose last turn (donation or assignment) was longest ago,
       c. then the better reliability record,
       d. then donor id, so the order is always deterministic,
  3. take the first as Confirmed and the second as Backup.

Circle health: a donor can give roughly once every 90-120 days, so a patient on
a 21-day cycle needs ceil(average gap / 21) donors to cover every cycle, plus 1
for a backup. With an average gap of 105 days that is 5 + 1 = 6 donors.
Smaller circles get a warning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    DonationRecord,
    Donor,
    Outcome,
    Patient,
    Sex,
)
from app.services import eligibility


@dataclass
class Reliability:
    showed_up: int
    expected: int

    @property
    def ratio(self) -> float:
        return 1.0 if self.expected == 0 else self.showed_up / self.expected

    @property
    def label(self) -> str:
        return f"{self.showed_up} of {self.expected}"


def reliability(db: Session, donor_id: int) -> Reliability:
    """Only a no-show counts against a donor. Deferred = they came; excused is ignored."""
    outcomes = db.scalars(select(DonationRecord.outcome).where(DonationRecord.donor_id == donor_id)).all()
    showed = sum(1 for o in outcomes if o in (Outcome.donated, Outcome.deferred))
    no_show = sum(1 for o in outcomes if o == Outcome.no_show)
    return Reliability(showed_up=showed, expected=showed + no_show)


@dataclass
class RankedDonor:
    donor: Donor
    donations_to_patient: int
    last_turn: date | None
    reliability: Reliability


@dataclass
class RotationResult:
    on_date: date
    order: list[RankedDonor]          # eligible donors, fairest first
    ineligible: dict[int, list[str]]  # donor_id -> reasons

    @property
    def confirmed(self) -> Donor | None:
        return self.order[0].donor if self.order else None

    @property
    def backup(self) -> Donor | None:
        return self.order[1].donor if len(self.order) > 1 else None


def _last_turn(db: Session, patient_id: int, donor_id: int, before: date) -> date | None:
    rec = db.scalar(
        select(DonationRecord.on_date)
        .where(DonationRecord.patient_id == patient_id, DonationRecord.donor_id == donor_id)
        .order_by(DonationRecord.on_date.desc())
    )
    appt = db.scalar(
        select(Appointment.transfusion_date)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.donor_id == donor_id,
            Appointment.status != AppointmentStatus.cancelled,
            Appointment.transfusion_date < before,
        )
        .order_by(Appointment.transfusion_date.desc())
    )
    dates = [d for d in (rec, appt) if d]
    return max(dates) if dates else None


def rank_circle(
    db: Session, patient: Patient, on_date: date, exclude_donor_ids: set[int] | None = None
) -> RotationResult:
    exclude = set(exclude_donor_ids or ())
    # donors who already cancelled this date are out for this date
    cancelled = db.scalars(
        select(Appointment.donor_id).where(
            Appointment.patient_id == patient.id,
            Appointment.transfusion_date == on_date,
            Appointment.status == AppointmentStatus.cancelled,
        )
    ).all()
    exclude |= set(cancelled)

    year_ago = on_date - timedelta(days=365)
    ranked: list[RankedDonor] = []
    ineligible: dict[int, list[str]] = {}
    for member in patient.circle:
        donor = member.donor
        if donor.id in exclude:
            ineligible[donor.id] = ["cancelled for this date"]
            continue
        check = eligibility.check(donor, on_date, patient.blood_group)
        if not check.eligible:
            ineligible[donor.id] = check.reasons
            continue
        count = len(
            db.scalars(
                select(DonationRecord.id).where(
                    DonationRecord.patient_id == patient.id,
                    DonationRecord.donor_id == donor.id,
                    DonationRecord.outcome == Outcome.donated,
                    DonationRecord.on_date >= year_ago,
                )
            ).all()
        )
        ranked.append(
            RankedDonor(
                donor=donor,
                donations_to_patient=count,
                last_turn=_last_turn(db, patient.id, donor.id, on_date),
                reliability=reliability(db, donor.id),
            )
        )

    ranked.sort(
        key=lambda r: (
            r.donations_to_patient,
            r.last_turn or date.min,
            -r.reliability.ratio,
            r.donor.id,
        )
    )
    return RotationResult(on_date=on_date, order=ranked, ineligible=ineligible)


def circle_health(patient: Patient) -> dict:
    size = len(patient.circle)
    gaps = [eligibility.MIN_INTERVAL_DAYS[m.donor.sex] for m in patient.circle]
    gap = sum(gaps) / len(gaps) if gaps else eligibility.MIN_INTERVAL_DAYS[Sex.male]
    needed = math.ceil(gap / patient.cycle_days) + 1
    ok = size >= needed
    weeks = round(patient.cycle_days / 7)
    msg = (
        f"Circle health: {size} donors, enough for a {weeks}-week cycle"
        if ok
        else f"Small circle: {size} donors, about {needed} needed for a {weeks}-week cycle"
    )
    return {"size": size, "recommended": needed, "ok": ok, "message": msg}
