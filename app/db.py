"""שכבת שמירת נתונים — SQLite (קובץ אחד, בלי שרת).

שומרים כל הודעה בדיוק בפורמט שה-API של Claude מצפה לו (JSON),
כך שאפשר להמשיך כל שיחה מאיפה שעצרה.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
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
    url TEXT NOT NULL,
    final_url TEXT,
    conversation_id TEXT,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ===== מנוע הבדיקות (Audits) =====
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,          -- origin מנורמל, למשל https://shop.co.il
    name TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    start_url TEXT NOT NULL,
    status TEXT NOT NULL,              -- queued / running / done / failed
    progress_json TEXT NOT NULL DEFAULT '[]',
    score INTEGER,
    category_scores_json TEXT,
    facts_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_audits_site ON audits(site_id, created_at);
CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    device TEXT NOT NULL,              -- desktop / mobile
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
    status TEXT NOT NULL,              -- passed / failed / warning / skipped
    detail TEXT,
    page_url TEXT,
    duration_ms INTEGER,
    screenshot_id TEXT
);
-- source מפריד בין סוגי המידע:
--   measured   = נבדק בפועל בדפדפן אמיתי
--   simulation = סימולציית לקוח (מבוססת כללים על נתונים שנמדדו)
--   store_data = נתונים אמיתיים מחיבור לחנות (עתידי)
--   ai         = השערה/המלצה של מודל AI (עתידי)
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,            -- critical / high / medium / low
    impact TEXT NOT NULL,              -- הערכת השפעה על מכירות: high / medium / low
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    fix_steps_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', -- open / in_progress / done / dismissed
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_audit ON findings(audit_id);
CREATE TABLE IF NOT EXISTS persona_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    persona TEXT NOT NULL,
    verdict TEXT NOT NULL,             -- likely_buy / hesitant / likely_leave
    blockers_json TEXT NOT NULL,
    positives_json TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- שיחות ----------
    def create_conversation(self, title: str = "שיחה חדשה") -> dict:
        conv = {"id": uuid.uuid4().hex, "title": title, "created_at": _now(), "updated_at": _now()}
        with self._conn() as c:
            c.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv["id"], conv["title"], conv["created_at"], conv["updated_at"]),
            )
        return conv

    def list_conversations(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        return dict(row) if row else None

    def rename_conversation(self, conv_id: str, title: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), conv_id),
            )

    def delete_conversation(self, conv_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        return cur.rowcount > 0

    # ---------- הודעות ----------
    def add_message(self, conv_id: str, role: str, content: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages (conversation_id, role, content_json, created_at) VALUES (?, ?, ?, ?)",
                (conv_id, role, json.dumps(content, ensure_ascii=False), _now()),
            )
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conv_id))

    def get_messages(self, conv_id: str) -> list[dict]:
        """מחזיר את ההודעות בפורמט ה-API: [{'role': ..., 'content': ...}, ...]"""
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content_json FROM messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,),
            ).fetchall()
        return [{"role": r["role"], "content": json.loads(r["content_json"])} for r in rows]

    # ---------- דוחות חקירת אתרים ----------
    def save_report(self, report: dict, conversation_id: str | None = None) -> str:
        report_id = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO research_reports (id, url, final_url, conversation_id, report_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report_id,
                    report.get("requested_url", ""),
                    report.get("final_url"),
                    conversation_id,
                    json.dumps(report, ensure_ascii=False),
                    _now(),
                ),
            )
        return report_id

    def list_reports(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, url, final_url, conversation_id, created_at, report_json"
                " FROM research_reports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            rep = json.loads(r["report_json"])
            out.append({
                "id": r["id"], "url": r["url"], "final_url": r["final_url"],
                "conversation_id": r["conversation_id"], "created_at": r["created_at"],
                "ok": rep.get("ok"), "score": rep.get("score"),
                "issue_count": len(rep.get("issues", [])),
            })
        return out

    def get_report(self, report_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM research_reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        rep = json.loads(row["report_json"])
        rep["id"] = row["id"]
        rep["created_at"] = row["created_at"]
        return rep

    # ================================================================ Audits
    def get_or_create_site(self, origin: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM sites WHERE url = ?", (origin,)).fetchone()
            if row:
                return dict(row)
            site = {"id": uuid.uuid4().hex, "url": origin, "name": None, "created_at": _now()}
            c.execute("INSERT INTO sites (id, url, name, created_at) VALUES (?, ?, ?, ?)",
                      (site["id"], site["url"], site["name"], site["created_at"]))
            return site

    def list_sites(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM sites ORDER BY created_at DESC")]

    def set_site_name(self, site_id: str, name: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE sites SET name = ? WHERE id = ? AND name IS NULL", (name, site_id))

    def create_audit(self, site_id: str, start_url: str) -> dict:
        audit = {"id": uuid.uuid4().hex, "site_id": site_id, "start_url": start_url,
                 "status": "queued", "created_at": _now()}
        with self._conn() as c:
            c.execute("INSERT INTO audits (id, site_id, start_url, status, created_at) VALUES (?, ?, ?, ?, ?)",
                      (audit["id"], site_id, start_url, "queued", audit["created_at"]))
        return audit

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
        """בדיקות שנשארו 'רצות' אחרי הפעלה מחדש של השרת — מסומנות כנכשלו."""
        with self._conn() as c:
            cur = c.execute("UPDATE audits SET status='failed', error=?, finished_at=? "
                            "WHERE status IN ('queued','running')",
                            ("השרת הופעל מחדש באמצע הבדיקה", _now()))
            return cur.rowcount

    @staticmethod
    def _audit_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("progress", "category_scores", "facts"):
            raw = d.pop(k + "_json", None)
            d[k] = json.loads(raw) if raw else None
        return d

    def get_audit(self, audit_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT a.*, s.url AS site_url, s.name AS site_name FROM audits a "
                            "JOIN sites s ON s.id = a.site_id WHERE a.id = ?", (audit_id,)).fetchone()
        return self._audit_row(row) if row else None

    def list_audits(self, site_id: str | None = None, limit: int = 50) -> list[dict]:
        q = ("SELECT a.id, a.site_id, a.start_url, a.status, a.score, a.category_scores_json, a.error, "
             "a.created_at, a.finished_at, s.url AS site_url, s.name AS site_name, "
             "(SELECT COUNT(*) FROM findings f WHERE f.audit_id = a.id) AS finding_count "
             "FROM audits a JOIN sites s ON s.id = a.site_id")
        args: tuple = ()
        if site_id:
            q += " WHERE a.site_id = ?"
            args = (site_id,)
        q += " ORDER BY a.created_at DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(q, (*args, limit)).fetchall()
        return [self._audit_row(r) for r in rows]

    def delete_audit(self, audit_id: str) -> list[str]:
        """מוחק בדיקה ומחזיר את נתיבי צילומי המסך למחיקה מהדיסק."""
        with self._conn() as c:
            paths = [r["path"] for r in c.execute("SELECT path FROM screenshots WHERE audit_id = ?", (audit_id,))]
            c.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
        return paths

    def add_screenshot(self, audit_id: str, label: str, device: str, page_url: str | None, path: str) -> str:
        sid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("INSERT INTO screenshots (id, audit_id, label, device, page_url, path, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (sid, audit_id, label, device, page_url, path, _now()))
        return sid

    def get_screenshot(self, sid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM screenshots WHERE id = ?", (sid,)).fetchone()
        return dict(row) if row else None

    def list_screenshots(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, label, device, page_url FROM screenshots WHERE audit_id = ? ORDER BY created_at", (audit_id,))]

    def save_audit_results(self, audit_id: str, site_id: str, steps: list[dict],
                           findings: list[dict], personas: list[dict]) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM journey_steps WHERE audit_id = ?", (audit_id,))
            c.execute("DELETE FROM findings WHERE audit_id = ?", (audit_id,))
            c.execute("DELETE FROM persona_results WHERE audit_id = ?", (audit_id,))
            for i, st in enumerate(steps):
                c.execute("INSERT INTO journey_steps (audit_id, position, key, title, status, detail, page_url, "
                          "duration_ms, screenshot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (audit_id, i, st["key"], st["title"], st["status"], st.get("detail"),
                           st.get("page_url"), st.get("duration_ms"), st.get("screenshot_id")))
            for f in findings:
                c.execute("INSERT INTO findings (id, audit_id, site_id, rule_id, source, category, severity, impact, "
                          "title, detail, why_it_matters, fix_steps_json, evidence_json, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (uuid.uuid4().hex, audit_id, site_id, f["rule_id"], f["source"], f["category"],
                           f["severity"], f["impact"], f["title"], f["detail"], f["why_it_matters"],
                           json.dumps(f.get("fix_steps", []), ensure_ascii=False),
                           json.dumps(f.get("evidence", {}), ensure_ascii=False), _now()))
            for p in personas:
                c.execute("INSERT INTO persona_results (audit_id, persona, verdict, blockers_json, positives_json) "
                          "VALUES (?, ?, ?, ?, ?)",
                          (audit_id, p["persona"], p["verdict"], json.dumps(p["blockers"], ensure_ascii=False),
                           json.dumps(p["positives"], ensure_ascii=False)))

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

    def list_open_findings(self, limit: int = 100) -> list[dict]:
        """בעיות מהבדיקה האחרונה (שהסתיימה) של כל אתר."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT f.*, s.url AS site_url FROM findings f JOIN sites s ON s.id = f.site_id "
                "WHERE f.audit_id IN (SELECT id FROM audits a WHERE status='done' AND created_at = "
                "(SELECT MAX(created_at) FROM audits b WHERE b.site_id = a.site_id AND b.status='done')) "
                "LIMIT ?", (limit,)).fetchall()
        return [self._finding_row(r) for r in rows]

    def update_finding_status(self, finding_id: str, status: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE findings SET status = ? WHERE id = ?", (status, finding_id))
        return cur.rowcount > 0

    def get_personas(self, audit_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT persona, verdict, blockers_json, positives_json FROM persona_results "
                             "WHERE audit_id = ? ORDER BY id", (audit_id,)).fetchall()
        return [{"persona": r["persona"], "verdict": r["verdict"], "blockers": json.loads(r["blockers_json"]),
                 "positives": json.loads(r["positives_json"])} for r in rows]
