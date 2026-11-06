"""Agency Mode: לקוחות, סביבת הדגמה (15 לקוחות דמו מסומנים), מכסות, הפרדת חשבונות ודפי לקוחות הדמו."""
from datetime import datetime, timezone

import pytest

from app.business import agency
from app.main import browser_available

from .conftest import register


def test_demo_client_pages_are_labeled_variants(make_client):
    c = make_client()
    olive = c.get("/demo-clients/olive/").text
    assert "לקוח דמו של P1 AI" in olive and 'id="pop"' not in olive and "/demo-store/" not in olive
    assert 'id="pop"' in c.get("/demo-clients/linen/").text  # ללקוח הזה הבעיה נשארה
    assert "972501234567" in c.get("/demo-clients/wine/pages/contact/").text
    assert c.get("/demo-clients/ghost/").status_code == 404
    assert c.get("/demo-clients/olive/..%2F..%2Fmain.py").status_code == 404
    assert len(agency.DEMO_CLIENTS) == 15 and len(agency.DEMO) == 15


@pytest.mark.skipif(not browser_available()[0], reason="Chromium/Playwright לא זמין")
def test_agency_overview_seed_quota_and_isolation(make_client):
    c = make_client()
    register(c, "agency@ad.co")
    assert c.get("/api/agency").json()["clients"] == []
    assert c.post("/api/agency/clients", json={"name": "x", "url": "https://8.8.8.8"}).status_code == 400  # בלי הרשאה
    real = c.post("/api/agency/clients", json={"name": "לקוח אמיתי", "url": "https://8.8.8.8", "confirm_permission": True}).json()
    assert c.post("/api/agency/demo").json()["created"] == 15
    assert c.post("/api/agency/demo").json()["created"] == 0  # בלי כפילויות
    d = c.get("/api/agency").json()
    assert d["totals"]["clients"] == 16 and d["totals"]["demo_clients"] == 15 and d["totals"]["running"] == 15
    assert c.get("/api/account").json()["usage"]["audits"] == 0  # בדיקות דמו לא נספרות במכסה
    # בדיקה של לקוח דמו "מסתיימת" עם ממצא חמור → הלקוח מסומן כדורש טיפול
    db = c.app.state.db
    demo = next(x for x in d["clients"] if x["is_demo"])
    aid = next(a["id"] for a in db.list_audits(c.get("/api/account").json()["account"]["id"]) if a["start_url"].startswith(demo["url"]))
    a = db.get_audit(aid, any_account=True)
    db.add_findings(aid, a["site_id"], [{"rule_id": "whatsapp_link_invalid", "source": "measured", "category": "conversion", "severity": "high",
                                         "impact": "high", "title": "קישור WhatsApp שבור", "detail": "d", "why_it_matters": "w", "fix_steps": []}])
    db.update_audit(aid, status="done", score=55, finished_at=datetime.now(timezone.utc).isoformat())
    row = next(x for x in c.get("/api/agency").json()["clients"] if x["id"] == demo["id"])
    assert row["needs_attention"] and row["report_ready"] and row["serious_issues"] == 1 and "ציון נמוך (55)" in row["reasons"]
    # הפרדה בין חשבונות
    o = make_client(db=db)
    register(o, "other@ad.co")
    assert o.get("/api/agency").json()["clients"] == []
    assert o.post(f"/api/agency/clients/{real['id']}/audit").status_code == 404
    assert o.delete(f"/api/agency/clients/{real['id']}").status_code == 404
    assert c.delete("/api/agency/demo").json()["removed"] == 15
    assert c.get("/api/agency").json()["totals"]["clients"] == 1
