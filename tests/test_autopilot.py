"""בונה דפי נחיתה + Autopilot: מנוע מודל (מוק), רינדור בטוח, גרסאות, פרסום באישור, טופס → ליד אמיתי, סוכנים ברצף עם העברת תוצרים."""
import asyncio

from app.business import autopilot, pages
from app.intelligence import engines

from .conftest import register
from .test_studio import FakeEngine


class SpecEngine(FakeEngine):
    async def structured(self, *, system, content, schema, **kw):
        from app.intelligence.client import Usage
        import json
        self.seen.append((system, json.loads(content[0]["text"])))
        if "sections" in schema["properties"]:
            return {"title": "פרחי בלום <script>", "description": "d", "primary_color": "javascript:alert(1)", "missing_info": [],
                    "sections": [{"type": "hero", "heading": "<img src=x onerror=alert(1)>", "text": "t", "items": [], "button_text": "לקנייה"},
                                 {"type": "testimonials", "heading": "x", "text": "", "items": [], "button_text": ""}]}, Usage(model="fake")
        return await super().structured(system=system, content=content, schema=schema)


def test_render_is_safe_and_has_no_fake_reviews():
    spec = pages.sanitize({"title": "<b>t</b>", "primary_color": "red; x", "sections": [
        {"type": "hero", "heading": "<script>alert(1)</script>", "text": "", "items": [], "button_text": "go"},
        {"type": "testimonials", "heading": "fake", "text": "", "items": [], "button_text": ""}]})
    assert spec["primary_color"] == "#5b54e8" and all(s["type"] != "testimonials" for s in spec["sections"])
    assert any(s["type"] == "form" for s in spec["sections"])  # תמיד יש טופס
    h = pages.render(spec, "abc", "public")
    assert "<script>" not in h and "&lt;script&gt;" in h and "action='/p/abc/lead'" in h
    assert "disabled" in pages.render(spec, "abc", "preview")


def test_pages_flow_publish_and_real_lead(make_client, monkeypatch):
    c = make_client()
    register(c, "pages@p1.co")
    monkeypatch.setattr(engines, "active_engine", lambda override=None: None)
    assert c.post("/api/pages", json={"brief": "x"}).status_code == 503
    monkeypatch.setattr(engines, "active_engine", lambda override=None: SpecEngine())
    pg = c.post("/api/pages", json={"brief": "דף לזרי פרחים"}).json()
    assert pg["version"] == 1 and pg["spec"]["primary_color"] == "#5b54e8"
    pv = c.get(f"/api/pages/{pg['id']}/preview")
    assert pv.status_code == 200 and pv.headers["x-frame-options"] == "SAMEORIGIN" and "script-src" not in pv.headers["content-security-policy"]
    assert "onerror=alert" not in pv.text.replace("&lt;img src=x onerror=alert(1)&gt;", "")
    e = c.post(f"/api/pages/{pg['id']}/edit", json={"instruction": "כותרת קצרה יותר"}).json()
    assert e["version"] == 2 and len(e["versions"]) == 2
    assert c.post(f"/api/pages/{pg['id']}/restore", json={"version": 1}).json()["version"] == 3
    assert "attachment" in c.get(f"/api/pages/{pg['id']}/export").headers["content-disposition"]
    assert c.get(f"/p/{pg['id']}/").status_code == 404  # לא מפורסם בלי אישור
    act = c.post(f"/api/pages/{pg['id']}/publish").json()
    assert act["kind"] == "publish_page" and act["status"] == "proposed" and act["risk"] == "medium"
    done = c.post(f"/api/actions/{act['id']}/approve").json()
    assert done["status"] == "done" and done["result"]["url"].endswith(f"/p/{pg['id']}/")
    assert c.get(f"/p/{pg['id']}/").status_code == 200
    assert c.post(f"/p/{pg['id']}/lead", data={"name": "בוט", "phone": "1", "website": "spam"}).status_code == 200
    r = c.post(f"/p/{pg['id']}/lead", data={"name": "דנה", "phone": "050-1111111", "message": "מעוניינת"})
    assert r.status_code == 200 and "תודה" in r.text
    leads = c.get("/api/leads").json()["items"]
    assert len(leads) == 1 and leads[0]["name"] == "דנה" and leads[0]["channel"] == "landing_page"  # המלכודת לא יצרה ליד
    o = make_client(db=c.app.state.db)
    register(o, "o2@p1.co")
    assert o.get(f"/api/pages/{pg['id']}").status_code == 404 and o.get(f"/api/pages/{pg['id']}/preview").status_code == 404


