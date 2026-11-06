"""P1 Autopilot — בקשה אחת בשפה חופשית → P1 CEO מפרק לצעדים → סוכנים רצים ברצף ומעבירים תוצרים זה לזה.

עקרונות:
- כל צעד = סוכן אמיתי (מודל / בדיקה / CRM). אין תוצאות מוכנות.
- כל סוכן מקבל את סיכומי הסוכנים הקודמים (handoff) — כך תוכנית השיווק נשענת על הבעיות שנמצאו, המודעות על התוכנית, ודף הנחיתה על שניהם.
- פעולות חיצוניות / שצורכות מכסה (בדיקת אתר, פרסום דף) לא רצות לבד: נוצרת פעולה במרכז האישורים.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from ..db import Database
from ..intelligence import engines
from . import actions, ceo, pages, store, studio

log = logging.getLogger("p1")
AGENTS = {
    "audit": "בדיקת האתר וממצאים שנמדדו", "research": "מחקר מתחרים ושוק", "strategy": "אסטרטגיית שיווק",
    "ads": "מודעות לפייסבוק/אינסטגרם/גוגל", "content": "לוח תוכן", "video": "תסריט סרטון", "landing_page": "דף נחיתה",
    "leads": "סקירת לידים ומכירות", "tasks": "תוכנית עבודה ומשימות",
}
KEYWORDS = [("audit", r"תבדוק|בדיקה|בעיות|אתר|audit|check"), ("research", r"מתחר|מחקר|שוק|research|competitor"),
            ("strategy", r"תוכנית שיווק|אסטרטגי|שיווק|marketing|strategy"), ("ads", r"מודע|פרסום|קמפיין|ads|campaign"),
            ("content", r"תוכן|פוסט|לוח|content|post"), ("video", r"סרטון|וידאו|video|reel"),
            ("landing_page", r"דף נחיתה|landing|עמוד"), ("leads", r"ליד|פניות|מכירות|לקוחות|lead|sales"),
            ("tasks", r"משימות|תנהל|ניהול|tasks|manage")]
ORDER = list(AGENTS)
PLAN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["steps", "reply"],
               "properties": {"reply": {"type": "string"}, "steps": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["agent", "goal"],
                   "properties": {"agent": {"type": "string", "enum": ORDER}, "goal": {"type": "string"}}}}}}
RESEARCH_SCHEMA = {"type": "object", "additionalProperties": False,
                   "required": ["source_note", "competitors", "market_insights", "differentiation", "missing_info"],
                   "properties": {"source_note": {"type": "string"},
                                  "competitors": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["name", "positioning", "strengths", "weaknesses"],
                                                  "properties": {"name": {"type": "string"}, "positioning": {"type": "string"},
                                                                 "strengths": {"type": "string"}, "weaknesses": {"type": "string"}}}},
                                  "market_insights": {"type": "array", "items": {"type": "string"}},
                                  "differentiation": {"type": "array", "items": {"type": "string"}},
                                  "missing_info": {"type": "array", "items": {"type": "string"}}}}


def rule_plan(text: str) -> list[dict]:
    hit = [a for a, pat in KEYWORDS if re.search(pat, text or "", re.I)]
    hit = hit or ["audit", "strategy", "tasks"]
    return [{"agent": a, "goal": AGENTS[a]} for a in ORDER if a in hit]


async def plan(db: Database, account: dict, text: str, engine=None) -> tuple[list[dict], str, str]:
    eng = engine or engines.active_engine()
    if eng is None:
        return rule_plan(text), "rules", ""
    try:
        data, _ = await eng.structured(
            system=("אתה P1 CEO. פרק את הבקשה של בעל העסק לצעדים לפי הסוכנים הזמינים בלבד (enum), בסדר הגיוני: "
                    "קודם בדיקה/מחקר, אחר כך אסטרטגיה, ואז תוצרים (מודעות, תוכן, דף נחיתה), ובסוף משימות. "
                    "בחר רק סוכנים שהבקשה צריכה. reply = משפט קצר בעברית שמסביר מה תעשה."),
            schema=PLAN_SCHEMA, max_tokens=2000, content=[{"type": "text", "text": text[:2000]}])
        steps = [s for s in data["steps"] if s["agent"] in AGENTS]
        seen, uniq = set(), []
        for s in sorted(steps, key=lambda s: ORDER.index(s["agent"])):
            if s["agent"] not in seen:
                seen.add(s["agent"])
                uniq.append(s)
        return (uniq or rule_plan(text)), "ai", data.get("reply", "")
    except Exception as e:  # noqa: BLE001 — המתכנן נכשל → פירוק לפי כללים, ומסומן כך
        log.warning("autopilot planner failed: %s", e)
        return rule_plan(text), "rules", ""


def create(db: Database, account: dict, user_id: str | None, text: str, steps: list[dict], planner: str, reply: str) -> dict:
    rid = uuid.uuid4().hex
    p = {"reply": reply, "steps": [{**s, "status": "pending", "summary": None, "ref": None, "error": None} for s in steps]}
    with db._conn() as c:
        c.execute("INSERT INTO runs (id, account_id, request, plan_json, status, planner, created_by, created_at) VALUES (?,?,?,?, 'running', ?,?,?)",
                  (rid, account["id"], text[:2000], json.dumps(p, ensure_ascii=False), planner, user_id, store.now()))
    store.log(db, account["id"], "run_started", f"Autopilot: {text[:80]}", ref_type="run", ref_id=rid, user_id=user_id)
    return get(db, rid, account["id"])  # type: ignore[return-value]


def get(db: Database, rid: str, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=? AND account_id=?", (rid, account_id)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["plan"] = json.loads(d.pop("plan_json"))
    return d


def list_runs(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        return [{**dict(r), "plan": json.loads(r["plan_json"])} for r in
                c.execute("SELECT * FROM runs WHERE account_id=? ORDER BY created_at DESC LIMIT 20", (account_id,))]


def _save(db: Database, run: dict, status: str | None = None) -> None:
    with db._conn() as c:
        c.execute("UPDATE runs SET plan_json=?, status=COALESCE(?, status), finished_at=CASE WHEN ? IS NULL THEN finished_at ELSE ? END WHERE id=?",
                  (json.dumps(run["plan"], ensure_ascii=False), status, status, store.now(), run["id"]))


def _short(o: dict) -> str:
    """סיכום קצר של תוצר — מה שעובר לסוכן הבא."""
    keys = ("summary", "answer", "differentiation", "market_insights", "audiences", "variants", "posts", "hook", "first_week")
    parts = []
    for k in keys:
        v = o.get(k)
        if v:
            parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)[:600]}")
    return " | ".join(parts)[:1500]


async def execute(db: Database, runner, account: dict, user_id: str | None, rid: str, engine=None) -> None:
    run = get(db, rid, account["id"])
    if not run:
        return
    handoff: list[dict] = []
    failed = False
    for step in run["plan"]["steps"]:
        step["status"] = "running"
        _save(db, run)
        try:
            summary, ref = await _step(db, runner, account, user_id, step, handoff, run["request"], engine)
            step.update(status="done" if not (ref or {}).get("needs_approval") else "awaiting_approval", summary=summary, ref=ref)
            handoff.append({"agent": step["agent"], "summary": summary})
        except studio.NotConfigured as e:
            step.update(status="failed", error=str(e))
            failed = True
        except Exception as e:  # noqa: BLE001 — כל כשל נשמר על הצעד ומוצג; הסוכנים הבאים ממשיכים
            log.warning("autopilot step %s failed: %s", step["agent"], e)
            step.update(status="failed", error=str(e)[:300])
        _save(db, run)
    _save(db, run, "failed" if failed and not any(s["status"] == "done" for s in run["plan"]["steps"]) else "done")
    store.log(db, account["id"], "run_done", f"Autopilot הסתיים: {sum(1 for s in run['plan']['steps'] if s['status'] == 'done')} צעדים בוצעו",
              ref_type="run", ref_id=rid)
    db.add_notification(account["id"], "run_done", "Autopilot סיים", run["request"][:120])


async def _step(db, runner, account, user_id, step, handoff, request, engine) -> tuple[str, dict | None]:
    a = step["agent"]
    extra = {"previous_agents": handoff, "goal": step["goal"]}
    if a == "audit":
        snap = ceo.snapshot(db, account)
        L = snap["latest"]
        measured = [f["title"] for f in snap["findings"] if f["source"] == "measured"]
        if L:
            return (f"נמצאה בדיקה מ-{(L.get('finished_at') or '')[:10]} (ציון {L.get('score')}). בעיות שנמדדו: " + "; ".join(measured[:10]),
                    {"type": "audit", "id": L["id"]})
        if snap["site"]:
            act = actions.propose(db, account, user_id, {"key": f"audit:{snap['site']['id']}", "kind": "run_audit", "title": "בדיקת האתר בדפדפן אמיתי",
                                                         "why": "Autopilot צריך נתונים מדודים מהאתר.", "payload": {"site_id": snap["site"]["id"], "url": snap["site"]["url"]}})
            return "אין עדיין בדיקה — הוכנה בדיקה לאישור (נספרת במכסה).", {"type": "action", "id": act["id"], "needs_approval": True}
        return "אין אתר בחשבון — לא ניתן לבדוק. הוסיפו אתר במסך 'אתרים'.", None
    if a == "research":
        res = await studio.run_custom(db, account, user_id, "research",
                                      "אתה חוקר שוק. נתח מתחרים והזדמנויות לעסק. אין לך גישה חיה לאינטרנט כרגע: כתוב ב-source_note "
                                      "שהניתוח מבוסס על ידע כללי של המודל ועל המתחרים שבעל העסק ציין, ושיש לאמת. אל תמציא מחירים או נתונים מספריים.",
                                      RESEARCH_SCHEMA, request, extra=extra, engine=engine)
        return _short(res["output"]), {"type": "ai_output", "id": res["id"]}
    if a == "video":
        res = await studio.run(db, account, user_id, "video_script", request, extra=extra, engine=engine)
        o = res["output"]
        scenes = ([{"seconds": "3", "visual": "", "voiceover": o["hook"]}] if o.get("hook") else []) + list(o.get("scenes") or [])
        if not scenes:
            return _short(o) or "נכתב תסריט", {"type": "ai_output", "id": res["id"]}
        from . import video
        v = await video.render(db, account, user_id, scenes, o.get("cta") or "", (request or "סרטון")[:60])
        return f"נכתב תסריט ונוצר סרטון MP4 ({v['seconds']} שנ'). {_short(o)[:300]}", {"type": "video", "id": v["id"], "url": v["url"]}
    kind = {"strategy": "marketing_strategy", "ads": "ad_copy", "content": "content_calendar"}.get(a)
    if kind:
        res = await studio.run(db, account, user_id, kind, request, extra=extra, engine=engine)
        return _short(res["output"]) or "הוכן", {"type": "ai_output", "id": res["id"]}
    if a == "landing_page":
        pg = await pages.generate(db, account, user_id, request, engine=engine, extra=extra)
        return f"נבנה דף נחיתה: {pg['spec']['title']} ({len(pg['spec']['sections'])} חלקים). לפרסום — נדרש אישור.", {"type": "page", "id": pg["id"]}
    if a == "leads":
        s = studio.leads_summary(db, account["id"])
        return (f"{s['total']} פניות · {s['new']} חדשות · {s['unanswered_24h']} מחכות מעל 24 שעות · {s['won']} נסגרו", {"type": "leads"})
    if a == "tasks":
        p = ceo.plan(ceo.snapshot(db, account))
        return "3 הפעולות הבאות: " + " · ".join(i["title"] for i in p["top3"]), {"type": "plan"}
    raise ValueError("סוכן לא מוכר")


async def plan_and_execute(db: Database, runner, account: dict, user_id: str | None, rid: str, engine=None) -> None:
    run = get(db, rid, account["id"])
    steps, planner, reply = await plan(db, account, run["request"], engine=engine)
    run["plan"] = {"reply": reply, "steps": [{**s, "status": "pending", "summary": None, "ref": None, "error": None} for s in steps]}
    with db._conn() as c:
        c.execute("UPDATE runs SET planner=? WHERE id=?", (planner, rid))
    _save(db, run)
    await execute(db, runner, account, user_id, rid, engine=engine)


def start_background(db: Database, runner, account: dict, user_id: str | None, rid: str) -> None:
    """התכנון והביצוע רצים ברקע — המסך מתעדכן בזמן אמת ולא מחכה למודל."""
    asyncio.get_running_loop().create_task(plan_and_execute(db, runner, account, user_id, rid))
