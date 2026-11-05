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
