"""בדיקת ערוצי פנייה: ניתוח קישורי WhatsApp, טפסי לידים וכללים — ובדפדפן אמיתי על חנות הדמו (בלי שליחת טפסים)."""
import asyncio

import pytest

from app.audit import leads
from app.audit.rules import _f
from app.main import browser_available


def test_whatsapp_numbers():
    assert leads.wa_number("https://wa.me/972501234567?text=hi") == "972501234567"
    assert leads.wa_number("https://api.whatsapp.com/send?phone=+972-50-123-4567") == "972501234567"
    assert leads.wa_valid("972501234567")[0]
    ok, why = leads.wa_valid("0501234567")
    assert not ok and "972501234567" in why
    assert not leads.wa_valid(None)[0] and not leads.wa_valid("12345")[0]


def _page(url, forms=(), wa=(), tel=()):
    return {"url": url, "forms": list(forms), "whatsapp": list(wa), "tel": list(tel), "mailto": 0}


FORM = {"fields": 9, "required": 0, "has_email": True, "has_tel": True, "has_submit": True, "labelled": 8, "is_search": False}


def test_rules_from_measured_contact_facts():
    c = leads.summarize(_page("https://x/"), _page("https://x/", wa=[{"href": "https://x/", "above_fold": False}][:0]),
                        _page("https://x/contact", forms=[FORM, {**FORM, "is_search": True, "fields": 1}],
                              wa=[{"href": "https://wa.me/0501234567", "above_fold": False}]))
    ids = {f["rule_id"] for f in leads.rules(c, {}, {}, _f)}
    assert {"whatsapp_link_invalid", "lead_form_too_long", "lead_form_unlabeled", "no_quick_contact_mobile"} <= ids
    assert "lead_form_no_submit" not in ids and len(c["lead_forms"]) == 1  # טופס חיפוש לא נחשב
    good = leads.summarize(_page("https://y/"), _page("https://y/", tel=[{"href": "tel:035551234", "above_fold": True}]), None)
    assert leads.rules(good, {}, {}, _f) == []
    assert all(f["source"] == "measured" for f in leads.rules(c, {}, {}, _f))


@pytest.mark.skipif(not browser_available()[0], reason="Chromium/Playwright לא זמין")
def test_demo_store_contact_channels_in_real_browser(tmp_path, make_client):
    from app.audit.runner import AuditRunner
    from app.db import Database
    from . import shop_server  # noqa: F401 — אותו מנגנון שרת כמו שאר הבדיקות
    c = make_client()
    url = None
    import threading
    import uvicorn
    cfg = uvicorn.Config(c.app, host="127.0.0.1", port=8765, log_level="error")
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    try:
        import time
        for _ in range(50):
            if srv.started:
                break
            time.sleep(0.1)
        url = "http://127.0.0.1:8765/demo-store/"
        db = Database(tmp_path / "l.db")
        runner = AuditRunner(db, allow_private=True, shot_root=tmp_path / "s")
        a = runner.enqueue(url)
        asyncio.run(runner.run(a["id"], a["site_id"], url))
        audit = db.get_audit(a["id"])
        contact = audit["facts"]["contact"]
        assert contact["lead_forms"] and contact["whatsapp"][0]["valid"] is False
        ids = {f["rule_id"] for f in db.get_findings(a["id"])}
        assert {"whatsapp_link_invalid", "lead_form_too_long", "no_quick_contact_mobile"} <= ids
        step = next(s for s in db.get_steps(a["id"]) if s["key"] == "contact_channels")
        assert "לא נשלח אף טופס" in step["detail"]
    finally:
        srv.should_exit = True
        th.join(timeout=10)
