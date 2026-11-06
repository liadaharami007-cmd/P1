"""תשלומים: בלי ספק → לא מחובר (503 + מה חסר). Paddle (מוק): קישור תשלום, חתימת webhook, שידור חוזר, עדכון מסלול."""
import hashlib
import hmac
import json
import time

import httpx

from app.saas import billing

from .conftest import register

ENV = {"PADDLE_API_KEY": "test_key", "PADDLE_WEBHOOK_SECRET": "whsec", "PADDLE_PRICE_PRO_MONTHLY": "pri_pro_m",
       "PADDLE_PRICE_AGENCY_MONTHLY": "pri_ag_m", "PADDLE_ENV": "sandbox"}


def _sign(body: bytes, secret="whsec", ts=None):
    ts = str(ts or int(time.time()))
    return f"ts={ts};h1=" + hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()


def test_not_configured_reports_whats_missing(make_client, monkeypatch):
    monkeypatch.delenv("P1_BILLING_PROVIDER", raising=False)
    c = make_client()
    register(c, "b@b.co")
    st = c.get("/api/billing").json()
    assert st["configured"] is False and "PADDLE_API_KEY" in st["missing"]
    assert c.post("/api/billing/checkout", json={"plan": "pro"}).status_code == 503
    assert c.post("/api/billing/webhook", content=b"{}").status_code == 503


def test_paddle_checkout_uses_sandbox_and_custom_data():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["body"], seen["auth"] = str(req.url), json.loads(req.content), req.headers["authorization"]
        return httpx.Response(201, json={"data": {"id": "txn_1", "checkout": {"url": "https://pay.example/checkout?_ptxn=txn_1"}}})
    p = billing.PaddleProvider(env=ENV, transport=httpx.MockTransport(handler))
    assert p.configured()
    url = p.create_checkout_url({"id": "acc1"}, "pro", "monthly", "a@a.co")
    assert url.startswith("https://pay.example") and seen["url"].startswith("https://sandbox-api.paddle.com/transactions")
    assert seen["body"]["custom_data"] == {"account_id": "acc1", "plan": "pro"} and seen["auth"] == "Bearer test_key"
    try:
        p.create_checkout_url({"id": "acc1"}, "pro", "yearly", None)
        raise AssertionError("expected missing price error")
    except billing.BillingError as e:
        assert e.status == 503


def test_webhook_signature_replay_and_plan_change(make_client, monkeypatch):
    monkeypatch.setenv("P1_BILLING_PROVIDER", "paddle")
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    c = make_client()
    register(c, "pay@b.co")
    acc = c.get("/api/account").json()["account"]
    ev = {"event_id": "evt_1", "event_type": "subscription.created",
          "data": {"status": "active", "customer_id": "ctm_1", "custom_data": {"account_id": acc["id"], "plan": "pro"}}}
    body = json.dumps(ev).encode()
    assert c.post("/api/billing/webhook", content=body, headers={"Paddle-Signature": _sign(body, "wrong")}).status_code == 401
    assert c.post("/api/billing/webhook", content=body, headers={"Paddle-Signature": _sign(body, ts=int(time.time()) - 3600)}).status_code == 401
    assert c.post("/api/billing/webhook", content=body).status_code == 401
    r = c.post("/api/billing/webhook", content=body, headers={"Paddle-Signature": _sign(body)})
    assert r.status_code == 200 and r.json()["status"] == "applied"
    a = c.get("/api/account").json()["account"]
    assert a["plan"] == "pro" and a["subscription_status"] == "active"
    assert c.post("/api/billing/webhook", content=body, headers={"Paddle-Signature": _sign(body)}).json()["status"] == "duplicate"
    fail = json.dumps({"event_id": "evt_2", "event_type": "transaction.payment_failed",
                       "data": {"custom_data": {"account_id": acc["id"]}}}).encode()
    c.post("/api/billing/webhook", content=fail, headers={"Paddle-Signature": _sign(fail)})
    assert c.get("/api/account").json()["account"]["subscription_status"] == "past_due"
    cancel = json.dumps({"event_id": "evt_3", "event_type": "subscription.canceled",
                         "data": {"status": "canceled", "custom_data": {"account_id": acc["id"], "plan": "pro"}}}).encode()
    c.post("/api/billing/webhook", content=cancel, headers={"Paddle-Signature": _sign(cancel)})
    a = c.get("/api/account").json()["account"]
    assert a["plan"] == "free" and a["subscription_status"] == "canceled"


def test_password_reset_flow(make_client, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    monkeypatch.delenv("P1_SMTP_HOST", raising=False)
    c = make_client()
    register(c, "admin@p1.co")  # המשתמש הראשון = מנהל פלטפורמה
    u = make_client(db=c.app.state.db)
    register(u, "user@p1.co")
    assert c.get("/api/auth/config").json()["email_configured"] is False
    assert u.post("/api/auth/forgot", json={"email": "user@p1.co"}).status_code == 503  # לא מעמידים פנים ששלחנו
    assert u.post("/api/admin/reset-link", json={"email": "user@p1.co"}).status_code == 403
    link = c.post("/api/admin/reset-link", json={"email": "user@p1.co"}).json()["link"]
    token = parse_qs(urlparse(link.replace("#/reset", "reset")).query)["token"][0]
    assert u.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    assert u.post("/api/auth/reset", json={"token": token, "password": "brand-new-password-1"}).json()["ok"]
    assert u.get("/api/auth/me").status_code == 401  # הסשנים הישנים בוטלו
    assert u.post("/api/auth/reset", json={"token": token, "password": "another-password-2"}).status_code == 400  # חד-פעמי
    assert u.post("/api/auth/login", json={"email": "user@p1.co", "password": "brand-new-password-1"}).status_code == 200
