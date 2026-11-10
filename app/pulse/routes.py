"""ClientPulse OS — API. כל נקודה דורשת התחברות (Ctx) ומסננת לפי ctx.account_id."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from ..db import Database
from ..saas.auth import Ctx, current
from . import ask as ask_mod, demo, engine, report, service as S, store

STATIC = Path(__file__).resolve().parent.parent / "static" / "pulse"


class ClientIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    industry: str | None = Field(None, max_length=80)
    owner: str | None = Field(None, max_length=40)
    target_cpl: float | None = Field(None, ge=0, le=1e6)
    monthly_budget: float | None = Field(None, ge=0, le=1e8)
    fee_monthly: float | None = Field(None, ge=0, le=1e7)
    hours_monthly: float | None = Field(None, ge=0, le=1000)
    hourly_cost: float | None = Field(None, ge=0, le=10000)
    other_costs_monthly: float | None = Field(None, ge=0, le=1e7)
    website: str | None = Field(None, max_length=300)
    platforms: list[str] | None = None
    thresholds: dict[str, float] | None = None


class CsvIn(BaseModel):
    csv: str = Field(..., max_length=2_000_000)


class NoteIn(BaseModel):
    kind: str = Field("note", pattern="^(note|call|meeting|decision)$")
    text: str = Field(..., min_length=1, max_length=4000)


class TaskIn(BaseModel):
    alert_key: str = Field(..., max_length=80)
    assignee: str | None = Field(None, max_length=40)


class ManualTaskIn(BaseModel):
    client_id: str = Field(..., max_length=40)
    title: str = Field(..., min_length=2, max_length=200)
    assignee: str | None = Field(None, max_length=40)
    due_days: int = Field(3, ge=1, le=30)
    source: str = Field("manual", pattern="^(manual|opportunity)$")


class DraftIn(BaseModel):
    client_id: str = Field(..., max_length=40)
    kind: str = Field(..., max_length=40)


class TaskActIn(BaseModel):
    extra: str | int | None = None


class FeedbackIn(BaseModel):
    key: str = Field(..., max_length=80)
    verdict: str


class RuleIn(BaseModel):
    on: bool


class AskIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=500)
    ai: bool = True


class ScenarioIn(BaseModel):
    scenario: str
    client_id: str | None = None


class AdvanceIn(BaseModel):
    days: int = Field(1, ge=1, le=14)


class MemberIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    role: str = Field("עובד", max_length=40)
    approver: bool = False


class AssumptionsIn(BaseModel):
    minPerClient: float = Field(..., ge=0, le=120)
    minPerAlert: float = Field(..., ge=0, le=240)
    workdays: int = Field(..., ge=1, le=31)


def _strip(r: dict) -> dict:
    """תוצאת ניתוח בלי רשימת הימים (כבדה) — לרשימות."""
    return {k: v for k, v in r.items() if k not in ("days",)}


def register(app: FastAPI, db: Database) -> None:
    store.ensure(db)

    def W(ctx: Ctx) -> dict:
        S.ensure_member(db, ctx.account_id, ctx.user, ctx.role)
        return S.ws(db, ctx.account_id)

    def can_approve(ctx: Ctx) -> bool:
        return ctx.role in ("owner", "admin") or ctx.is_admin

    def uname(ctx: Ctx) -> str:
        return ctx.user.get("name") or ctx.user["email"].split("@")[0]

    @app.get("/pulse")
    @app.get("/pulse/")
    def pulse_page():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # ---------------------------------------------------------------- מצב כללי
    @app.get("/api/pulse/state")
    def state(ctx: Ctx = Depends(current)):
        w = W(ctx)
        ref = S.ref_day(w)
        unread = store.one(db, "SELECT COUNT(*) n FROM pulse_notifications WHERE account_id=? AND read=0", (ctx.account_id,))["n"]
        n_clients = store.one(db, "SELECT COUNT(*) n FROM pulse_clients WHERE account_id=?", (ctx.account_id,))["n"]
        return {"demo": w["settings"].get("demo", False), "ref": ref, "ref_label": engine.fmt_day(ref), "ref_iso": engine.iso_of(ref),
                "offset": w["offset"], "last_run": w["last_run"], "team": S.team(db, ctx.account_id), "can_approve": can_approve(ctx),
                "user": {"name": uname(ctx), "role": ctx.role}, "unread": unread, "clients": n_clients, "agency": ctx.account.get("name"),
                "auto_daily": w["settings"].get("auto_daily", True)}

    @app.post("/api/pulse/demo")
    def demo_start(ctx: Ctx = Depends(current)):
        W(ctx)
        return {"ok": True, "check": S.seed_demo(db, ctx.account_id)}

    @app.delete("/api/pulse/demo")
    def demo_remove(ctx: Ctx = Depends(current)):
        W(ctx)
        S.remove_demo(db, ctx.account_id)
        return {"ok": True}

    @app.post("/api/pulse/check")
    def check(ctx: Ctx = Depends(current)):
        W(ctx)
        return S.run_check(db, ctx.account_id, manual=True, user=uname(ctx))

    # ---------------------------------------------------------------- מרכז פיקוד
    @app.get("/api/pulse/overview")
    def overview(ctx: Ctx = Depends(current)):
        w = W(ctx)
        acc = ctx.account_id
        run = S.analysis(db, acc)
        ref = run["ref"]
        states = S.alert_rows(db, acc)
        tasks = S.open_tasks(db, acc)
        res = run["results"]
        tw = engine.stats([d for r in res for d in r["days"] if ref - d["_i"] < 7])
        lw = engine.stats([d for r in res for d in r["days"] if 7 <= ref - d["_i"] < 14])
        risk = []
        for r in res:
            rk = engine.churn_risk(r, [a for a in states.values() if a["client_id"] == r["id"]], [t for t in tasks if t["client_id"] == r["id"]], ref)
            if rk["level"] in ("high", "medium") and r["status"] != "red":
                risk.append({"id": r["id"], "name": r["name"], "level": rk["level"], "reasons": rk["reasons"][:2]})
        risk.sort(key=lambda x: x["level"] != "high")
        changes = store.rows(db, "SELECT * FROM pulse_events WHERE account_id=? AND day>=? AND type IN ('alert','cleared','verified','verify_failed') ORDER BY id DESC LIMIT 12",
                             (acc, ref - 1))
        feed = store.rows(db, "SELECT * FROM pulse_events WHERE account_id=? ORDER BY id DESC LIMIT 16", (acc,))
        summ = S.summary_text(db, acc, run)
        return {"counts": run["counts"], "excess": run["excess"], "spend30": run["spend30"], "ms": run["ms"], "ref": ref,
                "summary": summ["parts"], "today": S.top_actions(db, acc, run, 5),
                "urgent": [{"id": r["id"], "name": r["name"], "title": r["alerts"][0]["title"], "what": r["alerts"][0]["what"],
                            "handling": (states.get(r["alerts"][0]["key"]) or {}).get("status")} for r in res if r["status"] == "red"][:8],
                "improved": [{"id": r["id"], "name": r["name"], "what": r["improved"]["what"]} for r in res if r["improved"]],
                "risk": risk[:6],
                "stale": [{"id": r["id"], "name": r["name"], "lag": r["lag"]} for r in res if r["lag"] >= 1],
                "tasks": {"open": len(tasks), "not_started": sum(1 for t in tasks if t["status"] == "new"),
                          "late": sum(1 for t in tasks if t["due_day"] is not None and t["due_day"] < ref and t["status"] in ("new", "in_progress", "awaiting_approval")),
                          "approval": sum(1 for t in tasks if t["status"] == "awaiting_approval")},
                "opps": sum(len(engine.opportunities(r, run["clients"][r["id"]])) for r in res),
                "week": {"spend": tw["spend"], "leads": tw["leads"], "cpl": tw["cpl"], "prev_spend": lw["spend"], "prev_leads": lw["leads"], "prev_cpl": lw["cpl"],
                         "sales": tw["sales"] if tw["has_sales"] else None, "prev_sales": lw["sales"] if lw["has_sales"] else None},
                "changes": changes, "feed": feed, "last_run": w["last_run"], "demo": w["settings"].get("demo", False)}

    # ---------------------------------------------------------------- לקוחות
    @app.get("/api/pulse/clients")
    def clients(ctx: Ctx = Depends(current)):
        W(ctx)
        run = S.analysis(db, ctx.account_id)
        states = S.alert_rows(db, ctx.account_id)
        out = []
        for r in run["results"]:
            c = run["clients"][r["id"]]
            out.append({"id": r["id"], "name": r["name"], "industry": r["industry"], "owner": r["owner"], "status": r["status"],
                        "is_demo": r["is_demo"], "health": r["health"]["score"], "improved": bool(r["improved"]), "lowData": r["lowData"],
                        "alerts": [{"title": a["title"], "severity": a["severity"], "type": a["type"], "handling": (states.get(a["key"]) or {}).get("status")} for a in r["alerts"]],
                        "cpl": r["rec"]["cpl"], "base_cpl": r["base"]["cpl"], "leads": r["rec"]["leads"], "spend": r["rec"]["spend"],
                        "target": r["goals"].get("targetCpl"), "lag": r["lag"], "source": c["source"], "priority": r["priority"]})
        return {"clients": out, "ref": run["ref"]}

    @app.post("/api/pulse/clients", status_code=201)
    def add_client(body: ClientIn, ctx: Ctx = Depends(current)):
        W(ctx)
        if not body.name:
            raise HTTPException(422, "שם לקוח חובה")
        return S.upsert_client(db, ctx.account_id, body.model_dump(exclude_none=True))

    @app.patch("/api/pulse/clients/{cid}")
    def edit_client(cid: str, body: ClientIn, ctx: Ctx = Depends(current)):
        W(ctx)
        try:
            return S.upsert_client(db, ctx.account_id, body.model_dump(exclude_unset=True), cid)
        except KeyError:
            raise HTTPException(404, "לקוח לא נמצא")

    @app.delete("/api/pulse/clients/{cid}")
    def del_client(cid: str, ctx: Ctx = Depends(current)):
        W(ctx)
        if not can_approve(ctx):
            raise HTTPException(403, "מחיקת לקוח מותרת רק לבעלים / מנהל")
        if not S.get_client(db, ctx.account_id, cid):
            raise HTTPException(404, "לקוח לא נמצא")
        S.delete_client(db, ctx.account_id, cid)
        return {"ok": True}

    @app.post("/api/pulse/clients/{cid}/import")
    def import_csv(cid: str, body: CsvIn, ctx: Ctx = Depends(current)):
        W(ctx)
        c = S.get_client(db, ctx.account_id, cid)
        if not c:
            raise HTTPException(404, "לקוח לא נמצא")
        if c["is_demo"]:
            raise HTTPException(400, "אי אפשר לייבא נתונים אמיתיים ללקוח דמו — צרו לקוח חדש")
        return S.import_csv(db, ctx.account_id, cid, body.csv)

    @app.get("/api/pulse/clients/{cid}")
    def client_detail(cid: str, days: int = 30, ctx: Ctx = Depends(current)):
        W(ctx)
        acc = ctx.account_id
        run = S.analysis(db, acc)
        r = run["byId"].get(cid)
        if not r:
            raise HTTPException(404, "לקוח לא נמצא")
        c = run["clients"][cid]
        states = S.alert_rows(db, acc, cid)
        alerts = []
        for a in r["alerts"]:
            st = states.get(a["key"], {})
            t = S.open_task_for(db, acc, a["key"])
            alerts.append({**a, "inv": engine.investigate(r, a), "handling": st.get("status"), "first_day": st.get("first_day"),
                           "history": st.get("history", []), "feedback": st.get("feedback"), "task": t})
        past = [s for k, s in states.items() if s["status"] in ("cleared", "resolved", "dismissed") and k not in {a["key"] for a in r["alerts"]}]
        events = store.rows(db, "SELECT * FROM pulse_events WHERE account_id=? AND client_id=? ORDER BY id DESC LIMIT 60", (acc, cid))
        tasks = S.all_tasks(db, acc, cid)
        days = max(7, min(90, days))
        return {"client": {k: v for k, v in c.items() if k != "params"}, "result": _strip(r), "alerts": alerts, "past_alerts": past,
                "series": S.series(r, days), "rolling": S.rolling_cpl(r, days), "events": events, "tasks": tasks,
                "notes": store.rows(db, "SELECT * FROM pulse_notes WHERE account_id=? AND client_id=? ORDER BY id DESC", (acc, cid)),
                "drafts": store.rows(db, "SELECT * FROM pulse_drafts WHERE account_id=? AND client_id=? ORDER BY id DESC", (acc, cid)),
                "opportunities": engine.opportunities(r, c), "profit": engine.profitability(c, r),
                "risk": engine.churn_risk(r, list(states.values()), [t for t in tasks if t["status"] != "closed"], run["ref"]),
                "thresholds": {k: {"label": v[0], "min": v[1], "max": v[2], "default": engine.THRESHOLDS[k], "value": c["thresholds"].get(k)}
                               for k, v in engine.EDITABLE.items()},
                "ref": run["ref"]}

    @app.post("/api/pulse/clients/{cid}/notes", status_code=201)
    def add_note(cid: str, body: NoteIn, ctx: Ctx = Depends(current)):
        W(ctx)
        if not S.get_client(db, ctx.account_id, cid):
            raise HTTPException(404, "לקוח לא נמצא")
        store.exe(db, "INSERT INTO pulse_notes (account_id, client_id, kind, text, user_name, created_at) VALUES (?,?,?,?,?,?)",
                  (ctx.account_id, cid, body.kind, body.text, uname(ctx), store.now()))
        S.ev(db, ctx.account_id, S.ref_day(S.ws(db, ctx.account_id)), "note",
             {"note": "הערה", "call": "תיעוד שיחה", "meeting": "סיכום פגישה", "decision": "החלטה"}[body.kind] + ": " + body.text[:80], cid, uname(ctx))
        return {"ok": True}

    # ---------------------------------------------------------------- התראות (משוב) · משימות
    @app.post("/api/pulse/alerts/feedback")
    def feedback(body: FeedbackIn, ctx: Ctx = Depends(current)):
        W(ctx)
        return S.alert_feedback(db, ctx.account_id, body.key, body.verdict, uname(ctx))

    @app.get("/api/pulse/tasks")
    def tasks(ctx: Ctx = Depends(current)):
        w = W(ctx)
        run = S.analysis(db, ctx.account_id)
        names = {cid: c["name"] for cid, c in run["clients"].items()}
        ts = S.all_tasks(db, ctx.account_id)
        for t in ts:
            t["client_name"] = names.get(t["client_id"], "—")
        return {"tasks": ts, "ref": S.ref_day(w), "status": S.STATUS, "actions": S.ACTION, "team": S.workload(db, ctx.account_id)}

    @app.post("/api/pulse/tasks", status_code=201)
    def new_task(body: TaskIn, ctx: Ctx = Depends(current)):
        W(ctx)
        try:
            return S.create_task(db, ctx.account_id, S.analysis(db, ctx.account_id), body.alert_key, by="user", assignee=body.assignee, by_name=uname(ctx))
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/pulse/tasks/manual", status_code=201)
    def manual_task(body: ManualTaskIn, ctx: Ctx = Depends(current)):
        W(ctx)
        try:
            return S.create_manual_task(db, ctx.account_id, body.client_id, body.title, body.assignee, body.due_days, uname(ctx), body.source)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/pulse/opportunities/draft")
    def opp_draft(body: DraftIn, ctx: Ctx = Depends(current)):
        W(ctx)
        try:
            return S.proposal_draft(db, ctx.account_id, body.client_id, body.kind, uname(ctx))
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/pulse/tasks/{tid}/{action}")
    def task_act(tid: str, action: str, body: TaskActIn | None = None, ctx: Ctx = Depends(current)):
        W(ctx)
        if action == "simulate_fix":
            return S.simulate_fix(db, ctx.account_id, tid)
        try:
            return S.task_action(db, ctx.account_id, tid, action, user_name=uname(ctx), can_approve=can_approve(ctx), extra=(body.extra if body else None))
        except KeyError:
            raise HTTPException(404, "משימה לא נמצאה")

    # ---------------------------------------------------------------- התראות פנימיות
    @app.get("/api/pulse/notifications")
    def notifications(ctx: Ctx = Depends(current)):
        W(ctx)
        return store.rows(db, "SELECT * FROM pulse_notifications WHERE account_id=? ORDER BY id DESC LIMIT 60", (ctx.account_id,))

    @app.post("/api/pulse/notifications/read")
    def notif_read(ctx: Ctx = Depends(current)):
        store.exe(db, "UPDATE pulse_notifications SET read=1 WHERE account_id=?", (ctx.account_id,))
        return {"ok": True}

    # ---------------------------------------------------------------- אוטומציות
    @app.get("/api/pulse/automations")
    def automations(ctx: Ctx = Depends(current)):
        w = W(ctx)
        runs = store.rows(db, "SELECT * FROM pulse_automation_runs WHERE account_id=? ORDER BY id DESC LIMIT 80", (ctx.account_id,))
        counts = {r["id"]: 0 for r in S.RULES}
        for r in store.rows(db, "SELECT rule_id, COUNT(*) n FROM pulse_automation_runs WHERE account_id=? AND status='ok' GROUP BY rule_id", (ctx.account_id,)):
            counts[r["rule_id"]] = r["n"]
        return {"rules": [{**r, "on": w["settings"]["rules"].get(r["id"], r["on"]), "runs": counts.get(r["id"], 0)} for r in S.RULES],
                "log": runs, "auto_daily": w["settings"].get("auto_daily", True),
                "schedule": "השרת מריץ בדיקה מלאה פעם ביום (הבדיקה הראשונה אחרי חצות UTC) כשה-worker פעיל, ובכל לחיצה על 'הרץ בדיקה'"}

    @app.put("/api/pulse/automations/{rid}")
    def set_rule(rid: str, body: RuleIn, ctx: Ctx = Depends(current)):
        w = W(ctx)
        if rid == "auto_daily":
            w["settings"]["auto_daily"] = body.on
        elif rid in {r["id"] for r in S.RULES}:
            w["settings"]["rules"][rid] = body.on
        else:
            raise HTTPException(404, "כלל לא קיים")
        if not can_approve(ctx):
            raise HTTPException(403, "שינוי אוטומציות מותר לבעלים / מנהל")
        S.save_settings(db, ctx.account_id, w["settings"])
        S.ev(db, ctx.account_id, S.ref_day(w), "automation", f"{'הופעל' if body.on else 'כובה'}: {S.rule_name(rid) if rid != 'auto_daily' else 'בדיקה יומית אוטומטית'}", user=uname(ctx))
        return {"ok": True}

    @app.post("/api/pulse/automations/{rid}/test")
    def test_rule(rid: str, ctx: Ctx = Depends(current)):
        W(ctx)
        if rid not in {r["id"] for r in S.RULES}:
            raise HTTPException(404, "כלל לא קיים")
        return {"would": S.dry_run(db, ctx.account_id, rid), "note": "בדיקה יבשה: שום דבר לא בוצע"}

    # ---------------------------------------------------------------- Ask
    @app.post("/api/pulse/ask")
    async def ask(body: AskIn, ctx: Ctx = Depends(current)):
        W(ctx)
        return await ask_mod.ask(db, ctx.account_id, body.q, body.ai)

    @app.get("/api/pulse/ask/suggestions")
    def ask_sugg(ctx: Ctx = Depends(current)):
        from ..intelligence import engines
        try:
            eng = engines.active_engine()
            label = f"{eng.id} ({eng.model})" if eng else None
        except Exception:  # noqa: BLE001
            label = None
        return {"suggestions": ask_mod.SUGGESTIONS, "engine": label}

    # ---------------------------------------------------------------- ערך · צוות · רווחיות · הזדמנויות
    @app.get("/api/pulse/impact")
    def impact(ctx: Ctx = Depends(current)):
        W(ctx)
        return S.impact(db, ctx.account_id)

    @app.put("/api/pulse/impact/assumptions")
    def set_assumptions(body: AssumptionsIn, ctx: Ctx = Depends(current)):
        w = W(ctx)
        w["settings"]["assumptions"] = body.model_dump()
        S.save_settings(db, ctx.account_id, w["settings"])
        return {"ok": True}

    @app.get("/api/pulse/team")
    def team(ctx: Ctx = Depends(current)):
        W(ctx)
        return {"team": S.workload(db, ctx.account_id), "can_manage": can_approve(ctx)}

    @app.post("/api/pulse/team", status_code=201)
    def add_member(body: MemberIn, ctx: Ctx = Depends(current)):
        W(ctx)
        if not can_approve(ctx):
            raise HTTPException(403, "הוספת עובדים מותרת לבעלים / מנהל")
        mid = "e" + uuid.uuid4().hex[:8]
        store.exe(db, "INSERT INTO pulse_team (account_id, id, name, role, approver) VALUES (?,?,?,?,?)",
                  (ctx.account_id, mid, body.name, body.role, 1 if body.approver else 0))
        return {"ok": True, "id": mid}

    @app.get("/api/pulse/profit")
    def profit(ctx: Ctx = Depends(current)):
        W(ctx)
        run = S.analysis(db, ctx.account_id)
        out, missing = [], []
        for r in run["results"]:
            f = engine.profitability(run["clients"][r["id"]], r)
            if f:
                out.append({"id": r["id"], "name": r["name"], "status": r["status"], "is_demo": r["is_demo"], **f})
            else:
                missing.append({"id": r["id"], "name": r["name"]})
        out.sort(key=lambda x: x["margin"] if x["margin"] is not None else 9)
        tot_fee = sum(x["fee"] for x in out)
        tot_cost = sum(x["costs"] for x in out)
        return {"clients": out, "missing": missing, "total": {"fee": tot_fee, "costs": tot_cost, "profit": tot_fee - tot_cost,
                                                               "margin": (tot_fee - tot_cost) / tot_fee if tot_fee else None},
                "note": "הכנסת הסוכנות (ריטיינר) מופרדת מתקציב הפרסום של הלקוח. עלות עבודה = שעות × עלות שעה שהוזנו."}

    @app.get("/api/pulse/opportunities")
    def opps(ctx: Ctx = Depends(current)):
        W(ctx)
        run = S.analysis(db, ctx.account_id)
        return [{"client_id": r["id"], "client": r["name"], "is_demo": r["is_demo"], **o} for r in run["results"]
                for o in engine.opportunities(r, run["clients"][r["id"]])]

    # ---------------------------------------------------------------- Demo Lab
    @app.get("/api/pulse/lab")
    def lab(ctx: Ctx = Depends(current)):
        w = W(ctx)
        return {"scenarios": demo.SCENARIOS, "demo": w["settings"].get("demo", False), "offset": w["offset"]}

    @app.post("/api/pulse/lab/scenario")
    def lab_scenario(body: ScenarioIn, ctx: Ctx = Depends(current)):
        W(ctx)
        return S.apply_scenario(db, ctx.account_id, body.scenario, body.client_id)

    @app.post("/api/pulse/lab/advance")
    def lab_advance(body: AdvanceIn, ctx: Ctx = Depends(current)):
        W(ctx)
        return S.advance(db, ctx.account_id, body.days)

    # ---------------------------------------------------------------- טיוטות · דוחות · חיבורים
    @app.get("/api/pulse/drafts")
    def drafts(ctx: Ctx = Depends(current)):
        return store.rows(db, "SELECT * FROM pulse_drafts WHERE account_id=? ORDER BY id DESC LIMIT 50", (ctx.account_id,))

    @app.post("/api/pulse/drafts/{did}/approve")
    def approve_draft(did: int, ctx: Ctx = Depends(current)):
        W(ctx)
        if not can_approve(ctx):
            raise HTTPException(403, "אישור הודעה ללקוח מותר לבעלים / מנהל")
        n = store.exe(db, "UPDATE pulse_drafts SET status='approved', approved_by=? WHERE account_id=? AND id=?", (uname(ctx), ctx.account_id, did))
        if not n:
            raise HTTPException(404, "טיוטה לא נמצאה")
        return {"ok": True, "msg": "אושר. השליחה ידנית (העתקה) — WhatsApp Business לא מחובר לחשבון הזה"}

    @app.get("/api/pulse/reports/client/{cid}.html")
    def report_html(cid: str, days: int = 30, ctx: Ctx = Depends(current)):
        W(ctx)
        h = report.client_report_html(db, ctx.account_id, cid, max(7, min(90, days)), ctx.account.get("name") or "")
        if not h:
            raise HTTPException(404, "לקוח לא נמצא")
        return HTMLResponse(h)

    @app.get("/api/pulse/reports/client/{cid}.pdf")
    async def report_pdf(cid: str, days: int = 30, ctx: Ctx = Depends(current)):
        W(ctx)
        h = report.client_report_html(db, ctx.account_id, cid, max(7, min(90, days)), ctx.account.get("name") or "")
        if not h:
            raise HTTPException(404, "לקוח לא נמצא")
        try:
            pdf = await report.to_pdf(h)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, f"יצירת PDF נכשלה ({type(e).__name__}). אפשר להדפיס את גרסת ה-HTML ל-PDF מהדפדפן")
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="report-{cid}.pdf"'})

    @app.get("/api/pulse/reports/weekly.html")
    def weekly(ctx: Ctx = Depends(current)):
        W(ctx)
        return HTMLResponse(report.weekly_html(db, ctx.account_id, ctx.account.get("name") or ""))

    @app.get("/api/pulse/integrations")
    def integrations(ctx: Ctx = Depends(current)):
        w = W(ctx)
        from ..intelligence import engines
        try:
            stt = engines.status()
            ai = [e for e in stt["engines"] if e["id"] == stt["active"] and e["id"] != "rules"]
        except Exception:  # noqa: BLE001
            ai = []
        n_csv = store.one(db, "SELECT COUNT(*) n FROM pulse_clients WHERE account_id=? AND source='csv'", (ctx.account_id,))["n"]
        return [
            {"id": "demo", "name": "נתוני דמו", "status": "connected" if w["settings"].get("demo") else "off", "kind": "ads",
             "note": "50 לקוחות מדומים, 90 ימי היסטוריה. מסומן 'דמו' בכל מקום"},
            {"id": "csv", "name": "ייבוא CSV (Meta / Google / כל מקור)", "status": "connected" if n_csv else "available", "kind": "ads",
             "note": f"{n_csv} לקוחות עם נתונים מיובאים" if n_csv else "זמין עכשיו: בתיק לקוח → ייבוא נתונים. עמודות: date, spend, impressions, clicks, leads (sales, revenue אופציונלי)"},
            {"id": "meta", "name": "Meta Marketing API", "status": "not_connected", "kind": "ads",
             "needs": "אפליקציית Meta for Developers + הרשאת ads_read + System User token (נשמר בכספת המוצפנת בשרת). ממשק המתאם מוכן: הוא כותב לאותה טבלת נתונים"},
            {"id": "google_ads", "name": "Google Ads API", "status": "not_connected", "kind": "ads", "needs": "Developer token מאושר + OAuth לחשבון MCC"},
            {"id": "crm", "name": "CRM (איכות לידים ומכירות)", "status": "not_connected", "kind": "crm",
             "needs": "API של ה-CRM (או עמודות sales/revenue ב-CSV). בלי זה לא מחושבים שיעור סגירה, CAC ו-ROAS"},
            {"id": "whatsapp", "name": "WhatsApp Business Platform", "status": "not_connected", "kind": "out",
             "needs": "WABA מאומת + תבניות מאושרות. עד אז: טיוטות להעתקה בלבד"},
            {"id": "email", "name": "Email", "status": "not_connected", "kind": "out", "needs": "ספק שליחה (SMTP) בשרת"},
            {"id": "ai", "name": "מודל AI לסוכן", "status": "connected" if ai else "not_connected", "kind": "ai",
             "note": ", ".join(e["name"] for e in ai) if ai else "", "needs": "" if ai else "GEMINI_API_KEY (חינם) או ANTHROPIC_API_KEY בשרת. עד אז הסוכן עונה ממנוע כללים"},
        ]
