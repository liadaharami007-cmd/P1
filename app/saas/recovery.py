"""שחזור סיסמה + שליחת מייל (SMTP רגיל — חינמי, בלי ספק חיצוני מחייב).

- אסימון אקראי חד-פעמי, נשמר רק כ-hash, תקף 30 דקות. שימוש בו מבטל את כל הסשנים הקיימים של המשתמש.
- בלי שרת מייל מוגדר — המערכת לא מעמידה פנים ששלחה: /api/auth/config מחזיר email_configured=false,
  ומנהל הפלטפורמה יכול להפיק קישור איפוס ידני.
הגדרה ב-.env: P1_SMTP_HOST, P1_SMTP_PORT (587), P1_SMTP_USER, P1_SMTP_PASSWORD, P1_SMTP_FROM, P1_PUBLIC_URL.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from .. import config
from ..db import Database

TTL_MINUTES = 30


def email_configured() -> bool:
    return bool(os.environ.get("P1_SMTP_HOST") and os.environ.get("P1_SMTP_FROM"))


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["P1_SMTP_FROM"], to, subject
    msg.set_content(body)
    with smtplib.SMTP(os.environ["P1_SMTP_HOST"], int(os.environ.get("P1_SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        if os.environ.get("P1_SMTP_USER"):
            s.login(os.environ["P1_SMTP_USER"], os.environ.get("P1_SMTP_PASSWORD", ""))
        s.send_message(msg)


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset(db: Database, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES)).isoformat()
    with db._conn() as c:
        c.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
        c.execute("INSERT INTO password_resets (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)",
                  (_h(token), user_id, exp, datetime.now(timezone.utc).isoformat()))
    return token


def reset_link(token: str) -> str:
    return f"{config.PUBLIC_URL}/#/reset?token={token}"


def consume(db: Database, token: str, new_hash: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with db._conn() as c:
        row = c.execute("SELECT user_id FROM password_resets WHERE token_hash=? AND used_at IS NULL AND expires_at > ?",
                        (_h(token), now)).fetchone()
        if not row:
            return False
        c.execute("UPDATE password_resets SET used_at=? WHERE token_hash=?", (now, _h(token)))
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, row["user_id"]))
        c.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
    return True
