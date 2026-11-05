"""אימות משתמשים: סיסמאות (scrypt), סשנים בעוגייה מאובטחת, הגבלת ניסיונות התחברות."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from ..db import Database

COOKIE = "p1_session"
SESSION_DAYS = 14
COOKIE_SECURE = os.environ.get("P1_COOKIE_SECURE", "0") == "1"  # להפעיל בייצור (HTTPS)
ALLOW_SIGNUP = os.environ.get("P1_ALLOW_SIGNUP", "1") == "1"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[a-z]{2,}$", re.I)

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), dk_hex)


def validate_credentials(email: str, password: str) -> None:
    if not EMAIL_RE.match(email or ""):
        raise HTTPException(400, "כתובת אימייל לא תקינה")
    if len(password or "") < 10:
        raise HTTPException(400, "הסיסמה חייבת להכיל לפחות 10 תווים")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """הגבלת ניסיונות בזיכרון (לתהליך אחד). בייצור עם כמה שרתים — להעביר ל-Redis."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


login_limiter = RateLimiter(limit=10, window_s=900)
signup_limiter = RateLimiter(limit=5, window_s=3600)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def start_session(db: Database, response, user_id: str, account_id: str, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.create_session(_token_hash(token), user_id, account_id, expires.isoformat(),
                      request.headers.get("user-agent"), client_ip(request))
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, path="/")


def end_session(db: Database, request: Request, response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.delete_session(_token_hash(token))
    response.delete_cookie(COOKIE, path="/")


class Ctx:
    """הקשר המשתמש המחובר: מי הוא, לאיזה חשבון הוא שייך ומה תפקידו."""

    def __init__(self, user: dict, account: dict, role: str):
        self.user, self.account, self.role = user, account, role

    @property
    def account_id(self) -> str:
        return self.account["id"]

    @property
    def user_id(self) -> str:
        return self.user["id"]

    @property
    def is_admin(self) -> bool:
        return bool(self.user.get("is_platform_admin"))


def current(request: Request) -> Ctx:
    """Dependency: דורש משתמש מחובר."""
    db: Database = request.app.state.db
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "נדרשת התחברות")
    sess = db.get_session(_token_hash(token))
    if not sess:
        raise HTTPException(401, "החיבור פג תוקף — התחברו מחדש")
    user = db.get_user(sess["user_id"])
    account = db.get_account(sess["account_id"])
    member = db.get_membership(sess["user_id"], sess["account_id"]) if user and account else None
    if not member:
        raise HTTPException(401, "נדרשת התחברות")
    ctx = Ctx(user, account, member["role"])
    request.state.ctx = ctx
    return ctx


def require_admin(request: Request) -> Ctx:
    ctx = current(request)
    if not ctx.is_admin:
        raise HTTPException(403, "אין הרשאה")
    return ctx
