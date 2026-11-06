"""Business OS: פרופיל עסק, CEO (בריאות/תוכנית/הוכחה), מרכז אישורים, חבילת תיקון, אימות תיקון והפרדת חשבונות."""
from datetime import datetime, timezone

import pytest

from app.business import brain, ceo
from app.intelligence import engines
from app.main import browser_available

from .conftest import register

PROFILE = {"business_name": "סדנת פשתן", "business_type": "ecommerce", "industry": "אופנה", "website": "https://8.8.8.8",
           "offer": "בגדי פשתן", "audience": "נשים 25-45", "goals": ["more_sales", "fix_site", "bogus"], "monthly_ad_budget": "3000"}


def _finish(db, audit_id, site_id, account_id, score, rules):
    db.add_findings(audit_id, site_id, [{"rule_id": r, "source": "measured", "category": "trust", "severity": "high", "impact": "high",
                                         "title": f"בעיה {r}", "detail": "d", "why_it_matters": "w", "fix_steps": ["x"]} for r in rules])
    db.update_audit(audit_id, status="done", score=score, category_scores={"trust": score},
                    finished_at=datetime.now(timezone.utc).isoformat())


def test_profile_validation_and_completeness():
    with pytest.raises(ValueError):
        brain.clean({"business_type": "casino"})
    with pytest.raises(ValueError):
        brain.clean({"monthly_ad_budget": "הרבה"})
    d = brain.clean(PROFILE)
    assert d["goals"] == ["more_sales", "fix_site"] and d["monthly_ad_budget"] == 3000
    assert brain.completeness(d)["ready"] and not brain.completeness({})["ready"]


