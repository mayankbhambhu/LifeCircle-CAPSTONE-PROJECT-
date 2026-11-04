"""LifeCircle data models (Milestone 2).

Every table here maps to one "object" in the app. See docs/DATA_MODELS.md for
the same models written out as property tables for the presentation.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- enums
class Role(str, enum.Enum):
    family = "family"
    donor = "donor"
    staff = "staff"


class Sex(str, enum.Enum):
    male = "male"
    female = "female"


class SlotRole(str, enum.Enum):
    confirmed = "confirmed"
    backup = "backup"


class AppointmentStatus(str, enum.Enum):
    scheduled = "scheduled"      # assigned by rotation, donor has not replied yet
    confirmed = "confirmed"      # donor said "Yes, I'll come"
    cancelled = "cancelled"      # donor said "I can't make it"
    completed = "completed"      # staff recorded an outcome


class RequestType(str, enum.Enum):
    planned = "planned"
    urgent = "urgent"


class RequestStatus(str, enum.Enum):
    sent_to_bank = "sent_to_bank"        # family pressed "Request urgent help"
    circle_alerted = "circle_alerted"    # staff approved, patient's own circle alerted
    nearby_alerted = "nearby_alerted"    # escalated to nearby eligible donors
    filled = "filled"                    # first donor accepted
    closed = "closed"                    # outcome recorded / cancelled


class AlertTier(str, enum.Enum):
    circle = "circle"
    nearby = "nearby"


class AlertStatus(str, enum.Enum):
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"   # someone else accepted first


class Outcome(str, enum.Enum):
    donated = "donated"
    deferred = "deferred"
    no_show = "no_show"
    excused = "excused"


# ---------------------------------------------------------------- tables
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    blood_bank_id: Mapped[int | None] = mapped_column(ForeignKey("blood_banks.id"))  # staff only

    donor: Mapped["Donor | None"] = relationship(back_populates="user", uselist=False)


class AuthSession(Base):
    """Login token issued after (demo) phone OTP sign-in."""

    __tablename__ = "auth_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class BloodBank(Base):
    __tablename__ = "blood_banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    blood_group: Mapped[str] = mapped_column(String(3))
    cycle_days: Mapped[int] = mapped_column(Integer, default=21)
    last_transfusion_date: Mapped[date] = mapped_column(Date)
    family_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    blood_bank_id: Mapped[int] = mapped_column(ForeignKey("blood_banks.id"))

    blood_bank: Mapped[BloodBank] = relationship()
    circle: Mapped[list["CircleMember"]] = relationship(back_populates="patient")


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    blood_group: Mapped[str] = mapped_column(String(3))
    sex: Mapped[Sex] = mapped_column(Enum(Sex))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    last_donation_date: Mapped[date | None] = mapped_column(Date)
    deferred_until: Mapped[date | None] = mapped_column(Date)  # set by staff on "Deferred"
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # blood bank verified badge

    # Donor-controlled privacy toggles (wireframe 7)
    show_next_eligible_to_staff: Mapped[bool] = mapped_column(Boolean, default=True)
    share_location_for_urgent: Mapped[bool] = mapped_column(Boolean, default=True)
    urgent_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="donor")


class CircleMember(Base):
    """A donor who belongs to a patient's fixed donor circle."""

    __tablename__ = "circle_members"
    __table_args__ = (UniqueConstraint("patient_id", "donor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    joined_on: Mapped[date] = mapped_column(Date)

    patient: Mapped[Patient] = relationship(back_populates="circle")
    donor: Mapped[Donor] = relationship()


class Appointment(Base):
    """One donor slot for one planned transfusion (confirmed or backup)."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    transfusion_date: Mapped[date] = mapped_column(Date)
    slot: Mapped[SlotRole] = mapped_column(Enum(SlotRole))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.scheduled
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)

    patient: Mapped[Patient] = relationship()
    donor: Mapped[Donor] = relationship()


class DonationRequest(Base):
    """An item in the blood bank's request queue (planned change or urgent need)."""

    __tablename__ = "donation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    blood_bank_id: Mapped[int] = mapped_column(ForeignKey("blood_banks.id"))
    type: Mapped[RequestType] = mapped_column(Enum(RequestType))
    status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus))
    needed_by: Mapped[datetime] = mapped_column(DateTime)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    circle_alerted_at: Mapped[datetime | None] = mapped_column(DateTime)
    nearby_alerted_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    filled_by_donor_id: Mapped[int | None] = mapped_column(ForeignKey("donors.id"))

    patient: Mapped[Patient] = relationship()
    alerts: Mapped[list["RequestAlert"]] = relationship(back_populates="request")


class RequestAlert(Base):
    """One alert sent to one donor for one urgent request."""

    __tablename__ = "request_alerts"
    __table_args__ = (UniqueConstraint("request_id", "donor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("donation_requests.id"))
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    tier: Mapped[AlertTier] = mapped_column(Enum(AlertTier))
    distance_km: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.sent)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)

    request: Mapped[DonationRequest] = relationship(back_populates="alerts")
    donor: Mapped[Donor] = relationship()


class DonationRecord(Base):
    """Final outcome recorded by blood bank staff after screening."""

    __tablename__ = "donation_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("donation_requests.id"))
    outcome: Mapped[Outcome] = mapped_column(Enum(Outcome))
    reason: Mapped[str] = mapped_column(String(200), default="")
    on_date: Mapped[date] = mapped_column(Date)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Notification(Base):
    """Simulated SMS / in-app message. Nothing is actually sent in the prototype."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PhoneViewLog(Base):
    """Audit row written every time staff is shown a donor's phone number."""

    __tablename__ = "phone_view_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"))
    context: Mapped[str] = mapped_column(String(80))
    viewed_at: Mapped[datetime] = mapped_column(DateTime)
