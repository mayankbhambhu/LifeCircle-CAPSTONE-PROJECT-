"""Eligibility pre-check.

This is a *preliminary* filter that uses recorded dates only. The final medical
eligibility decision is always made by blood bank staff at screening.

Rules follow the Government of India "Guidelines for Blood Donor Selection &
Blood Donor Referral" (National Blood Transfusion Council / MoHFW, 2017), for
whole-blood donation, limited to what can be checked from recorded data:
  * Age 18 to 65 on the donation date. First-time donors over 60 are not accepted.
  * Weight at least 45 kg (enough for a 350 ml unit; 450 ml needs 55 kg).
  * Minimum gap between whole-blood donations: 90 days (male), 120 days (female).
  * A donor marked "Deferred" by staff is not eligible until `deferred_until`.
Plus LifeCircle's own rules:
  * Only blood-bank-verified donors enter matching.
  * Red-cell ABO/Rh compatibility between donor and patient.

Haemoglobin (at least 12.5 g/dL), blood pressure, pulse, temperature, illness,
medication and travel history are checked at the blood bank on the day; the
app does not record them and does not make the final decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models import Donor, Sex

MIN_INTERVAL_DAYS = {Sex.male: 90, Sex.female: 120}
MIN_AGE, MAX_AGE, MAX_AGE_FIRST_TIME = 18, 65, 60
MIN_WEIGHT_KG = 45
DEFAULT_DEFERRAL_DAYS = 30


def age_on(dob: date, on_date: date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


# recipient blood group -> donor groups whose red cells it can receive
COMPATIBLE_DONORS: dict[str, set[str]] = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
}
BLOOD_GROUPS = list(COMPATIBLE_DONORS)


def is_compatible(donor_group: str, patient_group: str) -> bool:
    return donor_group in COMPATIBLE_DONORS.get(patient_group, set())


def next_eligible_date(donor: Donor) -> date:
    """First date on which the donor's recorded history allows a donation."""
    candidates = [date.min]
    if donor.last_donation_date:
        candidates.append(donor.last_donation_date + timedelta(days=MIN_INTERVAL_DAYS[donor.sex]))
    if donor.deferred_until:
        candidates.append(donor.deferred_until)
    return max(candidates)


@dataclass
class Eligibility:
    eligible: bool
    eligible_from: date
    reasons: list[str] = field(default_factory=list)


def check(donor: Donor, on_date: date, patient_group: str | None = None) -> Eligibility:
    reasons: list[str] = []
    eligible_from = next_eligible_date(donor)
    if not donor.verified:
        reasons.append("not verified by blood bank")
    if donor.date_of_birth:
        age = age_on(donor.date_of_birth, on_date)
        if age < MIN_AGE:
            reasons.append(f"under {MIN_AGE} (age {age})")
        elif age > MAX_AGE:
            reasons.append(f"over {MAX_AGE} (age {age})")
        elif age > MAX_AGE_FIRST_TIME and donor.last_donation_date is None:
            reasons.append(f"first-time donor over {MAX_AGE_FIRST_TIME}")
    if donor.weight_kg is not None and donor.weight_kg < MIN_WEIGHT_KG:
        reasons.append(f"weight under {MIN_WEIGHT_KG} kg")
    if eligible_from > on_date:
        if donor.deferred_until and donor.deferred_until == eligible_from:
            reasons.append(f"deferred until {eligible_from.isoformat()}")
        else:
            reasons.append(f"donation gap not met until {eligible_from.isoformat()}")
    if patient_group and not is_compatible(donor.blood_group, patient_group):
        reasons.append(f"{donor.blood_group} not compatible with {patient_group}")
    return Eligibility(eligible=not reasons, eligible_from=eligible_from, reasons=reasons)
