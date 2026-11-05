"""שכבת הנתונים — SQLite עם מיגרציות ממוספרות.

עקרונות:
- כל נתון עסקי שייך ל-account (חשבון). כל שאילתה שמגיעה מהמשתמש מסוננת לפי account_id — הפרדה מלאה בין לקוחות.
- הודעות צ'אט נשמרות בדיוק בפורמט ה-API של Claude (append-only).
- המעבר ל-Postgres בהמשך: SQL סטנדרטי, בלי תלות בתכונות ייחודיות ל-SQLite מלבד המיגרציה הראשונה.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 3

SCHEMA = """
-- ===== חשבונות ומשתמשים (SaaS) =====
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    subscription_status TEXT NOT NULL DEFAULT 'none',  -- none / trialing / active / past_due / canceled
    billing_customer_id TEXT,                          -- מזהה אצל ספק התשלומים (עתידי)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT,
    locale TEXT NOT NULL DEFAULT 'he',
    is_platform_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                                -- owner / admin / member
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, account_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,                       -- שומרים רק hash של הטוקן
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    user_agent TEXT,
    ip TEXT
);

-- ===== צ'אט =====
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    user_id TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS research_reports (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    url TEXT NOT NULL,
    final_url TEXT,
    conversation_id TEXT,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ===== בדיקות אתרים =====
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    url TEXT NOT NULL,                 -- origin מנורמל
    name TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (account_id, url)
);
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    account_id TEXT,
    created_by TEXT,
    start_url TEXT NOT NULL,
    status TEXT NOT NULL,              -- queued / running / done / failed
    progress_json TEXT NOT NULL DEFAULT '[]',
    score INTEGER,
    category_scores_json TEXT,
    facts_json TEXT,
    ai_status TEXT,                    -- null / running / done / partial / failed / not_configured / quota_exceeded
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_audits_site ON audits(site_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audits_account ON audits(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status, created_at);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,                -- navigate / loaded / click / type / select / screenshot / step_* / error / ai / info
    message TEXT NOT NULL,
    page_url TEXT,
    screenshot_id TEXT,
    ref TEXT                           -- מפתח השלב (home / product / ...) כשרלוונטי
);
CREATE INDEX IF NOT EXISTS idx_events_audit ON audit_events(audit_id, id);
CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    device TEXT NOT NULL,
    page_url TEXT,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journey_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    page_url TEXT,
    duration_ms INTEGER,
    screenshot_id TEXT
);
-- source: measured / simulation / store_data / ai
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    impact TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    fix_steps_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_audit ON findings(audit_id);
CREATE TABLE IF NOT EXISTS persona_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    persona TEXT NOT NULL,
    verdict TEXT NOT NULL,
    blockers_json TEXT NOT NULL,
    positives_json TEXT NOT NULL
);
-- כל קריאה למודל AI: מה, כמה עלה, ומה יצא
CREATE TABLE IF NOT EXISTS ai_runs (
    id TEXT PRIMARY KEY,
    audit_id TEXT REFERENCES audits(id) ON DELETE CASCADE,
    account_id TEXT,
    kind TEXT NOT NULL,                -- analysis / persona:<key> / chat
    status TEXT NOT NULL,              -- done / failed / skipped
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_runs_audit ON ai_runs(audit_id);
CREATE INDEX IF NOT EXISTS idx_ai_runs_account ON ai_runs(account_id, created_at);

-- ===== v3: סוכני לקוח, Fix Studio, Smart Monitor, התראות =====
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,               -- trust / fast_buyer / price / confused / mobile_ad
    engine TEXT NOT NULL,              -- rules (מסלול מבוסס כללים) / model:<name> בעתיד
    status TEXT NOT NULL,              -- queued / running / done / failed / interrupted / skipped
    started_at TEXT, finished_at TEXT,
    actions INTEGER NOT NULL DEFAULT 0,
    current_url TEXT, last_action TEXT, last_screenshot_id TEXT,
    verdict TEXT, result_json TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_audit ON agent_runs(audit_id);
CREATE TABLE IF NOT EXISTS fix_previews (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    audit_id TEXT NOT NULL,
    account_id TEXT,
    status TEXT NOT NULL,              -- running / done / failed / unsupported
    device TEXT NOT NULL,
    page_url TEXT,
    before_shot TEXT, after_shot TEXT,
    applied_json TEXT,                 -- אילו שינויים הוחלו בפועל בעותק המבודד
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fix_previews_finding ON fix_previews(finding_id, created_at);
CREATE TABLE IF NOT EXISTS monitors (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    account_id TEXT,
    frequency TEXT NOT NULL,           -- daily / weekly / monthly
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT NOT NULL,
    last_run_at TEXT,
    last_audit_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (site_id)
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    site_id TEXT,
    audit_id TEXT,
    kind TEXT NOT NULL,                -- new_issues / fixed_issues / score_change / audit_failed / monitor_skipped
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    data_json TEXT,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_account ON notifications(account_id, created_at);
"""

# עמודות שנוספו בגרסאות מאוחרות לטבלאות קיימות (מיגרציה בטוחה: ADD COLUMN אם חסר)
ADDED_COLUMNS = {
    "audit_events": {"agent": "TEXT"},
    "findings": {"fix_status": "TEXT NOT NULL DEFAULT 'proposed'", "priority": "INTEGER"},
    "sites": {"authorized_by": "TEXT", "authorized_at": "TEXT", "is_demo": "INTEGER NOT NULL DEFAULT 0"},
    "audits": {"trigger": "TEXT NOT NULL DEFAULT 'manual'", "cancel_requested": "INTEGER NOT NULL DEFAULT 0"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def month_start() -> str:
    n = datetime.now(timezone.utc)
    return datetime(n.year, n.month, 1, tzinfo=timezone.utc).isoformat()


def _cols(c: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def _migrate_v1(c: sqlite3.Connection) -> None:
    """מסכמה ללא חשבונות (גרסה 1) לסכמה מרובת חשבונות. נתונים קיימים נשמרים ומשויכים לחשבון הראשון שייווצר."""
    for table, col in (("conversations", "account_id"), ("conversations", "user_id"), ("research_reports", "account_id"),
                       ("audits", "account_id"), ("audits", "created_by"), ("audits", "ai_status")):
        if table in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")} and col not in _cols(c, table):
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    if "account_id" not in _cols(c, "sites"):
        c.executescript("""
            CREATE TABLE sites_v2 (id TEXT PRIMARY KEY, account_id TEXT, url TEXT NOT NULL, name TEXT,
                                   created_at TEXT NOT NULL, UNIQUE (account_id, url));
            INSERT INTO sites_v2 (id, account_id, url, name, created_at) SELECT id, NULL, url, name, created_at FROM sites;
            DROP TABLE sites;
            ALTER TABLE sites_v2 RENAME TO sites;
        """)


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE name='sites'").fetchone()
            conn.execute("PRAGMA foreign_keys = OFF")
            if has_tables and version < 2:
                _migrate_v1(conn)
            existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, cols in ADDED_COLUMNS.items():
                if table in existing:
                    have = _cols(conn, table)
                    for col, typ in cols.items():
                        if col not in have:
                            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            conn.executescript(SCHEMA)
            for table, cols in ADDED_COLUMNS.items():  # טבלאות חדשות לגמרי נוצרו עכשיו בלי העמודות
                have = _cols(conn, table)
                for col, typ in cols.items():
                    if col not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ================================================================ חשבונות ומשתמשים
    def count_users(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def create_user_with_account(self, email: str, password_hash: str, name: str | None, account_name: str,
                                 locale: str = "he", is_admin: bool = False) -> tuple[dict, dict]:
        user = {"id": uuid.uuid4().hex, "email": email, "name": name, "locale": locale,
                "is_platform_admin": int(is_admin), "created_at": _now()}
        acc = {"id": uuid.uuid4().hex, "name": account_name, "plan": "free", "subscription_status": "none",
               "created_at": _now()}
        with self._conn() as c:
            c.execute("INSERT INTO users (id, email, password_hash, name, locale, is_platform_admin, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (user["id"], email, password_hash, name, locale, int(is_admin), user["created_at"]))
            c.execute("INSERT INTO accounts (id, name, plan, subscription_status, created_at) VALUES (?, ?, ?, ?, ?)",
                      (acc["id"], account_name, "free", "none", acc["created_at"]))
            c.execute("INSERT INTO memberships (user_id, account_id, role, created_at) VALUES (?, ?, 'owner', ?)",
                      (user["id"], acc["id"], _now()))
        return user, acc

    def adopt_orphan_data(self, account_id: str) -> int:
        """נתונים מלפני מערכת החשבונות משויכים לחשבון הראשון (בעל הפלטפורמה)."""
        n = 0
        with self._conn() as c:
            for table in ("sites", "audits", "conversations", "research_reports"):
                n += c.execute(f"UPDATE {table} SET account_id = ? WHERE account_id IS NULL", (account_id,)).rowcount
        return n

    def get_user_by_email(self, email: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT id, email, name, locale, is_platform_admin, created_at, last_login_at FROM users WHERE id = ?",
                            (user_id,)).fetchone()
        return dict(row) if row else None

    def set_user_locale(self, user_id: str, locale: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE users SET locale = ? WHERE id = ?", (locale, user_id))

    def touch_login(self, user_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user_id))

    def primary_membership(self, user_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT m.account_id, m.role FROM memberships m WHERE m.user_id = ? ORDER BY m.created_at LIMIT 1",
                            (user_id,)).fetchone()
        return dict(row) if row else None

    def get_membership(self, user_id: str, account_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM memberships WHERE user_id = ? AND account_id = ?", (user_id, account_id)).fetchone()
        return dict(row) if row else None

    def get_account(self, account_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None

    def update_account(self, account_id: str, **fields: Any) -> None:
        allowed = {"name", "plan", "subscription_status", "billing_customer_id"}
        sets = [(k, v) for k, v in fields.items() if k in allowed]
        if not sets:
            return
        with self._conn() as c:
            c.execute(f"UPDATE accounts SET {', '.join(k + ' = ?' for k, _ in sets)} WHERE id = ?",
                      (*[v for _, v in sets], account_id))

    def create_session(self, token_hash: str, user_id: str, account_id: str, expires_at: str,
                       user_agent: str | None, ip: str | None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO sessions (token_hash, user_id, account_id, created_at, expires_at, user_agent, ip) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (token_hash, user_id, account_id, _now(), expires_at,
                                                       (user_agent or "")[:200], ip))

    def get_session(self, token_hash: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?", (token_hash, _now())).fetchone()
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def purge_expired_sessions(self) -> int:
        with self._conn() as c:
            return c.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now(),)).rowcount

    # ================================================================ שימוש ומכסות
    def usage(self, account_id: str, since: str | None = None) -> dict:
        since = since or month_start()
        with self._conn() as c:
            audits = c.execute("SELECT COUNT(*) FROM audits WHERE account_id = ? AND created_at >= ?", (account_id, since)).fetchone()[0]
            running = c.execute("SELECT COUNT(*) FROM audits WHERE account_id = ? AND status IN ('queued','running')",
                                (account_id,)).fetchone()[0]
            sites = c.execute("SELECT COUNT(*) FROM sites WHERE account_id = ?", (account_id,)).fetchone()[0]
            ai = c.execute("SELECT COUNT(DISTINCT audit_id), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), "
                           "COALESCE(SUM(cost_usd),0) FROM ai_runs WHERE account_id = ? AND created_at >= ? AND status = 'done'",
                           (account_id, since)).fetchone()
            chat = c.execute("SELECT COUNT(*) FROM ai_runs WHERE account_id = ? AND created_at >= ? AND kind = 'chat'",
                             (account_id, since)).fetchone()[0]
        return {"since": since, "audits": audits, "running": running, "sites": sites, "ai_analyses": ai[0] or 0,
                "ai_input_tokens": ai[1], "ai_output_tokens": ai[2], "ai_cost_usd": round(ai[3], 4), "chat_turns": chat}

    def record_ai_run(self, *, audit_id: str | None, account_id: str | None, kind: str, status: str,
                      model: str | None = None, usage: Any = None, result: Any = None, error: str | None = None) -> str:
        rid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO ai_runs (id, audit_id, account_id, kind, status, model, input_tokens, output_tokens, "
                      "cache_read_tokens, cache_write_tokens, cost_usd, result_json, error, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (rid, audit_id, account_id, kind, status, model or getattr(usage, "model", None),
                       getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0),
                       getattr(usage, "cache_read", 0), getattr(usage, "cache_write", 0),
                       getattr(usage, "cost_usd", 0.0) if usage else 0.0,
                       json.dumps(result, ensure_ascii=False) if result is not None else None, error, _now()))
        return rid

    def get_ai_runs(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM ai_runs WHERE audit_id = ? ORDER BY created_at", (audit_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["result"] = json.loads(d.pop("result_json")) if d.get("result_json") else None
            out.append(d)
        return out

    def clear_ai_results(self, audit_id: str) -> None:
        """לפני הרצה חוזרת של ניתוח AI: מסירים ממצאי AI קודמים (היסטוריית העלויות נשמרת ב-ai_runs)."""
        with self._conn() as c:
            c.execute("DELETE FROM findings WHERE audit_id = ? AND source = 'ai'", (audit_id,))

    # ================================================================ ניהול פלטפורמה
    def admin_overview(self) -> dict:
        since = month_start()
        with self._conn() as c:
            accounts = [dict(r) for r in c.execute("""
                SELECT a.id, a.name, a.plan, a.subscription_status, a.created_at,
                  (SELECT COUNT(*) FROM memberships m WHERE m.account_id = a.id) AS members,
                  (SELECT COUNT(*) FROM sites s WHERE s.account_id = a.id) AS sites,
                  (SELECT COUNT(*) FROM audits x WHERE x.account_id = a.id AND x.created_at >= ?) AS audits_month,
                  (SELECT COALESCE(SUM(cost_usd),0) FROM ai_runs r WHERE r.account_id = a.id AND r.created_at >= ?) AS ai_cost_month,
                  (SELECT u.email FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.account_id = a.id AND m.role='owner' LIMIT 1) AS owner_email
                FROM accounts a ORDER BY a.created_at DESC""", (since, since))]
            totals = {
                "accounts": len(accounts),
                "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "audits_month": c.execute("SELECT COUNT(*) FROM audits WHERE created_at >= ?", (since,)).fetchone()[0],
                "failed_audits_month": c.execute("SELECT COUNT(*) FROM audits WHERE created_at >= ? AND status='failed'", (since,)).fetchone()[0],
                "ai_cost_month": round(c.execute("SELECT COALESCE(SUM(cost_usd),0) FROM ai_runs WHERE created_at >= ?", (since,)).fetchone()[0], 4),
                "queued": c.execute("SELECT COUNT(*) FROM audits WHERE status IN ('queued','running')").fetchone()[0],
            }
        for a in accounts:
            a["ai_cost_month"] = round(a["ai_cost_month"], 4)
        return {"since": since, "totals": totals, "accounts": accounts}

    # ================================================================ צ'אט
    def create_conversation(self, account_id: str | None = None, user_id: str | None = None, title: str = "שיחה חדשה") -> dict:
        conv = {"id": uuid.uuid4().hex, "title": title, "created_at": _now(), "updated_at": _now()}
        with self._conn() as c:
            c.execute("INSERT INTO conversations (id, account_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (conv["id"], account_id, user_id, title, conv["created_at"], conv["updated_at"]))
        return conv

    def list_conversations(self, account_id: str | None = None) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE account_id IS ? "
                             "ORDER BY updated_at DESC", (account_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str, account_id: str | None = None) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND account_id IS ?",
                            (conv_id, account_id)).fetchone()
        return dict(row) if row else None

    def rename_conversation(self, conv_id: str, title: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, _now(), conv_id))

    def delete_conversation(self, conv_id: str, account_id: str | None = None) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM conversations WHERE id = ? AND account_id IS ?", (conv_id, account_id)).rowcount > 0

    def add_message(self, conv_id: str, role: str, content: Any) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO messages (conversation_id, role, content_json, created_at) VALUES (?, ?, ?, ?)",
                      (conv_id, role, json.dumps(content, ensure_ascii=False), _now()))
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conv_id))

    def get_messages(self, conv_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT role, content_json FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)).fetchall()
        return [{"role": r["role"], "content": json.loads(r["content_json"])} for r in rows]

    # ---------- בדיקת HTML מהירה (כלי של העוזר) ----------
    def save_report(self, report: dict, conversation_id: str | None = None, account_id: str | None = None) -> str:
        report_id = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO research_reports (id, account_id, url, final_url, conversation_id, report_json, created_at)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (report_id, account_id, report.get("requested_url", ""), report.get("final_url"), conversation_id,
                       json.dumps(report, ensure_ascii=False), _now()))
        return report_id

    def get_report(self, report_id: str, account_id: str | None = None) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM research_reports WHERE id = ? AND account_id IS ?", (report_id, account_id)).fetchone()
        if not row:
            return None
        rep = json.loads(row["report_json"])
        rep["id"], rep["created_at"] = row["id"], row["created_at"]
        return rep

    # ================================================================ אתרים ובדיקות
    def find_site(self, account_id: str | None, origin: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM sites WHERE account_id IS ? AND url = ?", (account_id, origin)).fetchone()
        return dict(row) if row else None

    def get_or_create_site(self, origin: str, account_id: str | None = None) -> dict:
        existing = self.find_site(account_id, origin)
        if existing:
            return existing
        site = {"id": uuid.uuid4().hex, "account_id": account_id, "url": origin, "name": None, "created_at": _now()}
        with self._conn() as c:
            c.execute("INSERT INTO sites (id, account_id, url, name, created_at) VALUES (?, ?, ?, ?, ?)",
                      (site["id"], account_id, origin, None, site["created_at"]))
        return site

    def list_sites(self, account_id: str | None = None) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM sites WHERE account_id IS ? ORDER BY created_at DESC", (account_id,))]

    def set_site_name(self, site_id: str, name: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE sites SET name = ? WHERE id = ? AND name IS NULL", (name, site_id))

    def create_audit(self, site_id: str, start_url: str, account_id: str | None = None, created_by: str | None = None,
                     trigger: str = "manual") -> dict:
        audit = {"id": uuid.uuid4().hex, "site_id": site_id, "start_url": start_url, "status": "queued",
                 "account_id": account_id, "created_at": _now(), "trigger": trigger}
        with self._conn() as c:
            c.execute("INSERT INTO audits (id, site_id, account_id, created_by, start_url, status, created_at, \"trigger\") "
                      "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)", (audit["id"], site_id, account_id, created_by, start_url, audit["created_at"], trigger))
        return audit

    def claim_next_queued(self) -> dict | None:
        """תור עבודות: לוקח את הבדיקה הוותיקה בתור ומסמן אותה כרצה (אטומי)."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT id, site_id, start_url, account_id FROM audits WHERE status = 'queued' "
                            "ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            c.execute("UPDATE audits SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'", (_now(), row["id"]))
            return dict(row)

    def update_audit(self, audit_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols, vals = [], []
        for k, v in fields.items():
            if k in ("progress", "category_scores", "facts"):
                k, v = k + "_json", json.dumps(v, ensure_ascii=False)
            cols.append(f"{k} = ?")
            vals.append(v)
        with self._conn() as c:
            c.execute(f"UPDATE audits SET {', '.join(cols)} WHERE id = ?", (*vals, audit_id))

    def fail_stale_audits(self) -> int:
        """בדיקות שהיו באמצע ריצה כשהשרת נעצר — מסומנות כנכשלו. בדיקות בתור נשארות בתור."""
        with self._conn() as c:
            return c.execute("UPDATE audits SET status='failed', error=?, finished_at=? WHERE status = 'running'",
                             ("השרת הופעל מחדש באמצע הבדיקה", _now())).rowcount

    @staticmethod
    def _audit_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("progress", "category_scores", "facts"):
            raw = d.pop(k + "_json", None)
            d[k] = json.loads(raw) if raw else None
        return d

    def get_audit(self, audit_id: str, account_id: str | None = None, *, any_account: bool = False) -> dict | None:
        q = ("SELECT a.*, s.url AS site_url, s.name AS site_name, s.is_demo FROM audits a JOIN sites s ON s.id = a.site_id WHERE a.id = ?")
        args: tuple = (audit_id,)
        if not any_account:
            q += " AND a.account_id IS ?"
            args += (account_id,)
        with self._conn() as c:
            row = c.execute(q, args).fetchone()
        return self._audit_row(row) if row else None

    def list_audits(self, account_id: str | None = None, site_id: str | None = None, limit: int = 50) -> list[dict]:
        q = ("SELECT a.id, a.site_id, a.start_url, a.status, a.score, a.category_scores_json, a.error, a.ai_status, "
             "a.created_at, a.started_at, a.finished_at, a.\"trigger\", s.url AS site_url, s.name AS site_name, s.is_demo, "
             "(SELECT COUNT(*) FROM findings f WHERE f.audit_id = a.id AND f.source = 'measured') AS finding_count "
             "FROM audits a JOIN sites s ON s.id = a.site_id WHERE a.account_id IS ?")
        args: tuple = (account_id,)
        if site_id:
            q += " AND a.site_id = ?"
            args += (site_id,)
        q += " ORDER BY a.created_at DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(q, (*args, limit)).fetchall()
        return [self._audit_row(r) for r in rows]

    def previous_done_audit(self, audit: dict) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT id FROM audits WHERE site_id = ? AND status = 'done' AND created_at < ? "
                            "ORDER BY created_at DESC LIMIT 1", (audit["site_id"], audit["created_at"])).fetchone()
        return self.get_audit(row["id"], any_account=True) if row else None

    def delete_audit(self, audit_id: str) -> list[str]:
        with self._conn() as c:
            paths = [r["path"] for r in c.execute("SELECT path FROM screenshots WHERE audit_id = ?", (audit_id,))]
            c.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
        return paths

    # ---------- יומן פעולות חי ----------
    def add_event(self, audit_id: str, kind: str, message: str, page_url: str | None = None,
                  screenshot_id: str | None = None, ref: str | None = None, agent: str | None = None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO audit_events (audit_id, at, kind, message, page_url, screenshot_id, ref, agent) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (audit_id, _now(), kind, message[:500], page_url, screenshot_id, ref, agent))

    def get_events(self, audit_id: str, after_id: int = 0, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, at, kind, message, page_url, screenshot_id, ref, agent FROM audit_events WHERE audit_id = ? AND id > ? "
                "ORDER BY id LIMIT ?", (audit_id, after_id, limit))]

    # ---------- צילומי מסך ----------
    def add_screenshot(self, audit_id: str, label: str, device: str, page_url: str | None, path: str) -> str:
        sid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO screenshots (id, audit_id, label, device, page_url, path, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (sid, audit_id, label, device, page_url, path, _now()))
        return sid

    def get_screenshot(self, sid: str, account_id: str | None = None) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT sc.* FROM screenshots sc JOIN audits a ON a.id = sc.audit_id "
                            "WHERE sc.id = ? AND a.account_id IS ?", (sid, account_id)).fetchone()
        return dict(row) if row else None

    def list_screenshots(self, audit_id: str, with_paths: bool = False) -> list[dict]:
        cols = "id, label, device, page_url" + (", path" if with_paths else "")
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                f"SELECT {cols} FROM screenshots WHERE audit_id = ? ORDER BY created_at", (audit_id,))]

    # ---------- תוצאות ----------
    def save_audit_results(self, audit_id: str, site_id: str, steps: list[dict], findings: list[dict],
                           personas: list[dict]) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM journey_steps WHERE audit_id = ?", (audit_id,))
            c.execute("DELETE FROM findings WHERE audit_id = ? AND source IN ('measured', 'simulation')", (audit_id,))
            c.execute("DELETE FROM persona_results WHERE audit_id = ?", (audit_id,))
            for i, st in enumerate(steps):
                c.execute("INSERT INTO journey_steps (audit_id, position, key, title, status, detail, page_url, "
                          "duration_ms, screenshot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (audit_id, i, st["key"], st["title"], st["status"], st.get("detail"),
                           st.get("page_url"), st.get("duration_ms"), st.get("screenshot_id")))
            for p in personas:
                c.execute("INSERT INTO persona_results (audit_id, persona, verdict, blockers_json, positives_json) "
                          "VALUES (?, ?, ?, ?, ?)", (audit_id, p["persona"], p["verdict"],
                                                     json.dumps(p["blockers"], ensure_ascii=False),
                                                     json.dumps(p["positives"], ensure_ascii=False)))
        self.add_findings(audit_id, site_id, findings)

    def add_findings(self, audit_id: str, site_id: str, findings: list[dict]) -> None:
        with self._conn() as c:
            for f in findings:
                c.execute("INSERT INTO findings (id, audit_id, site_id, rule_id, source, category, severity, impact, "
                          "title, detail, why_it_matters, fix_steps_json, evidence_json, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (uuid.uuid4().hex, audit_id, site_id, f["rule_id"], f["source"], f["category"],
                           f["severity"], f["impact"], f["title"], f["detail"], f["why_it_matters"],
                           json.dumps(f.get("fix_steps", []), ensure_ascii=False),
                           json.dumps(f.get("evidence", {}), ensure_ascii=False), _now()))

    def get_steps(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT key, title, status, detail, page_url, duration_ms, screenshot_id FROM journey_steps "
                "WHERE audit_id = ? ORDER BY position", (audit_id,))]

    @staticmethod
    def _finding_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["fix_steps"] = json.loads(d.pop("fix_steps_json"))
        d["evidence"] = json.loads(d.pop("evidence_json"))
        return d

    def get_findings(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM findings WHERE audit_id = ?", (audit_id,)).fetchall()
        return [self._finding_row(r) for r in rows]

    def list_task_findings(self, account_id: str | None, limit: int = 500) -> list[dict]:
        """ממצאים מהבדיקה האחרונה שהסתיימה של כל אתר בחשבון."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT f.*, s.url AS site_url FROM findings f JOIN sites s ON s.id = f.site_id "
                "WHERE s.account_id IS ? AND f.audit_id IN (SELECT id FROM audits a WHERE status='done' AND created_at = "
                "(SELECT MAX(created_at) FROM audits b WHERE b.site_id = a.site_id AND b.status='done')) "
                "LIMIT ?", (account_id, limit)).fetchall()
        return [self._finding_row(r) for r in rows]

    def update_finding_status(self, finding_id: str, status: str, account_id: str | None = None) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE findings SET status = ? WHERE id = ? AND audit_id IN "
                             "(SELECT id FROM audits WHERE account_id IS ?)", (status, finding_id, account_id)).rowcount > 0

    def get_personas(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT persona, verdict, blockers_json, positives_json FROM persona_results "
                             "WHERE audit_id = ? ORDER BY id", (audit_id,)).fetchall()
        return [{"persona": r["persona"], "verdict": r["verdict"], "blockers": json.loads(r["blockers_json"]),
                 "positives": json.loads(r["positives_json"])} for r in rows]

    # ================================================================ Fix Studio
    def set_fix_status(self, finding_id: str, status: str, account_id: str | None) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE findings SET fix_status = ? WHERE id = ? AND audit_id IN "
                             "(SELECT id FROM audits WHERE account_id IS ?)", (status, finding_id, account_id)).rowcount > 0

    def get_finding(self, finding_id: str, account_id: str | None) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT f.* FROM findings f JOIN audits a ON a.id = f.audit_id WHERE f.id = ? AND a.account_id IS ?",
                            (finding_id, account_id)).fetchone()
        return self._finding_row(row) if row else None

    def set_priorities(self, ranked: list[tuple[str, int]]) -> None:
        with self._conn() as c:
            c.executemany("UPDATE findings SET priority = ? WHERE id = ?", [(p, fid) for fid, p in ranked])

    def add_fix_preview(self, **row: Any) -> str:
        pid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO fix_previews (id, finding_id, audit_id, account_id, status, device, page_url, before_shot, "
                      "after_shot, applied_json, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (pid, row["finding_id"], row["audit_id"], row.get("account_id"), row["status"], row.get("device", "desktop"),
                       row.get("page_url"), row.get("before_shot"), row.get("after_shot"),
                       json.dumps(row.get("applied")) if row.get("applied") is not None else None, row.get("error"), _now()))
        return pid

    def latest_previews(self, audit_id: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM fix_previews WHERE audit_id = ? ORDER BY created_at", (audit_id,)).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            d = dict(r)
            d["applied"] = json.loads(d.pop("applied_json")) if d.get("applied_json") else None
            out[d["finding_id"]] = d
        return out

    # ================================================================ סוכני לקוח
    def create_agent_runs(self, audit_id: str, agents: list[str], engine: str) -> None:
        with self._conn() as c:
            for a in agents:
                if not c.execute("SELECT 1 FROM agent_runs WHERE audit_id = ? AND agent = ?", (audit_id, a)).fetchone():
                    c.execute("INSERT INTO agent_runs (id, audit_id, agent, engine, status) VALUES (?, ?, ?, ?, 'queued')",
                              (uuid.uuid4().hex, audit_id, a, engine))

    def update_agent_run(self, audit_id: str, agent: str, **fields: Any) -> None:
        allowed = {"status", "started_at", "finished_at", "actions", "current_url", "last_action", "last_screenshot_id",
                   "verdict", "result_json", "error"}
        sets = [(k, v) for k, v in fields.items() if k in allowed]
        if sets:
            with self._conn() as c:
                c.execute(f"UPDATE agent_runs SET {', '.join(k + ' = ?' for k, _ in sets)} WHERE audit_id = ? AND agent = ?",
                          (*[v for _, v in sets], audit_id, agent))

    def get_agent_runs(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM agent_runs WHERE audit_id = ? ORDER BY rowid", (audit_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["result"] = json.loads(d.pop("result_json")) if d.get("result_json") else None
            out.append(d)
        return out

    def interrupt_running_agents(self) -> int:
        with self._conn() as c:
            return c.execute("UPDATE agent_runs SET status = 'interrupted', error = 'השרת הופעל מחדש' "
                             "WHERE status IN ('queued','running')").rowcount

    def is_cancel_requested(self, audit_id: str) -> bool:
        with self._conn() as c:
            r = c.execute("SELECT cancel_requested FROM audits WHERE id = ?", (audit_id,)).fetchone()
        return bool(r and r[0])

    # ================================================================ אתרים מורשים + Smart Monitor + התראות
    def authorize_site(self, site_id: str, user_id: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE sites SET authorized_by = COALESCE(authorized_by, ?), authorized_at = COALESCE(authorized_at, ?) WHERE id = ?",
                      (user_id, _now(), site_id))

    def mark_demo_site(self, site_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE sites SET is_demo = 1 WHERE id = ?", (site_id,))

    def get_site(self, site_id: str, account_id: str | None) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM sites WHERE id = ? AND account_id IS ?", (site_id, account_id)).fetchone()
        return dict(row) if row else None

    def sites_overview(self, account_id: str | None) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
              SELECT s.*, m.frequency AS monitor_frequency, m.enabled AS monitor_enabled, m.next_run_at AS monitor_next,
                (SELECT COUNT(*) FROM audits a WHERE a.site_id = s.id) AS audits,
                (SELECT a.score FROM audits a WHERE a.site_id = s.id AND a.status='done' ORDER BY a.created_at DESC LIMIT 1) AS last_score,
                (SELECT a.finished_at FROM audits a WHERE a.site_id = s.id AND a.status='done' ORDER BY a.created_at DESC LIMIT 1) AS last_audit_at,
                (SELECT a.id FROM audits a WHERE a.site_id = s.id AND a.status='done' ORDER BY a.created_at DESC LIMIT 1) AS last_audit_id
              FROM sites s LEFT JOIN monitors m ON m.site_id = s.id WHERE s.account_id IS ? ORDER BY s.created_at DESC""", (account_id,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_monitor(self, site_id: str, account_id: str | None, frequency: str, enabled: bool, next_run_at: str) -> None:
        with self._conn() as c:
            if c.execute("SELECT 1 FROM monitors WHERE site_id = ?", (site_id,)).fetchone():
                c.execute("UPDATE monitors SET frequency = ?, enabled = ?, next_run_at = ? WHERE site_id = ?",
                          (frequency, int(enabled), next_run_at, site_id))
            else:
                c.execute("INSERT INTO monitors (id, site_id, account_id, frequency, enabled, next_run_at, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)", (uuid.uuid4().hex, site_id, account_id, frequency, int(enabled), next_run_at, _now()))

    def get_monitor(self, site_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM monitors WHERE site_id = ?", (site_id,)).fetchone()
        return dict(row) if row else None

    def due_monitors(self, now: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT m.*, s.url AS site_url FROM monitors m JOIN sites s ON s.id = m.site_id "
                "WHERE m.enabled = 1 AND m.next_run_at <= ?", (now,))]

    def monitor_ran(self, site_id: str, audit_id: str | None, next_run_at: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE monitors SET last_run_at = ?, last_audit_id = COALESCE(?, last_audit_id), next_run_at = ? WHERE site_id = ?",
                      (_now(), audit_id, next_run_at, site_id))

    def add_notification(self, account_id: str | None, kind: str, title: str, body: str, site_id: str | None = None,
                         audit_id: str | None = None, data: Any = None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO notifications (id, account_id, site_id, audit_id, kind, title, body, data_json, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (uuid.uuid4().hex, account_id, site_id, audit_id, kind, title, body,
                                                             json.dumps(data, ensure_ascii=False) if data is not None else None, _now()))

    def list_notifications(self, account_id: str | None, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM notifications WHERE account_id IS ? ORDER BY created_at DESC LIMIT ?", (account_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d.pop("data_json")) if d.get("data_json") else None
            out.append(d)
        return out

    def mark_notifications_read(self, account_id: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE notifications SET read_at = ? WHERE account_id IS ? AND read_at IS NULL", (_now(), account_id))

    def site_history(self, site_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, score, category_scores_json, finished_at, \"trigger\" FROM audits WHERE site_id = ? AND status = 'done' "
                             "ORDER BY created_at", (site_id,)).fetchall()
        return [{"id": r["id"], "score": r["score"], "categories": json.loads(r["category_scores_json"]) if r["category_scores_json"] else None,
                 "at": r["finished_at"], "trigger": r["trigger"]} for r in rows]
