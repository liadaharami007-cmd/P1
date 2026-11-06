"""בדיקות למנוע הבדיקות: כללים, ציון, סימולציה, ומסע רכישה מלא בדפדפן אמיתי מול חנות בדיקה מקומית."""
import asyncio

import pytest

from app.audit import personas, rules, scoring
from app.audit.browser import HostGuard
from app.audit.runner import AuditRunner
from app.db import Database
from app.main import browser_available

from . import shop_server
from .conftest import register

HAS_BROWSER = browser_available()[0]
needs_browser = pytest.mark.skipif(not HAS_BROWSER, reason="Chromium/Playwright לא זמין")


# ------------------------------------------------------------------ יחידה
def _home(**over):
    base = {"timing": {"ttfb": 100, "lcp": 1200, "load": 1500, "cls": 0}, "resources": 20, "transfer_kb": 800,
            "overlay": None, "has_search": True, "html": {"has_viewport": True, "phones": ["03"], "whatsapp_link": True},
            "html_issues": [], "load_ms": 1500}
    base.update(over)
    return base


GOOD_TRUST = {k: "https://x.test/" + k for k in ("returns", "shipping", "privacy", "terms", "contact", "about", "faq")}


def test_unreachable_site_is_critical_and_only_technical_scored():
    facts = {"home_error": "timeout"}
    steps = [{"key": "home", "status": "failed", "screenshot_id": None, "page_url": None}]
    f = rules.evaluate(facts, steps)
    assert f[0]["rule_id"] == "site_unreachable" and f[0]["severity"] == "critical"
    overall, cats = scoring.score(f, facts, steps)
    assert cats["trust"] is None and cats["technical"] == 70 and overall <= 49
    assert personas.simulate(facts) == []


def test_no_product_means_journey_not_scored_as_perfect():
    facts = {"home": _home(), "https": True, "trust_links": GOOD_TRUST, "search": {"available": True}}
    steps = [{"key": "home", "status": "passed"}, {"key": "product", "status": "warning", "detail": "לא נמצא"}]
    f = rules.evaluate(facts, steps)
    assert "no_product_found" in {x["rule_id"] for x in f}
    _, cats = scoring.score(f, facts, steps)
    assert cats["checkout"] is None  # לא נבדק => אין ציון, לא 100 מזויף
    assert all(x["source"] == "measured" for x in f)


def test_broken_checkout_rules():
    facts = {"home": _home(timing={"ttfb": 1, "lcp": 5200, "load": 6000, "cls": 0.4}), "https": True, "trust_links": GOOD_TRUST,
             "product": {"price_visible": False, "large_images": 1, "mentions_reviews": False, "mentions_shipping": True,
                         "mentions_returns": True, "description_chars": 3000, "jsonld_product": True},
             "add_to_cart": {"found": True, "clicked": True, "signals": ["x"]},
             "cart": {"reached": True, "empty": False},
             "checkout": {"button_found": True, "reached": True, "fields": 22, "login_required": True, "payment_methods": []},
             "search": {"available": True, "tested": True, "works": False},
             "mobile": {"horizontal_overflow": True, "scroll_width": 600, "viewport_width": 390, "small_tap_targets": 3,
                        "atc_above_fold": False, "atc_position_px": 900, "overlay": None}}
    steps = [{"key": k, "status": "passed"} for k in ("home", "product", "add_to_cart", "cart", "checkout")]
    ids = {x["rule_id"] for x in rules.evaluate(facts, steps)}
    assert {"slow_lcp", "layout_shift", "no_price", "few_images", "no_reviews", "forced_login", "long_checkout",
            "payment_methods_hidden", "search_broken", "mobile_overflow", "mobile_atc_below_fold"} <= ids
    sim = {p["persona"]: p for p in personas.simulate(facts)}
    assert sim["rushed"]["verdict"] == "likely_leave"
    assert sim["bargain"]["verdict"] == "likely_leave"  # אין מחיר = חסם קשה


def test_personas_reference_measured_facts():
    facts = {"home": _home(), "https": False, "trust_links": {}}
    sim = {p["persona"]: p for p in personas.simulate(facts)}
    assert sim["skeptic"]["verdict"] == "likely_leave"
    assert any("לא מאובטח" in b for b in sim["skeptic"]["blockers"])


