"""חיבורים רשמיים (מוקים): WhatsApp שליחה + webhook חתום → ליד, Shopify, WordPress, שליחה ללקוח רק באישור, ייצוא CSV."""
import hashlib
import hmac
import json

import httpx

from app.integrations import connectors

from .conftest import register

WA = {"WHATSAPP_TOKEN": "t", "WHATSAPP_PHONE_NUMBER_ID": "123", "WHATSAPP_VERIFY_TOKEN": "vt", "WHATSAPP_APP_SECRET": "sec"}


def test_whatsapp_send_formats_israeli_number(monkeypatch):
    for k, v in WA.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("P1_WHATSAPP_ACCOUNT_ID", "x")
    seen = {}

    def h(req):
        seen.update(json.loads(req.content), url=str(req.url), auth=req.headers["authorization"])
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})
    r = connectors.wa_send_text("050-123-4567", "שלום", transport=httpx.MockTransport(h))
    assert r["to"] == "972501234567" and seen["to"] == "972501234567" and seen["url"].endswith("/123/messages") and seen["auth"] == "Bearer t"


def test_shopify_and_wordpress(monkeypatch):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "s.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "tok")

    def h(req):
        p = req.url.path
        return httpx.Response(200, json={"shop": {"name": "חנות"}} if p.endswith("shop.json") else {"count": 7})
    s = connectors.shopify_summary(transport=httpx.MockTransport(h))
    assert s == {"source": "store_data", "shop": "חנות", "orders": 7, "products": 7}
    monkeypatch.setenv("WP_URL", "https://wp.test")
    monkeypatch.setenv("WP_USER", "u")
    monkeypatch.setenv("WP_APP_PASSWORD", "p")
    pages = connectors.wordpress_pages(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"id": 1, "title": {"rendered": "בית"}, "link": "l", "modified": "m"}])))
    assert pages[0]["title"] == "בית"


def test_webhook_inbound_and_approval_gated_send(make_client, monkeypatch):
    c = make_client()
    register(c, "wa@p1.co")
    acc = c.get("/api/account").json()["account"]["id"]
    for k, v in WA.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("P1_WHATSAPP_ACCOUNT_ID", acc)
    assert c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "x"}).status_code == 403
    assert c.get("/api/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"}).text == "42"
    body = json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "972501111111", "profile": {"name": "נועה"}}],
                                                         "messages": [{"from": "972501111111", "id": "m1", "type": "text", "text": {"body": "מחיר?"}}]}}]}]}).encode()
    assert c.post("/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    sig = "sha256=" + hmac.new(b"sec", body, hashlib.sha256).hexdigest()
    assert c.post("/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig}).json()["received"] == 1
    lead = c.get("/api/leads").json()["items"][0]
    assert lead["name"] == "נועה" and lead["channel"] == "whatsapp"
    act = c.post(f"/api/leads/{lead['id']}/send", json={"channel": "whatsapp", "body": "היי נועה"}).json()
    assert act["status"] == "proposed" and act["risk"] == "high"  # לא נשלח בלי אישור
    sent = {}
    monkeypatch.setattr(connectors, "wa_send_text", lambda to, body, transport=None: sent.update(to=to, body=body) or {"to": to})
    done = c.post(f"/api/actions/{act['id']}/approve").json()
    assert done["status"] == "done" and sent == {"to": "972501111111", "body": "היי נועה"}
    assert c.get("/api/leads").json()["items"][0]["status"] == "contacted"
    em = c.post(f"/api/leads/{lead['id']}/send", json={"channel": "email", "body": "x"}).json()
    failed = c.post(f"/api/actions/{em['id']}/approve").json()
    assert failed["status"] == "failed" and "SMTP" in failed["error"]  # אין שרת מייל — נכשל בגלוי
    csv = c.get("/api/leads/export.csv")
    assert csv.status_code == 200 and "נועה" in csv.text and "attachment" in csv.headers["content-disposition"]
