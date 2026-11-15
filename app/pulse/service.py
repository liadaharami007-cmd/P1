"""ClientPulse OS — שכבת התפעול: בדיקה → מחזור חיים של התראה → משימה → אישור → בדיקה חוזרת → הוכחת ערך.

הכול בצד שרת, מסונן לפי account_id. אותה זרימה רצה על נתוני דמו ועל נתונים אמיתיים (CSV / חיבור עתידי).
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from ..db import Database
from . import demo, engine
from .engine import fmt_day, money, pct
from .store import alert_obj, client_obj, exe, j, now, one, rows, task_obj, uj

STATUS = {"new": "חדש", "in_progress": "בטיפול", "awaiting_approval": "ממתין לאישור", "done": "בוצע",
          "awaiting_verification": "ממתין לבדיקה חוזרת", "closed": "נסגר"}
ACTION = {"check": "בדיקה ותיקון", "campaign_change": "שינוי בקמפיין", "budget_change": "שינוי תקציב", "client_message": "הודעה ללקוח"}
SENSITIVE = {"campaign_change", "budget_change", "client_message"}
RULES = [
    {"id": "red_task", "when": "לקוח הופך לאדום", "then": "צור משימה דחופה לאחראי הלקוח", "on": True},
    {"id": "escalate", "when": "התראה פתוחה יום שלם בלי שהתחיל טיפול", "then": "הסלם למנהלים (התראה פנימית)", "on": True},
    {"id": "no_leads_alert", "when": "קמפיין הפסיק להביא לידים", "then": "שלח התראה פנימית מיידית לאחראי", "on": True},
    {"id": "improve_draft", "when": "לקוח השתפר משמעותית", "then": "הכן טיוטת עדכון ללקוח (לאישור) והצע בדיקת הרחבה", "on": True},
    {"id": "recheck", "when": "משימה סומנה כבוצעה", "then": "קבע בדיקה חוזרת אוטומטית לפי מדד ההצלחה", "on": True},
    {"id": "overdue", "when": "משימה עברה את מועד היעד", "then": "התראה פנימית לאחראי ולמנהלים", "on": True},
    {"id": "data_health", "when": "מקור נתונים הפסיק להתעדכן", "then": "צור התראת תקינות נתונים", "on": True},
    {"id": "remind", "when": "יום לפני מועד של התחייבות או משימה", "then": "תזכורת לאחראי במערכת", "on": True},
    {"id": "daily_summary", "when": "תחילת יום (הבדיקה הראשונה ביום)", "then": "הפק סיכום בוקר", "on": True},
    {"id": "weekly_report", "when": "סוף שבוע (שישי)", "then": "הפק דוח ביצועים שבועי למשרד", "on": True},
]
DEFAULT_SETTINGS = {"rules": {r["id"]: r["on"] for r in RULES}, "assumptions": {"minPerClient": 4, "minPerAlert": 8, "workdays": 22},
                    "ops": {}, "improved_seen": {}, "auto_daily": True, "summary_day": None, "weekly_day": None,
                    "last_auto_real_day": None, "demo": False}

_cache: dict[tuple, dict] = {}


# ================================================================ סביבת עבודה
def ws(db: Database, acc: str, user_name: str | None = None) -> dict:
    r = one(db, "SELECT * FROM pulse_workspaces WHERE account_id=?", (acc,))
    if not r:
        exe(db, "INSERT OR IGNORE INTO pulse_workspaces (account_id, settings_json, created_at) VALUES (?,?,?)", (acc, j(DEFAULT_SETTINGS), now()))
        r = one(db, "SELECT * FROM pulse_workspaces WHERE account_id=?", (acc,))
    s = {**DEFAULT_SETTINGS, **uj(r["settings_json"], {})}
    s["rules"] = {**DEFAULT_SETTINGS["rules"], **s.get("rules", {})}
    return {"settings": s, "offset": r["day_offset"], "version": r["data_version"], "last_run": uj(r["last_run_json"])}


def save_settings(db: Database, acc: str, s: dict) -> None:
    exe(db, "UPDATE pulse_workspaces SET settings_json=? WHERE account_id=?", (j(s), acc))


def bump(db: Database, acc: str) -> None:
    exe(db, "UPDATE pulse_workspaces SET data_version=data_version+1 WHERE account_id=?", (acc,))


def ref_day(w: dict) -> int:
    """'היום' של הניתוח = אתמול (יום שלם אחרון) + היסט שעון הדמו (רק במצב דמו)."""
    return engine.today_idx() - 1 + (w["offset"] if w["settings"].get("demo") else 0)


def team(db: Database, acc: str) -> list[dict]:
    return [{**r, "approver": bool(r["approver"])} for r in rows(db, "SELECT * FROM pulse_team WHERE account_id=? ORDER BY rowid", (acc,))]


def team_map(db: Database, acc: str) -> dict:
    return {m["id"]: m for m in team(db, acc)}


def ensure_member(db: Database, acc: str, user: dict, role: str) -> None:
    if not one(db, "SELECT 1 FROM pulse_team WHERE account_id=? AND user_id=?", (acc, user["id"])):
        exe(db, "INSERT OR IGNORE INTO pulse_team (account_id, id, name, role, approver, user_id) VALUES (?,?,?,?,?,?)",
            (acc, "u_" + user["id"][:8], user.get("name") or user["email"].split("@")[0], "בעלים" if role == "owner" else "מנהל" if role == "admin" else "עובד",
             1 if role in ("owner", "admin") else 0, user["id"]))


def ev(db: Database, acc: str, day: int, type_: str, text: str, client_id: str | None = None, user: str | None = None, ref: str | None = None) -> None:
    exe(db, "INSERT INTO pulse_events (account_id, day, t, type, text, client_id, user, ref) VALUES (?,?,?,?,?,?,?,?)",
        (acc, day, now(), type_, text, client_id, user, ref))


def notify(db: Database, acc: str, day: int, text: str, kind: str = "info", route: str | None = None, to: str = "all") -> None:
    exe(db, "INSERT INTO pulse_notifications (account_id, day, t, text, kind, route, to_role) VALUES (?,?,?,?,?,?,?)",
        (acc, day, now(), text, kind, route, to))


# ================================================================ לקוחות ונתונים
def list_clients(db: Database, acc: str) -> list[dict]:
    return [client_obj(r) for r in rows(db, "SELECT * FROM pulse_clients WHERE account_id=? ORDER BY is_demo, rowid", (acc,))]


def get_client(db: Database, acc: str, cid: str) -> dict | None:
    r = one(db, "SELECT * FROM pulse_clients WHERE account_id=? AND id=?", (acc, cid))
    return client_obj(r) if r else None


CLIENT_FIELDS = ("name", "industry", "owner", "target_cpl", "monthly_budget", "fee_monthly", "hours_monthly", "hourly_cost",
                 "other_costs_monthly", "website", "contact_every_days")


def upsert_client(db: Database, acc: str, data: dict, cid: str | None = None) -> dict:
    if cid:
        cur = one(db, "SELECT * FROM pulse_clients WHERE account_id=? AND id=?", (acc, cid))
        if not cur:
            raise KeyError(cid)
        sets = {k: data[k] for k in CLIENT_FIELDS if k in data}
        if "platforms" in data:
            sets["platforms_json"] = j(data["platforms"])
        if "thresholds" in data:
            clean = {k: v for k, v in (data["thresholds"] or {}).items() if k in engine.EDITABLE}
            sets["thresholds_json"] = j(clean)
        if sets:
            exe(db, f"UPDATE pulse_clients SET {', '.join(k + '=?' for k in sets)} WHERE account_id=? AND id=?", (*sets.values(), acc, cid))
    else:
        cid = "m" + uuid.uuid4().hex[:8]
        exe(db, """INSERT INTO pulse_clients (account_id, id, name, industry, owner, target_cpl, monthly_budget, fee_monthly, hours_monthly,
                   hourly_cost, other_costs_monthly, website, platforms_json, thresholds_json, is_demo, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'manual',?)""",
            (acc, cid, data["name"], data.get("industry"), data.get("owner"), data.get("target_cpl"), data.get("monthly_budget"),
             data.get("fee_monthly"), data.get("hours_monthly"), data.get("hourly_cost"), data.get("other_costs_monthly"),
             data.get("website"), j(data.get("platforms") or []), j({}), now()))
    bump(db, acc)
    return get_client(db, acc, cid)  # type: ignore[return-value]


def delete_client(db: Database, acc: str, cid: str) -> None:
    for t in ("pulse_days", "pulse_alerts", "pulse_tasks", "pulse_notes", "pulse_drafts", "pulse_contacts", "pulse_commitments",
              "pulse_status_history", "pulse_decisions"):
        exe(db, f"DELETE FROM {t} WHERE account_id=? AND client_id=?", (acc, cid))
    exe(db, "DELETE FROM pulse_clients WHERE account_id=? AND id=?", (acc, cid))
    bump(db, acc)


def write_days(db: Database, acc: str, cid: str, days: list[dict], source: str, replace_from: str | None = None, replace_to: str | None = None) -> None:
    with db._conn() as c:
        if replace_from:
            c.execute("DELETE FROM pulse_days WHERE account_id=? AND client_id=? AND date BETWEEN ? AND ?", (acc, cid, replace_from, replace_to))
        c.executemany("""INSERT INTO pulse_days (account_id, client_id, date, spend, impressions, clicks, leads, sales, revenue, source)
                         VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id, client_id, date) DO UPDATE SET spend=excluded.spend,
                         impressions=excluded.impressions, clicks=excluded.clicks, leads=excluded.leads, sales=excluded.sales,
                         revenue=excluded.revenue, source=excluded.source""",
                      [(acc, cid, d["date"], d["spend"], d["impressions"], d["clicks"], d["leads"], d.get("sales"), d.get("revenue"), source) for d in days])


ALIASES = {
    "date": ("date", "day", "תאריך", "יום", "reporting starts"),
    "spend": ("spend", "amount spent", "amount spent (ils)", "cost", "הוצאה", "עלות", "סכום שהוצא"),
    "impressions": ("impressions", "impr.", "חשיפות"),
    "clicks": ("clicks", "link clicks", "קליקים", "הקלקות", "הקלקות על קישור"),
    "leads": ("leads", "conversions", "results", "לידים", "המרות", "תוצאות"),
    "sales": ("sales", "deals", "מכירות", "עסקאות"),
    "revenue": ("revenue", "הכנסה", "הכנסות"),
}


def import_csv(db: Database, acc: str, cid: str, text: str) -> dict:
    """ייבוא נתונים אמיתיים (למשל ייצוא יומי מ-Meta Ads Manager / Google Ads). לא ממציא ערכים חסרים."""
    reader = csv.reader(io.StringIO(text.strip().lstrip("﻿")))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return {"imported": 0, "errors": ["הקובץ ריק"]}
    col: dict[str, int] = {}
    for key, names in ALIASES.items():
        for i, h in enumerate(header):
            if h in names:
                col[key] = i
                break
    missing = [k for k in ("date", "spend", "impressions", "clicks", "leads") if k not in col]
    if missing:
        return {"imported": 0, "errors": ["חסרות עמודות חובה: " + ", ".join(missing) + ". נדרש: date, spend, impressions, clicks, leads (sales, revenue אופציונליים)"]}
    out, errors = [], []
    for n, row in enumerate(reader, start=2):
        if not any(x.strip() for x in row):
            continue
        try:
            dt = row[col["date"]].strip()
            engine.day_idx(dt)

            def num(k: str, cast=float):
                v = row[col[k]].replace(",", "").replace("₪", "").strip() if k in col and col[k] < len(row) else ""
                if v == "":
                    return None
                x = cast(float(v))
                if x < 0:
                    raise ValueError(f"ערך שלילי ב-{k}")
                return x
            d = {"date": dt, "spend": num("spend"), "impressions": num("impressions", int), "clicks": num("clicks", int), "leads": num("leads", int),
                 "sales": num("sales", int), "revenue": num("revenue")}
            if None in (d["spend"], d["impressions"], d["clicks"], d["leads"]):
                raise ValueError("ערך חובה ריק")
            out.append(d)
        except (ValueError, IndexError) as e:
            errors.append(f"שורה {n}: {e}")
    if out:
        write_days(db, acc, cid, out, "csv")
        exe(db, "UPDATE pulse_clients SET source='csv' WHERE account_id=? AND id=? AND is_demo=0", (acc, cid))
        bump(db, acc)
    return {"imported": len(out), "errors": errors[:20]}


# ================================================================ דמו
def seed_demo(db: Database, acc: str, owner: str | None = None) -> dict:
    """owner: חבר הצוות של המשתמש המחובר. כשניתן — כל לקוחות הדמו שלו (משרד של אדם אחד, כמו אצל ניב)."""
    w = ws(db, acc)
    s = w["settings"]
    exe(db, "UPDATE pulse_workspaces SET day_offset=0 WHERE account_id=?", (acc,))
    s.update({"demo": True, "ops": {}, "improved_seen": {}, "summary_day": None, "weekly_day": None})
    save_settings(db, acc, s)
    reset_demo_data(db, acc)
    for m in ([] if owner else demo.TEAM):
        exe(db, "INSERT OR IGNORE INTO pulse_team (account_id, id, name, role, approver, is_demo) VALUES (?,?,?,?,?,1)",
            (acc, m["id"], m["name"], m["role"], 1 if m["approver"] else 0))
    w = ws(db, acc)
    T0 = ref_day(w)
    for c in demo.build_clients(T0):
        p = c["params"]
        exe(db, """INSERT OR REPLACE INTO pulse_clients (account_id, id, name, industry, owner, target_cpl, monthly_budget, fee_monthly,
                   hours_monthly, hourly_cost, other_costs_monthly, platforms_json, thresholds_json, is_demo, params_json, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,'demo',?)""",
            (acc, "d" + c["id"], c["name"], c["industry"], owner or c["owner"], c["target_cpl"], c["monthly_budget"], c["fee_monthly"],
             c["hours_monthly"], c["hourly_cost"], c["other_costs_monthly"], j(c["platforms"]), j({}), j(p), now()))
    sync_demo(db, acc)
    _seed_demo_ops(db, acc, T0)
    ev(db, acc, T0, "lab", "סביבת דמו נוצרה: 50 לקוחות מדומים עם 90 ימי היסטוריה")
    return run_check(db, acc, manual=True)


FIRST = ["אורית", "משה", "שירן", "אבי", "מיכל", "רונן", "נועה", "דוד", "הילה", "יוסי", "ליאת", "עמית"]
DEMO_COMMIT = ["לשלוח דוח ביצועים חודשי", "להעלות קריאייטיב חדש לקמפיין", "לבדוק את טופס הלידים באתר", "להציע תקציב לרבעון הבא",
               "להקים קמפיין רימרקטינג", "לתאם פגישת סטטוס"]


def _seed_demo_ops(db: Database, acc: str, T0: int) -> None:
    """נתוני תפעול מדומים (מסומנים דמו דרך הלקוח): אנשי קשר, התחייבויות, שיחות מתועדות, שביעות רצון."""
    cl = rows(db, "SELECT id, owner, name FROM pulse_clients WHERE account_id=? AND is_demo=1 ORDER BY rowid", (acc,))
    for i, c in enumerate(cl):
        exe(db, "INSERT INTO pulse_contacts (account_id, client_id, name, role, phone, email, created_at) VALUES (?,?,?,?,?,?,?)",
            (acc, c["id"], f"{FIRST[i % len(FIRST)]} {c['name'].split()[-1]}", "בעלים" if i % 3 else "מנהלת שיווק",
             f"05{(i * 37) % 10}-{1000000 + i * 7919 % 9000000}", f"contact{i + 1}@example.com", now()))
        exe(db, "UPDATE pulse_clients SET contact_every_days=? WHERE account_id=? AND id=?", (14 if i % 4 == 0 else None, acc, c["id"]))
        if i % 4 != 1:  # שיחה מתועדת אחרונה
            day = T0 - (3 + (i * 5) % 20)
            exe(db, "INSERT INTO pulse_events (account_id, day, t, type, text, client_id, user, ref) VALUES (?,?,?,?,?,?,?,?)",
                (acc, day, now() - (T0 - day) * 86400, "note", "תיעוד שיחה: עדכון שוטף על הקמפיינים", c["id"], "דמו", "call"))
        if i % 3 == 0:
            due = T0 + [5, 2, 1, 0, -2, 9, 4, -5, 3, 12, 6, 1, 8, 15, -1, 7, 10][(i // 3) % 17]
            exe(db, "INSERT INTO pulse_commitments (account_id, client_id, text, owner, due_day, source, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (acc, c["id"], DEMO_COMMIT[i % len(DEMO_COMMIT)], c["owner"], due, "demo", "דמו", now()))
        sat = (2 if i == 8 else 1 if i == 30 else [4, 5, 3, 4, 5][i % 5]) if i % 2 == 0 else None
        if sat:
            exe(db, "UPDATE pulse_clients SET satisfaction=?, satisfaction_day=? WHERE account_id=? AND id=?", (sat, T0 - i % 9, acc, c["id"]))
    bump(db, acc)


def reset_demo_data(db: Database, acc: str) -> None:
    ids = [r["id"] for r in rows(db, "SELECT id FROM pulse_clients WHERE account_id=? AND is_demo=1", (acc,))]
    for cid in ids:
        delete_client(db, acc, cid)
    exe(db, "DELETE FROM pulse_team WHERE account_id=? AND is_demo=1", (acc,))
    for t in ("pulse_events", "pulse_notifications", "pulse_automation_runs", "pulse_verifications", "pulse_seen"):
        exe(db, f"DELETE FROM {t} WHERE account_id=?", (acc,))
    exe(db, "DELETE FROM pulse_tasks WHERE account_id=? AND client_id NOT IN (SELECT id FROM pulse_clients WHERE account_id=?)", (acc, acc))


def remove_demo(db: Database, acc: str) -> None:
    reset_demo_data(db, acc)
    w = ws(db, acc)
    s = w["settings"]
    s.update({"demo": False, "ops": {}})
    save_settings(db, acc, s)
    exe(db, "UPDATE pulse_workspaces SET day_offset=0, last_run_json=NULL WHERE account_id=?", (acc,))
    bump(db, acc)


def sync_demo(db: Database, acc: str, only: str | None = None) -> None:
    """ה'סנכרון' של ספק הדמו: כותב לטבלת הנתונים בדיוק כמו ספק אמיתי."""
    w = ws(db, acc)
    ref = ref_day(w)
    ops = w["settings"].get("ops", {})
    frm, to = engine.iso_of(ref - 89), engine.iso_of(ref)
    for r in rows(db, "SELECT id, params_json FROM pulse_clients WHERE account_id=? AND is_demo=1" + (" AND id=?" if only else ""),
                  (acc, only) if only else (acc,)):
        p = uj(r["params_json"])
        write_days(db, acc, r["id"], demo.gen_days(p, ref - 89, ref, ops.get(r["id"], [])), "demo", frm, to)
    exe(db, "DELETE FROM pulse_days WHERE account_id=? AND source='demo' AND date < ?", (acc, engine.iso_of(ref - 120)))
    bump(db, acc)


# ================================================================ ניתוח (עם מטמון לפי גרסת נתונים)
def analysis(db: Database, acc: str) -> dict:
    w = ws(db, acc)
    ref = ref_day(w)
    key = (db.path, acc, w["version"], ref)
    if key in _cache:
        return _cache[key]
    clients = list_clients(db, acc)
    frm = engine.iso_of(ref - 89)
    by: dict[str, list] = {c["id"]: [] for c in clients}
    for d in rows(db, "SELECT client_id, date, spend, impressions, clicks, leads, sales, revenue FROM pulse_days WHERE account_id=? AND date>=? AND date<=?",
                  (acc, frm, engine.iso_of(ref))):
        if d["client_id"] in by:
            by[d["client_id"]].append(d)
    agency_th = w["settings"].get("thresholds", {})
    for c in clients:  # ספי הסוכנות כברירת מחדל, ספי הלקוח גוברים
        c["thresholds"] = {**agency_th, **(c.get("thresholds") or {})}
    run = engine.analyze_portfolio([(c, by[c["id"]]) for c in clients], ref)
    run["clients"] = {c["id"]: c for c in clients}
    ops_overlay(db, acc, run, ref)
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = run
    return run


# ================================================================ אותות תפעוליים (שיטת יובל: לא רק ביצועי קמפיין)
OPS_TYPES = ("commitment", "contact", "satisfaction")


def _ops_alert(cid: str, type_: str, sev: str, title: str, what: str, numbers: list, why: str, hyp: str, checks: list,
               plan: list, success: str, days: int, period: str, priority_extra: float = 0) -> dict:
    return {"type": type_, "severity": sev, "durationDays": days, "confidence": "גבוהה", "period": period, "title": title, "what": what,
            "numbers": numbers, "why": why, "immediate": sev == "red", "key": f"{cid}:{type_}", "source": "ops",
            "priority": (1000 if sev == "red" else 100) + min(days, 14) * 5 + priority_extra,
            "inv": {"facts": [{"label": n[0], "before": n[1], "after": n[2], "change": None} for n in numbers], "drivers": [],
                    "hypotheses": [{"text": hyp, "evidence": what, "support": "נתמך בנתוני המערכת", "share": 1}], "checks": checks,
                    "plan": plan, "unknown": [], "success": {"text": success, "days": 1}, "engine": "rules"}}


def ops_overlay(db: Database, acc: str, run: dict, ref: int) -> None:
    """מוסיף לכל לקוח אותות שאינם ביצועי פרסום: התחייבויות באיחור, קשר עם הלקוח, שביעות רצון, בעיות חוזרות.
    רק ממידע שקיים במערכת. אין מידע — אין אות (ולא 'ירוק' מומצא)."""
    commits = rows(db, "SELECT * FROM pulse_commitments WHERE account_id=? AND status='open'", (acc,))
    contacts = {r["client_id"]: r["d"] for r in rows(db, "SELECT client_id, MAX(day) d FROM pulse_events WHERE account_id=? AND type='note' AND ref IN ('call','meeting') GROUP BY client_id", (acc,))}
    hist = rows(db, "SELECT key, history_json FROM pulse_alerts WHERE account_id=?", (acc,))
    opened = {}
    for h in hist:
        opened[h["key"]] = sum(1 for e in uj(h["history_json"], []) if e["a"].startswith("זוהתה") and ref - e["day"] <= 60)
    tm = team_map(db, acc)
    for r in run["results"]:
        c = run["clients"][r["id"]]
        add = []
        late = [x for x in commits if x["client_id"] == r["id"] and x["due_day"] < ref]
        if late:
            worst = max(ref - x["due_day"] for x in late)
            first = min(late, key=lambda x: x["due_day"])
            add.append(_ops_alert(r["id"], "commitment", "red" if worst >= 7 else "yellow", "התחייבות ללקוח באיחור",
                                  f"{len(late)} התחייבויות שניתנו ללקוח לא בוצעו בזמן. הוותיקה: \"{first['text']}\" (יעד {fmt_day(first['due_day'])}).",
                                  [["התחייבויות באיחור", "0", str(len(late))], ["ימי איחור מקסימליים", "", str(worst)]],
                                  "הבטחה שלא קוימה פוגעת באמון הלקוח מהר יותר מכל מדד קמפיין.",
                                  "ההתחייבות לא שויכה, נשכחה, או חסום משהו בצד שלנו", ["מי אחראי על ההתחייבות ומה חוסם אותה"],
                                  [{"text": f"להשלים: {first['text']} (אחראי: {(tm.get(first['owner']) or {}).get('name', 'לא שויך')})", "actionType": "check"},
                                   {"text": "לעדכן את הלקוח על מועד חדש", "actionType": "client_message"}],
                                  "כל ההתחייבויות שבאיחור סומנו כבוצעו", worst, "התחייבויות פתוחות"))
        every = c.get("contact_every_days")
        if every:
            last = contacts.get(r["id"])
            gap = ref - last if last is not None else None
            if gap is None or gap > every:
                add.append(_ops_alert(r["id"], "contact", "yellow", "אין קשר עם הלקוח לפי התדירות שנקבעה",
                                      (f"השיחה או הפגישה האחרונה שתועדה היא מלפני {gap} ימים" if gap is not None else "לא תועדה אף שיחה או פגישה") + f", והיעד הוא קשר כל {every} ימים.",
                                      [["ימים מהקשר האחרון", f"עד {every}", str(gap) if gap is not None else "—"]],
                                      "לקוח שלא שומע מאיתנו מרגיש שלא מטפלים בו, גם כשהקמפיינים בסדר.",
                                      "אין שגרת עדכון קבועה ללקוח", ["מתי דיברנו לאחרונה ומה סוכם"],
                                      [{"text": "לקבוע שיחת עדכון עם הלקוח ולתעד אותה בתיק", "actionType": "client_message"}],
                                      "תועדה שיחה או פגישה עם הלקוח", min(gap or 30, 30), f"תדירות קשר: כל {every} ימים"))
        sat = c.get("satisfaction")
        if sat and sat <= 2:
            add.append(_ops_alert(r["id"], "satisfaction", "red" if sat == 1 else "yellow", "שביעות רצון נמוכה",
                                  f"שביעות הרצון שתועדה היא {sat} מתוך 5" + (f" (עודכן {fmt_day(c['satisfaction_day'])})" if c.get("satisfaction_day") else "") + ".",
                                  [["שביעות רצון", "3–5", f"{sat}/5"]], "לקוח לא מרוצה הוא סיכון נטישה, גם כשהמספרים טובים.",
                                  "פער ציפיות, תקשורת או תוצאות", ["מה גרם לחוסר שביעות הרצון לפי השיחה האחרונה"],
                                  [{"text": "שיחת בירור של מנהל הסוכנות עם הלקוח", "actionType": "client_message"}],
                                  "שביעות הרצון עודכנה ל-3 ומעלה", 7, "שביעות רצון מתועדת", 50))
        r["alerts"].extend(add)
        for a in r["alerts"]:
            a["recurring"] = opened.get(a["key"], 0)
        r["alerts"].sort(key=lambda a: -a["priority"])
        if add:
            r["status"] = engine.status_of(r["alerts"], r["lowData"], bool(r["days"]))
            r["health"] = engine.health_score(r)
            r["priority"] = r["alerts"][0]["priority"] + 10 * (len(r["alerts"]) - 1)
    counts = {"green": 0, "yellow": 0, "red": 0, "nodata": 0, "improved": 0}
    for r in run["results"]:
        counts[r["status"]] += 1
        counts["improved"] += 1 if r["improved"] else 0
    run["counts"] = counts
    run["results"].sort(key=lambda r: -r["priority"])


def find_alert(run: dict, key: str) -> dict | None:
    r = run["byId"].get(key.split(":")[0])
    return next((a for a in r["alerts"] if a["key"] == key), None) if r else None


def alert_rows(db: Database, acc: str, client_id: str | None = None) -> dict[str, dict]:
    q, a = "SELECT * FROM pulse_alerts WHERE account_id=?", [acc]
    if client_id:
        q += " AND client_id=?"
        a.append(client_id)
    return {r["key"]: alert_obj(r) for r in rows(db, q, tuple(a))}


# ================================================================ בדיקה מלאה (הלב של המערכת)
RANK = {"red": 2, "yellow": 1}


def run_check(db: Database, acc: str, manual: bool = False, user: str | None = None) -> dict:
    w = ws(db, acc)
    ref = ref_day(w)
    run = analysis(db, acc)
    t = now()
    fresh, cleared = reconcile(db, acc, run, ref, t)
    tm = team_map(db, acc)
    for k, life in fresh:
        a = find_alert(run, k)
        ev(db, acc, ref, "alert", ("החמרה: " if life == "escalated" else "זוהתה חריגה: ") + a["title"], k.split(":")[0], ref=k)
    for k, title in cleared:
        ev(db, acc, ref, "cleared", "החריגה נעלמה, המדדים חזרו לטווח התקין: " + title, k.split(":")[0], ref=k)
    reopen_tasks(db, acc, fresh, ref)
    record_status(db, acc, run, ref, t)
    log = automations(db, acc, run, w, ref, fresh, tm)
    verify_tasks(db, acc, run, ref)
    summary = {"t": t, "day": ref, "ms": run["ms"], "n": len(run["results"]), "new": len(fresh), "cleared": len(cleared),
               "alerts": sum(len(r["alerts"]) for r in run["results"]), "manual": manual, "automations": len(log)}
    exe(db, "UPDATE pulse_workspaces SET last_run_json=? WHERE account_id=?", (j(summary), acc))
    if manual:
        ev(db, acc, ref, "check", f"בדיקה ידנית: {summary['n']} לקוחות נותחו ב-{summary['ms']} מ\"ש, {summary['new']} חריגות חדשות", user=user)
    return summary


STATUS_HE = {"green": "תקין", "yellow": "במעקב", "red": "דחוף", "nodata": "אין מספיק מידע"}


def record_status(db: Database, acc: str, run: dict, ref: int, t: float) -> None:
    last = {r["client_id"]: r["status"] for r in rows(db, """SELECT client_id, status FROM pulse_status_history WHERE id IN
              (SELECT MAX(id) FROM pulse_status_history WHERE account_id=? GROUP BY client_id)""", (acc,))}
    for r in run["results"]:
        prev = last.get(r["id"])
        if prev == r["status"]:
            continue
        reason = (r["alerts"][0]["title"] if r["alerts"] else "אין מספיק נתונים לקביעת מצב" if r["status"] == "nodata"
                  else "כל המדדים בטווח התקין")
        exe(db, "INSERT INTO pulse_status_history (account_id, client_id, day, t, status, prev, reason) VALUES (?,?,?,?,?,?,?)",
            (acc, r["id"], ref, t, r["status"], prev, reason))
        if prev:
            ev(db, acc, ref, "status", f"{r['name']}: {STATUS_HE[prev]} ← {STATUS_HE[r['status']]} ({reason})", r["id"])
            worse = {"green": 0, "nodata": 0, "yellow": 1, "red": 2}
            if worse[r["status"]] > worse[prev]:  # התראה רק כשהמצב משתנה לרעה — פעם אחת, לא כל יום
                notify(db, acc, ref, f"{r['name']} עבר ל{STATUS_HE[r['status']]}: {reason}", "danger" if r["status"] == "red" else "warn", f"client/{r['id']}")


def reconcile(db: Database, acc: str, run: dict, ref: int, t: float) -> tuple[list, list]:
    state = alert_rows(db, acc)
    seen, fresh = set(), []
    for r in run["results"]:
        for a in r["alerts"]:
            k = a["key"]
            seen.add(k)
            s = state.get(k)
            snap = {"cpl": r["rec"]["cpl"], "leads": r["rec"]["leads"], "spend": r["rec"]["spend"]}
            if not s or s["status"] == "cleared":
                hist = (s["history"] if s else []) + [{"day": ref, "t": t, "a": "זוהתה: " + a["title"]}]
                exe(db, """INSERT OR REPLACE INTO pulse_alerts (account_id, key, client_id, type, status, severity, max_severity, first_day, last_day,
                           title, was_yellow_first, first_t, snapshot_json, history_json) VALUES (?,?,?,?, 'open', ?,?,?,?,?,?,?,?,?)""",
                    (acc, k, r["id"], a["type"], a["severity"], a["severity"], ref, ref, a["title"], 1 if a["severity"] == "yellow" else 0, t, j(snap), j(hist)))
                fresh.append((k, "new"))
            else:
                hist, status = s["history"], s["status"]
                if RANK[a["severity"]] > RANK[s["severity"]]:
                    hist.append({"day": ref, "t": t, "a": "החמירה לאדום"})
                    if status in ("resolved", "dismissed"):
                        status = "open"
                    fresh.append((k, "escalated"))
                mx = a["severity"] if RANK[a["severity"]] > RANK[s["max_severity"]] else s["max_severity"]
                exe(db, "UPDATE pulse_alerts SET severity=?, last_day=?, title=?, max_severity=?, status=?, history_json=? WHERE account_id=? AND key=?",
                    (a["severity"], ref, a["title"], mx, status, j(hist), acc, k))
    cleared = []
    for k, s in state.items():
        if k not in seen and s["status"] != "cleared":
            s["history"].append({"day": ref, "t": t, "a": "נעלמה, המדדים חזרו לטווח התקין"})
            exe(db, "UPDATE pulse_alerts SET status='cleared', cleared_day=?, history_json=? WHERE account_id=? AND key=?",
                (ref, j(s["history"]), acc, k))
            cleared.append((k, s["title"]))
    return fresh, cleared


def alert_history_add(db: Database, acc: str, key: str, ref: int, text: str, status: str | None = None) -> None:
    s = one(db, "SELECT history_json, status FROM pulse_alerts WHERE account_id=? AND key=?", (acc, key))
    if not s:
        return
    h = uj(s["history_json"], [])
    h.append({"day": ref, "t": now(), "a": text})
    exe(db, "UPDATE pulse_alerts SET history_json=?, status=? WHERE account_id=? AND key=?", (j(h), status or s["status"], acc, key))


# ================================================================ אוטומציות (תיעוד ריצה + מניעת כפילות + ניסיון חוזר)
def _once(db: Database, acc: str, rule: str, run_key: str, fn, log: list, dry: bool) -> None:
    prev = one(db, "SELECT status, attempts FROM pulse_automation_runs WHERE account_id=? AND run_key=?", (acc, run_key))
    if prev and (prev["status"] == "ok" or prev["attempts"] >= 3):
        return
    if dry:
        log.append({"rule": rule, "key": run_key, "would": fn(True)})
        return
    try:
        detail = fn(False)
        status = "ok"
    except Exception as e:  # noqa: BLE001 — כישלון מתועד ויורץ שוב בבדיקה הבאה (עד 3 ניסיונות)
        detail, status = f"נכשל: {type(e).__name__}: {e}", "failed"
    if prev:
        exe(db, "UPDATE pulse_automation_runs SET status=?, detail=?, attempts=attempts+1, created_at=? WHERE account_id=? AND run_key=?",
            (status, detail, now(), acc, run_key))
    else:
        exe(db, "INSERT INTO pulse_automation_runs (account_id, rule_id, run_key, status, detail, created_at) VALUES (?,?,?,?,?,?)",
            (acc, rule, run_key, status, detail, now()))
    log.append({"rule": rule, "key": run_key, "status": status, "detail": detail})


def automations(db: Database, acc: str, run: dict, w: dict, ref: int, fresh: list, tm: dict, dry: bool = False, only: str | None = None) -> list:
    rules = w["settings"]["rules"]
    log: list = []
    on = lambda rid: (rules.get(rid) or dry) and (only is None or only == rid)  # noqa: E731
    alerts = alert_rows(db, acc)
    fresh_keys = {k for k, _ in fresh}

    def name_of(mid: str | None) -> str:
        return (tm.get(mid) or {}).get("name", mid or "—")
    for r in run["results"]:
        for a in r["alerts"]:
            k = a["key"]
            st = alerts.get(k, {})
            # משימה אחת ללקוח: רק להתראה האדומה החשובה ביותר שלו, ורק אם אין לו כבר משימה פתוחה (מונע כפילויות)
            top_red = next((x for x in r["alerts"] if x["severity"] == "red"), None)
            if (on("red_task") and top_red is a and (k in fresh_keys or dry) and not open_task_for(db, acc, k)
                    and not one(db, "SELECT 1 FROM pulse_tasks WHERE account_id=? AND client_id=? AND status!='closed'", (acc, r["id"]))):
                def mk(d: bool, r=r, k=k, a=a):
                    if d:
                        return f"תיווצר משימה ל{name_of(r['owner'])}: {a['title']} · {r['name']}"
                    t = create_task(db, acc, run, k, by="auto")
                    return f"נוצרה משימה ל{name_of(t['assignee'])}: {t['title']}"
                _once(db, acc, "red_task", f"red_task:{k}:{st.get('first_day', ref)}", mk, log, dry)
            if on("no_leads_alert") and a["type"] == "no_leads" and (k in fresh_keys or dry):
                def nl(d: bool, r=r, a=a):
                    if d:
                        return f"התראה פנימית ל{name_of(r['owner'])}: {a['title']} · {r['name']}"
                    notify(db, acc, ref, f"קמפיין הפסיק להביא לידים · {r['name']}: {a['what']}", "danger", f"client/{r['id']}")
                    return "נשלחה התראה פנימית"
                _once(db, acc, "no_leads_alert", f"no_leads:{k}:{st.get('first_day', ref)}", nl, log, dry)
            if on("data_health") and a["type"] == "data":
                def dh(d: bool, r=r, a=a):
                    if d:
                        return f"התראת תקינות נתונים: {r['name']}"
                    notify(db, acc, ref, f"תקינות נתונים: {r['name']} — {a['title']}", "warn", f"client/{r['id']}")
                    return "נוצרה התראת תקינות"
                _once(db, acc, "data_health", f"data:{k}:{st.get('first_day', ref)}", dh, log, dry)
    if on("escalate"):
        for k, s in alerts.items():
            t = open_task_for(db, acc, k)
            started = t and t["status"] not in ("new",)
            if s["status"] in ("open",) and ref - s["first_day"] >= 1 and not started and not s.get("escalated_day"):
                cl = run["byId"].get(s["client_id"])
                if not cl:
                    continue

                def esc(d: bool, s=s, cl=cl, k=k):
                    txt = f"הסלמה: \"{s['title']}\" אצל {cl['name']} פתוחה {ref - s['first_day']} ימים ועדיין לא התחיל טיפול"
                    if d:
                        return txt
                    notify(db, acc, ref, txt, "escalation", f"client/{cl['id']}", "approvers")
                    exe(db, "UPDATE pulse_alerts SET escalated_day=? WHERE account_id=? AND key=?", (ref, acc, k))
                    alert_history_add(db, acc, k, ref, "הוסלמה למנהלים")
                    return txt
                _once(db, acc, "escalate", f"escalate:{k}:{s['first_day']}", esc, log, dry)
    if on("improve_draft"):
        seen = w["settings"].get("improved_seen", {})
        for r in run["results"]:
            if r["improved"] and not (seen.get(r["id"]) and ref - seen[r["id"]] < 14):
                def imp(d: bool, r=r):
                    txt = (f"היי, עדכון קצר על הקמפיינים: ב-7 הימים האחרונים העלות לליד ירדה ב-{abs(pct(r['improved']['change']))}% "
                           f"({money(r['base']['cpl'])} ← {money(r['rec']['cpl'])}) ונכנסו {r['rec']['leads']} לידים. נמשיך לעקוב ונעדכן.")
                    if d:
                        return "תוכן טיוטה: " + txt
                    exe(db, "INSERT INTO pulse_drafts (account_id, client_id, day, kind, channel, text, created_at) VALUES (?,?,?,?,?,?,?)",
                        (acc, r["id"], ref, "improvement", "WhatsApp", txt, now()))
                    notify(db, acc, ref, f"טיוטת עדכון ללקוח מוכנה: {r['name']} (שיפור). אפשר גם לבחון הרחבת פעילות.", "success", f"client/{r['id']}")
                    s2 = ws(db, acc)["settings"]
                    s2.setdefault("improved_seen", {})[r["id"]] = ref
                    save_settings(db, acc, s2)
                    return f"הוכנה טיוטת עדכון ל{r['name']}"
                _once(db, acc, "improve_draft", f"improve:{r['id']}:{ref}", imp, log, dry)
    if on("overdue"):
        for t in open_tasks(db, acc):
            if t["status"] in ("new", "in_progress", "awaiting_approval") and t["due_day"] is not None and t["due_day"] < ref:
                def od(d: bool, t=t):
                    txt = f"משימה באיחור ({ref - t['due_day']} ימים): {t['title']} · {name_of(t['assignee'])}"
                    if d:
                        return txt
                    notify(db, acc, ref, txt, "warn", f"task/{t['id']}")
                    exe(db, "UPDATE pulse_tasks SET overdue_notified=? WHERE id=?", (ref, t["id"]))
                    return txt
                _once(db, acc, "overdue", f"overdue:{t['id']}:{ref}", od, log, dry)
    if on("remind"):
        for cm in rows(db, "SELECT * FROM pulse_commitments WHERE account_id=? AND status='open' AND due_day=?", (acc, ref + 1)):
            def rm(d: bool, cm=cm):
                txt = f"תזכורת: מחר יעד להתחייבות \"{cm['text']}\" · {(run['byId'].get(cm['client_id']) or {}).get('name', '')} · {name_of(cm['owner'])}"
                if d:
                    return txt
                notify(db, acc, ref, txt, "info", f"client/{cm['client_id']}")
                return txt
            _once(db, acc, "remind", f"remind:c{cm['id']}:{ref}", rm, log, dry)
        for t in open_tasks(db, acc):
            if t["due_day"] == ref + 1 and t["status"] in ("new", "in_progress"):
                def rt(d: bool, t=t):
                    txt = f"תזכורת: מחר יעד למשימה \"{t['title']}\" · {name_of(t['assignee'])}"
                    if d:
                        return txt
                    notify(db, acc, ref, txt, "info", f"task/{t['id']}")
                    return txt
                _once(db, acc, "remind", f"remind:t{t['id']}:{ref}", rt, log, dry)
    if on("daily_summary"):
        def ds(d: bool):
            txt = summary_text(db, acc, run)["plain"]
            if d:
                return "סיכום בוקר: " + txt[:140] + "…"
            notify(db, acc, ref, txt, "summary", "home")
            return "נוצר סיכום בוקר"
        _once(db, acc, "daily_summary", f"summary:{ref}", ds, log, dry)
    if on("weekly_report") and _weekday(ref) == 4:  # שישי
        def wr(d: bool):
            if d:
                return "יופק דוח שבועי למשרד"
            imp = impact(db, acc)
            notify(db, acc, ref, f"הדוח השבועי מוכן: {imp['detected']} חריגות זוהו, {imp['verified']} טופלו ואומתו בנתונים.", "summary", "reports")
            return "הופק דוח שבועי"
        _once(db, acc, "weekly_report", f"weekly:{ref}", wr, log, dry)
    for x in log:
        if x.get("status") == "ok":
            cid = None
            ev(db, acc, ref, "automation", f"[{rule_name(x['rule'])}] {x['detail']}", cid)
    return log


def _weekday(idx: int) -> int:
    return (idx + 3) % 7  # 1.1.1970 היה יום חמישי → 0=שני ... 4=שישי


def rule_name(rid: str) -> str:
    return next((r["when"] for r in RULES if r["id"] == rid), rid)


def dry_run(db: Database, acc: str, rule: str) -> list:
    w = ws(db, acc)
    return automations(db, acc, analysis(db, acc), w, ref_day(w), [], team_map(db, acc), dry=True, only=rule)


# ================================================================ משימות
def open_tasks(db: Database, acc: str) -> list[dict]:
    return [task_obj(r) for r in rows(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND status!='closed' ORDER BY created_at DESC", (acc,))]


def all_tasks(db: Database, acc: str, client_id: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM pulse_tasks WHERE account_id=?", [acc]
    if client_id:
        q += " AND client_id=?"
        a.append(client_id)
    return [task_obj(r) for r in rows(db, q + " ORDER BY created_at DESC", tuple(a))]


def get_task(db: Database, acc: str, tid: str) -> dict | None:
    r = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND id=?", (acc, tid))
    return task_obj(r) if r else None


def open_task_for(db: Database, acc: str, key: str) -> dict | None:
    r = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND alert_key=? AND status!='closed'", (acc, key))
    return task_obj(r) if r else None


def _save_task(db: Database, t: dict) -> None:
    exe(db, "UPDATE pulse_workspaces SET data_version=data_version+1 WHERE account_id=(SELECT account_id FROM pulse_tasks WHERE id=?)", (t["id"],))
    exe(db, """UPDATE pulse_tasks SET status=?, assignee=?, approved_by=?, due_day=?, done_day=?, recheck_day=?, closed_day=?,
               verification_json=?, history_json=?, minutes_spent=?, requires_approval=? WHERE id=?""",
        (t["status"], t["assignee"], t["approved_by"], t["due_day"], t["done_day"], t["recheck_day"], t["closed_day"],
         j(t["verification"]) if t["verification"] else None, j(t["history"]), t["minutes_spent"], 1 if t["requires_approval"] else 0, t["id"]))


def _th(t: dict, ref: int, who: str, a: str) -> None:
    t["history"].append({"day": ref, "t": now(), "who": who, "a": a})


def create_task(db: Database, acc: str, run: dict, key: str, by: str = "auto", assignee: str | None = None, by_name: str | None = None) -> dict:
    ex = open_task_for(db, acc, key)
    if ex:
        return ex
    r, a = run["byId"].get(key.split(":")[0]), find_alert(run, key)
    if not r or not a:
        raise KeyError("ההתראה כבר לא פעילה")
    ref = run["ref"]
    inv = engine.investigate(r, a)
    tm = team_map(db, acc)
    who = assignee if assignee in tm else (r["owner"] if r["owner"] in tm else next(iter(tm), None))
    t = {"id": "t" + uuid.uuid4().hex[:10], "history": []}
    _th(t, ref, "אוטומציה" if by == "auto" else (by_name or "משתמש"), "נוצרה משימה" + (" (כלל: לקוח הופך לאדום)" if by == "auto" else ""))
    needs = any(p["actionType"] in SENSITIVE for p in inv["plan"])
    exe(db, """INSERT INTO pulse_tasks (id, account_id, client_id, alert_key, title, severity, description, plan_json, success_json,
               requires_approval, assignee, due_day, status, created_by, created_day, before_json, history_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?,?,?,?,?)""",
        (t["id"], acc, r["id"], key, f"{a['title']} · {r['name']}", a["severity"],
         ("השערה מובילה: " + inv["hypotheses"][0]["text"] + ".") if inv["hypotheses"] else "", j(inv["plan"]), j(inv["success"]),
         1 if needs else 0, who, ref + (1 if a["severity"] == "red" else 3), by, ref,
         j({"cpl": r["rec"]["cpl"], "leads": r["rec"]["leads"], "spend": r["rec"]["spend"], "dailyLeads": r["rec"]["dailyLeads"]}),
         j(t["history"]), now()))
    alert_history_add(db, acc, key, ref, f"נפתחה משימה ל{(tm.get(who) or {}).get('name', '—')}")
    ev(db, acc, ref, "task", f"נוצרה משימה: {a['title']} · {r['name']} (אחראי: {(tm.get(who) or {}).get('name', '—')})", r["id"], by_name, t["id"])
    return get_task(db, acc, t["id"])  # type: ignore[return-value]


def create_manual_task(db: Database, acc: str, client_id: str, title: str, assignee: str | None, due_days: int, by_name: str,
                       source: str = "manual") -> dict:
    """משימה שלא נולדה מהתראה (הזדמנות / בקשת לקוח). נסגרת כשמסמנים בוצע — אין מדד לבדיקה חוזרת."""
    c = get_client(db, acc, client_id)
    if not c:
        raise KeyError("לקוח לא נמצא")
    ref = ref_day(ws(db, acc))
    tm = team_map(db, acc)
    who = assignee if assignee in tm else (c["owner"] if c["owner"] in tm else next(iter(tm), None))
    t = {"id": "t" + uuid.uuid4().hex[:10], "history": []}
    _th(t, ref, by_name, "נוצרה משימה" + (" מהזדמנות" if source == "opportunity" else ""))
    exe(db, """INSERT INTO pulse_tasks (id, account_id, client_id, alert_key, title, severity, description, plan_json, success_json,
               requires_approval, assignee, due_day, status, created_by, created_day, before_json, history_json, created_at)
               VALUES (?,?,?,NULL,?,?,?,?,NULL,0,?,?, 'new', ?,?,NULL,?,?)""",
        (t["id"], acc, client_id, f"{title} · {c['name']}", "imp" if source == "opportunity" else "yellow", "", j([{"text": title, "actionType": "check"}]),
         who, ref + max(1, min(30, due_days)), by_name, ref, j(t["history"]), now()))
    ev(db, acc, ref, "task", f"נוצרה משימה: {title} · {c['name']} (אחראי: {(tm.get(who) or {}).get('name', '—')})", client_id, by_name, t["id"])
    return get_task(db, acc, t["id"])  # type: ignore[return-value]


def proposal_draft(db: Database, acc: str, client_id: str, kind: str, user_name: str) -> dict:
    run = analysis(db, acc)
    r = run["byId"].get(client_id)
    if not r:
        raise KeyError("לקוח לא נמצא")
    op = next((o for o in engine.opportunities(r, run["clients"][client_id]) if o["kind"] == kind), None)
    if not op:
        raise KeyError("ההזדמנות כבר לא קיימת בנתונים")
    txt = (f"שלום, רצינו לשתף תובנה מהנתונים של {r['name']}:\n{op['evidence']}\n\nההצעה שלנו: {op['action']}."
           + (f"\n{op['potential']}." if op.get("potential") else "") + "\nנשמח לתאם שיחה קצרה כדי לסגור את הפרטים.")
    ref = run["ref"]
    exe(db, "INSERT INTO pulse_drafts (account_id, client_id, day, kind, channel, text, created_at) VALUES (?,?,?,?,?,?,?)",
        (acc, client_id, ref, "proposal", "Email / WhatsApp", txt, now()))
    ev(db, acc, ref, "note", f"הוכנה טיוטת הצעה: {op['title']}", client_id, user_name)
    return {"ok": True, "text": txt, "msg": "טיוטת ההצעה נשמרה בתיק הלקוח (לא נשלחה)"}


def task_action(db: Database, acc: str, tid: str, action: str, *, user_name: str, can_approve: bool, extra: Any = None) -> dict:
    t = get_task(db, acc, tid)
    if not t:
        raise KeyError(tid)
    w = ws(db, acc)
    ref = ref_day(w)
    st = t["status"]
    tm = team_map(db, acc)

    def go(ns: str, msg: str) -> dict:
        t["status"] = ns
        _th(t, ref, user_name, msg)
        _save_task(db, t)
        ev(db, acc, ref, "task", f"{msg}: {t['title']}", t["client_id"], user_name, t["id"])
        return {"ok": True, "msg": msg}
    if action == "start" and st == "new":
        alert_history_add(db, acc, t["alert_key"], ref, f"{user_name} התחיל/ה טיפול", "in_progress")
        return go("in_progress", "התחיל/ה טיפול")
    if action == "submit" and st == "in_progress":
        if t["requires_approval"] and not t["approved_by"]:
            kinds = ", ".join(ACTION[p["actionType"]] for p in t["plan"] if p["actionType"] in SENSITIVE)
            if can_approve:  # מי שמגיש הוא גם המאשר (בעלים / מנהל): מתועד כהחלטה, בלי לחכות לעצמו
                t["approved_by"] = user_name
                _decision(db, acc, t, "approve", user_name, ref, kinds)
                _th(t, ref, user_name, f"ביצע/ה ואישר/ה בעצמו ({kinds})")
                return _mark_done(db, acc, t, user_name, ref, w)
            return go("awaiting_approval", f"הוגש לאישור (הפעולה כוללת {kinds})")
        return _mark_done(db, acc, t, user_name, ref, w)
    if action == "approve" and st == "awaiting_approval":
        if not can_approve:
            return {"ok": False, "msg": "רק בעלים או מנהל בחשבון יכולים לאשר פעולה שמשנה קמפיין, תקציב או שולחת הודעה ללקוח"}
        t["approved_by"] = user_name
        _decision(db, acc, t, "approve", user_name, ref, "; ".join(p["text"] for p in t["plan"] if p["actionType"] in SENSITIVE))
        _th(t, ref, user_name, "אישר/ה את הפעולה. הביצוע בחשבון המודעות ידני — Meta / Google לא מחוברים")
        return _mark_done(db, acc, t, user_name, ref, w)
    if action == "reject" and st == "awaiting_approval":
        if not can_approve:
            return {"ok": False, "msg": "אין הרשאה לדחות"}
        _decision(db, acc, t, "reject", user_name, ref, str(extra) if extra else None)
        return go("in_progress", "הוחזר לטיפול ללא אישור" + (f": {extra}" if extra else ""))
    if action == "reassign" and st != "closed":
        if extra not in tm:
            return {"ok": False, "msg": "עובד לא קיים"}
        t["assignee"] = extra
        return go(st, f"הועבר ל{tm[extra]['name']}")
    if action == "log_time" and st != "closed":
        try:
            m = max(1, min(600, int(extra)))
        except (TypeError, ValueError):
            return {"ok": False, "msg": "מספר דקות לא תקין"}
        t["minutes_spent"] += m
        return go(st, f"תועדו {m} דקות עבודה")
    if action == "reopen" and st == "closed":
        return go("in_progress", "נפתחה מחדש")
    if action == "recheck_now" and st == "awaiting_verification":
        if ref < (t["recheck_day"] or 0):
            return {"ok": False, "msg": f"מוקדם מדי: הבדיקה החוזרת צריכה נתונים עד {fmt_day(t['recheck_day'])} (עוד {t['recheck_day'] - ref} ימים). בסביבת הדמו אפשר לקדם את השעון."}
        verify_tasks(db, acc, analysis(db, acc), ref, only=t["id"])
        t2 = get_task(db, acc, tid)
        return {"ok": True, "msg": "הבדיקה החוזרת בוצעה: " + ("הבעיה נפתרה ואומתה" if t2["status"] == "closed" else "המדד עדיין לא חזר ליעד")}
    return {"ok": False, "msg": f"הפעולה לא זמינה בסטטוס \"{STATUS.get(st, st)}\""}


def _decision(db: Database, acc: str, t: dict, decision: str, by: str, ref: int, rationale: str | None) -> None:
    exe(db, "INSERT INTO pulse_decisions (account_id, client_id, task_id, title, decision, by_name, rationale, day, t) VALUES (?,?,?,?,?,?,?,?,?)",
        (acc, t["client_id"], t["id"], t["title"], decision, by, rationale, ref, now()))


def _mark_done(db: Database, acc: str, t: dict, user_name: str, ref: int, w: dict) -> dict:
    t["done_day"], t["status"] = ref, "done"
    if not t.get("success"):  # משימה ידנית / הזדמנות: אין מדד לאימות
        t["status"], t["closed_day"] = "closed", ref
        _th(t, ref, user_name, "בוצע ונסגר")
        _save_task(db, t)
        ev(db, acc, ref, "task", f"בוצע: {t['title']}", t["client_id"], user_name, t["id"])
        return {"ok": True, "msg": "בוצע ונסגר"}
    _th(t, ref, user_name, "סומן כבוצע. הבעיה לא נסגרת עד שהמדדים יאשרו")
    if w["settings"]["rules"].get("recheck"):
        t["status"] = "awaiting_verification"
        t["recheck_day"] = ref + t["success"]["days"]
        _th(t, ref, "אוטומציה", f"נקבעה בדיקה חוזרת ל-{fmt_day(t['recheck_day'])} (מדד: {t['success']['text']})")
    _save_task(db, t)
    alert_history_add(db, acc, t["alert_key"], ref, "טופל — ממתין לאימות בנתונים", "in_progress")
    ev(db, acc, ref, "task", f"בוצע: {t['title']}", t["client_id"], user_name, t["id"])
    msg = f"סומן כבוצע. בדיקה חוזרת ב-{fmt_day(t['recheck_day'])}" if t["status"] == "awaiting_verification" else "סומן כבוצע"
    return {"ok": True, "msg": msg}


def verify_tasks(db: Database, acc: str, run: dict, ref: int, only: str | None = None) -> None:
    for t in open_tasks(db, acc):
        if (t["status"] != "awaiting_verification" or not t["alert_key"] or ref < (t["recheck_day"] or 0)
                or (only and t["id"] != only)):
            continue
        r = run["byId"].get(t["client_id"])
        if not r:
            continue
        kind = t["alert_key"].split(":")[1]
        if kind in OPS_TYPES:  # אות תפעולי: הצליח אם האות כבר לא קיים
            res = {"ok": not any(a["type"] == kind for a in r["alerts"]), "cpl": None, "leads": r["rec"]["leads"], "days": ref - t["done_day"]}
        else:
            res = engine.eval_success(r, kind, t["success"], t["done_day"], ref)
        exe(db, "UPDATE pulse_decisions SET outcome=? WHERE account_id=? AND task_id=? AND decision='approve'",
            ("אומת בנתונים" if res["ok"] else "הבדיקה החוזרת נכשלה", acc, t["id"]))
        t["verification"] = {"day": ref, "ok": res["ok"], "before": t["before"], "after": res}
        if res["ok"]:
            t["status"], t["closed_day"] = "closed", ref
            extra = f" (עלות לליד {money(t['before'].get('cpl') or 0)} ← {money(res['cpl'])})" if res.get("cpl") and t["before"].get("cpl") else ""
            _th(t, ref, "בדיקה חוזרת", f"אומת בנתונים: {t['success']['text']}{extra}. המשימה נסגרה")
            s = one(db, "SELECT status, first_day FROM pulse_alerts WHERE account_id=? AND key=?", (acc, t["alert_key"]))
            if s:
                alert_history_add(db, acc, t["alert_key"], ref, "נפתרה ואומתה בנתונים", "cleared" if s["status"] == "cleared" else "resolved")
            ev(db, acc, ref, "verified", f"אומת: הבעיה נפתרה · {t['title']}", t["client_id"], ref=t["id"])
            exe(db, """INSERT INTO pulse_verifications (account_id, task_id, title, client_id, day, ok, before_json, after_json, detected_day)
                       VALUES (?,?,?,?,?,1,?,?,?)""", (acc, t["id"], t["title"], t["client_id"], ref, j(t["before"]), j(res), s["first_day"] if s else None))
        else:
            t["status"] = "in_progress"
            what = f"עלות לליד {money(res['cpl'])}" if res.get("cpl") else f"{res['leads']} לידים"
            _th(t, ref, "בדיקה חוזרת", f"הפעולה בוצעה, אבל המדד עדיין לא חזר ליעד ({what}). נדרשת פעולה נוספת")
            ev(db, acc, ref, "verify_failed", f"בדיקה חוזרת נכשלה: {t['title']}", t["client_id"], ref=t["id"])
            notify(db, acc, ref, f"בדיקה חוזרת: הבעיה עדיין קיימת · {t['title']}", "warn", f"task/{t['id']}")
        _save_task(db, t)


def reopen_tasks(db: Database, acc: str, fresh: list, ref: int) -> None:
    for k, _ in fresh:
        r = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND alert_key=? AND status='closed' AND ?-closed_day<=21 ORDER BY closed_day DESC",
                (acc, k, ref))
        if r and not open_task_for(db, acc, k):
            t = task_obj(r)
            t["status"], t["approved_by"] = "new", None
            _th(t, ref, "מערכת", "נפתחה מחדש: הבעיה חזרה")
            _save_task(db, t)
            ev(db, acc, ref, "task", f"משימה נפתחה מחדש, הבעיה חזרה: {t['title']}", t["client_id"], ref=t["id"])


def alert_feedback(db: Database, acc: str, key: str, verdict: str, user_name: str) -> dict:
    """משוב על התראה: 'useful' או 'false_positive' (סוגר אותה כ-dismissed עד שתחמיר). משמש למדידת התראות שווא."""
    if verdict not in ("useful", "false_positive"):
        return {"ok": False, "msg": "משוב לא תקין"}
    s = one(db, "SELECT status FROM pulse_alerts WHERE account_id=? AND key=?", (acc, key))
    if not s:
        return {"ok": False, "msg": "התראה לא נמצאה"}
    ref = ref_day(ws(db, acc))
    exe(db, "UPDATE pulse_alerts SET feedback=? WHERE account_id=? AND key=?", (verdict, acc, key))
    if verdict == "false_positive":
        alert_history_add(db, acc, key, ref, f"{user_name} סימן/ה כהתראת שווא", "dismissed")
        t = open_task_for(db, acc, key)
        if t:
            t["status"], t["closed_day"] = "closed", ref
            _th(t, ref, user_name, "נסגרה: ההתראה סומנה כהתראת שווא")
            _save_task(db, t)
    else:
        alert_history_add(db, acc, key, ref, f"{user_name} סימן/ה שההתראה מועילה")
    return {"ok": True, "msg": "תודה — המשוב נשמר" + (" וההתראה הושתקה עד שתחמיר" if verdict == "false_positive" else "")}


# ================================================================ סיכום · פעולות היום
def summary_text(db: Database, acc: str, run: dict) -> dict:
    res = run["results"]
    red = [r for r in res if r["status"] == "red"]
    trend = [r for r in res if any(a["type"] == "trend" for a in r["alerts"])]
    imp = [r for r in res if r["improved"]]
    top = top_actions(db, acc, run, 3)
    plain = (f"נמצאו {len(red)} לקוחות שדורשים טיפול, {len(trend)} במגמת הידרדרות מתמשכת ו-{len(imp)} שהשתפרו משמעותית."
             + (f" ההוצאה העודפת המשוערת מחריגות בשבוע האחרון: {money(run['excess'])}." if run["excess"] > 0 else "")
             + (" הפעולות החשובות להיום: " + " ".join(f"{i + 1}. {x['text']}" for i, x in enumerate(top)) if top else ""))
    parts = [{"t": "נמצאו "}, {"t": f"{len(red)} לקוחות שדורשים טיפול", "route": "clients?f=red"}, {"t": ", "},
             {"t": f"{len(trend)} במגמת הידרדרות", "route": "clients?f=yellow"}, {"t": " ו-"},
             {"t": f"{len(imp)} שהשתפרו משמעותית", "route": "clients?f=improved"}, {"t": "."}]
    return {"plain": plain, "parts": parts, "top": top}


SEV = {"red": "דחוף (אדום)", "yellow": "דורש מעקב (צהוב)"}


def alert_card(db: Database, acc: str, run: dict, r: dict, a: dict, st: dict | None, t: dict | None, tm: dict) -> dict:
    """כרטיס חריגה בדיוק לפי הדרישה של יובל: מה קרה · מתי התחיל · מה השתנה · חומרה · נתונים תומכים · הסברים · מה לבדוק ·
    הפעולה הבאה · מי אחראי · האם טופל · האם השתפר. כל שדה מחושב מנתונים / מצב אמיתי במערכת."""
    st = st or {}
    if not t:  # גם משימה שכבר נסגרה — כדי לענות "האם השתפר"
        row = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND alert_key=? ORDER BY created_at DESC LIMIT 1", (acc, a["key"]))
        if not row:  # חריגה משנית אצל לקוח שכבר יש לו משימה פתוחה — מטופלת במסגרתה (אוטומציה פותחת משימה אחת ללקוח)
            row = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND client_id=? AND status!='closed' AND alert_key IS NOT NULL ORDER BY created_at LIMIT 1",
                      (acc, r["id"]))
        t = task_obj(row) if row else None
    inv = engine.investigate(r, a)
    ref = run["ref"]
    first = st.get("first_day", ref)
    big = sorted([f for f in inv["facts"] if f["change"] is not None], key=lambda f: -abs(f["change"]))[:3]
    owner = (t or {}).get("assignee") or r["owner"]
    if not t:
        handled = "לא — עדיין לא נפתחה משימה"
    else:
        handled = {"new": "עוד לא — משימה פתוחה, הטיפול לא התחיל", "in_progress": "בטיפול עכשיו",
                   "awaiting_approval": "טופל — ממתין לאישור מנהל", "awaiting_verification": "כן — טופל",
                   "done": "כן — טופל", "closed": "כן — טופל ונסגר"}.get(t["status"], t["status"])
    v = (t or {}).get("verification")
    if t and t["status"] == "awaiting_verification":
        improved = f"נבדק אוטומטית ב-{fmt_day(t['recheck_day'])} (מדד: {t['success']['text']})"
    elif v:
        improved = ("כן — אומת בנתונים" if v["ok"] else "לא — הבדיקה החוזרת הראתה שהבעיה עדיין קיימת")
    else:
        improved = "עוד אין מה למדוד — הטיפול לא בוצע"
    return {
        "key": a["key"], "client_id": r["id"], "client": r["name"], "is_demo": r["is_demo"], "severity": a["severity"], "title": a["title"],
        "what": a["what"], "started": first, "started_label": fmt_day(first), "days_open": ref - first, "period": a["period"],
        "changed": [f"{f['label']}: {f['before']} ← {f['after']} ({'+' if f['change'] > 0 else ''}{round(f['change'] * 100)}%)" for f in big],
        "severity_label": SEV[a["severity"]] + f" · ביטחון {a['confidence']}",
        "evidence": [" ".join(x for x in n if x) for n in a["numbers"]] + [a["why"]],
        "explanations": [h["text"] + f" ({h['support']})" for h in inv["hypotheses"][:3]],
        "check": inv["checks"][:3], "next": inv["plan"][0]["text"] if inv["plan"] else "—",
        "owner": owner, "owner_name": (tm.get(owner) or {}).get("name", "לא שויך"),
        "handled": handled, "improved": improved, "potential": (r.get("recovery") or {}).get("text"), "potential_leads": (r.get("recovery") or {}).get("leads_week"), "task_id": (t or {}).get("id"), "task_status": (t or {}).get("status"),
        "late": bool(t and t.get("due_day") is not None and t["due_day"] < ref and t["status"] in ("new", "in_progress", "awaiting_approval")),
        "priority": a["priority"]}


def suggestion(r: dict, client: dict) -> dict | None:
    """לירוקים (ולמי שאין לו מספיק מידע): מה אפשר להציע או לשפר. מבוסס נתונים בלבד."""
    if r["status"] == "nodata":
        return {"text": "חסרים נתונים כדי לקבוע מצב — לבדוק שהנתונים מתעדכנים", "kind": "data"}
    if r["status"] != "green":
        return None
    ops = engine.opportunities(r, client)
    if ops:
        return {"text": ops[0]["title"], "kind": ops[0]["kind"], "action": ops[0]["action"]}
    tgt, rc = (r.get("goals") or {}).get("targetCpl"), r["rec"]["cpl"]
    if tgt and rc and rc <= tgt * 0.9:
        return {"text": f"העלות לליד {round((1 - rc / tgt) * 100)}% מתחת ליעד — אפשר להציע ללקוח הגדלת תקציב הדרגתית", "kind": "scale",
                "action": "להציע ללקוח הגדלת תקציב של 10–20% לשבועיים"}
    return {"text": "יציב — אין צורך בפעולה כרגע", "kind": "keep"}


def alert_board(db: Database, acc: str) -> dict:
    run = analysis(db, acc)
    states = alert_rows(db, acc)
    tasks = {t["alert_key"]: t for t in open_tasks(db, acc)}
    tm = team_map(db, acc)
    cards = []
    for r in run["results"]:
        for a in r["alerts"]:
            st = states.get(a["key"], {})
            if st.get("status") == "dismissed":
                continue
            t = tasks.get(a["key"])
            if not t:
                row = one(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND alert_key=? ORDER BY created_at DESC LIMIT 1", (acc, a["key"]))
                t = task_obj(row) if row else None
            cards.append(alert_card(db, acc, run, r, a, st, t, tm))
    cards.sort(key=lambda c: -c["priority"])
    ref = run["ref"]
    happened = rows(db, "SELECT * FROM pulse_events WHERE account_id=? AND day>=? AND type IN ('alert','cleared','verified','verify_failed') ORDER BY id DESC LIMIT 30", (acc, ref - 1))
    missing = []
    for c in cards:
        if not c["task_id"]:
            missing.append({"text": f"אין מטפל: {c['title']} · {c['client']}", "route": f"client/{c['client_id']}", "kind": "owner"})
        elif c["late"]:
            missing.append({"text": f"באיחור: {c['title']} · {c['client']} ({c['owner_name']})", "route": f"task/{c['task_id']}", "kind": "late"})
        elif c["task_status"] == "awaiting_approval":
            missing.append({"text": f"ממתין לאישור שלך: {c['title']} · {c['client']}", "route": f"task/{c['task_id']}", "kind": "approval"})
    for r in run["results"]:
        if r["lag"] >= 1:
            missing.append({"text": f"חסרים נתונים: {r['name']} ({'אין נתונים בכלל' if r['lag'] >= 99 else str(r['lag']) + ' ימים'})", "route": f"client/{r['id']}", "kind": "data"})
    return {"cards": cards, "happened": happened, "missing": missing, "ref": ref,
            "board": [{"id": r["id"], "name": r["name"], "status": r["status"], "improved": bool(r["improved"]), "cpl": r["rec"]["cpl"],
                       "leads": r["rec"]["leads"], "base_cpl": r["base"]["cpl"], "suggest": suggestion(r, run["clients"][r["id"]]),
                       "title": r["alerts"][0]["title"] if r["alerts"] else ("השתפר" if r["improved"] else "תקין")} for r in run["results"]]}


def top_actions(db: Database, acc: str, run: dict, n: int = 5) -> list[dict]:
    states = alert_rows(db, acc)
    tasks = {t["alert_key"]: t for t in open_tasks(db, acc)}
    tm = team_map(db, acc)
    out = []
    for r in run["results"]:
        for a in r["alerts"]:
            st = states.get(a["key"], {})
            if st.get("status") in ("resolved", "dismissed"):
                continue
            t = tasks.get(a["key"])
            score = a["priority"] + (300 if t and t.get("due_day") is not None and t["due_day"] < run["ref"] else 0)
            num = ""
            if a["numbers"] and len(a["numbers"][0]) > 3 and a["numbers"][0][3]:
                num = f" ({a['numbers'][0][0]} {a['numbers'][0][3]})"
            if not t:
                text, why = f"לפתוח משימה: {a['title']} · {r['name']}{num}", "אין עדיין משימה ואין מטפל"
            elif t["status"] == "awaiting_approval":
                text, why = f"לאשר: {a['title']} · {r['name']}", "ממתין לאישור מנהל"
                score += 400
            elif t["due_day"] is not None and t["due_day"] < run["ref"] and t["status"] in ("new", "in_progress"):
                text, why = f"משימה באיחור ({run['ref'] - t['due_day']} ימים): {a['title']} · {r['name']}", f"אחראי: {(tm.get(t['assignee']) or {}).get('name', '—')}"
            elif t["status"] == "new":
                text, why = f"טרם התחיל טיפול: {a['title']} · {r['name']}", f"אחראי: {(tm.get(t['assignee']) or {}).get('name', '—')}"
            elif t["status"] == "awaiting_verification":
                text, why = f"ממתין לבדיקה חוזרת: {a['title']} · {r['name']}", f"בדיקה ב-{fmt_day(t['recheck_day'])}"
                score -= 600
            else:
                text, why = f"בטיפול: {a['title']} · {r['name']}", f"אחראי: {(tm.get(t['assignee']) or {}).get('name', '—')}"
                score -= 200
            out.append({"text": text, "why": why, "route": f"task/{t['id']}" if t else f"client/{r['id']}", "score": score,
                        "severity": a["severity"], "clientId": r["id"]})
    for r in run["results"]:
        if r["improved"]:
            out.append({"text": f"לבחון הרחבת פעילות: {r['name']} — העלות לליד ירדה {abs(pct(r['improved']['change']))}%", "why": "הזדמנות",
                        "route": f"client/{r['id']}", "score": 120, "severity": "imp", "clientId": r["id"]})
    out.sort(key=lambda x: -x["score"])
    return out[:n]


# ================================================================ הוכחת ערך
def impact(db: Database, acc: str) -> dict:
    w = ws(db, acc)
    run = analysis(db, acc)
    alerts = alert_rows(db, acc)
    tasks = all_tasks(db, acc)
    ver = rows(db, "SELECT * FROM pulse_verifications WHERE account_id=? ORDER BY id DESC", (acc,))
    handled = [t for t in tasks if any(any(x in h["a"] for x in ("התחיל", "הוגש", "בוצע")) for h in t["history"])]
    days_to_handle = []
    for t in handled:
        s = alerts.get(t["alert_key"])
        h = next((h for h in t["history"] if any(x in h["a"] for x in ("התחיל", "הוגש", "בוצע"))), None)
        if s and h:
            days_to_handle.append(max(0, h["day"] - s["first_day"]))
    early = sum(1 for s in alerts.values() if s["was_yellow_first"] and s["max_severity"] == "yellow")
    events = []
    for v in ver:
        b, a = uj(v["before_json"], {}), uj(v["after_json"], {})
        est = (b["cpl"] - a["cpl"]) * (a.get("dailyLeads") or 0) * 7 if b.get("cpl") and a.get("cpl") and a["cpl"] < b["cpl"] else None
        events.append({"title": v["title"], "client_id": v["client_id"], "day": v["day"], "detected_day": v["detected_day"], "before": b, "after": a,
                       "estWeekly": est})
    A = w["settings"]["assumptions"]
    manual = A["minPerClient"] * len(run["results"]) * A["workdays"]
    sys_min = A["minPerAlert"] * len(alerts)
    fp = sum(1 for s in alerts.values() if s.get("feedback") == "false_positive")
    useful = sum(1 for s in alerts.values() if s.get("feedback") == "useful")
    return {"detected": len(alerts), "tasks": len(tasks), "handled": len(handled), "verified": len(ver),
            "handle_rate": round(len(handled) / len(alerts), 2) if alerts else None,
            "avg_days_to_handle": round(sum(days_to_handle) / len(days_to_handle), 1) if days_to_handle else None,
            "early": early, "events": events, "avoidedWeekly": sum(e["estWeekly"] or 0 for e in events),
            "false_positives": fp, "useful": useful,
            "time": {"manualMin": manual, "sysMin": sys_min, "savedHours": max(0, (manual - sys_min) / 60), "assumptions": A,
                     "note": "הערכה לפי הנחות שאתם קובעים (דקות לבדיקה ידנית של לקוח ביום מול דקות לטיפול בהתראה) — לא מדידה"}}


# ================================================================ צוות ועומס
def workload(db: Database, acc: str) -> list[dict]:
    ref = ref_day(ws(db, acc))
    tasks = open_tasks(db, acc)
    clients = list_clients(db, acc)
    out = []
    for m in team(db, acc):
        ts = [t for t in tasks if t["assignee"] == m["id"]]
        out.append({**m, "open": len(ts), "late": sum(1 for t in ts if t["due_day"] is not None and t["due_day"] < ref and t["status"] in ("new", "in_progress", "awaiting_approval")),
                    "not_started": sum(1 for t in ts if t["status"] == "new"), "red": sum(1 for t in ts if t["severity"] == "red"),
                    "clients": sum(1 for c in clients if c["owner"] == m["id"]),
                    "minutes": sum(t["minutes_spent"] for t in all_tasks(db, acc) if t["assignee"] == m["id"])})
    return out


# ================================================================ Demo Lab
def pick_demo_client(db: Database, acc: str, run: dict) -> dict | None:
    used = set(ws(db, acc)["settings"].get("ops", {}).keys())
    cands = [r for r in run["results"] if r["is_demo"] and r["status"] == "green" and not r["improved"] and not r["lowData"]
             and r["id"] not in used and r["rec"]["dailySpend"] > 200]
    cands.sort(key=lambda r: -r["base"]["leads"])
    return cands[0] if cands else next((r for r in run["results"] if r["is_demo"] and r["status"] == "green"), None)


def apply_scenario(db: Database, acc: str, sid: str, client_id: str | None = None) -> dict:
    w = ws(db, acc)
    if not w["settings"].get("demo"):
        return {"ok": False, "msg": "Demo Lab פועל רק בסביבת דמו"}
    sc = next((s for s in demo.SCENARIOS if s["id"] == sid), None)
    if not sc:
        return {"ok": False, "msg": "תרחיש לא קיים"}
    run = analysis(db, acc)
    if sc.get("special"):
        t = next((t for t in open_tasks(db, acc) if t["severity"] == "red" and t["status"] == "new"), None)
        if not t:
            c = pick_demo_client(db, acc, run)
            apply_scenario(db, acc, "cpl", c["id"] if c else None)
        advance(db, acc, 2)
        return {"ok": True, "msg": "השעון התקדם יומיים. משימה דחופה לא טופלה — ראו הסלמה והתראת איחור", "route": "tasks"}
    cl = run["byId"].get(client_id) if client_id else pick_demo_client(db, acc, run)
    if not cl or not cl["is_demo"]:
        return {"ok": False, "msg": "לא נמצא לקוח דמו מתאים"}
    ref = ref_day(w)
    s = w["settings"]
    s.setdefault("ops", {}).setdefault(cl["id"], []).append({**sc["op"], "from": ref - sc["back"], "sid": sid})
    save_settings(db, acc, s)
    sync_demo(db, acc, cl["id"])
    ev(db, acc, ref, "lab", f"Demo Lab · הופעל תרחיש \"{sc['name']}\" (שינוי בנתוני הדמו)", cl["id"])
    before = cl["status"]
    summ = run_check(db, acc)
    after = analysis(db, acc)["byId"][cl["id"]]
    return {"ok": True, "client_id": cl["id"], "client": cl["name"], "before": before, "after": after["status"], "check": summ,
            "msg": f"{cl['name']}: {SL[before]} ← {SL[after['status']]}", "route": f"client/{cl['id']}"}


SL = {"green": "תקין", "yellow": "במעקב", "red": "דחוף"}


def simulate_fix(db: Database, acc: str, tid: str) -> dict:
    w = ws(db, acc)
    t = get_task(db, acc, tid)
    if not t or not w["settings"].get("demo"):
        return {"ok": False, "msg": "סימולציית תיקון זמינה רק למשימות בסביבת הדמו"}
    c = get_client(db, acc, t["client_id"])
    if not c or not c["is_demo"]:
        return {"ok": False, "msg": "זה לקוח אמיתי — אין סימולציה. התוצאה תימדד מהנתונים האמיתיים"}
    ref = ref_day(w)
    s = w["settings"]
    s.setdefault("ops", {}).setdefault(c["id"], []).append({"op": "fix", "from": ref + 1})
    save_settings(db, acc, s)
    _th(t, ref, "Demo Lab", f"סימולציה: השפעת התיקון הוחלה על נתוני הדמו מ-{fmt_day(ref + 1)}")
    _save_task(db, t)
    ev(db, acc, ref, "lab", "סימולציה: הוחלה השפעת תיקון על נתוני הלקוח", c["id"], ref=t["id"])
    return {"ok": True, "msg": "השפעת התיקון תופיע בנתונים מהיום הבא. קדמו את השעון כדי לראות את הבדיקה החוזרת"}


def advance(db: Database, acc: str, n: int) -> dict:
    w = ws(db, acc)
    if not w["settings"].get("demo"):
        return {"ok": False, "msg": "שעון דמו זמין רק בסביבת דמו"}
    n = max(1, min(14, int(n)))
    exe(db, "UPDATE pulse_workspaces SET day_offset=day_offset+? WHERE account_id=?", (n, acc))
    sync_demo(db, acc)
    ref = ref_day(ws(db, acc))
    ev(db, acc, ref, "lab", f"שעון הדמו התקדם ב-{n} {'יום' if n == 1 else 'ימים'} ל-{fmt_day(ref)}")
    summ = run_check(db, acc)
    return {"ok": True, "msg": f"השעון התקדם ל-{fmt_day(ref)}. {summ['new']} חריגות חדשות, {summ['cleared']} נעלמו", "check": summ}


# ================================================================ סדרות לגרפים
def series(r: dict, days_n: int = 30) -> list[dict]:
    ref = r["lastIdx"]
    if ref is None:
        return []
    out = []
    for d in r["days"]:
        if 0 <= (r["days"][-1]["_i"] - d["_i"]) < days_n:
            out.append({"date": d["date"], "spend": d["spend"], "leads": d["leads"], "clicks": d["clicks"], "impressions": d["impressions"],
                        "cpl": round(d["spend"] / d["leads"], 1) if d["leads"] else None,
                        "ctr": round(d["clicks"] / d["impressions"] * 100, 2) if d["impressions"] else None,
                        "sales": d.get("sales")})
    return out


def rolling_cpl(r: dict, days_n: int = 60, w: int = 7) -> list[dict]:
    ds = r["days"]
    out = []
    for i in range(len(ds)):
        if ds[-1]["_i"] - ds[i]["_i"] >= days_n:
            continue
        win_ = [d for d in ds if 0 <= ds[i]["_i"] - d["_i"] < w]
        sp, ld = sum(d["spend"] for d in win_), sum(d["leads"] for d in win_)
        out.append({"date": ds[i]["date"], "cpl": round(sp / ld, 1) if ld else None})
    return out



# ================================================================ התחייבויות · אנשי קשר · שביעות רצון
def add_commitment(db: Database, acc: str, cid: str, text: str, owner: str | None, due_in: int, by: str, source: str = "manual") -> dict:
    ref = ref_day(ws(db, acc))
    i = exe(db, "INSERT INTO pulse_commitments (account_id, client_id, text, owner, due_day, source, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (acc, cid, text, owner, ref + due_in, source, by, now()))
    ev(db, acc, ref, "commitment", f"התחייבות ללקוח: {text} (יעד {fmt_day(ref + due_in)})", cid, by)
    bump(db, acc)
    return one(db, "SELECT * FROM pulse_commitments WHERE id=?", (i,))  # type: ignore[return-value]


def set_commitment(db: Database, acc: str, cmid: int, status: str, by: str) -> bool:
    r = one(db, "SELECT * FROM pulse_commitments WHERE account_id=? AND id=?", (acc, cmid))
    if not r or status not in ("open", "done", "cancelled"):
        return False
    ref = ref_day(ws(db, acc))
    exe(db, "UPDATE pulse_commitments SET status=?, done_day=? WHERE id=?", (status, ref if status == "done" else None, cmid))
    ev(db, acc, ref, "commitment", ("בוצעה התחייבות: " if status == "done" else "בוטלה התחייבות: " if status == "cancelled" else "נפתחה מחדש: ") + r["text"], r["client_id"], by)
    bump(db, acc)
    return True


def set_satisfaction(db: Database, acc: str, cid: str, score: int, by: str) -> None:
    ref = ref_day(ws(db, acc))
    exe(db, "UPDATE pulse_clients SET satisfaction=?, satisfaction_day=? WHERE account_id=? AND id=?", (score, ref, acc, cid))
    ev(db, acc, ref, "note", f"עודכנה שביעות רצון: {score}/5", cid, by, "satisfaction")
    bump(db, acc)


# ================================================================ סקירת בוקר: מה השתנה מאז הכניסה הקודמת
def touch_seen(db: Database, acc: str, user_id: str) -> float | None:
    """מחזיר את זמן הכניסה הקודמת ומעדכן. כניסה תוך 20 דק' לא נחשבת כניסה חדשה (רענון)."""
    r = one(db, "SELECT * FROM pulse_seen WHERE account_id=? AND user_id=?", (acc, user_id))
    t = now()
    if not r:
        exe(db, "INSERT INTO pulse_seen (account_id, user_id, last_t, prev_t) VALUES (?,?,?,NULL)", (acc, user_id, t))
        return None
    if t - (r["last_t"] or 0) > 1200:
        exe(db, "UPDATE pulse_seen SET prev_t=last_t, last_t=? WHERE account_id=? AND user_id=?", (t, acc, user_id))
        return r["last_t"]
    exe(db, "UPDATE pulse_seen SET last_t=? WHERE account_id=? AND user_id=?", (t, acc, user_id))
    return r["prev_t"]


