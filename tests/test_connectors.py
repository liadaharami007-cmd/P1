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
    monkeypatch.setattr(connectors, "wa_send_text", lambda to, body, transport=None, cfg=None: sent.update(to=to, body=body) or {"to": to})
    done = c.post(f"/api/actions/{act['id']}/approve").json()
    assert done["status"] == "done" and sent == {"to": "972501111111", "body": "היי נועה"}
    assert c.get("/api/leads").json()["items"][0]["status"] == "contacted"
    em = c.post(f"/api/leads/{lead['id']}/send", json={"channel": "email", "body": "x"}).json()
    failed = c.post(f"/api/actions/{em['id']}/approve").json()
    assert failed["status"] == "failed" and "SMTP" in failed["error"]  # אין שרת מייל — נכשל בגלוי
    csv = c.get("/api/leads/export.csv")
    assert csv.status_code == 200 and "נועה" in csv.text and "attachment" in csv.headers["content-disposition"]


def test_per_account_connections_encrypted_and_isolated(make_client, monkeypatch, tmp_path):
    from app import config
    from app.integrations import accounts
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = make_client()
    register(c, "conn@p1.co")
    assert c.put("/api/connections/shopify", json={"values": {"SHOPIFY_STORE_DOMAIN": "a.myshopify.com"}}).status_code == 400  # חסר טוקן
    monkeypatch.setattr(connectors, "shopify_summary", lambda transport=None, cfg=None: {"source": "store_data", "shop": cfg["SHOPIFY_STORE_DOMAIN"], "orders": 3, "products": 2})
    r = c.put("/api/connections/shopify", json={"values": {"SHOPIFY_STORE_DOMAIN": "a.myshopify.com", "SHOPIFY_ADMIN_TOKEN": "shpat_SECRET1234"}}).json()
    assert r["status"] == "connected" and r["data"]["orders"] == 3
    tok = next(f for f in r["fields"] if f["key"] == "SHOPIFY_ADMIN_TOKEN")
    assert tok["value"] is None and tok["hint"] == "••••1234"  # הסוד לא חוזר
    assert "shpat_SECRET1234" not in c.get("/api/connections").text and "SECRET1234" not in c.get("/api/connections").text
    with c.app.state.db._conn() as cx:
        raw = cx.execute("SELECT creds_enc FROM connections").fetchone()[0]
    assert "shpat_SECRET1234" not in raw  # מוצפן בבסיס הנתונים
    # עדכון בלי לשלוח שוב את הסוד — הסוד הקודם נשמר
    r2 = c.put("/api/connections/shopify", json={"values": {"SHOPIFY_STORE_DOMAIN": "b.myshopify.com"}}).json()
    assert r2["data"]["shop"] == "b.myshopify.com"
    monkeypatch.setattr(connectors, "wordpress_pages", lambda transport=None, cfg=None: (_ for _ in ()).throw(RuntimeError("WordPress החזיר 401")))
    w = c.put("/api/connections/wordpress", json={"values": {"WP_URL": "https://x", "WP_USER": "u", "WP_APP_PASSWORD": "p"}}).json()
    assert w["status"] == "error" and "401" in w["error"]
    o = make_client(db=c.app.state.db)
    register(o, "conn2@p1.co")
    assert all(i["status"] == "not_connected" for i in o.get("/api/connections").json()["items"])
    assert c.delete("/api/connections/wordpress").status_code == 204


def test_embed_collect_from_any_site(make_client):
    c = make_client()
    register(c, "embed@p1.co")
    e = c.get("/api/connections").json()["embed"]
    assert e["key"].startswith("p1_") and 'data-p1-key="' + e["key"] in e["snippet"]
    js = c.get("/embed.js")
    assert js.status_code == 200 and "password" in js.text and "cc-" in js.text  # מסנן סיסמאות ואשראי
    body = json.dumps({"name": "יוסי", "phone": "050-2222222", "message": "מעוניין", "page": "https://client-site.co.il/contact"})
    r = c.post(f"/api/collect/{e['key']}", content=body, headers={"Origin": "https://client-site.co.il", "Content-Type": "text/plain"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "*"
    lead = c.get("/api/leads").json()["items"][0]
    assert lead["name"] == "יוסי" and lead["channel"] == "website_form" and "client-site" in lead["message"]
    assert c.post("/api/collect/p1_wrong", content=body).status_code == 404
    assert c.post(f"/api/collect/{e['key']}", content=json.dumps({"name": "x"})).status_code == 400
    new = c.post("/api/embed/rotate").json()["key"]
    assert new != e["key"] and c.post(f"/api/collect/{e['key']}", content=body).status_code == 404
    # בקשה ממקור זר לנתיב רגיל עדיין חסומה (CSRF)
    assert c.post("/api/leads", json={"name": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_ga4_oauth_flow_and_report(make_client, monkeypatch, tmp_path):
    from urllib.parse import parse_qs, urlparse
    from app import config
    from app.integrations import google
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = make_client()
    register(c, "ga@p1.co")
    monkeypatch.delenv("P1_GOOGLE_CLIENT_ID", raising=False)
    assert c.get("/api/oauth/google/start", follow_redirects=False).status_code == 503
    ga = next(i for i in c.get("/api/connections").json()["items"] if i["provider"] == "ga4")
    assert ga["oauth"]["ready"] is False and "P1_GOOGLE_CLIENT_ID" in ga["oauth"]["missing"]
    monkeypatch.setenv("P1_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("P1_GOOGLE_CLIENT_SECRET", "csec")
    r = c.get("/api/oauth/google/start", follow_redirects=False)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert r.status_code == 302 and q["scope"] == [google.SCOPE] and q["access_type"] == ["offline"]
    assert c.get("/api/oauth/google/callback", params={"code": "x", "state": "forged"}, follow_redirects=False).headers["location"].endswith("google=error")
    monkeypatch.setattr(google, "exchange", lambda code, transport=None: {"refresh_token": "rt_SECRET"})
    ok = c.get("/api/oauth/google/callback", params={"code": "x", "state": q["state"][0]}, follow_redirects=False)
    assert ok.headers["location"].endswith("google=ok")

    def h(req):
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at"})
        assert req.headers["authorization"] == "Bearer at" and "/properties/123:runReport" in req.url.path
        return httpx.Response(200, json={"rows": [{"dimensionValues": [{"value": "Organic Search"}], "metricValues": [{"value": "40"}, {"value": "55"}, {"value": "3"}, {"value": "5"}]},
                                                  {"dimensionValues": [{"value": "Direct"}], "metricValues": [{"value": "10"}, {"value": "12"}, {"value": "1"}, {"value": "2"}]}]})
    real = google.ga4_summary
    monkeypatch.setattr(google, "ga4_summary", lambda transport=None, cfg=None: real(transport=httpx.MockTransport(h), cfg=cfg))
    g = c.put("/api/connections/ga4", json={"values": {"GA4_PROPERTY_ID": "properties/123"}}).json()
    assert g["status"] == "connected" and g["data"]["sessions"] == 67 and g["data"]["purchases"] == 4 and g["oauth"]["linked"]
    assert "rt_SECRET" not in c.get("/api/connections").text
