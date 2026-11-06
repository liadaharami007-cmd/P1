"""סוכני המחלקות: Gemini (מוק HTTP), הרצה על הקשר עסקי אמיתי, 503 בלי מנוע, לידים + סיווג AI, פניות ישנות בתוכנית."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from app.business import studio
from app.intelligence import engines

from .conftest import register


def test_gemini_engine_structured_and_retry():
    calls = {"n": 0}

    def handler(req: httpx.Request):
        calls["n"] += 1
        body = json.loads(req.content)
        assert req.headers["x-goog-api-key"] == "k" and body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["systemInstruction"]["parts"][0]["text"] == "sys" and "responseJsonSchema" in body["generationConfig"]
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({"answer": "שלום"})}]}}],
                                         "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4}})
    eng = engines.GeminiEngine(model="gemini-2.5-flash", transport=httpx.MockTransport(handler), key="k", fallbacks=[])
    import app.intelligence.engines as E
    orig = asyncio.sleep
    E_sleep = []

    async def fast(s):
        E_sleep.append(s)
    asyncio.sleep = fast
    try:
        data, usage = asyncio.run(eng.structured(system="sys", content=[{"type": "text", "text": "hi"}], schema={"type": "object"}))
    finally:
        asyncio.sleep = orig
    assert data == {"answer": "שלום"} and usage.cost_usd == 0 and usage.model == "gemini:gemini-2.5-flash" and calls["n"] == 2


def test_pick_gemini_model():
    assert engines.pick_gemini_model(["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]) == "gemini-2.5-flash"
    assert engines.pick_gemini_model(["gemini-pro"]) is None


class FakeEngine:
    id = "fake"

    def __init__(self):
        self.seen = []

    async def structured(self, *, system, content, schema, **kw):
        from app.intelligence.client import Usage
        payload = json.loads(content[0]["text"])
        self.seen.append((system, payload))
        out = {k: ([] if v.get("type") == "array" else False if v.get("type") == "boolean" else "low" if "enum" in v else "x")
               for k, v in schema["properties"].items()}
        return out, Usage(model="fake-model")


def test_studio_requires_engine_and_grounds_on_real_data(make_client, monkeypatch):
    c = make_client()
    register(c, "studio@p1.co")
    monkeypatch.setattr(engines, "active_engine", lambda override=None: None)
    r = c.post("/api/studio/run", json={"kind": "ad_copy", "input": "מודעה לקיץ"})
    assert r.status_code == 503 and "Gemini" in r.json()["detail"]
    fake = FakeEngine()
    monkeypatch.setattr(engines, "active_engine", lambda override=None: fake)
    c.put("/api/business/profile", json={"data": {"business_name": "פרחי בלום", "offer": "זרי פרחים"}})
    out = c.post("/api/studio/run", json={"kind": "ad_copy", "input": "מודעה לקיץ"}).json()
    assert out["source"] == "ai" and out["model"] == "fake-model" and "business_name" in out["grounded_on"]["profile_fields"]
    system, payload = fake.seen[-1]
    assert "אסור להמציא" in system and payload["business_context"]["profile"]["business_name"] == "פרחי בלום"
    assert c.get("/api/studio/history").json()["items"][0]["kind"] == "ad_copy"
    assert c.post("/api/studio/run", json={"kind": "hack", "input": "x"}).status_code == 400


def test_leads_crud_triage_and_ceo_item(make_client, monkeypatch):
    c = make_client()
    register(c, "leads@p1.co")
    lead = c.post("/api/leads", json={"name": "רותי", "contact": "050-0000000", "channel": "whatsapp", "message": "כמה עולה זר לחתונה?"}).json()
    assert lead["status"] == "new"
    monkeypatch.setattr(engines, "active_engine", lambda override=None: None)
    assert c.post(f"/api/leads/{lead['id']}/triage").status_code == 503
    monkeypatch.setattr(engines, "active_engine", lambda override=None: FakeEngine())
    t = c.post(f"/api/leads/{lead['id']}/triage").json()
    assert t["ai"]["model"] == "fake-model" and t["status"] == "new"  # טיוטה בלבד — לא נשלח כלום
    assert c.patch(f"/api/leads/{lead['id']}", json={"status": "bogus"}).status_code == 400
    assert c.patch(f"/api/leads/{lead['id']}", json={"status": "contacted"}).json()["status"] == "contacted"
    old = c.post("/api/leads", json={"name": "דני", "message": "מתעניין"}).json()
    db = c.app.state.db
    with db._conn() as cx:
        cx.execute("UPDATE leads SET created_at=? WHERE id=?", ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(), old["id"]))
    assert c.get("/api/leads").json()["summary"]["unanswered_24h"] == 1
    assert any(i["key"] == "leads:stale" for i in c.get("/api/business/overview").json()["plan"]["items"])
    o = make_client(db=db)
    register(o, "o@p1.co")
    assert o.get("/api/leads").json()["items"] == [] and o.patch(f"/api/leads/{lead['id']}", json={"status": "won"}).status_code == 404


def test_crm_followups_and_funnel(make_client):
    c = make_client()
    register(c, "crm@p1.co")
    db = c.app.state.db
    ids = [c.post("/api/leads", json={"name": f"L{i}", "channel": "whatsapp" if i % 2 else "landing_page"}).json()["id"] for i in range(6)]
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert c.patch(f"/api/leads/{ids[0]}", json={"follow_up_at": "לא תאריך"}).status_code == 400
    c.patch(f"/api/leads/{ids[0]}", json={"follow_up_at": past, "value": 1200})
    assert c.get("/api/leads").json()["summary"]["followups_due"] == 1
    assert studio.remind_followups(db) == 1 and studio.remind_followups(db) == 0  # תזכורת אחת בלבד
    assert any(n["kind"] == "lead_followup" for n in c.get("/api/notifications").json()["items"])
    f = c.get("/api/leads").json()["funnel"]
    assert f["win_rate"] is None and "5" in f["win_rate_note"] and f["open_value"] == 1200
    for i in ids[:3]:
        c.patch(f"/api/leads/{i}", json={"status": "won"})
    for i in ids[3:5]:
        c.patch(f"/api/leads/{i}", json={"status": "lost"})
    f = c.get("/api/leads").json()["funnel"]
    assert f["win_rate"] == 60 and f["won_value"] == 1200 and f["by_channel"]["whatsapp"] == 3
