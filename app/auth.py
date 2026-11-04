"""Sign-in and role-based access.

Prototype sign-in: phone number + OTP. No SMS is sent; the demo OTP is 1234.
After sign-in the client sends `Authorization: Bearer <token>` on every call.
Each router declares which role may call it with `require(Role.x)`.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import clock
from app.db import get_db
from app.models import AuthSession, Role, User

DEMO_OTP = "1234"


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_hex(24)
    db.add(AuthSession(token=token, user_id=user.id, created_at=clock.now()))
    db.commit()
    return token


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in first")
    sess = db.get(AuthSession, token)
    if not sess:
        raise HTTPException(401, "Session expired, sign in again")
    return db.get(User, sess.user_id)


def require(*roles: Role):
    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This screen is for {', '.join(r.value for r in roles)} accounts only")
        return user

    return guard
