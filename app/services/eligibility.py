"""Eligibility pre-check.

This is a *preliminary* filter that uses recorded dates only. The final medical
eligibility decision is always made by blood bank staff at screening.

Rules used (configurable below):
  * Minimum gap between whole-blood donations: 90 days (male), 120 days (female).
    These follow common Indian (NBTC) whole-blood guidance; change them here if
    your blood bank uses different numbers.
  * A donor marked "Deferred" by staff is not eligible until `deferred_until`.
  * Only blood-bank-verified donors enter matching.
  * Red-cell ABO/Rh compatibility between donor and patient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models import Donor, Sex

MIN_INTERVAL_DAYS = {Sex.male: 90, Sex.female: 120}
DEFAULT_DEFERRAL_DAYS = 30

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
    if eligible_from > on_date:
        if donor.deferred_until and donor.deferred_until == eligible_from:
            reasons.append(f"deferred until {eligible_from.isoformat()}")
        else:
            reasons.append(f"donation gap not met until {eligible_from.isoformat()}")
    if patient_group and not is_compatible(donor.blood_group, patient_group):
        reasons.append(f"{donor.blood_group} not compatible with {patient_group}")
    return Eligibility(eligible=not reasons, eligible_from=eligible_from, reasons=reasons)
