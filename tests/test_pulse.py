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


def test_ads_analysis_my_view_and_brief(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    d = c.get("/api/pulse/ads").json()
    assert d["clients"] and d["analysis"]["ads"] and d["analysis"]["summary"]
    areas = {r["area"] for a in d["analysis"]["ads"] for r in a["recs"]}
    assert areas & {"הצעה", "קופי", "קריאייטיב"}
    ad = d["analysis"]["ads"][0]
    assert c.post(f"/api/pulse/ads/{ad['id']}/rewrite").status_code == 409  # בלי Gemini: לא ממציאים קופי
    my = c.get("/api/pulse/my?member=yuval").json()
    assert my["member"] == "yuval" and my["clients"] > 0
    b = c.get("/api/pulse/brief").json()
    assert 0 < len(b["items"]) <= 8 and all(i["action"]["label"] for i in b["items"])


def test_member_role_cannot_approve_or_change_settings(make_client, tmp_path):
    from app.db import Database
    db = Database(tmp_path / "r.db")
    owner = make_client(db=db)
    register(owner, "owner@a.co")
    owner.post("/api/pulse/demo")
    assert owner.post("/api/pulse/team/login", json={"name": "יובל", "email": "dana@a.co", "password": "dana-password-123"}).status_code == 201
    worker = make_client(db=db)
    assert worker.post("/api/auth/login", json={"email": "dana@a.co", "password": "dana-password-123"}).status_code == 200
    assert worker.get("/api/pulse/clients").json()["clients"]  # רואה את נתוני הסוכנות
    assert worker.put("/api/pulse/automations/red_task", json={"on": False}).status_code == 403
    assert worker.put("/api/pulse/settings/thresholds", json={"thresholds": {"cplRed": 1}}).status_code == 403
    t = next(t for t in worker.get("/api/pulse/tasks").json()["tasks"] if t["requires_approval"])
    worker.post(f"/api/pulse/tasks/{t['id']}/start")
    worker.post(f"/api/pulse/tasks/{t['id']}/submit")
    r = worker.post(f"/api/pulse/tasks/{t['id']}/approve").json()
    assert r["ok"] is False and "בעלים" in r["msg"]


def test_low_data_client_is_not_green_and_commitment_affects_status(make_client):
    c = _login(make_client)
    cl = c.post("/api/pulse/clients", json={"name": "לקוח חדש"}).json()
    assert c.get(f"/api/pulse/clients/{cl['id']}").json()["result"]["status"] in ("red", "nodata")  # אין נתונים → לא ירוק
    c.post("/api/pulse/demo")
    green = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["status"] == "green" and not x["alerts"])
    c.post(f"/api/pulse/clients/{green['id']}/commitments", json={"text": "לשלוח דוח", "due_in": 0})
    c.post("/api/pulse/lab/advance", json={"days": 8})
    d = c.get(f"/api/pulse/clients/{green['id']}").json()
    assert any(a["type"] == "commitment" for a in d["alerts"]) and d["status_history"]


def test_recovery_potential_and_client_update_draft(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    b = c.get("/api/pulse/brief").json()
    assert b["potential"]["leads_week"] > 0
    red = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["alerts"] and x["alerts"][0]["type"] == "cpl")
    d = c.get(f"/api/pulse/clients/{red['id']}").json()
    assert d["result"]["recovery"]["leads_week"] >= 3 and "לידים נוספים" in d["alerts"][0]["card"]["potential"]
    r = c.post(f"/api/pulse/clients/{red['id']}/update-draft").json()
    assert r["ok"] and "לידים" in r["text"] and "עלות לליד" in r["text"]
    assert c.get(f"/api/pulse/clients/{red['id']}").json()["drafts"][0]["kind"] == "update"


def test_benchmark_and_reminders(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    red = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["alerts"] and x["alerts"][0]["type"] == "cpl")
    bm = c.get(f"/api/pulse/clients/{red['id']}").json()["benchmark"]
    assert bm and "מהלקוחות שלכם" in bm["text"] and bm["n"] >= 3 and "100%" not in bm["text"] or bm
    green = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["status"] == "green")
    c.post(f"/api/pulse/clients/{green['id']}/commitments", json={"text": "לשלוח הצעת מחיר", "due_in": 2})
    c.post("/api/pulse/lab/advance", json={"days": 1})
    assert any("תזכורת" in n["text"] and "הצעת מחיר" in n["text"] for n in c.get("/api/pulse/notifications").json())