def brief(db: Database, acc: str, since: float | None, can_approve: bool) -> dict:
    run = analysis(db, acc)
    ref = run["ref"]
    tm = team_map(db, acc)
    states = alert_rows(db, acc)
    tasks = open_tasks(db, acc)
    by_key = {t["alert_key"]: t for t in tasks}
    since_t = since or 0
    items: list[dict] = []

    def add(score, kind, sev, title, detail, label, route=None, act=None, arg=None):
        items.append({"score": score, "kind": kind, "severity": sev, "title": title, "detail": detail,
                      "action": {"label": label, "route": route, "act": act, "arg": arg}})
    changes = rows(db, "SELECT * FROM pulse_status_history WHERE account_id=? AND prev IS NOT NULL AND t>? ORDER BY id DESC", (acc, since_t)) if since else \
        rows(db, "SELECT * FROM pulse_status_history WHERE account_id=? AND prev IS NOT NULL AND day>=? ORDER BY id DESC", (acc, ref - 1))
    names = {r["id"]: r["name"] for r in run["results"]}
    seen_c = set()
    worse, better = [], []
    rank = {"green": 0, "nodata": 0, "yellow": 1, "red": 2}
    for ch in changes:
        if ch["client_id"] in seen_c or ch["client_id"] not in names:
            continue
        seen_c.add(ch["client_id"])
        (worse if rank[ch["status"]] > rank[ch["prev"] or "green"] else better).append(ch)
    for ch in worse:
        r = run["byId"][ch["client_id"]]
        a = r["alerts"][0] if r["alerts"] else None
        t = by_key.get(a["key"]) if a else None
        add(900 if ch["status"] == "red" else 500, "worse", ch["status"], f"{names[ch['client_id']]} עבר ל{STATUS_HE[ch['status']]}",
            ch["reason"] + (f" · {a['what']}" if a else ""), "פתח הסבר" if not t else "למשימה", route=f"client/{ch['client_id']}" if not t else f"task/{t['id']}")
    for r in run["results"]:
        for a in r["alerts"]:
            if a["severity"] != "red" or r["id"] in seen_c:
                continue
            st = states.get(a["key"], {})
            if st.get("status") in ("resolved", "dismissed"):
                continue
            t = by_key.get(a["key"])
            if not t and not one(db, "SELECT 1 FROM pulse_tasks WHERE account_id=? AND client_id=? AND status!='closed'", (acc, r["id"])):
                add(800 + a["priority"] / 100, "nohandler", "red", f"{r['name']}: {a['title']}", a["what"] + " אין עדיין מטפל.",
                    "צור משימה", act="createTask", arg=a["key"])
            elif t and t["due_day"] is not None and t["due_day"] < ref and t["status"] in ("new", "in_progress"):
                add(700, "late", "red", f"משימה דחופה באיחור: {r['name']}", f"{a['title']} · אחראי: {(tm.get(t['assignee']) or {}).get('name', '—')} · {ref - t['due_day']} ימי איחור",
                    "למשימה", route=f"task/{t['id']}")
            elif t and t["status"] == "new":
                add(600 + a["priority"] / 100, "notstarted", "red", f"{r['name']}: {a['title']}",
                    (f"פוטנציאל: ~{r['recovery']['leads_week']} לידים בשבוע. " if r.get("recovery") else "") + f"{a['what']} המשימה אצל {(tm.get(t['assignee']) or {}).get('name', '—')} — הטיפול עוד לא התחיל.", "פתח הסבר", route=f"client/{r['id']}")
            elif ref - st.get("first_day", ref) >= 3 and t and t["status"] != "awaiting_verification":
                add(450, "stuck", "yellow", f"בעיה פתוחה {ref - st['first_day']} ימים: {r['name']}", a["title"], "למשימה", route=f"task/{t['id']}")
            seen_c.add(r["id"])
    for t in tasks:
        if t["status"] == "awaiting_approval":
            add(850 if can_approve else 300, "approval", "yellow", f"ממתין לאישור: {t['title']}",
                "; ".join(p["text"] for p in t["plan"] if p["actionType"] in SENSITIVE), "בדוק ואשר" if can_approve else "צפה", route=f"task/{t['id']}")
    for cm in rows(db, "SELECT * FROM pulse_commitments WHERE account_id=? AND status='open' AND due_day<=? ORDER BY due_day", (acc, ref + 1)):
        if cm["client_id"] not in names:
            continue
        late = ref - cm["due_day"]
        add(min(640, 500 + late * 20) if late > 0 else 400, "commitment", "red" if late >= 7 else "yellow",
            f"התחייבות ל{names[cm['client_id']]}" + (f" באיחור {late} ימים" if late > 0 else " — היעד היום" if late == 0 else " — היעד מחר"),
            f"{cm['text']} · אחראי: {(tm.get(cm['owner']) or {}).get('name', 'לא שויך')}", "סמן כבוצע", act="commitDone", arg=str(cm["id"]))
    for t in [t for t in tasks if t["status"] == "awaiting_verification" and t["recheck_day"] is not None and t["recheck_day"] <= ref]:
        add(380, "verify", "imp", f"בדיקה חוזרת מוכנה: {t['title']}", t["success"]["text"] if t.get("success") else "", "הרץ בדיקה חוזרת", act="task", arg=f"{t['id']}|recheck_now")
    for ch in better[:3]:
        add(200, "better", "green", f"{names[ch['client_id']]} השתפר ל{STATUS_HE[ch['status']]}", ch["reason"], "לתיק הלקוח", route=f"client/{ch['client_id']}")
    for r in [r for r in run["results"] if r["improved"]][:2]:
        add(150, "opportunity", "imp", f"הזדמנות: {r['name']}", r["improved"]["what"], "לבחון הרחבה", route=f"client/{r['id']}")
    items.sort(key=lambda x: -x["score"])
    ver = rows(db, "SELECT * FROM pulse_verifications WHERE account_id=? ORDER BY id DESC LIMIT 3", (acc,))
    pot = [r["recovery"] for r in run["results"] if r.get("recovery")]
    week = {"detected": one(db, "SELECT COUNT(*) n FROM pulse_alerts WHERE account_id=? AND first_day>=?", (acc, ref - 6))["n"],
            "handled": one(db, "SELECT COUNT(*) n FROM pulse_tasks WHERE account_id=? AND done_day>=?", (acc, ref - 6))["n"],
            "improved": one(db, "SELECT COUNT(*) n FROM pulse_verifications WHERE account_id=? AND day>=?", (acc, ref - 6))["n"],
            "handled_today": one(db, "SELECT COUNT(*) n FROM pulse_tasks WHERE account_id=? AND done_day=?", (acc, ref))["n"]}
    return {"since": since, "week": week, "items": items[:8], "potential": {"leads_week": sum(p["leads_week"] for p in pot), "clients": len(pot)} if pot else None, "more": max(0, len(items) - 8), "counts": run["counts"],
            "verified": [{"title": v["title"], "client_id": v["client_id"], "before": uj(v["before_json"], {}), "after": uj(v["after_json"], {})} for v in ver],
            "ref": ref, "scan_ms": run["ms"], "clients": len(run["results"])}


