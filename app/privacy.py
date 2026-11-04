"""Privacy routing: what each role is allowed to see about a donor.

Every API response that mentions a donor goes through `donor_view`, so the rule
lives in one place:

  viewer            sees
  ----------------  -------------------------------------------------------------
  patient family    first name + verified badge. Never phone, location, history.
  another donor     first name only (e.g. "You are next after Priya").
  the donor         everything about themselves.
  blood bank staff  full name, phone, verification, eligibility, reliability.
                    Every time a phone number is shown to staff, a row is
                    written to phone_view_logs.

Patients are shown to donors as "Name hidden" with only the blood group.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import clock
from app.models import Donor, Patient, PhoneViewLog, Role, User
from app.services import eligibility, rotation
from app.services.scheduling import first_name


def donor_view(db: Session, donor: Donor, viewer: User, context: str = "") -> dict:
    if viewer.role == Role.family:
        return {"id": donor.id, "name": first_name(donor.user.name), "verified": donor.verified}

    if viewer.role == Role.donor and viewer.id != donor.user_id:
        return {"id": donor.id, "name": first_name(donor.user.name)}

    rel = rotation.reliability(db, donor.id)
    data = {
        "id": donor.id,
        "name": donor.user.name,
        "phone": donor.user.phone,
        "blood_group": donor.blood_group,
        "verified": donor.verified,
        "last_donation_date": donor.last_donation_date,
        "reliability": rel.label,
    }
    if viewer.role == Role.donor:  # looking at themselves
        data["next_eligible_date"] = eligibility.next_eligible_date(donor)
        return data

    # staff
    if donor.show_next_eligible_to_staff:
        data["next_eligible_date"] = eligibility.next_eligible_date(donor)
        data["eligible_today"] = eligibility.check(donor, clock.today()).eligible
    else:
        data["next_eligible_date"] = "hidden by donor"
        data.pop("last_donation_date")
    data["urgent_alerts_enabled"] = donor.urgent_alerts_enabled
    db.add(PhoneViewLog(staff_user_id=viewer.id, donor_id=donor.id, context=context or "view", viewed_at=clock.now()))
    return data


def patient_view_for_donor(patient: Patient) -> dict:
    return {"name": "Name hidden", "blood_group": patient.blood_group}
