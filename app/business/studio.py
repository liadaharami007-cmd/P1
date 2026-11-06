"""סוכני AI של המחלקות (שיווק, שירות לקוחות, מכירות/לידים, ייעוץ CEO) — על מנוע מודל אמיתי בלבד.

- הקשר העסקי (knowledge) נבנה רק מנתונים אמיתיים: פרופיל שבעל העסק הזין + טקסט שנקרא מהאתר בבדיקה האחרונה + ממצאים שנמדדו.
- כל פלט נשמר ב-ai_outputs עם המנוע והמודל, ומסומן source=ai (השערה/טיוטה — לא עובדה).
- בלי מנוע פעיל: NotConfigured — לא מחזירים תשובה מוכנה.
- הסוכנים לא שולחים הודעות, לא מפרסמים ולא משנים אתר. הם מכינים טיוטות שבעל העסק מאשר.
"""
from __future__ import annotations

import json
import uuid

from ..db import Database
from ..intelligence import engines
from . import ceo, store


class NotConfigured(Exception):
    pass


GUARD = ("כתוב בעברית פשוטה (אלא אם המשתמש כתב באנגלית). השתמש רק במידע שמופיע בהקשר העסקי. "
         "אסור להמציא מחירים, מבצעים, ביקורות, נתוני מכירות, אחוזים או הבטחות. כשמידע חסר — כתוב זאת ב-missing_info "
         "והשתמש ב-[להשלמה] במקום להמציא. התוכן הוא טיוטה לאישור בעל העסק.")


def knowledge(db: Database, account: dict) -> dict:
    snap = ceo.snapshot(db, account)
    L = snap["latest"] or {}
    ex = (L.get("facts") or {}).get("page_excerpts") or {}
    return {"profile": snap["profile"],
            "site": snap["site"]["url"] if snap["site"] else None,
            "site_text": {k: (v or "")[:2500] for k, v in ex.items()},
            "measured_issues": [f["title"] for f in snap["findings"] if f["source"] == "measured"][:20],
            "latest_score": L.get("score")}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": required or list(props)}


S = {"type": "string"}
LS = {"type": "array", "items": S}
TASKS: dict[str, dict] = {
    "marketing_strategy": {
        "system": "אתה אסטרטג שיווק לעסקים קטנים בישראל. בנה אסטרטגיה מעשית לחודש הקרוב.",
        "schema": _obj({"summary": S, "audiences": {"type": "array", "items": _obj({"name": S, "pain": S, "message": S})},
                        "channels": {"type": "array", "items": _obj({"channel": S, "why": S, "first_step": S})},
                        "offer_ideas": LS, "first_week": LS, "missing_info": LS})},
    "ad_copy": {
        "system": "אתה קופירייטר למודעות ממומנות (Meta/Google). כתוב וריאציות קצרות וממירות.",
        "schema": _obj({"variants": {"type": "array", "items": _obj({"platform": S, "headline": S, "primary_text": S, "cta": S, "angle": S})},
                        "missing_info": LS})},
    "content_calendar": {
        "system": "אתה מנהל תוכן. בנה לוח תוכן לשבועיים לרשתות החברתיות.",
        "schema": _obj({"posts": {"type": "array", "items": _obj({"day": S, "platform": S, "format": S, "idea": S, "caption": S})},
                        "missing_info": LS})},
    "video_script": {
        "system": "אתה במאי תוכן UGC. כתוב תסריט סרטון קצר (15–30 שניות) לרשתות. יצירת הווידאו עצמו לא מחוברת — רק תסריט וסטוריבורד.",
        "schema": _obj({"hook": S, "scenes": {"type": "array", "items": _obj({"seconds": S, "visual": S, "voiceover": S})},
                        "cta": S, "missing_info": LS})},
    "support_answer": {
        "system": ("אתה נציג שירות של העסק. ענה ללקוח רק לפי המידע בהקשר העסקי (פרופיל + טקסט מהאתר). "
                   "אם התשובה לא נמצאת במידע — אל תנחש: answerable=false והצע להעביר לנציג אנושי."),
        "schema": _obj({"answer": S, "answerable": {"type": "boolean"}, "sources": LS, "handoff_reason": S, "missing_info": LS})},
    "lead_triage": {
        "system": "אתה מנהל מכירות. סווג פנייה של לקוח פוטנציאלי והכן טיוטת תשובה (לא נשלחת אוטומטית).",
        "schema": _obj({"intent": S, "urgency": {"type": "string", "enum": ["high", "medium", "low"]}, "summary": S,
                        "objections": LS, "draft_reply": S, "next_step": S, "missing_info": LS})},
    "consult": {
        "system": ("אתה P1 CEO — יועץ עסקי. ענה לשאלה של בעל העסק על בסיס ההקשר העסקי והממצאים שנמדדו. "
                   "היה ענייני וקצר, תן צעדים מעשיים, וציין על מה כל המלצה מבוססת."),
        "schema": _obj({"answer": S, "steps": LS, "based_on": LS, "missing_info": LS})},
}