# ================================================================ ידע הסוכנות · היסטוריית החלטות
ALERT_NAMES = {"cpl": "זינוק בעלות לליד", "no_leads": "אין לידים", "spend_up": "הוצאה בלי לידים", "ctr": "ירידת CTR", "cvr": "ירידה בהמרה",
               "trend": "הידרדרות הדרגתית", "goal": "חריגה מיעד", "data": "חוסר נתונים", "no_sales": "לידים בלי מכירות",
               "commitment": "התחייבות באיחור", "contact": "חוסר קשר עם לקוח", "satisfaction": "שביעות רצון נמוכה"}


def knowledge(db: Database, acc: str) -> dict:
    """מה עבד בעבר: טיפולים שאומתו בנתונים, לפי סוג בעיה + לקחים שתועדו ידנית."""
    done = [task_obj(r) for r in rows(db, "SELECT * FROM pulse_tasks WHERE account_id=? AND status='closed' AND alert_key IS NOT NULL", (acc,))]
    by: dict[str, dict] = {}
    for t in done:
        v = t.get("verification") or {}
        kind = t["alert_key"].split(":")[1]
        g = by.setdefault(kind, {"type": kind, "name": ALERT_NAMES.get(kind, kind), "fixed": 0, "failed_first": 0, "days": [], "actions": {}})
        if v.get("ok"):
            g["fixed"] += 1
            g["days"].append((t.get("closed_day") or 0) - (t.get("created_day") or 0))
            for p in t["plan"]:
                g["actions"][p["text"]] = g["actions"].get(p["text"], 0) + 1
        if any("נכשלה" in h["a"] or "עדיין לא חזר" in h["a"] for h in t["history"]):
            g["failed_first"] += 1
    out = []
    for g in by.values():
        out.append({"type": g["type"], "name": g["name"], "fixed": g["fixed"], "failed_first": g["failed_first"],
                    "avg_days": round(sum(g["days"]) / len(g["days"]), 1) if g["days"] else None,
                    "actions": sorted(g["actions"].items(), key=lambda x: -x[1])[:4]})
    out.sort(key=lambda g: -g["fixed"])
    lessons = rows(db, "SELECT * FROM pulse_notes WHERE account_id=? AND kind='lesson' ORDER BY id DESC LIMIT 50", (acc,))
    return {"patterns": out, "lessons": lessons}


