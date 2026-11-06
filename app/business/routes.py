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
    follow_up_at: str | None = None
    value: float | None = None


class VideoIn(BaseModel):
    output_id: str | None = None   # תסריט שסוכן הווידאו כבר כתב (ai_outputs)
    scenes: list[dict] | None = None
    cta: str = ""
    title: str = "סרטון"


class ConnIn(BaseModel):
    values: dict[str, str]


class SendIn(BaseModel):
    channel: str
    body: str


class RunIn(BaseModel):
    request: str
    agents: list[str] | None = None   # מסלול מוכן (ממשימה של P1 CEO) — מדלג על שלב התכנון


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
                "funnel": studio.funnel(db, ctx.account_id),
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
        if body.follow_up_at is not None:
            from datetime import datetime as _dt
            try:
                fields["follow_up_at"] = _dt.fromisoformat(body.follow_up_at).isoformat() if body.follow_up_at else None
            except ValueError:
                raise HTTPException(400, "תאריך לא תקין")
            fields["reminded_at"] = None
        if body.value is not None:
            if body.value < 0:
                raise HTTPException(400, "ערך לא תקין")
            fields["value"] = body.value
        if fields:
            studio.update_lead(db, lead_id, ctx.account_id, **fields)
        return studio.get_lead(db, lead_id, ctx.account_id)

    @app.post("/api/leads/{lead_id}/send", status_code=201)
    def send_to_lead(lead_id: str, body: SendIn, ctx: Ctx = Depends(current)):
        """מכין שליחה ללקוח — לא שולח. השליחה עצמה רק אחרי אישור במרכז האישורים."""
        lead = studio.get_lead(db, lead_id, ctx.account_id)
        if not lead:
            raise HTTPException(404, "הפנייה לא נמצאה")
        if body.channel not in ("whatsapp", "email") or not body.body.strip():
            raise HTTPException(400, "ערוץ או תוכן לא תקינים")
        kind = "send_whatsapp" if body.channel == "whatsapp" else "send_email"
        return actions.propose(db, ctx.account, ctx.user_id, {"key": f"{kind}:{lead_id}:{hash(body.body) % 10**8}", "kind": kind,
                                                              "title": f"שליחה ל{lead['name']} ({'WhatsApp' if kind == 'send_whatsapp' else 'מייל'})",
                                                              "why": body.body[:300], "payload": {"lead_id": lead_id, "body": body.body[:4000]}})

    @app.get("/api/leads/export.csv")
    def export_leads(ctx: Ctx = Depends(current)):
        """ייצוא ל-CSV (נפתח ב-Google Sheets / Excel)."""
        import csv
        import io
        from fastapi.responses import Response as R
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["name", "contact", "channel", "status", "value", "follow_up_at", "message", "created_at"])
        for l in studio.list_leads(db, ctx.account_id):
            w.writerow([l["name"], l["contact"], l["channel"], l["status"], l.get("value") or "", l.get("follow_up_at") or "", l["message"], l["created_at"]])
        return R("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="p1-leads.csv"'})

    # ------------------------------------------------------------ סוכן וידאו (מוטיון טקסט → MP4)
    @app.post("/api/videos", status_code=201)
    async def make_video(body: VideoIn, ctx: Ctx = Depends(current)):
        from . import video
        scenes, cta, title = body.scenes, body.cta, body.title
        if body.output_id:
            h = next((x for x in studio.history(db, ctx.account_id, "video_script", 100) if x["id"] == body.output_id), None)
            if not h:
                raise HTTPException(404, "התסריט לא נמצא")
            scenes, cta, title = h["output"].get("scenes") or [], h["output"].get("cta") or cta, (h["input"] or "סרטון")[:80]
            if h["output"].get("hook"):
                scenes = [{"seconds": "3", "visual": "", "voiceover": h["output"]["hook"]}] + scenes
        if not scenes:
            raise HTTPException(400, "אין סצנות לסרטון")
        ok, missing = browser_available()
        if not ok:
            raise HTTPException(503, missing)
        try:
            return await video.render(db, ctx.account, ctx.user_id, scenes, cta, title)
        except RuntimeError as e:
            raise HTTPException(500, str(e))

    @app.get("/api/videos")
    def videos(ctx: Ctx = Depends(current)):
        from . import video
        return {"items": video.list_videos(db, ctx.account_id)}

    @app.get("/api/videos/{vid}.mp4")
    def video_file(vid: str, ctx: Ctx = Depends(current)):
        from fastapi.responses import FileResponse as F
        from . import video
        p = video.video_path(db, vid, ctx.account_id)
        if not p:
            raise HTTPException(404, "לא נמצא")
        return F(p, media_type="video/mp4")

    # ------------------------------------------------------------ חיבורים של כל לקוח (מוצפנים) + קוד הטמעה לטפסים
    from ..integrations import accounts as acc_conn

    @app.get("/api/connections")
    def my_connections(ctx: Ctx = Depends(current)):
        key = acc_conn.embed_key(db, ctx.account_id)
        return {"items": acc_conn.overview(db, ctx.account_id), "embed": {"key": key, "snippet": acc_conn.embed_snippet(key)}}

    @app.put("/api/connections/{provider}")
    def save_connection(provider: str, body: ConnIn, ctx: Ctx = Depends(current)):
        if ctx.role not in ("owner", "admin"):
            raise HTTPException(403, "רק בעלים/מנהל יכולים לחבר חשבונות")
        try:
            return acc_conn.save(db, ctx.account_id, provider, body.values)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/connections/{provider}/test")
    def test_connection(provider: str, ctx: Ctx = Depends(current)):
        if provider not in acc_conn.PROVIDERS:
            raise HTTPException(404, "ספק לא מוכר")
        return acc_conn.test(db, ctx.account_id, provider)

    @app.delete("/api/connections/{provider}", status_code=204)
    def delete_connection(provider: str, ctx: Ctx = Depends(current)):
        if not acc_conn.remove(db, ctx.account_id, provider):
            raise HTTPException(404, "אין חיבור")

    @app.get("/api/oauth/google/start")
    def google_start(ctx: Ctx = Depends(current)):
        from fastapi.responses import RedirectResponse
        from ..integrations import google
        if not google.configured():
            raise HTTPException(503, "התחברות עם Google לא הוגדרה בשרת (P1_GOOGLE_CLIENT_ID / P1_GOOGLE_CLIENT_SECRET)")
        return RedirectResponse(google.start_url(ctx.account_id), status_code=302)

    @app.get("/api/oauth/google/callback")
    def google_callback(code: str = "", state: str = "", error: str = "", ctx: Ctx = Depends(current)):
        from fastapi.responses import RedirectResponse
        from ..integrations import google
        acc = google.pop_state(state)
        if error or not code or acc != ctx.account_id:
            return RedirectResponse("/#/connect?google=error", status_code=302)
        try:
            tok = google.exchange(code)
        except RuntimeError:
            return RedirectResponse("/#/connect?google=error", status_code=302)
        old = acc_conn.load(db, ctx.account_id, "ga4") or {}
        import json as _json
        from ..integrations.accounts import _fernet
        with db._conn() as c:  # שומרים את הטוקן גם לפני שהוזן Property ID
            c.execute("""INSERT INTO connections (account_id, provider, creds_enc, status, created_at, updated_at) VALUES (?, 'ga4', ?, 'saved', ?, ?)
                         ON CONFLICT(account_id, provider) DO UPDATE SET creds_enc=excluded.creds_enc, status='saved', updated_at=excluded.updated_at""",
                      (ctx.account_id, _fernet().encrypt(_json.dumps({**old, "GA4_REFRESH_TOKEN": tok["refresh_token"]}).encode()).decode(), store.now(), store.now()))
        return RedirectResponse("/#/connect?google=ok", status_code=302)

    @app.post("/api/embed/rotate")
    def rotate_embed(ctx: Ctx = Depends(current)):
        key = acc_conn.embed_key(db, ctx.account_id, rotate=True)
        return {"key": key, "snippet": acc_conn.embed_snippet(key)}

    @app.post("/api/collect/{key}")
    async def collect_lead(key: str, request: Request):
        """קליטת טופס מאתר של לקוח (כל פלטפורמה). ציבורי: מפתח + הגבלת קצב + ולידציה. אין cookie ואין גישה לנתונים."""
        import json as _json
        from fastapi.responses import Response as R
        from ..saas import auth as _auth
        acc = acc_conn.account_for_key(db, key)
        if not acc:
            raise HTTPException(404, "מפתח לא מוכר")
        if not _auth.signup_limiter.hit("collect|" + _auth.client_ip(request)):
            raise HTTPException(429, "יותר מדי פניות")
        try:
            d = _json.loads((await request.body())[:8000] or b"{}")
        except ValueError:
            raise HTTPException(400, "נתונים לא תקינים")
        phone, email = str(d.get("phone") or "")[:40], str(d.get("email") or "")[:120]
        if not (phone or email):
            raise HTTPException(400, "חסר טלפון או מייל")
        name = str(d.get("name") or "").strip()[:120] or phone or email
        page = str(d.get("page") or "")[:300]
        lead = studio.add_lead(db, acc, name, " · ".join(x for x in (phone, email) if x), "website_form",
                               (f"[{page}] " if page else "") + str(d.get("message") or "")[:2000])
        db.add_notification(acc, "new_lead", f"פנייה מהאתר: {name}", page[:120])
        store.log(db, acc, "lead_added", f"פנייה מהאתר: {name}", ref_type="lead", ref_id=lead["id"])
        return R(status_code=204, headers={"Access-Control-Allow-Origin": "*"})

    # ------------------------------------------------------------ חיבורים רשמיים: WhatsApp webhook · Shopify · WordPress
    @app.get("/api/whatsapp/webhook")
    def wa_verify(request: Request):
        import os as _os
        from fastapi.responses import PlainTextResponse
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and _os.environ.get("WHATSAPP_VERIFY_TOKEN") and q.get("hub.verify_token") == _os.environ["WHATSAPP_VERIFY_TOKEN"]:
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "אימות נכשל")

    @app.post("/api/whatsapp/webhook")
    async def wa_inbound(request: Request):
        import json as _json
        import os as _os
        from ..integrations import connectors
        body = await request.body()
        if not connectors.wa_verify_signature(body, request.headers.get("x-hub-signature-256")):
            raise HTTPException(401, "חתימה לא תקינה")
        acc = _os.environ.get("P1_WHATSAPP_ACCOUNT_ID")
        if not acc or not db.get_account(acc):
            raise HTTPException(503, "WhatsApp לא משויך לחשבון")
        n = 0
        for m in connectors.wa_parse_inbound(_json.loads(body or b"{}")):
            studio.add_lead(db, acc, m["name"] or m["from"], m["from"], "whatsapp", m["text"])
            db.add_notification(acc, "new_lead", f"הודעת WhatsApp: {m['name']}", m["text"][:120])
            n += 1
        return {"received": n}

    @app.get("/api/integrations/{name}/test")
    def test_integration(name: str, ctx: Ctx = Depends(current)):
        from ..integrations import connectors
        fn = {"shopify": connectors.shopify_summary, "wordpress": connectors.wordpress_pages}.get(name)
        if not fn:
            raise HTTPException(404, "חיבור לא מוכר")
        try:
            return {"ok": True, "data": fn()}
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"החיבור נכשל: {type(e).__name__}")

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
        if body.agents:
            steps = [{"agent": a, "goal": autopilot.AGENTS[a]} for a in autopilot.ORDER if a in set(body.agents)]
            if not steps:
                raise HTTPException(400, "אין סוכנים מתאימים")
            run = autopilot.create(db, ctx.account, ctx.user_id, body.request, steps, "mission", "P1 CEO מפעיל את הסוכנים לפי התוכנית שבניתם יחד.")
            import asyncio as _aio
            _aio.get_running_loop().create_task(autopilot.execute(db, runner, ctx.account, ctx.user_id, run["id"]))
            return run
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
