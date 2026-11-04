"""End-to-end tests of the core loop against the seeded demo data."""
import os
import re
import tempfile
from datetime import date

os.environ["LIFECIRCLE_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["LIFECIRCLE_TODAY"] = "2026-11-03"

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.main import app
from app.models import Donor, Sex
from app.seed import reset_and_seed
from app.services import eligibility, geo

PHONE = re.compile(r"\+91 \d{5} \d{5}")


@pytest.fixture()
def c():
    clock.reset()
    reset_and_seed()
    client = TestClient(app)
    client.tokens = {a["name"]: client.post(f"/demo/login/{a['id']}").json()["token"] for a in client.get("/demo/accounts").json()}
    return client


def as_(c, name):
    return {"Authorization": f"Bearer {c.tokens[name]}"}


# ------------------------------------------------------------ unit: eligibility + geo
def test_eligibility_gap_by_sex():
    d = Donor(blood_group="B+", sex=Sex.male, verified=True, last_donation_date=date(2026, 8, 1), lat=0, lng=0)
    assert not eligibility.check(d, date(2026, 10, 29)).eligible  # 89 days
    assert eligibility.check(d, date(2026, 10, 30)).eligible       # 90 days
    d.sex = Sex.female
    assert not eligibility.check(d, date(2026, 11, 28)).eligible   # 119 days
    assert eligibility.check(d, date(2026, 11, 29)).eligible


def test_eligibility_compatibility_verification_and_deferral():
    d = Donor(blood_group="A+", sex=Sex.male, verified=True, last_donation_date=None, lat=0, lng=0)
    assert not eligibility.check(d, date(2026, 11, 3), "B+").eligible
    assert eligibility.check(Donor(blood_group="O-", sex=Sex.male, verified=True, lat=0, lng=0), date(2026, 11, 3), "AB+").eligible
    d.blood_group, d.verified = "B+", False
    assert "not verified by blood bank" in eligibility.check(d, date(2026, 11, 3), "B+").reasons
    d.verified, d.deferred_until = True, date(2026, 12, 1)
    assert not eligibility.check(d, date(2026, 11, 3), "B+").eligible


def test_indian_guidelines_age_and_weight():
    on = date(2026, 11, 3)
    d = Donor(blood_group="B+", sex=Sex.male, verified=True, lat=0, lng=0, weight_kg=60,
              date_of_birth=date(2008, 11, 4), last_donation_date=None)
    assert "under 18 (age 17)" in eligibility.check(d, on).reasons
    d.date_of_birth = date(2008, 11, 3)
    assert eligibility.check(d, on).eligible                      # 18 today
    d.date_of_birth = date(1964, 1, 1)                            # 62, never donated
    assert "first-time donor over 60" in eligibility.check(d, on).reasons
    d.last_donation_date = date(2025, 1, 1)                       # 62, repeat donor
    assert eligibility.check(d, on).eligible
    d.date_of_birth = date(1960, 1, 1)                            # 66
    assert "over 65 (age 66)" in eligibility.check(d, on).reasons
    d.date_of_birth, d.weight_kg = date(1990, 1, 1), 44.5
    assert "weight under 45 kg" in eligibility.check(d, on).reasons


def test_haversine_known_distance():
    # Connaught Place to India Gate is about 2.4 km in a straight line
    assert 2.0 < geo.haversine_km(28.6315, 77.2167, 28.6129, 77.2295) < 2.6


# ------------------------------------------------------------ planned mode
def test_family_home_signature_view(c):
    h = c.get("/family/home", headers=as_(c, "Rohan Mehta")).json()
    assert h["next_transfusion"] == "2026-11-12" and h["days_until"] == 9
    assert h["confirmed"]["name"] == "Amit" and h["backup"]["name"] == "Priya"
    assert h["circle_health"]["ok"]


def test_small_circle_warning(c):
    h = c.get("/family/home", headers=as_(c, "Sunita Rao")).json()
    assert not h["circle_health"]["ok"]


def test_fair_rotation_prefers_fewer_recent_donations(c):
    # Amit gave Aarav 2x in the last year, Priya 3x -> Amit first even though Priya's last turn is older
    turns = c.get("/donor/home", headers=as_(c, "Priya Sharma")).json()["rotation"]
    assert turns[0]["position"] == 2 and turns[0]["after"] == "Amit"


def test_cancel_promotes_backup_and_then_falls_back_to_blood_bank(c):
    fam, amit, priya = as_(c, "Rohan Mehta"), as_(c, "Amit Tiwari"), as_(c, "Priya Sharma")
    appt = c.get("/donor/home", headers=amit).json()["upcoming"][0]["id"]
    r = c.post(f"/donor/appointments/{appt}/cancel", headers=amit).json()
    assert "Priya promoted from backup to confirmed" in " ".join(r["events"])
    h = c.get("/family/home", headers=fam).json()
    assert h["confirmed"]["name"] == "Priya" and h["backup"] is None
    assert any("Priya promoted" in n["text"] for n in c.get("/family/notifications", headers=fam).json())

    appt = c.get("/donor/home", headers=priya).json()["upcoming"][0]["id"]
    r = c.post(f"/donor/appointments/{appt}/cancel", headers=priya).json()
    assert r["request_id"]
    queue = c.get("/staff/queue", headers=as_(c, "R. Kumar")).json()
    assert any(q["id"] == r["request_id"] for q in queue)


def test_planned_outcome_moves_cycle_forward(c):
    staff = as_(c, "R. Kumar")
    row = c.get("/staff/today", headers=staff).json()["rows"][0]
    assert row["for"] == "Meera"
    c.post("/staff/outcomes", headers=staff, json={"donor_id": row["donor"]["id"], "outcome": "donated", "appointment_id": row["appointment_id"]})
    h = c.get("/family/home", headers=as_(c, "Sunita Rao")).json()
    assert h["next_transfusion"] == "2026-12-01"


# ------------------------------------------------------------ urgent mode
def _urgent(c):
    r = c.post("/family/urgent", headers=as_(c, "Rohan Mehta"), json={"note": "Hb dropped"}).json()
    assert r["status"] == "sent_to_bank"
    return r["id"]


def test_urgent_goes_to_blood_bank_not_donors(c):
    _urgent(c)
    assert c.get("/donor/alerts", headers=as_(c, "Amit Tiwari")).json() == []


def test_urgent_circle_first_then_nearby_ranked_by_distance(c):
    rid, staff = _urgent(c), as_(c, "R. Kumar")
    assert c.post(f"/staff/requests/{rid}/approve", headers=staff).json()["circle_alerted"] == 2  # Amit, Priya
    assert len(c.get("/donor/alerts", headers=as_(c, "Amit Tiwari")).json()) == 1
    assert c.get("/donor/alerts", headers=as_(c, "Rahul Verma")).json() == []

    clock.advance(minutes=15)  # nobody answered: lazy timer escalates on next read
    assert c.get(f"/family/requests/{rid}", headers=as_(c, "Rohan Mehta")).json()["status"] == "nearby_alerted"

    cands = c.get(f"/staff/requests/{rid}/candidates", headers=staff).json()["candidates"]
    nearby = [x for x in cands if x["tier"] == "nearby"]
    names = [x["name"] for x in nearby]
    assert names == ["Rahul Verma", "Ananya Singh", "Ishaan Gupta", "Vikram Joshi", "Sneha Kapoor"]
    assert [x["distance_km"] for x in nearby] == sorted(x["distance_km"] for x in nearby)
    # filtered out: unverified, gave recently, alerts off, location off, incompatible, too far
    # and the Indian (NBTC) rules: under 18, first-time donor over 60, under 45 kg
    for skipped in ["Pooja Nair", "Arjun Reddy", "Kavya Iyer", "Farhan Ali", "Rohit Das", "Tanvi Shah", "Manish Yadav",
                    "Kabir Malhotra", "Leela Bose", "Sameer Khan"]:
        assert skipped not in names

    alert = c.get("/donor/alerts", headers=as_(c, "Ishaan Gupta")).json()[0]
    assert alert["distance"] == "2.4 km" and alert["patient"]["name"] == "Name hidden"


def test_first_acceptance_wins(c):
    rid, staff = _urgent(c), as_(c, "R. Kumar")
    c.post(f"/staff/requests/{rid}/approve", headers=staff)
    c.post(f"/staff/requests/{rid}/escalate", headers=staff)
    a1 = c.get("/donor/alerts", headers=as_(c, "Ananya Singh")).json()[0]["id"]
    a2 = c.get("/donor/alerts", headers=as_(c, "Amit Tiwari")).json()[0]["id"]
    assert c.post(f"/donor/alerts/{a1}/accept", headers=as_(c, "Ananya Singh")).status_code == 200
    late = c.post(f"/donor/alerts/{a2}/accept", headers=as_(c, "Amit Tiwari"))
    assert late.status_code == 409
    assert c.get(f"/family/requests/{rid}", headers=as_(c, "Rohan Mehta")).json()["status"] == "filled"
    # staff records the outcome; donor's eligibility clock restarts
    q = next(q for q in c.get("/staff/queue", headers=staff).json() if q["id"] == rid)
    assert q["confirmed_donor"]["name"] == "Ananya Singh"
    r = c.post("/staff/outcomes", headers=staff, json={"donor_id": q["confirmed_donor"]["id"], "outcome": "donated", "request_id": rid})
    assert r.status_code == 201
    assert c.get("/donor/home", headers=as_(c, "Ananya Singh")).json()["eligible_now"] is False


# ------------------------------------------------------------ privacy + roles
def test_family_never_sees_phone_numbers(c):
    fam = as_(c, "Rohan Mehta")
    rid = _urgent(c)
    c.post(f"/staff/requests/{rid}/approve", headers=as_(c, "R. Kumar"))
    for path in ["/family/home", f"/family/requests/{rid}", "/family/notifications", "/family/plan"]:
        assert not PHONE.search(c.get(path, headers=fam).text), path


def test_donor_sees_no_other_phone_numbers(c):
    body = c.get("/donor/home", headers=as_(c, "Priya Sharma")).text
    assert PHONE.findall(body) == ["+91 98111 22334"]  # only her own


def test_roles_are_enforced(c):
    assert c.get("/staff/donors", headers=as_(c, "Rohan Mehta")).status_code == 403
    assert c.get("/staff/donors", headers=as_(c, "Amit Tiwari")).status_code == 403
    assert c.get("/family/home", headers=as_(c, "R. Kumar")).status_code == 403
    assert c.get("/family/home").status_code == 401


def test_staff_phone_views_are_logged(c):
    staff = as_(c, "R. Kumar")
    before = len(c.get("/staff/audit/phone-views", headers=staff).json())
    donors = c.get("/staff/donors", headers=staff).json()
    assert PHONE.search(donors[0]["phone"])
    after = len(c.get("/staff/audit/phone-views", headers=staff).json())
    assert after - before == len(donors)


def test_donor_can_hide_next_eligible_date_from_staff(c):
    c.put("/donor/privacy", headers=as_(c, "Amit Tiwari"), json={"show_next_eligible_to_staff": False})
    amit = next(d for d in c.get("/staff/donors", headers=as_(c, "R. Kumar")).json() if d["name"] == "Amit Tiwari")
    assert amit["next_eligible_date"] == "hidden by donor"


def test_otp_login(c):
    assert c.post("/auth/login", json={"phone": "+91 90000 00001", "otp": "0000"}).status_code == 401
    ok = c.post("/auth/login", json={"phone": "+91 90000 00001", "otp": "1234"}).json()
    assert ok["role"] == "family"