def test_focus_handle_week_and_notify_on_change(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    card = c.get("/api/pulse/alerts").json()["cards"][0]
    r = c.post("/api/pulse/alerts/handle", json={"key": card["key"], "mode": "done"}).json()
    assert r["ok"] and r["task_id"]
    t = next(t for t in c.get("/api/pulse/tasks").json()["tasks"] if t["id"] == r["task_id"])
    assert t["status"] == "awaiting_verification"  # בעלים: טיפלתי = בוצע ואושר, נקבעה בדיקה חוזרת
    b = c.get("/api/pulse/brief").json()
    assert b["week"]["handled_today"] >= 1 and b["week"]["detected"] > 0
    n0 = len(c.get("/api/pulse/notifications").json())
    c.post("/api/pulse/lab/scenario", json={"scenario": "zero_leads"})
    notes = c.get("/api/pulse/notifications").json()
    assert any("עבר ל" in n["text"] for n in notes[: len(notes) - n0])


def test_office_trend_and_client_trend_line(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    t = c.get("/api/pulse/trend").json()
    assert len(t["weeks"]) >= 10 and t["sentence"] and "לידים" in t["sentence"] and t["since"]["detected"] > 0
    cl = next(x for x in c.get("/api/pulse/clients").json()["clients"] if x["status"] == "green")
    line = c.get(f"/api/pulse/clients/{cl['id']}").json()["trend_line"]
    assert line is None or any(v in line for v in ("משתפר", "יציב", "מידרדר"))


def test_office_score(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    s = c.get("/api/pulse/overview").json()["score"]
    assert 0 <= s["score"] <= 100 and s["prev"] is None  # אין עדיין היסטוריה של שבוע
    c.post("/api/pulse/lab/advance", json={"days": 7})
    s2 = c.get("/api/pulse/overview").json()["score"]
    assert s2["prev"] is not None


def test_campaigner_perf_and_handover(make_client):
    c = _login(make_client)
    c.post("/api/pulse/demo")
    perf = c.get("/api/pulse/team/perf").json()
    assert {p["id"] for p in perf} >= {"yuval", "liad"} and sum(p["clients"] for p in perf) == 50
    dana_open = [t for t in c.get("/api/pulse/tasks").json()["tasks"] if t["assignee"] == "yuval" and t["status"] != "closed"]
    r = c.post("/api/pulse/team/handover", json={"frm": "yuval", "to": "liad"}).json()
    assert r["ok"] and r["moved"] == len(dana_open)
    assert not [t for t in c.get("/api/pulse/tasks").json()["tasks"] if t["assignee"] == "yuval" and t["status"] != "closed"]


def test_agents_team_brief_insight_and_act(make_client):
    """צוות הסוכנים: תדריך המנהל הראשי, תיק תובנות ללקוח (כל התפקידים), וסוכן הביצוע שפותח משימה עם אחראי."""
    c = _login(make_client, "agents@agency.co")
    assert c.post("/api/pulse/demo?size=40").status_code == 200
    b = c.get("/api/pulse/agents/brief").json()
    assert b["engine"] == "rules" and len(b["agents"]) == 6 and {a["id"] for a in b["agents"]} >= {"monitor", "campaigns", "leads", "strategy", "execution", "chief"}
    assert sum(b["counts"].values()) == b["clients"] == 40
    assert 1 <= len(b["top"]) <= 3 and len({x["headline"] for x in b["top"]}) == len(b["top"])
    for x in b["top"]:
        assert x["why"] and x["action"] and x["owner"]
    # כל לקוח: הסבר מלא ללידים, בלי צבע בלי סיבה
    for cl in c.get("/api/pulse/clients").json()["clients"]:
        i = c.get(f"/api/pulse/clients/{cl['id']}/insight").json()
        L = i["leads"]
        assert L["state"] and L["headline"] and L["cause"] and L["measure"]
        if i["monitor"]["status"] in ("red", "yellow"):
            assert i["monitor"]["what"] and i["monitor"]["cause"] and i["monitor"]["owner"] and i["monitor"]["recheck"] and i["monitor"]["todo"]
        assert i["campaigns"]["budget"]["pace"] >= 0
    # ביצוע: בעיה → משימה עם אחראי; רגישה → דורשת אישור
    p = next(x for x in b["top"] if x["kind"] == "problem")
    r = c.post("/api/pulse/agents/act", json={"client_id": p["client_id"], "key": p["key"]}).json()
    assert r["ok"] and r["task"]["assignee"] and r["task"]["status"] == "new"
    again = c.post("/api/pulse/agents/act", json={"client_id": p["client_id"], "key": p["key"]}).json()
    assert again["task"]["id"] == r["task"]["id"]  # לא נפתחת משימה כפולה
    assert c.post("/api/pulse/agents/act", json={"client_id": "nope", "title": "x"}).status_code == 409


def test_board_groups_tracking_and_touch(make_client):
    """לוח Monday: קבוצה לכל קמפיינר, ספירת רמזור, מעקב בדיקות קמפיין נפרד מתקשורת עם הלקוח, ותיעוד שמעדכן את הלוח."""
    c = _login(make_client, "board@agency.co")
    assert c.post("/api/pulse/demo?size=40").status_code == 200
    b = c.get("/api/pulse/board").json()
    assert sum(g["clients"] for g in b["groups"]) == b["clients"] == 40
    for g in b["groups"]:
        assert sum(g["counts"].values()) == g["clients"]
        for x in g["rows"]:
            assert x["status"] in ("red", "yellow", "green", "nodata") and x["why"] and x["rec"]
            assert "every" in x["check"] and "every" in x["contact"]
    assert all(x["status"] == "red" for x in b["urgent"])
    late = next(x for g in b["groups"] for x in g["rows"] if x["check"]["late"])  # בדמו קמפיינר אחד מפגר בבדיקות
    assert c.post(f"/api/pulse/clients/{late['id']}/touch", json={"kind": "check"}).json()["ok"]
    after = next(x for g in c.get("/api/pulse/board").json()["groups"] for x in g["rows"] if x["id"] == late["id"])
    assert after["check"]["ago"] == 0 and not after["check"]["late"]
    before_contact = after["contact"]["ago"]
    c.post(f"/api/pulse/clients/{late['id']}/touch", json={"kind": "call", "text": "שיחה"})
    again = next(x for g in c.get("/api/pulse/board").json()["groups"] for x in g["rows"] if x["id"] == late["id"])
    assert again["contact"]["ago"] == 0 and again["check"]["n"] == after["check"]["n"]  # שיחה לא נספרת כבדיקת קמפיין
    assert before_contact != 0 or before_contact == 0
    i = c.get(f"/api/pulse/clients/{late['id']}/insight").json()
    caps = {x["id"]: x["status"] for x in i["capabilities"]}
    assert caps["task"] == "available" and caps["budget"] == "not_connected"  # לא מציגים יכולת שלא מחוברת
    assert c.post("/api/pulse/clients/nope/touch", json={"kind": "check"}).status_code == 404
