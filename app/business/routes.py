"""נתיבי API של Business OS. כל נתיב דורש משתמש מחובר ומסנן לפי החשבון שלו."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..db import Database
from ..intelligence import engines
from ..saas.auth import Ctx, current
from . import actions, agency, autopilot, brain, ceo, missions, pages, store, studio


class ProfileIn(BaseModel):
    data: dict[str, Any]


class ActionIn(BaseModel):
    key: str


class IntentIn(BaseModel):
    text: str | None = None
    intent: str | None = None


class MissionIn(BaseModel):
    intent: str
    answers: dict[str, Any] = {}


class StudioIn(BaseModel):
    kind: str
    input: str = ""


class LeadIn(BaseModel):
    name: str
    contact: str = ""
    channel: str = "other"
    message: str = ""


class LeadPatch(BaseModel):
    status: str | None = None
    notes: str | None = None


class RunIn(BaseModel):
    request: str


class PageIn(BaseModel):
    brief: str = ""


class PageEditIn(BaseModel):
    instruction: str


class VersionIn(BaseModel):
    version: int


class ClientIn(BaseModel):
    name: str
    url: str
    industry: str | None = None
    confirm_permission: bool = False


def register(app: FastAPI, db: Database, runner, browser_available: Callable[[], tuple[bool, str | None]]) -> None:

    def _action_or_404(action_id: str, ctx: Ctx) -> dict:
        a = store.get_action(db, action_id, ctx.account_id)
        if not a:
            raise HTTPException(404, "הפעולה לא נמצאה")
        return a

    @app.get("/api/business/profile")
    def get_profile(ctx: Ctx = Depends(current)):
        p = store.get_profile(db, ctx.account_id)
        data = p["data"] if p else {}
        return {"data": data, "updated_at": p["updated_at"] if p else None, "completeness": brain.completeness(data),
                "options": {"business_type": brain.BUSINESS_TYPES, "goals": brain.GOALS, "channels": brain.CHANNELS}}

    @app.put("/api/business/profile")
    def put_profile(body: ProfileIn, ctx: Ctx = Depends(current)):
        try:
            data = brain.clean(body.data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        first = store.get_profile(db, ctx.account_id) is None
        store.save_profile(db, ctx.account_id, data, ctx.user_id)
        store.log(db, ctx.account_id, "profile_created" if first else "profile_updated",
                  "נוצר פרופיל העסק" if first else "פרופיל העסק עודכן", user_id=ctx.user_id)
        return get_profile(ctx)

    @app.get("/api/business/overview")
    def overview(ctx: Ctx = Depends(current)):
        for a in store.list_actions(db, ctx.account_id, "executing"):
            actions.refresh(db, a)
        snap = ceo.snapshot(db, ctx.account)
        L = snap["latest"]
        return {"profile": snap["profile"], "completeness": snap["completeness"],
                "site": snap["site"], "latest": {k: L.get(k) for k in ("id", "score", "finished_at", "start_url", "is_demo")} if L else None,
                "health": ceo.health(snap), "plan": ceo.plan(snap), "proof": ceo.proof(db, snap),
                "pending_actions": [a for a in store.list_actions(db, ctx.account_id) if a["status"] in ("proposed", "executing")],
                "engines": engines.status()["active"]}

    @app.get("/api/business/value")
    def value(ctx: Ctx = Depends(current)):
        return ceo.value(db, ctx.account)

    @app.get("/api/business/weekly")
    def weekly(ctx: Ctx = Depends(current)):
        return ceo.weekly(db, ceo.snapshot(db, ctx.account))

    @app.get("/api/business/timeline")
    def timeline(ctx: Ctx = Depends(current)):
        return {"items": ceo.timeline(db, ceo.snapshot(db, ctx.account))}

    @app.post("/api/business/brief")
    async def brief(ctx: Ctx = Depends(current)):
        engine = engines.active_engine()
        if engine is None:
            return {"ai_status": "not_configured", "engine": "rules",
                    "missing": "אין מנוע מודל פעיל: חסר ANTHROPIC_API_KEY, או שרת Ollama מקומי לא רץ."}
        try:
            return {"ai_status": "done", **(await ceo.ai_brief(db, ceo.snapshot(db, ctx.account), engine))}
        except Exception as e:  # noqa: BLE001 — כשל במנוע מוצג כמו שהוא, בלי תשובה מומצאת
            db.record_ai_run(audit_id=None, account_id=ctx.account_id, kind="ceo_brief", status="failed", error=str(e)[:300])
            raise HTTPException(502, f"המנוע לא החזיר תשובה: {str(e)[:200]}")

    # ------------------------------------------------------------ P1 CEO: כוונה → שאלות → משימה + תוכנית
    @app.post("/api/ceo/intent")
    def ceo_intent(body: IntentIn, ctx: Ctx = Depends(current)):
        if body.intent:
            if body.intent not in missions.INTENTS:
                raise HTTPException(400, "מסלול לא מוכר")
            res = {"intent": body.intent, "label": missions.INTENTS[body.intent], "source": "choice", "matched": None}
        else:
            if not (body.text or "").strip():
                raise HTTPException(400, "כתבו מה תרצו להשיג")
            res = missions.classify(body.text[:2000])
        prof = (store.get_profile(db, ctx.account_id) or {"data": {}})["data"]
        return {**res, "questions": missions.questions_for(res["intent"], prof), "ai": missions.ceo_engine_active()}

    @app.post("/api/missions", status_code=201)
    def create_mission(body: MissionIn, ctx: Ctx = Depends(current)):
        from ..saas import plans
        try:
            return missions.create_mission(db, ctx.account, ctx.user_id, body.intent, body.answers)
        except (ValueError, plans.QuotaError) as e:
            raise HTTPException(400, getattr(e, "message", None) or str(e))

    @app.get("/api/missions")
    def list_missions(ctx: Ctx = Depends(current)):
        return {"items": missions.list_missions(db, ctx.account_id)}

    @app.get("/api/missions/{mission_id}")
    def get_mission(mission_id: str, ctx: Ctx = Depends(current)):
        m = missions.get_mission(db, mission_id, ctx.account_id)
        if not m:
            raise HTTPException(404, "המשימה לא נמצאה")
        return m

    @app.get("/api/ceo/today")
    def ceo_today(ctx: Ctx = Depends(current)):
        return missions.today(db, ctx.account)

    # ------------------------------------------------------------ סוכני המחלקות (שיווק / שירות / ייעוץ) — מנוע מודל אמיתי בלבד
    @app.post("/api/studio/run")
    async def studio_run(body: StudioIn, ctx: Ctx = Depends(current)):
        from ..intelligence.client import IntelligenceError
        if not body.input.strip() and body.kind not in ("marketing_strategy", "content_calendar"):
            raise HTTPException(400, "כתבו מה לבקש")
        try:
            return await studio.run(db, ctx.account, ctx.user_id, body.kind, body.input)
        except studio.NotConfigured as e:
            raise HTTPException(503, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except IntelligenceError as e:
            db.record_ai_run(audit_id=None, account_id=ctx.account_id, kind=f"studio:{body.kind}", status="failed", error=str(e)[:300])
            raise HTTPException(502, str(e))

    @app.get("/api/studio/history")
    def studio_history(kind: str | None = None, ctx: Ctx = Depends(current)):
        return {"items": studio.history(db, ctx.account_id, kind), "ai": missions.ceo_engine_active()}

    # ------------------------------------------------------------ לידים
    @app.get("/api/leads")
    def leads(ctx: Ctx = Depends(current)):
        return {"items": studio.list_leads(db, ctx.account_id), "summary": studio.leads_summary(db, ctx.account_id),
                "ai": missions.ceo_engine_active()}

    @app.post("/api/leads", status_code=201)
    def add_lead(body: LeadIn, ctx: Ctx = Depends(current)):
        if not body.name.strip():
            raise HTTPException(400, "חסר שם")
        lead = studio.add_lead(db, ctx.account_id, body.name.strip(), body.contact, body.channel, body.message)
        store.log(db, ctx.account_id, "lead_added", f"פנייה חדשה: {lead['name']}", ref_type="lead", ref_id=lead["id"], user_id=ctx.user_id)
        return lead

    @app.patch("/api/leads/{lead_id}")
    def patch_lead(lead_id: str, body: LeadPatch, ctx: Ctx = Depends(current)):
        if not studio.get_lead(db, lead_id, ctx.account_id):
            raise HTTPException(404, "הפנייה לא נמצאה")
        fields = {}
        if body.status is not None:
            if body.status not in studio.LEAD_STATUSES:
                raise HTTPException(400, "סטטוס לא חוקי")
            fields["status"] = body.status
        if body.notes is not None:
            fields["notes"] = body.notes[:2000]
        if fields:
            studio.update_lead(db, lead_id, ctx.account_id, **fields)
        return studio.get_lead(db, lead_id, ctx.account_id)

    @app.delete("/api/leads/{lead_id}", status_code=204)
    def delete_lead(lead_id: str, ctx: Ctx = Depends(current)):
        with db._conn() as c:
            if not c.execute("DELETE FROM leads WHERE id=? AND account_id=?", (lead_id, ctx.account_id)).rowcount:
                raise HTTPException(404, "הפנייה לא נמצאה")

    @app.post("/api/leads/{lead_id}/triage")
    async def triage_lead(lead_id: str, ctx: Ctx = Depends(current)):
        from ..intelligence.client import IntelligenceError
        lead = studio.get_lead(db, lead_id, ctx.account_id)
        if not lead:
            raise HTTPException(404, "הפנייה לא נמצאה")
        try:
            res = await studio.run(db, ctx.account, ctx.user_id, "lead_triage",
                                   f"פנייה מ-{lead['name']} ({lead['channel']}): {lead['message']}")
        except studio.NotConfigured as e:
            raise HTTPException(503, str(e))
        except IntelligenceError as e:
            raise HTTPException(502, str(e))
        studio.update_lead(db, lead_id, ctx.account_id, ai={**res["output"], "model": res["model"]})
        return studio.get_lead(db, lead_id, ctx.account_id)

    # ------------------------------------------------------------ Autopilot: בקשה אחת → כמה סוכנים ברצף
    @app.post("/api/autopilot", status_code=202)
    async def autopilot_run(body: RunIn, ctx: Ctx = Depends(current)):
        if not body.request.strip():
            raise HTTPException(400, "כתבו מה תרצו ש-P1 יעשה")
        run = autopilot.create(db, ctx.account, ctx.user_id, body.request, [], "pending", "")
        autopilot.start_background(db, runner, ctx.account, ctx.user_id, run["id"])
        return run

    @app.get("/api/autopilot")
    def autopilot_list(ctx: Ctx = Depends(current)):
        return {"items": autopilot.list_runs(db, ctx.account_id), "ai": missions.ceo_engine_active()}

    @app.get("/api/autopilot/{rid}")
    def autopilot_get(rid: str, ctx: Ctx = Depends(current)):
        r = autopilot.get(db, rid, ctx.account_id)
        if not r:
            raise HTTPException(404, "לא נמצא")
        return r

    # ------------------------------------------------------------ בונה דפי נחיתה
    def _page(pid: str, ctx: Ctx) -> dict:
        pg = pages.get(db, pid, ctx.account_id)
        if not pg:
            raise HTTPException(404, "הדף לא נמצא")
        return pg

    async def _ai(coro):
        from ..intelligence.client import IntelligenceError
        try:
            return await coro
        except studio.NotConfigured as e:
            raise HTTPException(503, str(e))
        except IntelligenceError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/pages")
    def list_pages(ctx: Ctx = Depends(current)):
        return {"items": pages.list_pages(db, ctx.account_id), "ai": missions.ceo_engine_active()}

    @app.post("/api/pages", status_code=201)
    async def create_page(body: PageIn, ctx: Ctx = Depends(current)):
        return await _ai(pages.generate(db, ctx.account, ctx.user_id, body.brief))

    @app.get("/api/pages/{pid}")
    def get_page(pid: str, ctx: Ctx = Depends(current)):
        return _page(pid, ctx)

    @app.post("/api/pages/{pid}/edit")
    async def edit_page(pid: str, body: PageEditIn, ctx: Ctx = Depends(current)):
        if not body.instruction.strip():
            raise HTTPException(400, "כתבו מה לשנות")
        return await _ai(pages.edit(db, ctx.account, ctx.user_id, _page(pid, ctx), body.instruction))

    @app.post("/api/pages/{pid}/restore")
    def restore_page(pid: str, body: VersionIn, ctx: Ctx = Depends(current)):
        res = pages.restore(db, _page(pid, ctx), body.version)
        if not res:
            raise HTTPException(404, "הגרסה לא נמצאה")
        return res

    @app.get("/api/pages/{pid}/preview")
    def preview_page(pid: str, ctx: Ctx = Depends(current)):
        from fastapi.responses import HTMLResponse as H
        return H(pages.render(_page(pid, ctx)["spec"], pid, "preview"))

    @app.get("/api/pages/{pid}/export")
    def export_page(pid: str, ctx: Ctx = Depends(current)):
        from fastapi.responses import HTMLResponse as H
        pg = _page(pid, ctx)
        return H(pages.render(pg["spec"], pid, "public"), headers={"Content-Disposition": f'attachment; filename="landing-{pid[:8]}.html"'})

    @app.post("/api/pages/{pid}/publish", status_code=201)
    def publish_page(pid: str, ctx: Ctx = Depends(current)):
        pg = _page(pid, ctx)
        return actions.propose(db, ctx.account, ctx.user_id, {"key": f"publish:{pid}", "kind": "publish_page", "title": f"פרסום דף: {pg['title']}",
                                                              "why": "הדף יהיה זמין בקישור ציבורי והטופס יקלוט פניות ל-CRM.", "payload": {"page_id": pid}})

    @app.post("/api/pages/{pid}/unpublish")
    def unpublish_page(pid: str, ctx: Ctx = Depends(current)):
        _page(pid, ctx)
        pages.set_status(db, pid, ctx.account_id, "draft")
        return {"status": "draft"}

    @app.get("/p/{pid}/")
    def public_page(pid: str):
        from fastapi.responses import HTMLResponse as H
        pg = pages.get(db, pid, None)
        if not pg or pg["status"] != "published":
            raise HTTPException(404, "לא נמצא")
        return H(pages.render(pg["spec"], pid, "public"))

    @app.post("/p/{pid}/lead")
    async def public_lead(pid: str, request: Request):
        from fastapi.responses import HTMLResponse as H
        from ..saas import auth as _auth
        pg = pages.get(db, pid, None)
        if not pg or pg["status"] != "published":
            raise HTTPException(404, "לא נמצא")
        if not _auth.signup_limiter.hit("pagelead|" + _auth.client_ip(request)):
            raise HTTPException(429, "יותר מדי פניות. נסו שוב מאוחר יותר")
        from urllib.parse import parse_qs
        raw = parse_qs((await request.body())[:20000].decode("utf-8", "replace"))
        form = {k: v[0] for k, v in raw.items()}
        if (form.get("website") or "").strip():  # מלכודת בוטים
            return H("<p>תודה!</p>")
        name, phone = str(form.get("name") or "").strip()[:120], str(form.get("phone") or "").strip()[:40]
        if not name or not phone:
            raise HTTPException(400, "חסרים שם וטלפון")
        contact = phone + (" · " + str(form.get("email"))[:120] if form.get("email") else "")
        lead = studio.add_lead(db, pg["account_id"], name, contact, "landing_page", f"[{pg['title']}] " + str(form.get("message") or "")[:2000])
        store.log(db, pg["account_id"], "lead_added", f"פנייה חדשה מדף הנחיתה: {name}", ref_type="lead", ref_id=lead["id"])
        db.add_notification(pg["account_id"], "new_lead", f"פנייה חדשה: {name}", f"מדף הנחיתה '{pg['title']}'")
        return H("<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                 "<body style='font:18px system-ui;text-align:center;padding:60px 20px'><h1>תודה! קיבלנו את הפרטים</h1><p>נחזור אליכם בהקדם.</p></body></html>")

    # ------------------------------------------------------------ Agency Mode
    @app.get("/api/agency")
    def agency_overview(ctx: Ctx = Depends(current)):
        return agency.overview(db, ctx.account)

    @app.post("/api/agency/clients", status_code=201)
    def agency_add(body: ClientIn, ctx: Ctx = Depends(current)):
        from .. import config
        from ..research.analyzer import assert_public_host, normalize_url
        if not body.confirm_permission:
            raise HTTPException(400, "יש לאשר שיש לכם הרשאה מהלקוח לבדוק את האתר שלו")
        if not body.name.strip():
            raise HTTPException(400, "חסר שם לקוח")
        try:
            url = normalize_url(body.url)
            if not config.DEV_ALLOW_PRIVATE_TARGETS:
                assert_public_host(url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        cl = agency.add_client(db, ctx.account_id, body.name.strip(), url, body.industry)
        store.log(db, ctx.account_id, "client_added", f"נוסף לקוח: {cl['name']}", user_id=ctx.user_id)
        return cl

    @app.delete("/api/agency/clients/{client_id}", status_code=204)
    def agency_delete(client_id: str, ctx: Ctx = Depends(current)):
        if not agency.delete_client(db, client_id, ctx.account_id):
            raise HTTPException(404, "הלקוח לא נמצא")

    @app.post("/api/agency/clients/{client_id}/audit", status_code=202)
    def agency_audit(client_id: str, ctx: Ctx = Depends(current)):
        from ..saas import plans
        cl = agency.get_client(db, client_id, ctx.account_id)
        if not cl:
            raise HTTPException(404, "הלקוח לא נמצא")
        ok, missing = browser_available()
        if not ok:
            raise HTTPException(503, missing)
        try:
            return agency.queue_audit(db, runner, ctx.account, ctx.user_id, cl)
        except plans.QuotaError as e:
            raise HTTPException(402, e.message)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/agency/demo", status_code=201)
    def agency_demo(ctx: Ctx = Depends(current)):
        ok, missing = browser_available()
        if not ok:
            raise HTTPException(503, missing)
        return {"created": len(agency.seed_demo(db, runner, ctx.account, ctx.user_id))}

    @app.delete("/api/agency/demo")
    def agency_demo_remove(ctx: Ctx = Depends(current)):
        return {"removed": agency.remove_demo(db, ctx.account_id)}

    # ------------------------------------------------------------ Human Approval Center
    @app.get("/api/actions")
    def list_actions(status: str | None = None, ctx: Ctx = Depends(current)):
        return {"items": [actions.refresh(db, a) for a in store.list_actions(db, ctx.account_id, status)]}

    @app.post("/api/actions", status_code=201)
    def create_action(body: ActionIn, ctx: Ctx = Depends(current)):
        item = next((i for i in ceo.plan(ceo.snapshot(db, ctx.account))["items"] if i["key"] == body.key), None)
        if not item:
            raise HTTPException(404, "הפריט כבר לא בתוכנית (אולי טופל)")
        try:
            return actions.propose(db, ctx.account, ctx.user_id, item)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/actions/{action_id}")
    def get_action(action_id: str, ctx: Ctx = Depends(current)):
        return actions.refresh(db, _action_or_404(action_id, ctx))

    @app.post("/api/actions/{action_id}/approve")
    def approve(action_id: str, ctx: Ctx = Depends(current)):
        a = _action_or_404(action_id, ctx)
        if ctx.role not in ("owner", "admin"):
            raise HTTPException(403, "רק בעלים/מנהל של החשבון יכולים לאשר פעולות")
        if a["kind"] in ("run_audit", "verify_fix"):
            ok, missing = browser_available()
            if not ok:
                raise HTTPException(503, missing)
        try:
            return actions.approve_and_execute(db, runner, ctx.account, ctx.user_id, a)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/actions/{action_id}/reject")
    def reject(action_id: str, ctx: Ctx = Depends(current)):
        try:
            return actions.reject(db, _action_or_404(action_id, ctx), ctx.user_id)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/actions/{action_id}/package.html")
    def package(action_id: str, ctx: Ctx = Depends(current)):
        a = _action_or_404(action_id, ctx)
        if a["kind"] != "fix_package" or a["status"] != "done":
            raise HTTPException(409, "החבילה זמינה אחרי אישור הפעולה")
        return HTMLResponse(actions.package_html(a), headers={"Content-Disposition": f'attachment; filename="p1-fix-{action_id[:8]}.html"'})
