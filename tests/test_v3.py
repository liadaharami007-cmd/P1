"""בדיקות ל-P1 3.0: Fix Studio, סוכני לקוח, עצירה, Smart Monitor, מנועי AI, SSE והפרדת חשבונות ביכולות החדשות."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app import monitor
from app.audit.runner import AuditRunner
from app.db import Database
from app.fixstudio import catalog, service
from app.intelligence import engines
from app.main import browser_available

from . import shop_server
from .conftest import register

needs_browser = pytest.mark.skipif(not browser_available()[0], reason="Chromium/Playwright לא זמין")


# ------------------------------------------------------------------ Fix Studio — קטלוג
def test_find_usps_from_real_text():
    usps = catalog.find_usps(['משלוח חינם בהזמנה מעל 200 ש"ח, והחזרה קלה עד 14 יום. תפורים בישראל.'])
    assert usps[0] == 'משלוח חינם בהזמנה מעל 200 ש"ח' and "תפורים בישראל" in usps


def test_every_generator_returns_a_complete_fix():
    facts = {"product": {"h1": "חולצת פשתן", "url": "https://x.test/p", "jsonld_price": "289"},
             "home": {"html": {"title": "סדנת פשתן", "phones": []}}, "page_excerpts": {"product": "משלוח חינם מעל 300 ש\"ח"}}
    for rid in catalog.GENERATORS:
        f = {"rule_id": rid, "category": "conversion", "fix_steps": ["x"], "evidence": {}}
        fix = catalog.propose(f, facts)
        assert fix["summary"] and fix["steps"] and fix["kind"] in {"content", "design", "ux", "flow", "technical"}, rid
        if fix["preview"]["supported"]:
            assert fix["preview"]["ops"] and fix["preview"]["device"] in ("desktop", "mobile"), rid


def test_missing_info_is_a_placeholder_not_invented():
    fix = catalog.propose({"rule_id": "no_returns_info_pdp", "category": "trust", "fix_steps": [], "evidence": {}},
                          {"page_excerpts": {}})
    assert catalog.PH in json.dumps(fix, ensure_ascii=False) and fix["has_placeholders"]


# ------------------------------------------------------------------ מנועי AI
def test_engine_status_without_any_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(engines, "ollama_status", lambda timeout=1.5: (False, "not running"))
    monkeypatch.setattr(engines, "gemini_status", lambda *a, **k: (False, "חסר GEMINI_API_KEY", None))
    st = engines.status()
    assert st["active"] == "rules" and engines.active_engine() is None
    assert {e["id"] for e in st["engines"]} == {"anthropic", "gemini", "ollama", "rules"}


def test_ollama_engine_structured_call():
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        assert body["format"]["type"] == "object" and body["stream"] is False
        return httpx.Response(200, json={"message": {"content": json.dumps({"answer": "ok"})}, "prompt_eval_count": 12, "eval_count": 3})
    eng = engines.OllamaEngine(url="http://ollama.test", model="m", transport=httpx.MockTransport(handler))
    data, usage = asyncio.run(eng.structured(system="s", content=[{"type": "text", "text": "hi"}],
                                             schema={"type": "object", "properties": {"answer": {"type": "string"}}}))
    assert data == {"answer": "ok"} and usage.cost_usd == 0 and usage.input_tokens == 12


# ------------------------------------------------------------------ Smart Monitor
def test_monitor_tick_queues_due_audits_and_reschedules(tmp_path):
    db = Database(tmp_path / "m.db")
    runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "s")
    site = db.get_or_create_site("https://8.8.8.8")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.upsert_monitor(site["id"], None, "weekly", True, past)
    created = monitor.tick(db, runner)
    assert len(created) == 1
    a = db.get_audit(created[0], any_account=True)
    assert a["trigger"] == "monitor" and a["status"] == "queued"
    assert db.get_monitor(site["id"])["next_run_at"] > datetime.now(timezone.utc).isoformat()
    assert monitor.tick(db, runner) == []  # לא רץ שוב לפני הזמן


def test_monitor_keeps_path_and_demo_flag(tmp_path):
    db = Database(tmp_path / "md.db")
    runner = AuditRunner(db, shot_root=tmp_path / "s")  # בלי allow_private — כמו בייצור
    first = runner.enqueue("http://localhost:8000/demo-store/", None, None, demo=True)
    db.update_audit(first["id"], status="done")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.upsert_monitor(first["site_id"], None, "weekly", True, past)
    created = monitor.tick(db, runner)
    a = db.get_audit(created[0], any_account=True)
    assert a["start_url"] == "http://localhost:8000/demo-store/" and a["trigger"] == "monitor" and a["is_demo"] == 1


def test_change_notifications(tmp_path):
    db = Database(tmp_path / "n.db")
    site = db.get_or_create_site("https://shop.test", "acc")
    def done_audit(score, rules_):
        a = db.create_audit(site["id"], "https://shop.test", "acc")
        db.add_findings(a["id"], site["id"], [{"rule_id": r, "source": "measured", "category": "trust", "severity": "high",
                                               "impact": "high", "title": r, "detail": "d", "why_it_matters": "w"} for r in rules_])
        db.update_audit(a["id"], status="done", score=score, category_scores={"trust": score}, finished_at=datetime.now(timezone.utc).isoformat())
        return a["id"]
    done_audit(50, ["no_reviews", "no_https"])
    monitor.notify_changes(db, done_audit(50, []))  # הבסיס
    second = done_audit(70, ["no_reviews", "broken_links"])
    monitor.notify_changes(db, second)
    kinds = {n["kind"] for n in db.list_notifications("acc") if n["audit_id"] == second}
    assert kinds == {"new_issues", "score_change"}


# ------------------------------------------------------------------ API
def test_v3_api_isolation_and_plans(make_client):
    a = make_client()
    register(a, "a@a.co")
    site = a.post("/api/sites", json={"url": "https://8.8.8.8", "confirm_permission": True}).json()
    assert site["authorized_at"]
    assert a.post("/api/sites", json={"url": "https://1.1.1.1", "confirm_permission": False}).status_code == 400
    assert a.post("/api/sites", json={"url": "https://1.1.1.1", "confirm_permission": True}).status_code == 402  # Free: אתר אחד
    assert a.put(f"/api/sites/{site['id']}/monitor", json={"frequency": "daily"}).status_code == 402
    assert a.put(f"/api/sites/{site['id']}/monitor", json={"frequency": "monthly"}).json()["frequency"] == "monthly"
    audit = a.post("/api/audits", json={"url": "https://8.8.8.8", "confirm_permission": True}).json()
    assert a.post(f"/api/audits/{audit['id']}/stop").status_code == 200
    assert a.get(f"/api/audits/{audit['id']}").json()["status"] == "stopped"
    b = make_client(db=a.app.state.db)
    register(b, "b@b.co")
    for path in (f"/api/audits/{audit['id']}/fixes", f"/api/audits/{audit['id']}/stream", f"/api/sites/{site['id']}/progress"):
        assert b.get(path).status_code == 404, path
    assert b.post(f"/api/audits/{audit['id']}/stop").status_code == 404
    assert b.get("/api/notifications").json()["items"] == []
    assert a.get("/api/engines").json()["active"] in ("rules", "anthropic", "ollama")


def test_demo_store_is_served_and_labeled(make_client):
    c = make_client()
    r = c.get("/demo-store/")
    assert r.status_code == 200 and "חנות דמו של P1" in r.text
    assert c.get("/demo-store/products/linen-shirt/").status_code == 200
    register(c, "d@d.co")
    a = c.post("/api/demo/start").json()
    assert a["trigger"] == "demo"
    # אבטחה: כותרת Host מזויפת לא משנה את כתובת הבדיקה (SSRF)
    forged = c.post("/api/demo/start", headers={"Host": "169.254.169.254"})
    assert forged.status_code in (202, 402)
    if forged.status_code == 202:
        assert "169.254" not in forged.json()["start_url"]
    assert c.get("/api/sites").json()["sites"][0]["is_demo"] == 1


# ------------------------------------------------------------------ דפדפן אמיתי: סוכנים + Fix Studio + SSE
@needs_browser
def test_agents_fix_preview_and_stream(tmp_path, make_client):
    db = Database(tmp_path / "v3.db")
    url, srv = shop_server.start("good_shop")
    runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "shots")
    audit = runner.enqueue(url)
    try:
        asyncio.run(runner.run(audit["id"], audit["site_id"], url))
        runs = {r["agent"]: r for r in db.get_agent_runs(audit["id"])}
        assert set(runs) == {"trust", "fast_buyer", "price", "confused", "mobile_ad"}
        assert all(r["status"] == "done" and r["engine"] == "rules" for r in runs.values())
        assert runs["fast_buyer"]["result"]["metrics"]["reached_checkout"] is True
        assert runs["price"]["result"]["metrics"]["price_visible"] is True
        agent_events = [e for e in db.get_events(audit["id"]) if e["agent"]]
        assert {e["agent"] for e in agent_events} == set(runs) and any(e["kind"] == "click" for e in agent_events)
        findings = db.get_findings(audit["id"])
        assert all(f["priority"] for f in findings if f["source"] == "measured")
        a = db.get_audit(audit["id"])
        a["_allow_private"] = True
        target = next(f for f in findings if catalog.propose(f, a["facts"])["preview"].get("supported"))
        pv = asyncio.run(service.make_preview(db, a, target, shot_root=tmp_path / "shots"))
        assert pv["status"] == "done" and any(o["ok"] for o in pv["applied"])
        assert Path(db.get_screenshot(pv["before_shot"])["path"]).exists() and Path(db.get_screenshot(pv["after_shot"])["path"]).exists()
    finally:
        srv.shutdown()
    # SSE על בדיקה שהסתיימה: נתונים אמיתיים ואז אירוע סיום
    c = make_client(db=db)
    register(c, "sse@p1.ai")  # המשתמש הראשון מקבל את הנתונים שנוצרו בלי חשבון
    body = c.get(f"/api/audits/{audit['id']}/stream").text
    first = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0])
    assert first["status"] == "done" and len(first["agents"]) == 5 and first["events"]
    assert "event: end" in body


@needs_browser
def test_stop_before_start_marks_stopped(tmp_path):
    db = Database(tmp_path / "stop.db")
    url, srv = shop_server.start("good_shop")
    runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "s")
    audit = runner.enqueue(url)
    db.update_audit(audit["id"], cancel_requested=1)
    try:
        asyncio.run(runner.run(audit["id"], audit["site_id"], url))
    finally:
        srv.shutdown()
    assert db.get_audit(audit["id"])["status"] == "stopped"