def test_host_guard():
    g = HostGuard()
    assert asyncio.run(g.is_allowed("http://127.0.0.1:8000/")) is False
    assert asyncio.run(g.is_allowed("http://169.254.169.254/latest")) is False
    assert asyncio.run(g.is_allowed("https://8.8.8.8/")) is True
    assert asyncio.run(g.is_allowed("file:///etc/passwd")) is False
    assert asyncio.run(HostGuard(allow_private=True).is_allowed("http://127.0.0.1/")) is True


# ------------------------------------------------------------------ API
def test_api_requires_permission_and_blocks_internal(make_client):
    client = make_client()
    register(client, "owner@shop.co.il")
    r = client.post("/api/audits", json={"url": "https://shop.example", "confirm_permission": False})
    assert r.status_code == 400 and "הרשאה" in r.json()["detail"]
    r = client.post("/api/audits", json={"url": "http://127.0.0.1:9", "confirm_permission": True})
    assert r.status_code == 400 and "פנימית" in r.json()["detail"]
    d = client.get("/api/dashboard").json()
    assert d["sites"] == [] and d["site"] is None
    ints = {i["id"]: i["status"] for i in client.get("/api/integrations").json()}
    assert ints["shopify"] == "not_built" and ints["wordpress"] == "not_built"  # לא מוצג כמחובר
    assert all(s != "connected" for k, s in ints.items() if k not in ("claude", "ollama", "email", "paddle"))
    m = client.get("/api/methodology").json()
    assert sum(m["weights"].values()) == 100 and m["counts_sources"] == ["measured"]


# ------------------------------------------------------------------ דפדפן אמיתי
def _run_shop(tmp_path, name):
    db = Database(tmp_path / f"{name}.db")
    url, srv = shop_server.start(name)
    runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "shots")
    site = db.get_or_create_site(url.rstrip("/"))
    audit = db.create_audit(site["id"], url)
    try:
        asyncio.run(runner.run(audit["id"], site["id"], url))
    finally:
        srv.shutdown()
    return db, audit["id"]


@needs_browser
def test_full_journey_good_shop(tmp_path):
    db, aid = _run_shop(tmp_path, "good_shop")
    a = db.get_audit(aid)
    assert a["status"] == "done", a["error"]
    steps = {s["key"]: s["status"] for s in db.get_steps(aid)}
    assert steps == {"home": "passed", "trust": "passed", "product": "passed", "add_to_cart": "passed",
                     "cart": "passed", "checkout": "passed", "search": "passed", "mobile": "passed", "contact_channels": "passed",
                     "links": "passed"}
    assert a["facts"]["checkout"]["login_required"] is False
    assert a["facts"]["product"]["price_visible"] is True
    ids = {f["rule_id"] for f in db.get_findings(aid)}
    assert not ids & {"atc_missing", "atc_failed", "cart_empty_after_add", "checkout_failed", "no_returns_policy"}
    assert "no_https" in ids  # השרת המקומי הוא http — ממצא נכון
    shots = db.list_screenshots(aid)
    assert {s["label"] for s in shots} >= {"home", "product", "after-add-to-cart", "cart", "checkout"}
    assert any(s["device"] == "mobile" for s in shots)
    assert {p["persona"] for p in db.get_personas(aid)} == set(personas.PERSONAS)


@needs_browser
def test_full_journey_broken_shop(tmp_path):
    db, aid = _run_shop(tmp_path, "broken_shop")
    a = db.get_audit(aid)
    assert a["status"] == "done", a["error"]
    steps = {s["key"]: s for s in db.get_steps(aid)}
    assert steps["add_to_cart"]["status"] == "warning"
    assert steps["cart"]["status"] == "failed"
    assert steps["checkout"]["status"] == "skipped"
    ids = {f["rule_id"] for f in db.get_findings(aid)}
    assert {"cart_empty_after_add", "atc_no_feedback", "entry_popup", "no_returns_policy", "no_viewport"} <= ids
    assert a["score"] <= 49
    verdicts = {p["persona"]: p["verdict"] for p in db.get_personas(aid)}
    assert verdicts["rushed"] == "likely_leave"


