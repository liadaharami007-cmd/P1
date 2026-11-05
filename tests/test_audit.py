"""בדיקות למנוע הבדיקות: כללים, ציון, סימולציה, ומסע רכישה מלא בדפדפן אמיתי מול חנות בדיקה מקומית."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config
from app.audit import personas, rules, scoring
from app.audit.browser import HostGuard
from app.audit.runner import AuditRunner
from app.db import Database
from app.main import browser_available, create_app

from . import shop_server

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


def test_unreachable_site_is_critical_and_only_journey_scored():
    facts = {"home_error": "timeout"}
    steps = [{"key": "home", "status": "failed", "screenshot_id": None, "page_url": None}]
    f = rules.evaluate(facts, steps)
    assert f[0]["rule_id"] == "site_unreachable" and f[0]["severity"] == "critical"
    overall, cats = scoring.score(f, facts, steps)
    assert cats["trust"] is None and cats["journey"] == 70 and overall <= 49
    assert personas.simulate(facts) == []


def test_no_product_means_journey_not_scored_as_perfect():
    facts = {"home": _home(), "https": True, "trust_links": GOOD_TRUST, "search": {"available": True}}
    steps = [{"key": "home", "status": "passed"}, {"key": "product", "status": "warning", "detail": "לא נמצא"}]
    f = rules.evaluate(facts, steps)
    assert "no_product_found" in {x["rule_id"] for x in f}
    _, cats = scoring.score(f, facts, steps)
    assert cats["journey"] is None  # לא נבדק => אין ציון, לא 100 מזויף
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
def test_api_requires_permission_and_blocks_internal(tmp_path):
    client = TestClient(create_app(db=Database(tmp_path / "a.db")))
    r = client.post("/api/audits", json={"url": "https://shop.example", "confirm_permission": False})
    assert r.status_code == 400 and "הרשאה" in r.json()["detail"]
    r = client.post("/api/audits", json={"url": "http://127.0.0.1:9", "confirm_permission": True})
    assert r.status_code == 400 and "פנימית" in r.json()["detail"]
    assert client.get("/api/dashboard").json() == {"sites": [], "site": None}
    ints = {i["id"]: i["status"] for i in client.get("/api/integrations").json()}
    assert ints["shopify"] == "planned" and ints["woocommerce"] == "planned"  # לא מוצג כמחובר


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
                     "cart": "passed", "checkout": "passed", "search": "passed", "mobile": "passed"}
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