def test_autopilot_runs_agents_in_sequence_with_handoff(make_client, monkeypatch):
    c = make_client()
    register(c, "auto@p1.co")
    db = c.app.state.db
    acc = db.get_account(c.get("/api/account").json()["account"]["id"])
    assert [s["agent"] for s in autopilot.rule_plan("תבדוק את העסק, תבנה תוכנית שיווק, תכין דף נחיתה ומודעות ותנהל משימות")] == \
        ["audit", "strategy", "ads", "landing_page", "tasks"]
    eng = SpecEngine()
    steps = autopilot.rule_plan("תבנה תוכנית שיווק, מודעות ודף נחיתה ותנהל משימות")
    run = autopilot.create(db, acc, None, "תבנה תוכנית שיווק, מודעות ודף נחיתה", steps, "rules", "")
    asyncio.run(autopilot.execute(db, None, acc, None, run["id"], engine=eng))
    r = c.get(f"/api/autopilot/{run['id']}").json()
    assert r["status"] == "done" and all(s["status"] == "done" for s in r["plan"]["steps"]), r
    # כל סוכן אחרי הראשון קיבל את התוצרים של הקודמים
    handoffs = [p.get("previous_agents") for _, p in eng.seen if "previous_agents" in p]
    assert handoffs and len(handoffs[-1]) >= 2
    assert c.get("/api/pages").json()["items"]  # דף נחיתה אמיתי נוצר
    monkeypatch.setattr(engines, "active_engine", lambda override=None: None)
    run2 = autopilot.create(db, acc, None, "מודעות", [{"agent": "ads", "goal": "x"}], "rules", "")
    asyncio.run(autopilot.execute(db, None, acc, None, run2["id"]))
    r2 = c.get(f"/api/autopilot/{run2['id']}").json()
    assert r2["plan"]["steps"][0]["status"] == "failed" and "Gemini" in r2["plan"]["steps"][0]["error"]


def test_plan_and_execute_in_background(make_client):
    c = make_client()
    register(c, "bg@p1.co")
    db = c.app.state.db
    acc = db.get_account(c.get("/api/account").json()["account"]["id"])
    run = autopilot.create(db, acc, None, "תכין מודעות ותנהל משימות", [], "pending", "")
    assert run["plan"]["steps"] == []
    asyncio.run(autopilot.plan_and_execute(db, None, acc, None, run["id"], engine=SpecEngine()))
    r = autopilot.get(db, run["id"], acc["id"])
    assert r["status"] == "done" and r["planner"] in ("ai", "rules") and r["plan"]["steps"]


import pytest  # noqa: E402

from app.main import browser_available  # noqa: E402


@pytest.mark.skipif(not browser_available()[0], reason="Chromium/Playwright לא זמין")
def test_video_agent_renders_real_mp4(make_client, tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = make_client()
    register(c, "video@p1.co")
    assert c.post("/api/videos", json={"scenes": []}).status_code == 400
    v = c.post("/api/videos", json={"title": "קיץ", "cta": "להזמנה", "scenes": [
        {"seconds": "2", "visual": "<script>x</script>", "voiceover": "פשתן טבעי לקיץ"}, {"seconds": "2", "visual": "", "voiceover": "משלוח מהיר"}]}).json()
    assert v["seconds"] >= 7
    f = c.get(v["url"])
    assert f.status_code == 200 and f.headers["content-type"] == "video/mp4" and len(f.content) > 10000 and f.content[4:8] == b"ftyp"
    o = make_client(db=c.app.state.db)
    register(o, "o3@p1.co")
    assert o.get(v["url"]).status_code == 404


def test_research_visits_competitor_sites(make_client, monkeypatch):
    import app.research.analyzer as an
    c = make_client()
    register(c, "res@p1.co")
    c.put("/api/business/profile", json={"data": {"competitors": "https://rival.co.il, shop.other.com ועוד מתחרה בלי אתר"}})
    db = c.app.state.db
    acc = db.get_account(c.get("/api/account").json()["account"]["id"])
    seen = []

    async def fake(url, **kw):
        seen.append(url)
        return {"ok": url.startswith("https"), "error": None if url.startswith("https") else "blocked", "facts": {"title": "T"}, "issues": []}
    monkeypatch.setattr(an, "analyze_url", fake)
    eng = SpecEngine()
    run = autopilot.create(db, acc, None, "מחקר מתחרים", [{"agent": "research", "goal": "x"}], "rules", "")
    asyncio.run(autopilot.execute(db, None, acc, None, run["id"], engine=eng))
    r = autopilot.get(db, run["id"], acc["id"])
    assert seen == ["https://rival.co.il", "shop.other.com"] and "1/2" in r["plan"]["steps"][0]["summary"]
    assert eng.seen[-1][1]["competitor_sites_measured"][1]["ok"] is False


def test_video_seconds_parsing_handles_model_formats():
    from app.business.video import _seconds
    assert [_seconds(x) for x in (3, "4s", "0-5", "5-8", "00:03-00:06", "", None, "שלוש", 60)] == [3, 4, 5, 3, 3, 3, 3, 3, 6]
