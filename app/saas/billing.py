"""תשלומים ומנויים — ממשק אחיד לספק תשלומים + מימוש Paddle Billing.

למה Paddle: Stripe לא תומך בעסקים הרשומים בישראל. Paddle הוא Merchant of Record — הוא גובה, מנפיק חשבוניות/קבלות
ומטפל במע"מ, ויש לו סביבת Sandbox לבדיקות. P1 לא שומר פרטי כרטיס אשראי בשום שלב — הלקוח משלם בדף של Paddle.

הגדרה (רק ב-.env / משתני סביבה — אף פעם לא בקוד):
  P1_BILLING_PROVIDER=paddle
  PADDLE_ENV=sandbox            (או production — רק אחרי בדיקות ואישור)
  PADDLE_API_KEY=...            מפתח API של Paddle
  PADDLE_WEBHOOK_SECRET=...     סוד החתימה של ה-notification destination
  PADDLE_PRICE_PRO_MONTHLY / PADDLE_PRICE_PRO_YEARLY / PADDLE_PRICE_AGENCY_MONTHLY / PADDLE_PRICE_AGENCY_YEARLY  (מזהי pri_...)

ה-webhook (POST /api/billing/webhook) הוא המקור היחיד לשינוי מסלול: חתימה מאומתת, הגנה מפני שידור חוזר
(חלון זמן + מזהה אירוע חד-פעמי), ורק אז accounts.plan / subscription_status מתעדכנים.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Protocol

import httpx

PAID_PLANS = ("pro", "agency")
INTERVALS = ("monthly", "yearly")
TOLERANCE_SECONDS = 300


class BillingError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


class BillingProvider(Protocol):
    name: str

    def configured(self) -> bool: ...
    def missing(self) -> list[str]: ...
    def create_checkout_url(self, account: dict, plan: str, interval: str, email: str | None) -> str: ...
    def customer_portal_url(self, account: dict) -> str: ...
    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> dict: ...


class NotConfigured:
    name = "none"

    def configured(self) -> bool:
        return False

    def missing(self) -> list[str]:
        return ["P1_BILLING_PROVIDER=paddle", "PADDLE_API_KEY", "PADDLE_WEBHOOK_SECRET", "PADDLE_PRICE_PRO_MONTHLY", "PADDLE_PRICE_AGENCY_MONTHLY"]

    def create_checkout_url(self, account, plan, interval, email):
        raise BillingError("ספק תשלומים לא מחובר", 503)

    def customer_portal_url(self, account):
        raise BillingError("ספק תשלומים לא מחובר", 503)

    def parse_webhook(self, body, headers):
        raise BillingError("ספק תשלומים לא מחובר", 503)


class PaddleProvider:
    """Paddle Billing API v1 (https://developer.paddle.com). נבדק מול מוק בלבד — עוד לא מול חשבון Paddle אמיתי."""
    name = "paddle"

    def __init__(self, env: dict[str, str] | None = None, transport: httpx.BaseTransport | None = None):
        e = env if env is not None else dict(os.environ)
        self.api_key = e.get("PADDLE_API_KEY", "")
        self.secret = e.get("PADDLE_WEBHOOK_SECRET", "")
        self.sandbox = e.get("PADDLE_ENV", "sandbox") != "production"
        self.base = "https://sandbox-api.paddle.com" if self.sandbox else "https://api.paddle.com"
        self.prices = {(p, i): e.get(f"PADDLE_PRICE_{p.upper()}_{i.upper()}", "") for p in PAID_PLANS for i in INTERVALS}
        self.transport = transport

    def missing(self) -> list[str]:
        need = {"PADDLE_API_KEY": self.api_key, "PADDLE_WEBHOOK_SECRET": self.secret,
                "PADDLE_PRICE_PRO_MONTHLY": self.prices[("pro", "monthly")], "PADDLE_PRICE_AGENCY_MONTHLY": self.prices[("agency", "monthly")]}
        return [k for k, v in need.items() if not v]

    def configured(self) -> bool:
        return not self.missing()

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=20, transport=self.transport,
                            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

    def create_checkout_url(self, account: dict, plan: str, interval: str, email: str | None) -> str:
        if plan not in PAID_PLANS or interval not in INTERVALS:
            raise BillingError("מסלול או תקופת חיוב לא חוקיים")
        price = self.prices[(plan, interval)]
        if not price:
            raise BillingError(f"לא הוגדר מחיר ב-Paddle למסלול {plan} ({interval})", 503)
        body: dict[str, Any] = {"items": [{"price_id": price, "quantity": 1}],
                                "custom_data": {"account_id": account["id"], "plan": plan}}
        if account.get("billing_customer_id"):
            body["customer_id"] = account["billing_customer_id"]
        with self._client() as c:
            r = c.post("/transactions", json=body)
        if r.status_code >= 300:
            raise BillingError(f"Paddle החזיר שגיאה ({r.status_code})", 502)
        url = (r.json().get("data") or {}).get("checkout", {}).get("url")
        if not url:
            raise BillingError("Paddle לא החזיר קישור תשלום — יש להגדיר Default payment link בהגדרות Paddle", 502)
        return url

    def customer_portal_url(self, account: dict) -> str:
        cid = account.get("billing_customer_id")
        if not cid:
            raise BillingError("לחשבון עדיין אין מנוי בתשלום", 409)
        with self._client() as c:
            r = c.post(f"/customers/{cid}/portal-sessions", json={})
        if r.status_code >= 300:
            raise BillingError(f"Paddle החזיר שגיאה ({r.status_code})", 502)
        return r.json()["data"]["urls"]["general"]["overview"]

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> dict:
        """אימות חתימה Paddle-Signature: ts=...;h1=HMAC_SHA256(secret, f"{ts}:{body}")."""
        sig = headers.get("paddle-signature", "")
        parts = dict(p.split("=", 1) for p in sig.split(";") if "=" in p)
        ts, h1 = parts.get("ts", ""), parts.get("h1", "")
        if not ts.isdigit() or not h1 or not self.secret:
            raise BillingError("חתימה חסרה", 401)
        if abs(time.time() - int(ts)) > TOLERANCE_SECONDS:
            raise BillingError("חתימה ישנה מדי (הגנה מפני שידור חוזר)", 401)
        expected = hmac.new(self.secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, h1):
            raise BillingError("חתימה לא תקינה", 401)
        return json.loads(body)


def get_provider() -> BillingProvider:
    if os.environ.get("P1_BILLING_PROVIDER") == "paddle":
        return PaddleProvider()
    return NotConfigured()


# ---------------------------------------------------------------- עיבוד אירועים → מצב החשבון
STATUS_MAP = {"active": "active", "trialing": "trialing", "past_due": "past_due", "paused": "past_due", "canceled": "canceled"}


def apply_event(db, event: dict) -> dict:
    """מעדכן חשבון לפי אירוע מאומת. אידמפוטנטי לפי event_id. מחזיר מה נעשה."""
    eid, etype = event.get("event_id"), event.get("event_type", "")
    data = event.get("data") or {}
    custom = data.get("custom_data") or {}
    account_id = custom.get("account_id")
    with db._conn() as c:
        if eid and c.execute("SELECT 1 FROM billing_events WHERE id=?", (eid,)).fetchone():
            return {"status": "duplicate"}
        c.execute("INSERT INTO billing_events (id, type, account_id, payload_json, created_at) VALUES (?,?,?,?,datetime('now'))",
                  (eid or f"noid-{time.time_ns()}", etype, account_id, json.dumps(event)[:20000]))
    if not account_id or not db.get_account(account_id):
        return {"status": "ignored", "reason": "no account"}
    plan = custom.get("plan")
    if etype.startswith("subscription."):
        status = STATUS_MAP.get(data.get("status", ""), "none")
        fields: dict[str, Any] = {"subscription_status": status}
        if data.get("customer_id"):
            fields["billing_customer_id"] = data["customer_id"]
        if status in ("active", "trialing") and plan in PAID_PLANS:
            fields["plan"] = plan
        if status == "canceled":
            fields["plan"] = "free"
        db.update_account(account_id, **fields)
        return {"status": "applied", **fields}
    if etype == "transaction.payment_failed":
        db.update_account(account_id, subscription_status="past_due")
        return {"status": "applied", "subscription_status": "past_due"}
    if etype == "transaction.completed" and data.get("customer_id"):
        db.update_account(account_id, billing_customer_id=data["customer_id"])
        return {"status": "applied"}
    return {"status": "ignored", "reason": etype}