@pytest.mark.skipif(not browser_available()[0], reason="Chromium/Playwright לא זמין")
def test_business_os_end_to_end(make_client, monkeypatch):
    monkeypatch.setattr(engines, "status", lambda: {"active": "rules", "preferred": "auto", "engines": []})
    c = make_client()
    register(c, "owner@biz.co")
    db = c.app.state.db

    ov = c.get("/api/business/overview").json()
    keys = [i["key"] for i in ov["plan"]["items"]]
    assert keys[:2] == ["add_site", "profile"] or set(keys) >= {"profile", "add_site"}
    assert ov["health"]["overall"] is None and "אין מספיק מידע" in ov["health"]["overall_reason"]

    assert c.put("/api/business/profile", json={"data": {"business_type": "casino"}}).status_code == 400
    prof = c.put("/api/business/profile", json={"data": PROFILE}).json()
    assert prof["completeness"]["ready"]

    site = c.post("/api/sites", json={"url": "https://8.8.8.8", "confirm_permission": True}).json()
    item = next(i for i in c.get("/api/business/overview").json()["plan"]["items"] if i["kind"] == "run_audit")
    act = c.post("/api/actions", json={"key": item["key"]}).json()
    assert act["status"] == "proposed" and act["changes"] and act["risk"] == "none"
    assert c.post("/api/actions", json={"key": item["key"]}).json()["id"] == act["id"]  # בלי כפילויות
    run = c.post(f"/api/actions/{act['id']}/approve").json()
    assert run["status"] == "executing" and run["result"]["audit_id"]
    assert c.post(f"/api/actions/{act['id']}/approve").status_code == 409

    # הבדיקה "מסתיימת" עם ממצאים → הפעולה מסתיימת והתוכנית מציעה תיקונים
    _finish(db, run["result"]["audit_id"], site["id"], c.get("/api/account").json()["account"]["id"], 60,
            ["no_returns_info_pdp", "no_reviews"])
    ov = c.get("/api/business/overview").json()
    assert c.get(f"/api/actions/{act['id']}").json()["status"] == "done"
    assert ov["health"]["domains"][0]["status"] == "measured" and ov["health"]["domains"][0]["score"] == 60
    fix_item = next(i for i in ov["plan"]["items"] if i["kind"] == "fix_package")
    assert any(i["kind"] == "enable_monitor" for i in ov["plan"]["items"])

    fx = c.post("/api/actions", json={"key": fix_item["key"]}).json()
    done = c.post(f"/api/actions/{fx['id']}/approve").json()
    assert done["status"] == "done" and done["result"]["fix"]["steps"]
    pkg = c.get(f"/api/actions/{fx['id']}/package.html")
    assert pkg.status_code == 200 and "חבילת תיקון" in pkg.text and "attachment" in pkg.headers["content-disposition"]
    fid = fx["payload"]["finding_id"]
    acc_id = c.get("/api/account").json()["account"]["id"]
    assert db.get_finding(fid, acc_id)["fix_status"] == "approved"

    # בעל העסק מסמן "יושם" → מופיעה פעולת אימות; בדיקה חוזרת מודדת מה באמת נעלם
    c.patch(f"/api/findings/{fid}/fix", json={"status": "applied"})
    v_item = next(i for i in c.get("/api/business/overview").json()["plan"]["items"] if i["kind"] == "verify_fix")
    v = c.post(f"/api/actions/{c.post('/api/actions', json={'key': v_item['key']}).json()['id']}/approve").json()
    rule = db.get_finding(fid, acc_id)["rule_id"]
    others = [r for r in ("no_returns_info_pdp", "no_reviews") if r != rule]
    _finish(db, v["result"]["audit_id"], site["id"], acc_id, 75, others)
    v = c.get(f"/api/actions/{v['id']}").json()
    assert v["status"] == "done" and [x["rule_id"] for x in v["result"]["verified_fixed"]] == [rule]

    ov = c.get("/api/business/overview").json()
    proof = ov["proof"]
    assert proof["audits_done"] == 2 and any(x["rule_id"] == rule for x in proof["issues_fixed_verified"])
    assert proof["time_saved_estimate"]["kind"] == "estimate" and proof["revenue_claim"] is None
    tl = c.get("/api/business/timeline").json()["items"]
    assert {"profile_created", "action_done", "audit_done"} <= {x["kind"] for x in tl}
    wk = c.get("/api/business/weekly").json()
    assert wk["audits_in_period"] == 2 and wk["engine"] == "rules"
    assert c.post("/api/business/brief").json()["ai_status"] == "not_configured"

    # דחייה + הפרדת חשבונות
    mon = next(i for i in ov["plan"]["items"] if i["kind"] == "enable_monitor")
    m = c.post("/api/actions", json={"key": mon["key"]}).json()
    assert c.post(f"/api/actions/{m['id']}/reject").json()["status"] == "rejected"
    other = make_client(db=db)
    register(other, "other@biz.co")
    assert other.get(f"/api/actions/{act['id']}").status_code == 404
    assert other.post(f"/api/actions/{fx['id']}/approve").status_code == 404
    assert other.get(f"/api/actions/{fx['id']}/package.html").status_code == 404
    assert other.get("/api/business/profile").json()["data"] == {}
    assert other.get("/api/actions").json()["items"] == []


def test_ai_brief_uses_only_engine_output(make_client, monkeypatch):
    class Fake:
        id = "fake"

        async def structured(self, **kw):
            from app.intelligence.client import Usage
            assert "אסור להמציא" in kw["system"]
            return {"summary": "s", "insufficient_data": ["אין נתוני מכירות"], "advice": []}, Usage(model="fake-model")
    monkeypatch.setattr(engines, "active_engine", lambda override=None: Fake())
    c = make_client()
    register(c, "ai@biz.co")
    r = c.post("/api/business/brief").json()
    assert r["ai_status"] == "done" and r["source"] == "ai" and r["insufficient_data"] == ["אין נתוני מכירות"]


def test_health_never_invents_overall():
    snap = {"latest": {"id": "a", "score": 80, "finished_at": "2026-01-01"}, "done": [{"score": 80}]}
    h = ceo.health(snap)
    assert h["overall"] is None and sum(1 for d in h["domains"] if d["status"] == "no_data") >= 5
