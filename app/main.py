"""LifeCircle API + demo web app.

Run:  uvicorn app.main:app --reload     then open http://127.0.0.1:8000
API docs (Swagger): http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import auth, clock
from app.db import engine, get_db
from app.models import Base, User
from app.routers import donor, family, staff
from app.seed import reset_and_seed

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not inspect(engine).has_table("users"):
        reset_and_seed()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="LifeCircle API",
    description="Planned blood donations for regular-transfusion patients, with a reliable urgent backup. "
    "PROTOTYPE with seeded demo data. Not for clinical use.",
    version="0.2.0",
)
app.include_router(family.router)
app.include_router(donor.router)
app.include_router(staff.router)


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    phone: str
    otp: str


@app.post("/auth/login", tags=["Auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Phone + OTP sign-in. In the prototype no SMS is sent and the OTP is always 1234."""
    user = db.scalar(select(User).where(User.phone == body.phone))
    if not user or body.otp != auth.DEMO_OTP:
        raise HTTPException(401, "Wrong phone number or code")
    return {"token": auth.issue_token(db, user), "role": user.role.value, "name": user.name}


@app.get("/auth/me", tags=["Auth"])
def whoami(user: User = Depends(auth.current_user)):
    return {"id": user.id, "name": user.name, "role": user.role.value}


# ------------------------------------------------------------------ demo helpers
@app.get("/demo/accounts", tags=["Demo"])
def demo_accounts(db: Session = Depends(get_db)):
    """Seeded accounts for the demo login screen. Phone numbers are not listed."""
    users = db.scalars(select(User).order_by(User.role, User.id)).all()
    return [{"id": u.id, "name": u.name, "role": u.role.value} for u in users]


@app.post("/demo/login/{user_id}", tags=["Demo"])
def demo_login(user_id: int, db: Session = Depends(get_db)):
    """One-click sign-in as a seeded account, so the demo skips the OTP step."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such demo account")
    return {"token": auth.issue_token(db, user), "role": user.role.value, "name": user.name}


@app.post("/demo/reset", tags=["Demo"])
def demo_reset():
    clock.reset()
    reset_and_seed()
    return {"ok": True, "today": clock.today()}


class AdvanceIn(BaseModel):
    minutes: int = 0
    days: int = 0


@app.post("/demo/advance", tags=["Demo"])
def demo_advance(body: AdvanceIn):
    """Move the demo clock forward (e.g. 15 minutes to trigger urgent escalation)."""
    return {"now": clock.advance(body.minutes, body.days)}


@app.get("/demo/clock", tags=["Demo"])
def demo_clock():
    return {"now": clock.now()}


# ------------------------------------------------------------------ frontend
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")
