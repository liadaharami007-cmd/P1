"""ClientPulse OS — מנוע הרמזור, מחזור חיים, משימות, אוטומציות, הפרדת חשבונות, דמו, CSV, דוחות."""
import math

from app.pulse import engine
from app.pulse.engine import analyze_client, iso_of, stats

from .conftest import register

REF = 20700


def days(n=60, spend=500, impr=20000, clicks=400, leads=10, ref=REF, mod=None):
    out = []
    for i in range(n):
        t = ref - n + 1 + i
        d = {"date": iso_of(t), "spend": spend, "impressions": impr, "clicks": clicks, "leads": leads}
        if mod:
            d = mod(ref - t, d)
        if d:
            out.append(d)
    return out


C = {"id": "x", "name": "לקוח בדיקה", "goals": {"targetCpl": 60}}


# ---------------------------------------------------------------- מנוע
def test_stable_client_is_green_and_no_division_by_zero():
    r = analyze_client(C, days(), REF)
    assert r["status"] == "green" and r["alerts"] == []
    assert r["health"]["score"] == 100
    s = stats([{"date": iso_of(1), "spend": 0, "impressions": 0, "clicks": 0, "leads": 0}])
    assert s["cpl"] is None and s["ctr"] is None and s["cvr"] is None  # אין חלוקה באפס


def test_cpl_spike_is_red_with_facts_and_investigation():
    r = analyze_client(C, days(mod=lambda a, d: {**d, "leads": 3} if a < 4 else d), REF)
    a = next(x for x in r["alerts"] if x["type"] == "cpl")
    assert r["status"] == "red" and a["severity"] == "red"
    assert a["numbers"] and a["why"] and a["confidence"]
    inv = engine.investigate(r, a)
    assert inv["facts"] and inv["hypotheses"] and inv["plan"] and inv["success"]["targetCpl"]
    assert any("נחיתה" in h["text"] for h in inv["hypotheses"])  # הקליקים זהים → ההמרה ירדה


def test_small_change_is_not_red():
    r = analyze_client(C, days(mod=lambda a, d: {**d, "leads": 9} if a < 3 else d), REF)
    assert r["status"] == "green"


def test_zero_leads_and_missing_data():
    r = analyze_client(C, days(mod=lambda a, d: {**d, "leads": 0} if a < 2 else d), REF)
    assert any(a["type"] == "no_leads" and a["severity"] == "red" for a in r["alerts"])
    gap = analyze_client(C, days(mod=lambda a, d: None if a < 2 else d), REF)
    assert gap["alerts"][0]["type"] == "data" and gap["status"] == "red"
    empty = analyze_client(C, [], REF)
    assert empty["alerts"][0]["type"] == "data"


def test_low_spend_caps_red_to_yellow():
    r = analyze_client(C, days(spend=20, leads=2, mod=lambda a, d: {**d, "leads": 0} if a < 3 else d), REF)
    assert all(a["severity"] != "red" for a in r["alerts"] if a["type"] != "data")


def test_improvement_and_trend_and_custom_threshold():
    r = analyze_client(C, days(mod=lambda a, d: {**d, "leads": 18} if a < 7 else d), REF)
    assert r["improved"] and r["status"] == "green"
    trend = analyze_client({**C, "goals": {}}, days(n=60, leads=40, spend=2000,
                            mod=lambda a, d: {**d, "leads": max(1, round(40 / (1.12 ** ((27 - a) / 7)))) if a <= 27 else d}), REF)
    assert any(a["type"] in ("trend", "cpl") for a in trend["alerts"])
    strict = engine.thresholds_for({"cplYellow": 99, "evil": 1})
    assert strict["cplYellow"] == 2.0 and "evil" not in strict  # קלמפ לטווח + רק מפתחות מותרים


def test_leads_without_sales_only_when_sales_data_exists():
    def m(a, d):
        return {**d, "sales": 0 if a < 14 else 2}
    r = analyze_client(C, days(n=60, leads=10, mod=m), REF)
    assert any(a["type"] == "no_sales" for a in r["alerts"])
    r2 = analyze_client(C, days(), REF)
    assert r2["sales28"] is None and not any(a["type"] == "no_sales" for a in r2["alerts"])


def test_profitability_separates_agency_fee_from_ad_budget():
    assert engine.profitability({"fee_monthly": None}) is None
    f = engine.profitability({"fee_monthly": 5000, "hours_monthly": 20, "hourly_cost": 100, "other_costs_monthly": 500})
    assert f["profit"] == 2500 and math.isclose(f["margin"], 0.5)


