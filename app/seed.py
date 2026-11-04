"""Seeded DEMO data. Every person here is fictional.

Dates are relative to "today" so the demo always looks the same:
  * Aarav (B+, 21-day cycle) had his last transfusion 12 days ago, so the next
    one is in 9 days. Fair rotation picks Amit (confirmed) and Priya (backup);
    the other four circle donors gave recently and are not eligible yet.
  * Meera (O+, 28-day cycle) is due today and has a small circle of 3, so the
    family sees a small-circle warning and staff see her donor on "Today".
  * 12 donors outside any circle live around the blood bank for urgent mode.
    Some are deliberately filtered out (unverified, gave recently, opted out of
    alerts or location, wrong blood group, too far) to show the filters work.

Run:  python -m app.seed
"""
from __future__ import annotations

from datetime import timedelta
from math import cos, radians

from sqlalchemy.orm import Session

from app import clock
from app.db import SessionLocal, engine
from app.models import (
    Base,
    BloodBank,
    CircleMember,
    DonationRecord,
    Donor,
    Outcome,
    Patient,
    Role,
    Sex,
    User,
)
from app.services import scheduling

BANK = ("District Blood Bank", 28.6139, 77.2090)


def offset(km_north: float, km_east: float) -> tuple[float, float]:
    lat = BANK[1] + km_north / 111.0
    lng = BANK[2] + km_east / (111.320 * cos(radians(BANK[1])))
    return round(lat, 6), round(lng, 6)


# name, phone, group, sex, (km N, km E), last-donation days ago, verified, alerts, location
CIRCLE_AARAV = [
    ("Amit Tiwari", "+91 98765 43210", "B+", Sex.male, (1.2, 0.0), 117, True, True, True),
    ("Priya Sharma", "+91 98111 22334", "B+", Sex.female, (-1.5, 1.0), 138, True, True, True),
    ("Sahil Khanna", "+91 98222 33445", "O+", Sex.male, (3.0, -2.0), 33, True, True, True),
    ("Divya Menon", "+91 98333 44556", "B-", Sex.female, (-2.5, -2.5), 75, True, True, True),
    ("Karan Patel", "+91 99887 76655", "B+", Sex.male, (0.0, 3.8), 12, True, True, True),
    ("Neha Saxena", "+91 91234 56780", "O+", Sex.female, (2.0, 0.0), 54, True, True, True),
]
CIRCLE_MEERA = [
    ("Rajesh Kumar", "+91 97000 11111", "O+", Sex.male, (-3.0, 1.0), 95, True, True, True),
    ("Deepa Pillai", "+91 97000 22222", "O-", Sex.female, (1.0, -4.0), 130, True, True, True),
    ("Suresh Bhat", "+91 97000 33333", "O+", Sex.male, (4.0, 4.0), 40, True, True, True),
]
EXTERNAL = [
    ("Rahul Verma", "+91 96000 00001", "B+", Sex.male, (1.2, 0.0), 200, True, True, True),
    ("Ishaan Gupta", "+91 96000 00002", "O+", Sex.male, (0.0, 2.4), 150, True, True, True),
    ("Ananya Singh", "+91 96000 00003", "B+", Sex.female, (-2.0, 0.0), 180, True, True, True),
    ("Vikram Joshi", "+91 96000 00004", "O-", Sex.male, (2.7, 2.7), None, True, True, True),
    ("Sneha Kapoor", "+91 96000 00005", "B-", Sex.female, (-5.0, 5.9), 300, True, True, True),
    ("Pooja Nair", "+91 96000 00006", "B+", Sex.female, (4.5, 0.0), 200, False, True, True),   # unverified
    ("Arjun Reddy", "+91 96000 00007", "B+", Sex.male, (0.0, -5.1), 20, True, True, True),     # gave recently
    ("Kavya Iyer", "+91 96000 00008", "O+", Sex.female, (-6.3, 0.0), 200, True, False, True),  # alerts off
    ("Farhan Ali", "+91 96000 00009", "O+", Sex.male, (6.0, -6.6), 200, True, True, False),    # location off
    ("Rohit Das", "+91 96000 00010", "A+", Sex.male, (1.0, 0.0), 200, True, True, True),      # incompatible
    ("Tanvi Shah", "+91 96000 00011", "AB+", Sex.female, (0.0, 2.2), 200, True, True, True),  # incompatible
    ("Manish Yadav", "+91 96000 00012", "B+", Sex.male, (14.0, 0.0), 200, True, True, True),  # too far
]