# ------------------------------------------------------------------ P1 Intelligence (Claude מדומה — לבדיקות בלבד)
class FakeAI:
    """מחליף את Claude בבדיקות אוטומטיות בלבד: מחזיר JSON תקין לפי הסכמה, ורושם מה נשלח."""

    def __init__(self):
        self.calls = []
        self.beta = type("B", (), {"messages": self})()

    async def create(self, **kw):
        import json
        from types import SimpleNamespace
        self.calls.append(kw)
        if "P1 Intelligence" in kw["system"]:
            data = {"executive_summary": "סיכום", "conversion_readiness": "בינונית", "top_strengths": ["מהיר"],
                    "ai_findings": [{"title": "הצעת הערך לא ברורה", "category": "conversion", "severity": "high",
                                     "impact": "high", "observation": "בכותרת אין יתרון", "evidence_refs": ["home/desktop"],
                                     "why_it_matters": "x", "recommendation": "לנסח כותרת", "confidence": "medium"}],
                    "copy_suggestions": [{"area": "headline", "current_text": "בגדים", "suggested_text": "בגדי כותנה",
                                          "rationale": "ספציפי"}],
                    "action_plan": [{"priority": 1, "title": "לעבור ל-HTTPS", "why_first": "אמון", "related_refs": ["no_https"],
                                     "effort": "low", "expected_effect": "יותר אמון"}],
                    "comparison_notes": ""}
        else:
            data = {"understood": "חנות בגדים", "caught_attention": ["מחיר"], "confusing": [], "distrust": ["אין https"],
                    "purchase_issues": [], "improvements": ["https"], "verdict": "hesitant", "verdict_reason": "אמון"}
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=800, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0),
                               content=[SimpleNamespace(type="text", text=json.dumps(data, ensure_ascii=False))])


@needs_browser
def test_ai_pipeline_and_pdf(tmp_path):
    from app.report.data import assemble
    from app.report.pdf import render_pdf
    fake = FakeAI()
    db = Database(tmp_path / "ai.db")
    url, srv = shop_server.start("good_shop")
    runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "shots", ai_client=fake)
    audit = runner.enqueue(url)
    try:
        asyncio.run(runner.run(audit["id"], audit["site_id"], url))
    finally:
        srv.shutdown()
    a = db.get_audit(audit["id"])
    assert a["status"] == "done" and a["ai_status"] == "done"
    # הבקשה ל-Claude: סכמה מובנית, fallback, וצילומי מסך אמיתיים
    main = next(c for c in fake.calls if "P1 Intelligence" in c["system"])
    assert main["output_config"]["format"]["type"] == "json_schema" and main["fallbacks"] == "default"
    assert any(b.get("type") == "image" for b in main["messages"][0]["content"])
    assert len(fake.calls) == 6  # ניתוח + 5 סוכני לקוח
    runs = db.get_ai_runs(audit["id"])
    assert all(r["status"] == "done" for r in runs) and all(r["cost_usd"] > 0 for r in runs)
    findings = db.get_findings(audit["id"])
    ai = [f for f in findings if f["source"] == "ai"]
    assert ai and ai[0]["evidence"]["confidence"] == "medium"
    # השערות AI לא משנות את הציון
    measured = [f for f in findings if f["source"] != "ai"]
    assert scoring.score(measured, a["facts"], db.get_steps(audit["id"]))[0] == a["score"]
    events = [e["kind"] for e in db.get_events(audit["id"])]
    assert {"navigate", "click", "screenshot", "ai"} <= set(events)
    report = assemble(db, a)
    assert report["ai"]["analysis"]["executive_summary"] == "סיכום" and len(report["ai"]["personas"]) == 5
    pdf = asyncio.run(render_pdf(report, db.list_screenshots(audit["id"], with_paths=True)))
    assert pdf[:4] == b"%PDF" and len(pdf) > 20000
    (tmp_path / "r.pdf").write_bytes(pdf)


@needs_browser
def test_ai_not_configured_is_honest(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    db, aid = _run_shop(tmp_path, "broken_shop")
    a = db.get_audit(aid)
    assert a["ai_status"] == "not_configured"
    assert not [f for f in db.get_findings(aid) if f["source"] == "ai"]
    assert db.get_ai_runs(aid) == []