# ---------------------------------------------------------------- API מקצה לקצה
def _login(make_client, email="boss@agency.co"):
    c = make_client()
    register(c, email, name="ניב")
    return c


def test_end_to_end_red_client_flow(make_client):
    c = _login(make_client)
    assert c.get("/pulse").status_code == 200
    r = c.post("/api/pulse/demo")
    assert r.status_code == 200 and r.json()["check"]["n"] == 50
    ov = c.get("/api/pulse/overview").json()
    assert ov["counts"]["red"] >= 5 and ov["today"] and ov["demo"]
    cl = c.get("/api/pulse/clients").json()["clients"]
    red = next(x for x in cl if x["status"] == "red" and x["alerts"][0]["type"] == "cpl")
    d = c.get(f"/api/pulse/clients/{red['id']}").json()
    a = d["alerts"][0]
    assert a["inv"]["facts"] and a["inv"]["plan"] and d["series"] and d["timeline" if "timeline" in d else "events"] is not None
    # אוטומציה פתחה משימה אחת ללקוח (לא כפולה)
    tasks = [t for t in c.get("/api/pulse/tasks").json()["tasks"] if t["client_id"] == red["id"]]
    assert len(tasks) == 1
    t = tasks[0]
    assert c.post(f"/api/pulse/tasks/{t['id']}/start").json()["ok"]
    res = c.post(f"/api/pulse/tasks/{t['id']}/submit").json()
    assert res["ok"]
    t = c.get("/api/pulse/tasks").json()["tasks"]
    t = next(x for x in t if x["client_id"] == red["id"])
    if t["status"] == "awaiting_approval":
        assert c.post(f"/api/pulse/tasks/{t['id']}/approve").json()["ok"]  # בעלים יכול לאשר
    t = next(x for x in c.get("/api/pulse/tasks").json()["tasks"] if x["id"] == t["id"])
    assert t["status"] == "awaiting_verification"
    early = c.post(f"/api/pulse/tasks/{t['id']}/recheck_now").json()
    assert not early["ok"] and "מוקדם" in early["msg"]
    assert c.post(f"/api/pulse/tasks/{t['id']}/simulate_fix").json()["ok"]
    assert c.post("/api/pulse/lab/advance", json={"days": 4}).json()["ok"]
    t = next(x for x in c.get("/api/pulse/tasks").json()["tasks"] if x["id"] == t["id"])
    assert t["status"] == "closed" and t["verification"]["ok"]
    imp = c.get("/api/pulse/impact").json()
    assert imp["verified"] >= 1 and imp["events"]
    rep = c.get(f"/api/pulse/reports/client/{red['id']}.html")
    assert rep.status_code == 200 and "דוח ביצועים" in rep.text and "דמו" in rep.text
    ans = c.post("/api/pulse/ask", json={"q": "מה השתנה בשבוע האחרון?"}).json()
    assert ans["engine"] == "rules" and ans["intent"] == "changes" and "אומתו" in ans["text"]