def _donor(db: Session, row, today) -> Donor:
    name, phone, group, sex, (n, e), last, verified, alerts, loc = row
    u = User(name=name, phone=phone, role=Role.donor)
    db.add(u)
    db.flush()
    lat, lng = offset(n, e)
    d = Donor(
        user_id=u.id,
        blood_group=group,
        sex=sex,
        lat=lat,
        lng=lng,
        last_donation_date=today - timedelta(days=last) if last is not None else None,
        verified=verified,
        urgent_alerts_enabled=alerts,
        share_location_for_urgent=loc,
    )
    db.add(d)
    db.flush()
    return d


def seed(db: Session) -> None:
    today = clock.today()
    bank = BloodBank(name=BANK[0], lat=BANK[1], lng=BANK[2])
    db.add(bank)
    db.flush()

    staff = User(name="R. Kumar", phone="+91 90000 00100", role=Role.staff, blood_bank_id=bank.id)
    fam1 = User(name="Rohan Mehta", phone="+91 90000 00001", role=Role.family)
    fam2 = User(name="Sunita Rao", phone="+91 90000 00002", role=Role.family)
    db.add_all([staff, fam1, fam2])
    db.flush()

    aarav = Patient(name="Aarav", blood_group="B+", cycle_days=21, last_transfusion_date=today - timedelta(days=12),
                    family_user_id=fam1.id, blood_bank_id=bank.id)
    meera = Patient(name="Meera", blood_group="O+", cycle_days=28, last_transfusion_date=today - timedelta(days=28),
                    family_user_id=fam2.id, blood_bank_id=bank.id)
    db.add_all([aarav, meera])
    db.flush()

    def rec(d: Donor, days_ago: int, outcome=Outcome.donated, patient=None, reason=""):
        db.add(DonationRecord(donor_id=d.id, patient_id=patient.id if patient else None, outcome=outcome,
                              reason=reason, on_date=today - timedelta(days=days_ago), recorded_by_user_id=staff.id))

    circle_a = [_donor(db, r, today) for r in CIRCLE_AARAV]
    circle_m = [_donor(db, r, today) for r in CIRCLE_MEERA]
    for r in EXTERNAL:
        _donor(db, r, today)

    for d in circle_a:
        db.add(CircleMember(patient_id=aarav.id, donor_id=d.id, joined_on=today - timedelta(days=400)))
    for d in circle_m:
        db.add(CircleMember(patient_id=meera.id, donor_id=d.id, joined_on=today - timedelta(days=400)))

    amit, priya, sahil, divya, karan, neha = circle_a
    # Donation history for Aarav (drives fair rotation and "showed up 4 of 5").
    rec(karan, 12, patient=aarav)
    rec(sahil, 33, patient=aarav)
    rec(neha, 54, patient=aarav)
    rec(divya, 75, patient=aarav)
    rec(amit, 117, patient=aarav)
    rec(priya, 138, patient=aarav)
    rec(amit, 222, Outcome.no_show, patient=aarav)
    rec(amit, 243, patient=aarav)
    rec(priya, 264, patient=aarav)
    rec(priya, 350, patient=aarav)
    rec(amit, 400)
    rec(amit, 520)
    rec(karan, 180, Outcome.excused, patient=aarav, reason="illness")

    rajesh, deepa, suresh = circle_m
    rec(suresh, 40, patient=meera)
    rec(rajesh, 95, patient=meera)
    rec(deepa, 130, patient=meera)
    db.commit()

    for p in (aarav, meera):
        db.refresh(p)
        scheduling.ensure_plan(db, p)


def reset_and_seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    reset_and_seed()
    print("Seeded demo data.")
