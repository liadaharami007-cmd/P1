"""Google Analytics 4 לכל לקוח — התחברות בלחיצה (OAuth 2.0 רשמי של Google, הרשאת קריאה בלבד).

הפעלה חד-פעמית ע"י בעל P1 (חינם): Google Cloud → APIs & Services → OAuth client (Web) →
P1_GOOGLE_CLIENT_ID + P1_GOOGLE_CLIENT_SECRET, ו-redirect URI = <P1_PUBLIC_URL>/api/oauth/google/callback.
להפעיל API: "Google Analytics Data API". אחרי זה כל לקוח לוחץ "התחברות עם Google" ובוחר Property.
ה-refresh token נשמר מוצפן בכספת של החשבון. אין גישת כתיבה.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from .. import config

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DATA = "https://analyticsdata.googleapis.com/v1beta"
_states: dict[str, tuple[str, datetime]] = {}


def configured() -> bool:
    return bool(os.environ.get("P1_GOOGLE_CLIENT_ID") and os.environ.get("P1_GOOGLE_CLIENT_SECRET"))


def redirect_uri() -> str:
    return config.PUBLIC_URL + "/api/oauth/google/callback"


def start_url(account_id: str) -> str:
    st = secrets.token_urlsafe(24)
    _states[st] = (account_id, datetime.now(timezone.utc) + timedelta(minutes=10))
    return AUTH + "?" + urlencode({"client_id": os.environ["P1_GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri(), "response_type": "code",
                                   "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": st})


def pop_state(st: str) -> str | None:
    v = _states.pop(st, None)
    return v[0] if v and v[1] > datetime.now(timezone.utc) else None


def exchange(code: str, transport: httpx.BaseTransport | None = None) -> dict:
    with httpx.Client(timeout=20, transport=transport) as c:
        r = c.post(TOKEN, data={"code": code, "client_id": os.environ["P1_GOOGLE_CLIENT_ID"], "client_secret": os.environ["P1_GOOGLE_CLIENT_SECRET"],
                                "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    if r.status_code != 200 or "refresh_token" not in r.json():
        raise RuntimeError(f"Google לא אישר את ההתחברות ({r.status_code})")
    return r.json()


def access_token(refresh: str, transport: httpx.BaseTransport | None = None) -> str:
    with httpx.Client(timeout=20, transport=transport) as c:
        r = c.post(TOKEN, data={"refresh_token": refresh, "client_id": os.environ["P1_GOOGLE_CLIENT_ID"],
                                "client_secret": os.environ["P1_GOOGLE_CLIENT_SECRET"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"פג תוקף ההתחברות ל-Google — יש להתחבר מחדש ({r.status_code})")
    return r.json()["access_token"]


def ga4_summary(transport: httpx.BaseTransport | None = None, cfg: dict | None = None) -> dict:
    """28 הימים האחרונים: משתמשים, כניסות, מקורות תנועה מובילים, אירועי רכישה. נתונים אמיתיים בלבד (source=store_data)."""
    cfg = cfg or {}
    if not cfg.get("GA4_REFRESH_TOKEN"):
        raise RuntimeError("Google Analytics לא מחובר — לחצו 'התחברות עם Google'")
    if not cfg.get("GA4_PROPERTY_ID"):
        raise RuntimeError("חסר מספר Property של GA4 (Admin → Property settings → Property ID)")
    tok = access_token(cfg["GA4_REFRESH_TOKEN"], transport)
    pid = "".join(ch for ch in cfg["GA4_PROPERTY_ID"] if ch.isdigit())
    body = {"dateRanges": [{"startDate": "28daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "totalUsers"}, {"name": "sessions"}, {"name": "ecommercePurchases"}, {"name": "keyEvents"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 8}
    with httpx.Client(timeout=30, transport=transport) as c:
        r = c.post(f"{DATA}/properties/{pid}:runReport", json=body, headers={"Authorization": f"Bearer {tok}"})
    if r.status_code != 200:
        raise RuntimeError(f"Google Analytics החזיר {r.status_code}: {r.text[:150]}")
    rows = r.json().get("rows", [])
    chans = [{"channel": x["dimensionValues"][0]["value"], **{k: int(float(v["value"])) for k, v in zip(("users", "sessions", "purchases", "key_events"), x["metricValues"])}}
             for x in rows]
    tot = {k: sum(ch[k] for ch in chans) for k in ("users", "sessions", "purchases", "key_events")}
    return {"source": "store_data", "period": "28 ימים", **tot, "channels": chans}