async def run(db: Database, account: dict, user_id: str | None, kind: str, user_input: str, extra: dict | None = None,
              engine=None) -> dict:
    if kind not in TASKS:
        raise ValueError("סוג משימה לא מוכר")
    t = TASKS[kind]
    return await run_custom(db, account, user_id, kind, t["system"], t["schema"], user_input, extra=extra, engine=engine)


async def run_custom(db: Database, account: dict, user_id: str | None, kind: str, system: str, schema: dict, user_input: str,
                     extra: dict | None = None, engine=None) -> dict:
    """הרצת סוכן על מנוע אמיתי עם הקשר עסקי אמיתי. extra = הקשר נוסף (למשל תוצרים של סוכנים קודמים)."""
    eng = engine or engines.active_engine()
    if eng is None:
        raise NotConfigured("אין מנוע מודל פעיל. חברו Gemini (חינם) או Claude במסך 'חיבורים'.")
    kb = knowledge(db, account)
    payload = {"business_context": kb, "request": user_input[:4000], **(extra or {})}
    data, usage = await eng.structured(system=system + "\n" + GUARD, schema=schema, max_tokens=8000,
                                       content=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)[:60000]}])
    db.record_ai_run(audit_id=None, account_id=account["id"], kind=f"studio:{kind}", status="done", usage=usage, result=data)
    oid = uuid.uuid4().hex
    with db._conn() as c:
        c.execute("INSERT INTO ai_outputs (id, account_id, kind, input, output_json, engine, model, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (oid, account["id"], kind, user_input[:4000], json.dumps(data, ensure_ascii=False), getattr(eng, "id", "ai"), usage.model, user_id, store.now()))
    store.log(db, account["id"], "ai_output", f"P1 הכין: {kind}", ref_type="ai_output", ref_id=oid, user_id=user_id)
    return {"id": oid, "kind": kind, "source": "ai", "engine": getattr(eng, "id", "ai"), "model": usage.model, "output": data,
            "grounded_on": {"profile_fields": sorted(kb["profile"]), "site_pages": sorted(kb["site_text"]), "issues": len(kb["measured_issues"])}}


def history(db: Database, account_id: str, kind: str | None = None, limit: int = 30) -> list[dict]:
    q, a = "SELECT * FROM ai_outputs WHERE account_id=?", [account_id]
    if kind:
        q += " AND kind=?"
        a.append(kind)
    with db._conn() as c:
        rows = c.execute(q + " ORDER BY created_at DESC LIMIT ?", (*a, limit)).fetchall()
    return [{**{k: r[k] for k in ("id", "kind", "input", "engine", "model", "created_at")}, "output": json.loads(r["output_json"]), "source": "ai"} for r in rows]


# ---------------------------------------------------------------- לידים (מכירות) — CRUD אמיתי, AI רק לסיווג וטיוטה
LEAD_STATUSES = ("new", "contacted", "won", "lost")


def add_lead(db: Database, account_id: str, name: str, contact: str, channel: str, message: str, client_id: str | None = None) -> dict:
    lid = uuid.uuid4().hex
    with db._conn() as c:
        c.execute("INSERT INTO leads (id, account_id, client_id, name, contact, channel, message, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'new', ?, ?)",
                  (lid, account_id, client_id, name[:120], contact[:200], channel[:40], message[:4000], store.now(), store.now()))
    return get_lead(db, lid, account_id)  # type: ignore[return-value]


def get_lead(db: Database, lead_id: str, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT * FROM leads WHERE id=? AND account_id=?", (lead_id, account_id)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["ai"] = json.loads(d.pop("ai_json")) if d.get("ai_json") else None
    return d


def list_leads(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM leads WHERE account_id=? ORDER BY created_at DESC LIMIT 300", (account_id,))]
    return [get_lead(db, i, account_id) for i in ids]  # type: ignore[misc]


def update_lead(db: Database, lead_id: str, account_id: str, **fields) -> None:
    if "ai" in fields:
        fields["ai_json"] = json.dumps(fields.pop("ai"), ensure_ascii=False)
    fields["updated_at"] = store.now()
    with db._conn() as c:
        c.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in fields)} WHERE id=? AND account_id=?", (*fields.values(), lead_id, account_id))


def remind_followups(db: Database) -> int:
    """נקרא מה-worker כל דקה: פנייה שהגיע זמן המעקב שלה → התראה אחת (בתוך המערכת; לא נשלחת הודעה ללקוח)."""
    now = store.now()
    with db._conn() as c:
        due = [dict(r) for r in c.execute("SELECT id, account_id, name FROM leads WHERE follow_up_at IS NOT NULL AND follow_up_at <= ? "
                                          "AND reminded_at IS NULL AND status IN ('new','contacted')", (now,))]
        for d in due:
            c.execute("UPDATE leads SET reminded_at=? WHERE id=?", (now, d["id"]))
    for d in due:
        db.add_notification(d["account_id"], "lead_followup", f"תזכורת: לחזור ל{d['name']}", "הגיע זמן המעקב שקבעתם")
    return len(due)


def funnel(db: Database, account_id: str) -> dict:
    """משפך מכירה מנתוני ה-CRM בלבד (נמדד). אחוז סגירה רק כשיש מספיק פניות שהוכרעו."""
    ls = list_leads(db, account_id)
    by = {s: [x for x in ls if x["status"] == s] for s in LEAD_STATUSES}
    decided = len(by["won"]) + len(by["lost"])
    by_channel: dict[str, int] = {}
    for x in ls:
        by_channel[x["channel"] or "other"] = by_channel.get(x["channel"] or "other", 0) + 1
    return {"stages": {s: len(v) for s, v in by.items()}, "by_channel": by_channel,
            "win_rate": round(100 * len(by["won"]) / decided) if decided >= 5 else None,
            "win_rate_note": None if decided >= 5 else "אחוז סגירה יוצג אחרי 5 פניות שהוכרעו (נסגר/לא רלוונטי)",
            "won_value": round(sum(x.get("value") or 0 for x in by["won"]), 2),
            "open_value": round(sum(x.get("value") or 0 for x in by["new"] + by["contacted"]), 2),
            "opportunities": [{"id": x["id"], "name": x["name"], "reason": (x.get("ai") or {}).get("summary")}
                              for x in ls if x["status"] in ("new", "contacted") and (x.get("ai") or {}).get("urgency") == "high"][:10]}


def leads_summary(db: Database, account_id: str) -> dict:
    from datetime import datetime, timedelta, timezone
    ls = list_leads(db, account_id)
    stale = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    now = store.now()
    return {"followups_due": sum(1 for x in ls if x.get("follow_up_at") and x["follow_up_at"] <= now and x["status"] in ("new", "contacted")),
            "total": len(ls), "new": sum(1 for x in ls if x["status"] == "new"),
            "unanswered_24h": sum(1 for x in ls if x["status"] == "new" and x["created_at"] < stale),
            "won": sum(1 for x in ls if x["status"] == "won"), "lost": sum(1 for x in ls if x["status"] == "lost")}