def test_lab_scenario_changes_status_and_creates_alert(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    r = c.post("/api/pulse/lab/scenario", json={"scenario": "zero_leads"}).json()
    assert r["ok"] and r["before"] == "green" and r["after"] in ("red", "yellow")
    d = c.get(f"/api/pulse/clients/{r['client_id']}").json()
    assert any(a["type"] == "no_leads" for a in d["alerts"])
    notes = c.get("/api/pulse/notifications").json()
    assert any("הפסיק להביא לידים" in n["text"] for n in notes)
    # תרחיש "עובד לא מטפל" → איחור + הסלמה
    r2 = c.post("/api/pulse/lab/scenario", json={"scenario": "ignored"}).json()
    assert r2["ok"]
    notes = c.get("/api/pulse/notifications").json()
    assert any("באיחור" in n["text"] for n in notes) and any("הסלמה" in n["text"] for n in notes)


def test_automation_dedupe_toggle_and_dry_run(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    n1 = len(c.get("/api/pulse/tasks").json()["tasks"])
    c.post("/api/pulse/check")
    c.post("/api/pulse/check")
    assert len(c.get("/api/pulse/tasks").json()["tasks"]) == n1  # בלי כפילויות בבדיקות חוזרות
    log = c.get("/api/pulse/automations").json()["log"]
    assert len({x["run_key"] for x in log}) == len(log)
    dry = c.post("/api/pulse/automations/daily_summary/test").json()
    assert "שום דבר" in dry["note"]
    assert c.put("/api/pulse/automations/red_task", json={"on": False}).json()["ok"]
    assert not next(r for r in c.get("/api/pulse/automations").json()["rules"] if r["id"] == "red_task")["on"]


def test_account_isolation_and_permissions(make_client, tmp_path):
    from app.db import Database
    db = Database(tmp_path / "iso.db")
    a = make_client(db=db)
    register(a, "a@a.co")
    a.post("/api/pulse/demo")
    cid = a.get("/api/pulse/clients").json()["clients"][0]["id"]
    b = make_client(db=db)
    register(b, "b@b.co")
    assert b.get("/api/pulse/clients").json()["clients"] == []
    assert b.get(f"/api/pulse/clients/{cid}").status_code == 404
    assert b.get(f"/api/pulse/reports/client/{cid}.html").status_code == 404
    anon = make_client(db=db)
    assert anon.get("/api/pulse/overview").status_code == 401


def test_real_client_csv_import_and_validation(make_client):
    c = _login(make_client)
    cl = c.post("/api/pulse/clients", json={"name": "לקוח אמיתי", "target_cpl": 80, "fee_monthly": 4000, "hours_monthly": 10, "hourly_cost": 150}).json()
    bad = c.post(f"/api/pulse/clients/{cl['id']}/import", json={"csv": "date,spend\n2026-01-01,5"}).json()
    assert bad["imported"] == 0 and "חסרות" in bad["errors"][0]
    ref = c.get("/api/pulse/state").json()["ref"]
    lines = ["Day,Amount spent (ILS),Impressions,Link clicks,Leads"]
    for i in range(40):
        lines.append(f"{iso_of(ref - 39 + i)},400,15000,300,{5 if i < 37 else 0}")
    lines.append("2026-13-01,1,1,1,1")
    lines.append(f"{iso_of(ref)},-5,1,1,1")
    res = c.post(f"/api/pulse/clients/{cl['id']}/import", json={"csv": "\n".join(lines)}).json()
    assert res["imported"] == 40 and len(res["errors"]) == 2
    d = c.get(f"/api/pulse/clients/{cl['id']}").json()
    assert d["client"]["source"] == "csv" and not d["client"]["is_demo"]
    assert any(a["type"] == "no_leads" for a in d["alerts"])
    assert d["profit"]["profit"] == 2500
    assert c.post("/api/pulse/lab/scenario", json={"scenario": "cpl", "client_id": cl["id"]}).json()["ok"] is False
    integ = {i["id"]: i for i in c.get("/api/pulse/integrations").json()}
    assert integ["csv"]["status"] == "connected" and integ["meta"]["status"] == "not_connected"


def test_ask_intents_and_false_positive_feedback(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    for q, intent in [("מה קורה היום במשרד?", "today"), ("אילו עובדים עמוסים?", "team"), ("איפה אנחנו מפסידים כסף?", "money"),
                      ("אילו לקוחות כדאי לפתח?", "opportunities"), ("ספר לי בדיחה", "unknown")]:
        assert c.post("/api/pulse/ask", json={"q": q}).json()["intent"] == intent
    cl = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["alerts"])
    name = cl["name"]
    assert c.post("/api/pulse/ask", json={"q": f"למה {name} במצב הזה?"}).json()["intent"] == "why"
    key = c.get(f"/api/pulse/clients/{cl['id']}").json()["alerts"][0]["key"]
    assert c.post("/api/pulse/alerts/feedback", json={"key": key, "verdict": "false_positive"}).json()["ok"]
    assert c.get("/api/pulse/impact").json()["false_positives"] == 1


def test_scheduler_runs_once_per_day(make_client, tmp_path):
    from app.db import Database
    from app.pulse import scheduler
    db = Database(tmp_path / "s.db")
    c = make_client(db=db)
    register(c, "s@s.co")
    c.post("/api/pulse/demo")
    assert scheduler.tick(db) == 1
    assert scheduler.tick(db) == 0


def test_alert_board_has_every_field_yuval_asked_for(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    d = c.get("/api/pulse/alerts").json()
    assert d["cards"] and d["board"] and d["missing"]
    for card in d["cards"]:
        for k in ("what", "started_label", "changed", "severity_label", "evidence", "explanations", "check", "next", "owner_name", "handled", "improved"):
            assert card[k] not in (None, ""), k
    red = next(x for x in d["cards"] if x["severity"] == "red" and x["task_id"])
    assert "טופל" in red["handled"] or "לא" in red["handled"]
    cid = red["client_id"]
    assert c.get(f"/api/pulse/clients/{cid}").json()["alerts"][0]["card"]["next"]
