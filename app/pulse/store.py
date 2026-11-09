"""ClientPulse — שכבת נתונים (SQLite, אותו קובץ DB של P1). כל שאילתה מסוננת לפי account_id — הפרדה מלאה בין סוכנויות."""
from __future__ import annotations

import json
import time
from typing import Any

from ..db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS pulse_workspaces (
    account_id TEXT PRIMARY KEY, settings_json TEXT NOT NULL, day_offset INTEGER NOT NULL DEFAULT 0,
    data_version INTEGER NOT NULL DEFAULT 0, last_run_json TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_team (
    account_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, role TEXT, approver INTEGER NOT NULL DEFAULT 0,
    user_id TEXT, is_demo INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (account_id, id));
CREATE TABLE IF NOT EXISTS pulse_clients (
    account_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, industry TEXT, owner TEXT,
    target_cpl REAL, monthly_budget REAL, fee_monthly REAL, hours_monthly REAL, hourly_cost REAL, other_costs_monthly REAL,
    platforms_json TEXT, website TEXT, thresholds_json TEXT, is_demo INTEGER NOT NULL DEFAULT 0, params_json TEXT,
    source TEXT NOT NULL DEFAULT 'manual', created_at REAL NOT NULL, PRIMARY KEY (account_id, id));
CREATE TABLE IF NOT EXISTS pulse_days (
    account_id TEXT NOT NULL, client_id TEXT NOT NULL, date TEXT NOT NULL, spend REAL NOT NULL, impressions INTEGER NOT NULL,
    clicks INTEGER NOT NULL, leads INTEGER NOT NULL, sales INTEGER, revenue REAL, source TEXT NOT NULL,
    PRIMARY KEY (account_id, client_id, date));
CREATE TABLE IF NOT EXISTS pulse_alerts (
    account_id TEXT NOT NULL, key TEXT NOT NULL, client_id TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL,
    severity TEXT NOT NULL, max_severity TEXT NOT NULL, first_day INTEGER NOT NULL, last_day INTEGER NOT NULL, cleared_day INTEGER,
    title TEXT, escalated_day INTEGER, was_yellow_first INTEGER, first_t REAL, snapshot_json TEXT, history_json TEXT NOT NULL,
    feedback TEXT, PRIMARY KEY (account_id, key));
CREATE TABLE IF NOT EXISTS pulse_tasks (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, client_id TEXT NOT NULL, alert_key TEXT, title TEXT NOT NULL, severity TEXT,
    description TEXT, plan_json TEXT, success_json TEXT, requires_approval INTEGER NOT NULL DEFAULT 0, approved_by TEXT,
    assignee TEXT, due_day INTEGER, status TEXT NOT NULL, created_by TEXT, created_day INTEGER, done_day INTEGER,
    recheck_day INTEGER, closed_day INTEGER, before_json TEXT, verification_json TEXT, history_json TEXT NOT NULL,
    overdue_notified INTEGER, minutes_spent INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS pulse_tasks_acc ON pulse_tasks(account_id, status);
CREATE TABLE IF NOT EXISTS pulse_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, day INTEGER NOT NULL, t REAL NOT NULL, type TEXT NOT NULL,
    text TEXT NOT NULL, client_id TEXT, user TEXT, ref TEXT);
CREATE INDEX IF NOT EXISTS pulse_events_acc ON pulse_events(account_id, id);
CREATE TABLE IF NOT EXISTS pulse_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, day INTEGER NOT NULL, t REAL NOT NULL, text TEXT NOT NULL,
    kind TEXT, route TEXT, to_role TEXT, read INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS pulse_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, client_id TEXT, day INTEGER, kind TEXT, channel TEXT,
    text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', approved_by TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, rule_id TEXT NOT NULL, run_key TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT, attempts INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, UNIQUE (account_id, run_key));
CREATE TABLE IF NOT EXISTS pulse_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, task_id TEXT, title TEXT, client_id TEXT, day INTEGER,
    ok INTEGER, before_json TEXT, after_json TEXT, detected_day INTEGER);
CREATE TABLE IF NOT EXISTS pulse_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, client_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
    user_name TEXT, created_at REAL NOT NULL);
"""

_ensured: set[str] = set()


def ensure(db: Database) -> None:
    if db.path in _ensured and db.path != ":memory:":
        return
    with db._conn() as c:
        c.executescript(SCHEMA)
    _ensured.add(db.path)


def j(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


def uj(s: str | None, default: Any = None) -> Any:
    return json.loads(s) if s else default


def rows(db: Database, q: str, args: tuple = ()) -> list[dict]:
    with db._conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def one(db: Database, q: str, args: tuple = ()) -> dict | None:
    with db._conn() as c:
        r = c.execute(q, args).fetchone()
    return dict(r) if r else None


def exe(db: Database, q: str, args: tuple = ()) -> int:
    with db._conn() as c:
        cur = c.execute(q, args)
        return cur.lastrowid or cur.rowcount


def now() -> float:
    return time.time()


# ---------------------------------------------------------------- המרות שורה → אובייקט
def client_obj(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "industry": r["industry"], "owner": r["owner"], "is_demo": bool(r["is_demo"]),
            "goals": {"targetCpl": r["target_cpl"], "monthlyBudget": r["monthly_budget"]},
            "fee_monthly": r["fee_monthly"], "hours_monthly": r["hours_monthly"], "hourly_cost": r["hourly_cost"],
            "other_costs_monthly": r["other_costs_monthly"], "platforms": uj(r["platforms_json"], []), "website": r["website"],
            "thresholds": uj(r["thresholds_json"], {}), "source": r["source"], "params": uj(r["params_json"])}


def task_obj(r: dict) -> dict:
    d = dict(r)
    for k in ("plan", "success", "before", "verification", "history"):
        d[k] = uj(d.pop(k + "_json"), [] if k in ("plan", "history") else None)
    d["requires_approval"] = bool(d["requires_approval"])
    return d


def alert_obj(r: dict) -> dict:
    d = dict(r)
    d["history"] = uj(d.pop("history_json"), [])
    d["snapshot"] = uj(d.pop("snapshot_json"))
    return d
