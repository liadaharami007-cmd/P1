"""גישה לנתוני Business OS. כל פונקציה מקבלת account_id ומסננת לפיו — הפרדה מלאה בין עסקים."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..db import Database


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- פרופיל עסק (Business Brain)
def get_profile(db: Database, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT data_json, updated_at FROM business_profiles WHERE account_id=?", (account_id,)).fetchone()
    if not r:
        return None
    return {"data": json.loads(r["data_json"]), "updated_at": r["updated_at"]}


def save_profile(db: Database, account_id: str, data: dict, user_id: str | None) -> None:
    with db._conn() as c:
        c.execute("""INSERT INTO business_profiles (account_id, data_json, updated_at, updated_by) VALUES (?,?,?,?)
                     ON CONFLICT(account_id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at,
                     updated_by=excluded.updated_by""", (account_id, json.dumps(data, ensure_ascii=False), now(), user_id))


# ---------------------------------------------------------------- יומן פעילות (Growth Timeline)
def log(db: Database, account_id: str, kind: str, title: str, detail: str | None = None,
        ref_type: str | None = None, ref_id: str | None = None, user_id: str | None = None) -> None:
    with db._conn() as c:
        c.execute("INSERT INTO activity (account_id, kind, title, detail, ref_type, ref_id, user_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (account_id, kind, title, detail, ref_type, ref_id, user_id, now()))


def list_activity(db: Database, account_id: str, limit: int = 200) -> list[dict]:
    with db._conn() as c:
        rows = c.execute("SELECT * FROM activity WHERE account_id=? ORDER BY id DESC LIMIT ?", (account_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- פעולות (Human Approval Center)
_JSON = ("changes_json", "payload_json", "result_json")


def _action(r: Any) -> dict:
    d = dict(r)
    for k in _JSON:
        d[k[:-5]] = json.loads(d.pop(k)) if d.get(k) else None
    return d


def create_action(db: Database, account_id: str, *, kind: str, title: str, summary: str, changes: list[str], risk: str,
                  payload: dict, source: str, site_id: str | None = None, user_id: str | None = None) -> dict:
    aid = uuid.uuid4().hex
    with db._conn() as c:
        c.execute("""INSERT INTO actions (id, account_id, site_id, kind, title, summary, changes_json, risk, payload_json, source,
                     status, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?, 'proposed', ?, ?)""",
                  (aid, account_id, site_id, kind, title, summary, json.dumps(changes, ensure_ascii=False), risk,
                   json.dumps(payload, ensure_ascii=False), source, now(), user_id))
    return get_action(db, aid, account_id)  # type: ignore[return-value]


def get_action(db: Database, action_id: str, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT * FROM actions WHERE id=? AND account_id=?", (action_id, account_id)).fetchone()
    return _action(r) if r else None


def list_actions(db: Database, account_id: str, status: str | None = None, limit: int = 100) -> list[dict]:
    q, args = "SELECT * FROM actions WHERE account_id=?", [account_id]
    if status:
        q += " AND status=?"
        args.append(status)
    with db._conn() as c:
        rows = c.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
    return [_action(r) for r in rows]


def open_action_for(db: Database, account_id: str, kind: str, key: str) -> dict | None:
    """פעולה פתוחה (מוצעת/מאושרת/רצה) מאותו סוג על אותו יעד — כדי לא ליצור כפילויות."""
    for a in list_actions(db, account_id):
        if a["kind"] == kind and a["status"] in ("proposed", "approved", "executing") and a["payload"].get("key") == key:
            return a
    return None


def update_action(db: Database, action_id: str, account_id: str, **fields: Any) -> None:
    for k in ("result", "payload", "changes"):
        if k in fields:
            fields[k + "_json"] = json.dumps(fields.pop(k), ensure_ascii=False)
    sets = ", ".join(f"{k}=?" for k in fields)
    with db._conn() as c:
        c.execute(f"UPDATE actions SET {sets} WHERE id=? AND account_id=?", (*fields.values(), action_id, account_id))