def decisions(db: Database, acc: str, client_id: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM pulse_decisions WHERE account_id=?", [acc]
    if client_id:
        q += " AND client_id=?"
        a.append(client_id)
    return rows(db, q + " ORDER BY id DESC LIMIT 100", tuple(a))


def update_draft(db: Database, acc: str, cid: str, by: str) -> dict:
    """טיוטת עדכון ללקוח מנתוני המערכת בלבד: מה המצב, מה מצאנו, מה עושים, הצעד הבא. נשמרת בתיק — לא נשלחת."""
    run = analysis(db, acc)
    r = run["byId"].get(cid)
    if not r:
        raise KeyError("לקוח לא נמצא")
    c = run["clients"][cid]
    contact = one(db, "SELECT name FROM pulse_contacts WHERE account_id=? AND client_id=? ORDER BY id LIMIT 1", (acc, cid))
    rc, b = r["rec"], r["base"]
    lines = [f"היי {contact['name'].split()[0] if contact else ''}, עדכון שבועי על הקמפיינים:".replace("היי ,", "היי,"),
             f"• 7 הימים האחרונים: {rc['leads']} לידים, עלות לליד {money(rc['cpl'])}" + (f" (לעומת {money(b['cpl'])} בממוצע)" if b["cpl"] else "") + "."]
    tgt = (c.get("goals") or {}).get("targetCpl")
    if tgt and rc["cpl"]:
        lines.append(f"• מול היעד שסיכמנו ({money(tgt)}): " + ("עומדים ביעד." if rc["cpl"] <= tgt else "עדיין מעל היעד."))
    perf = [a for a in r["alerts"] if a.get("source") != "ops"]
    if r["improved"]:
        lines.append("• החדשות הטובות: " + r["improved"]["what"])
    if perf:
        a = perf[0]
        t = open_task_for(db, acc, a["key"])
        lines.append(f"• מה זיהינו: {a['what']}")
        lines.append("• מה אנחנו עושים: " + engine.investigate(r, a)["plan"][0]["text"] + (" (כבר בטיפול)" if t and t["status"] != "new" else "") + ".")
    elif not r["improved"]:
        lines.append("• הקמפיינים יציבים ובטווח התקין.")
    done = rows(db, "SELECT title FROM pulse_verifications WHERE account_id=? AND client_id=? ORDER BY id DESC LIMIT 1", (acc, cid))
    if done:
        lines.append("• טופל ואומת: " + done[0]["title"].split(" · ")[0] + ".")
    lines.append("נמשיך לעקוב ונעדכן. שאלות? אנחנו כאן.")
    txt = "\n".join(lines)
    ref = run["ref"]
    exe(db, "INSERT INTO pulse_drafts (account_id, client_id, day, kind, channel, text, created_at) VALUES (?,?,?,?,?,?,?)",
        (acc, cid, ref, "update", "WhatsApp", txt, now()))
    ev(db, acc, ref, "note", "הוכנה טיוטת עדכון ללקוח", cid, by)
    return {"ok": True, "text": txt, "msg": "הטיוטה נשמרה בתיק הלקוח (לא נשלחה). אפשר להעתיק ולשלוח."}


def benchmark(run: dict, cid: str) -> dict | None:
    """השוואה ללקוחות אחרים של אותה סוכנות באותו ענף (או לכל התיק כשאין מספיק). מהנתונים של המשרד בלבד."""
    r = run["byId"].get(cid)
    if not r or not r["rec"]["cpl"] or r["lowData"]:
        return None
    same = [x for x in run["results"] if x["id"] != cid and x["industry"] == r["industry"] and x["rec"]["cpl"] and not x["lowData"]]
    if len(same) >= 3:  # אותו ענף: משווים עלות לליד ישירות
        worse = sum(1 for x in same if x["rec"]["cpl"] < r["rec"]["cpl"]) / len(same)
        text = f"העלות לליד ({money(r['rec']['cpl'])}) " + (f"יקרה מ-{round(worse * 100)}%" if worse >= 0.5 else f"זולה מ-{round((1 - worse) * 100)}%") + f" מהלקוחות שלכם ב{r['industry']}"
        share = worse
    else:  # ענפים שונים: משווים ביחס ליעד של כל לקוח (השוואה הוגנת בין ענפים)
        tgt = (r.get("goals") or {}).get("targetCpl")
        same = [x for x in run["results"] if x["id"] != cid and x["rec"]["cpl"] and not x["lowData"] and (x.get("goals") or {}).get("targetCpl")]
        if not tgt or len(same) < 5:
            return None
        ratio = r["rec"]["cpl"] / tgt
        share = sum(1 for x in same if x["rec"]["cpl"] / x["goals"]["targetCpl"] < ratio) / len(same)
        pos = f"{round(abs(ratio - 1) * 100)}% {'מעל היעד' if ratio > 1 else 'מתחת ליעד'}"
        text = (f"ביחס ליעד שלו ({pos}), זה הלקוח במצב החלש ביותר בתיק" if share >= 0.99
                else f"ביחס ליעד שלו ({pos}), הלקוח במצב חלש מ-{round(share * 100)}% מהלקוחות שלכם" if share >= 0.5
                else f"ביחס ליעד שלו ({pos}), הלקוח במצב טוב מ-{round((1 - share) * 100)}% מהלקוחות שלכם")
    return {"text": text + f" ({len(same)} לקוחות להשוואה, 7 ימים)", "share": share, "n": len(same)}


def handle_alert(db: Database, acc: str, key: str, mode: str, user_name: str, can_approve: bool) -> dict:
    """פעולה אחת מתוך מסך המיקוד: 'start' = אני על זה, 'done' = טיפלתי. פותח משימה אם צריך ומקדם אותה."""
    run = analysis(db, acc)
    t = open_task_for(db, acc, key)
    if not t:
        try:
            t = create_task(db, acc, run, key, by="user", by_name=user_name)
        except KeyError:
            return {"ok": False, "msg": "החריגה כבר לא פעילה — רעננו"}
    if t["status"] == "new":
        task_action(db, acc, t["id"], "start", user_name=user_name, can_approve=can_approve)
    if mode == "done":
        t = get_task(db, acc, t["id"])
        if t["status"] == "in_progress":
            r = task_action(db, acc, t["id"], "submit", user_name=user_name, can_approve=can_approve)
            return {"ok": r["ok"], "msg": "מעולה. " + r["msg"], "task_id": t["id"]}
    return {"ok": True, "msg": "רשמתי שאתה מטפל בזה", "task_id": t["id"]}


def office_trend(db: Database, acc: str) -> dict:
    """התמונה הגדולה: לידים ועלות לליד לכל המשרד, 12 שבועות + מה המערכת עשתה מאז שהתחילה."""
    run = analysis(db, acc)
    ref = run["ref"]
    weeks = []
    for w in range(11, -1, -1):
        ds = [d for r in run["results"] for d in r["days"] if w * 7 <= ref - d["_i"] < w * 7 + 7]
        st_ = engine.stats(ds)
        weeks.append({"label": fmt_day(ref - w * 7 - 6), "leads": st_["leads"], "spend": round(st_["spend"]),
                      "cpl": round(st_["cpl"], 1) if st_["cpl"] else None, "n": st_["n"]})
    weeks = [w for w in weeks if w["n"]]
    cur, month = (weeks[-1], weeks[-5]) if len(weeks) >= 5 else (weeks[-1] if weeks else None, None)
    sentence = None
    if cur and month and month["leads"]:
        chg = cur["leads"] / month["leads"] - 1
        sentence = (f"השבוע נכנסו {cur['leads']:,} לידים בכל המשרד, {'+' if chg >= 0 else ''}{round(chg * 100)}% לעומת לפני חודש. "
                    f"העלות לליד {money(cur['cpl'])} (לפני חודש {money(month['cpl'])}).")
    since = {"detected": one(db, "SELECT COUNT(*) n FROM pulse_alerts WHERE account_id=?", (acc,))["n"],
             "handled": one(db, "SELECT COUNT(*) n FROM pulse_tasks WHERE account_id=? AND done_day IS NOT NULL", (acc,))["n"],
             "improved": one(db, "SELECT COUNT(*) n FROM pulse_verifications WHERE account_id=?", (acc,))["n"],
             "first_day": one(db, "SELECT MIN(day) d FROM pulse_events WHERE account_id=?", (acc,))["d"]}
    since["first_label"] = fmt_day(since["first_day"]) if since["first_day"] is not None else None
    return {"weeks": weeks, "sentence": sentence, "since": since, "is_demo": any(r["is_demo"] for r in run["results"])}


def client_trend_line(r: dict) -> str | None:
    """'האם זה עובד?' בשורה אחת: מגמת עלות לליד ב-4 השבועות האחרונים."""
    ws = [w["cpl"] for w in r["weeks"] if w["cpl"]]
    if len(ws) < 3 or r["lowData"]:
        return None
    first, last = ws[0], ws[-1]
    ch = last / first - 1
    verdict = "משתפר" if ch <= -0.08 else "מידרדר" if ch >= 0.08 else "יציב"
    return f"עלות לליד ב-4 השבועות האחרונים: {' ← '.join(money(x) for x in ws)} · {verdict}"


def office_score(db: Database, acc: str, run: dict) -> dict:
    """ציון המשרד 0–100: ירוק = 100, צהוב = 50, אדום = 0 (בלי לקוחות שאין עליהם מספיק מידע). + הציון לפני שבוע מהיסטוריית הרמזור."""
    def score(statuses: list[str]) -> int | None:
        v = [{"green": 100, "yellow": 50, "red": 0}[x] for x in statuses if x in ("green", "yellow", "red")]
        return round(sum(v) / len(v)) if v else None
    now_ = score([r["status"] for r in run["results"]])
    ref = run["ref"]
    hist = rows(db, """SELECT client_id, status FROM pulse_status_history WHERE id IN (SELECT MAX(id) FROM pulse_status_history
                       WHERE account_id=? AND day<=? GROUP BY client_id)""", (acc, ref - 7))
    prev = score([h["status"] for h in hist]) if len(hist) >= max(3, len(run["results"]) // 2) else None
    return {"score": now_, "prev": prev, "formula": "תקין = 100, במעקב = 50, דחוף = 0; ממוצע על כל הלקוחות שיש עליהם מספיק נתונים"}
