"""שרת P1 AI — FastAPI.

הפעלה:  uvicorn app.main:app --reload
כל נקודת API (חוץ מהרשמה/התחברות/בריאות) דורשת משתמש מחובר, וכל נתון מסונן לפי החשבון שלו.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import Agent, AgentError, to_display
from .audit import compare as compare_mod
from .audit import scoring
from .audit.rules import CATEGORIES, CATEGORIES_EN
from .audit.runner import AuditRunner
from .db import Database
from .intelligence.client import configured as ai_configured
from .logging_setup import log, setup as setup_logging
from .report.data import assemble
from .saas import auth, billing, plans
from .saas.auth import Ctx, current, require_admin

STATIC = config.ROOT / "app" / "static"
FINDING_STATUSES = {"open", "in_progress", "done", "dismissed"}
RUN_WORKER = os.environ.get("P1_RUN_WORKER", "1") == "1"


# ---------------------------------------------------------------- סכמות קלט
class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class AuditIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    confirm_permission: bool = False


class FindingStatusIn(BaseModel):
    status: str


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    name: str | None = Field(default=None, max_length=100)
    business_name: str | None = Field(default=None, max_length=120)
    locale: str = "he"


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class MeIn(BaseModel):
    locale: str


class PlanIn(BaseModel):
    plan: str


class FixStatusIn(BaseModel):
    status: str


class SiteIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    confirm_permission: bool = False


class MonitorIn(BaseModel):
    frequency: str
    enabled: bool = True


def browser_available() -> tuple[bool, str | None]:
    if importlib.util.find_spec("playwright") is None:
        return False, "חבילת playwright לא מותקנת (pip install -r requirements.txt)"
    path = config.chromium_path()
    if path and not Path(path).exists():
        return False, f"הדפדפן לא נמצא בנתיב {path}"
    return True, None


def integrations(ai_ready: bool) -> list[dict]:
    """מצב החיבורים — אמת בלבד."""
    return [
        {"id": "claude", "name": "Claude API (Anthropic)", "status": "connected" if ai_ready else "not_connected",
         "powers": "P1 Intelligence: ניתוח ראיות, 5 סוכני לקוח מדומים, תוכנית פעולה, הצעות ניסוח, עוזר AI",
         "requires": "ANTHROPIC_API_KEY בקובץ .env בשרת"},
        {"id": "shopify", "name": "Shopify", "status": "planned",
         "powers": "הזמנות, עגלות נטושות ומוצרים — משפך המרה אמיתי", "requires": "אפליקציית Shopify (OAuth) והתקנה בחנות"},
        {"id": "woocommerce", "name": "WooCommerce", "status": "planned",
         "powers": "הזמנות, מוצרים ולקוחות מחנות וורדפרס", "requires": "מפתחות REST API של WooCommerce"},
        {"id": "ga4", "name": "Google Analytics 4", "status": "planned",
         "powers": "מקורות תנועה ונקודות נטישה אמיתיות", "requires": "OAuth של Google והרשאת קריאה לנכס GA4"},
        {"id": "pagespeed", "name": "Google PageSpeed / CrUX", "status": "planned",
         "powers": "מדדי מהירות של משתמשים אמיתיים", "requires": "מפתח API של Google (חינמי)"},
        {"id": "billing", "name": "ספק תשלומים", "status": "connected" if billing.get_provider().configured() else "planned",
         "powers": "מנויים חודשיים וגבייה", "requires": "בחירת ספק (Stripe / Paddle / ספק ישראלי) והגדרת webhook"},
    ]


def create_app(db: Database | None = None, agent: Agent | None = None, runner: AuditRunner | None = None) -> FastAPI:
    setup_logging()
    database = db or Database(config.DB_PATH)
    the_runner = runner or AuditRunner(database, allow_private=config.DEV_ALLOW_PRIVATE_TARGETS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.fail_stale_audits()
        database.interrupt_running_agents()
        database.purge_expired_sessions()
        task = asyncio.create_task(the_runner.worker()) if RUN_WORKER else None
        yield
        the_runner.stop()
        if task:
            task.cancel()

    app = FastAPI(title="P1 AI", version="0.3.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.db = database
    app.state.agent = agent or Agent(database)
    app.state.runner = the_runner

    # ---------------------------------------------------------------- middleware
    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        t = time.perf_counter()
        # הגנת CSRF: בקשות משנות-מצב חייבות להגיע מאותו מקור
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "בקשה ממקור לא מורשה"}, status_code=403)
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled error", extra={"request_id": rid, "path": request.url.path})
            response = JSONResponse({"detail": "שגיאה פנימית בשרת", "request_id": rid}, status_code=500)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/demo-store"):  # חנות הדמו: דפים פשוטים עם סקריפטים פנימיים, בלי גישה ל-API
            response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                                           "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                                       "status": response.status_code, "ms": int((time.perf_counter() - t) * 1000)})
        return response

    # ---------------------------------------------------------------- בריאות + אימות
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/auth/config")
    def auth_config():
        return {"signup_allowed": auth.ALLOW_SIGNUP, "has_users": database.count_users() > 0}

    @app.post("/api/auth/register", status_code=201)
    def register(body: RegisterIn, request: Request, response: Response):
        if not auth.ALLOW_SIGNUP:
            raise HTTPException(403, "ההרשמה סגורה")
        if not auth.signup_limiter.hit(auth.client_ip(request)):
            raise HTTPException(429, "יותר מדי ניסיונות הרשמה. נסו שוב מאוחר יותר")
        email = body.email.strip().lower()
        auth.validate_credentials(email, body.password)
        if database.get_user_by_email(email):
            raise HTTPException(409, "כבר קיים משתמש עם האימייל הזה")
        first = database.count_users() == 0
        user, acc = database.create_user_with_account(
            email, auth.hash_password(body.password), (body.name or "").strip() or None,
            (body.business_name or "").strip() or email.split("@")[1], locale=body.locale if body.locale in ("he", "en") else "he",
            is_admin=first)
        if first:  # המשתמש הראשון = בעל הפלטפורמה, ומקבל נתונים שנוצרו לפני מערכת החשבונות
            database.adopt_orphan_data(acc["id"])
        auth.start_session(database, response, user["id"], acc["id"], request)
        log.info("user registered", extra={"user_id": user["id"], "account_id": acc["id"]})
        return {"ok": True}

    @app.post("/api/auth/login")
    def login(body: LoginIn, request: Request, response: Response):
        email = body.email.strip().lower()
        if not auth.login_limiter.hit(f"{auth.client_ip(request)}|{email}"):
            raise HTTPException(429, "יותר מדי ניסיונות התחברות. נסו שוב בעוד 15 דקות")
        user = database.get_user_by_email(email)
        if not user or not auth.verify_password(body.password, user["password_hash"]):
            raise HTTPException(401, "אימייל או סיסמה שגויים")
        m = database.primary_membership(user["id"])
        if not m:
            raise HTTPException(403, "למשתמש אין חשבון פעיל")
        database.touch_login(user["id"])
        auth.start_session(database, response, user["id"], m["account_id"], request)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        auth.end_session(database, request, response)
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(ctx: Ctx = Depends(current)):
        return {"user": ctx.user, "account": {k: ctx.account[k] for k in ("id", "name", "plan", "subscription_status")},
                "role": ctx.role}

    @app.patch("/api/me")
    def update_me(body: MeIn, ctx: Ctx = Depends(current)):
        if body.locale not in ("he", "en"):
            raise HTTPException(400, "שפה לא נתמכת")
        database.set_user_locale(ctx.user_id, body.locale)
        return {"locale": body.locale}

    # ---------------------------------------------------------------- מצב המערכת
    @app.get("/api/status")
    def status(ctx: Ctx = Depends(current)):
        ai_ready = ai_configured() or app.state.agent.ready
        b_ok, b_missing = browser_available()
        from .intelligence import engines
        eng = engines.status()
        return {
            "model": config.MODEL,
            "engines": eng,
            "capabilities": {
                "browser_audit": {"ready": b_ok, "missing": b_missing},
                "ai_analysis": {"ready": eng["active"] != "rules", "engine": eng["active"],
                                "missing": None if eng["active"] != "rules" else "ANTHROPIC_API_KEY / Ollama"},
                "customer_agents": {"ready": b_ok, "engine": "rules", "missing": b_missing},
                "rules_simulation": {"ready": b_ok, "missing": b_missing},
                "chat": {"ready": app.state.agent.ready, "missing": None if app.state.agent.ready else "ANTHROPIC_API_KEY"},
                "store_data": {"ready": False, "missing": "חיבור Shopify / WooCommerce (טרם נבנה)"},
                "billing": {"ready": billing.get_provider().configured(), "missing": "ספק תשלומים"},
            },
            "categories": CATEGORIES, "categories_en": CATEGORIES_EN,
        }

    @app.get("/api/methodology")
    def methodology(ctx: Ctx = Depends(current)):
        from .audit.rules import RULE_CATEGORY
        return {**scoring.methodology(), "rule_category": RULE_CATEGORY}

    @app.get("/api/engines")
    def get_engines(ctx: Ctx = Depends(current)):
        from .intelligence import engines
        return engines.status()

    @app.get("/api/integrations")
    def get_integrations(ctx: Ctx = Depends(current)):
        return integrations(ai_configured() or app.state.agent.ready)

    @app.get("/api/account")
    def account(ctx: Ctx = Depends(current)):
        usage = database.usage(ctx.account_id)
        return {"account": ctx.account, "role": ctx.role, "plan": plans.plan_of(ctx.account), "plans": plans.PLANS,
                "usage": usage, "billing": {"provider": billing.get_provider().name,
                                            "configured": billing.get_provider().configured()}}

    # ---------------------------------------------------------------- בדיקות
    def _audit_or_404(audit_id: str, ctx: Ctx) -> dict:
        a = database.get_audit(audit_id, ctx.account_id)
        if not a:
            raise HTTPException(404, "הבדיקה לא נמצאה")
        return a

    @app.post("/api/audits", status_code=202)
    async def start_audit(body: AuditIn, ctx: Ctx = Depends(current)):
        if not body.confirm_permission:
            raise HTTPException(400, "יש לאשר שאתם הבעלים של האתר או שיש לכם הרשאה לבדוק אותו")
        ok, missing = browser_available()
        if not ok:
            raise HTTPException(503, missing)
        try:
            audit = the_runner.enqueue(body.url, ctx.account, ctx.user_id)
        except plans.QuotaError as e:
            raise HTTPException(402, e.message)
        except ValueError as e:
            raise HTTPException(400, str(e))
        log.info("audit queued", extra={"audit_id": audit["id"], "account_id": ctx.account_id})
        return audit

    @app.get("/api/audits")
    def list_audits(site_id: str | None = None, ctx: Ctx = Depends(current)):
        return database.list_audits(ctx.account_id, site_id)

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str, ctx: Ctx = Depends(current)):
        return assemble(database, _audit_or_404(audit_id, ctx))

    @app.get("/api/audits/{audit_id}/events")
    def audit_events(audit_id: str, after: int = 0, ctx: Ctx = Depends(current)):
        a = _audit_or_404(audit_id, ctx)
        return {"status": a["status"], "ai_status": a.get("ai_status"), "started_at": a.get("started_at"),
                "finished_at": a.get("finished_at"), "error": a.get("error"), "start_url": a["start_url"],
                "progress": a.get("progress") or [], "events": database.get_events(audit_id, after)}

    @app.post("/api/audits/{audit_id}/analyze", status_code=202)
    async def reanalyze(audit_id: str, ctx: Ctx = Depends(current)):
        a = _audit_or_404(audit_id, ctx)
        if a["status"] != "done":
            raise HTTPException(409, "אפשר לנתח רק בדיקה שהסתיימה")
        if a.get("ai_status") == "running":
            raise HTTPException(409, "ניתוח AI כבר רץ")
        from .intelligence import engines
        if engines.status()["active"] == "rules":
            raise HTTPException(503, "אין מנוע AI מחובר (Claude / Ollama) — מנוע הכללים כבר הופעל בבדיקה")
        database.update_audit(audit_id, ai_status="running")
        t = asyncio.create_task(the_runner.run_ai(audit_id))
        the_runner._tasks.add(t)
        t.add_done_callback(the_runner._tasks.discard)
        return {"ai_status": "running"}

    @app.get("/api/audits/{audit_id}/compare")
    def compare_audits(audit_id: str, base: str | None = None, ctx: Ctx = Depends(current)):
        after = _audit_or_404(audit_id, ctx)
        before = database.get_audit(base, ctx.account_id) if base else database.previous_done_audit(after)
        if not before or before["site_id"] != after["site_id"]:
            raise HTTPException(404, "אין בדיקה קודמת של אותו אתר להשוואה")
        return compare_mod.compare(before, database.get_findings(before["id"]), after, database.get_findings(after["id"]))

    @app.get("/api/audits/{audit_id}/report.pdf")
    async def report_pdf(audit_id: str, ctx: Ctx = Depends(current)):
        from .report.pdf import render_pdf
        a = _audit_or_404(audit_id, ctx)
        if a["status"] != "done":
            raise HTTPException(409, "הדוח זמין רק לבדיקה שהסתיימה")
        pdf = await render_pdf(assemble(database, a), database.list_screenshots(audit_id, with_paths=True))
        name = (urlparse(a["start_url"]).hostname or "site").replace(".", "-")
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="p1-report-{name}-{a["id"][:8]}.pdf"'})

    @app.delete("/api/audits/{audit_id}", status_code=204)
    def delete_audit(audit_id: str, ctx: Ctx = Depends(current)):
        a = _audit_or_404(audit_id, ctx)
        if a["status"] in ("queued", "running") or a.get("ai_status") == "running":
            raise HTTPException(409, "אי אפשר למחוק בדיקה שעדיין רצה")
        the_runner.delete(audit_id)

    @app.get("/api/screenshots/{shot_id}")
    def get_screenshot(shot_id: str, ctx: Ctx = Depends(current)):
        shot = database.get_screenshot(shot_id, ctx.account_id)
        if not shot or not Path(shot["path"]).exists():
            raise HTTPException(404, "צילום המסך לא נמצא")
        return FileResponse(shot["path"], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @app.patch("/api/findings/{finding_id}")
    def update_finding(finding_id: str, body: FindingStatusIn, ctx: Ctx = Depends(current)):
        if body.status not in FINDING_STATUSES:
            raise HTTPException(400, "סטטוס לא חוקי")
        if not database.update_finding_status(finding_id, body.status, ctx.account_id):
            raise HTTPException(404, "הממצא לא נמצא")
        return {"id": finding_id, "status": body.status}

    @app.get("/api/tasks")
    def tasks(ctx: Ctx = Depends(current)):
        return database.list_task_findings(ctx.account_id)

    @app.get("/api/dashboard")
    def dashboard(site_id: str | None = None, ctx: Ctx = Depends(current)):
        sites = database.list_sites(ctx.account_id)
        usage = database.usage(ctx.account_id)
        if not sites:
            return {"sites": [], "site": None, "usage": usage, "plan": plans.plan_of(ctx.account)}
        all_audits = database.list_audits(ctx.account_id, None, 200)
        site = next((s for s in sites if s["id"] == site_id), None) or \
            next((s for s in sites if all_audits and s["id"] == all_audits[0]["site_id"]), sites[0])
        audits = [a for a in all_audits if a["site_id"] == site["id"]]
        done = [a for a in audits if a["status"] == "done"]
        latest = database.get_audit(done[0]["id"], ctx.account_id) if done else None
        findings = database.get_findings(latest["id"]) if latest else []
        measured = [f for f in findings if f["source"] == "measured"]
        sev = {s: 0 for s in ("critical", "high", "medium", "low")}
        st = {s: 0 for s in FINDING_STATUSES}
        for f in measured:
            st[f["status"]] += 1
            if f["status"] in ("open", "in_progress"):
                sev[f["severity"]] += 1
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        imp = {"high": 0, "medium": 1, "low": 2}
        top = sorted([f for f in measured if f["status"] in ("open", "in_progress")],
                     key=lambda f: (f.get("priority") or 999, order[f["severity"]], imp[f["impact"]]))[:6]
        report = assemble(database, latest) if latest else None
        return {
            "sites": sites, "site": site, "usage": usage, "plan": plans.plan_of(ctx.account),
            "latest": {k: latest[k] for k in ("id", "score", "category_scores", "finished_at", "start_url", "ai_status")} if latest else None,
            "running": [a for a in audits if a["status"] in ("queued", "running")],
            "trend": [{"id": a["id"], "score": a["score"], "categories": a["category_scores"], "at": a["finished_at"]}
                      for a in reversed(done)],
            "severity_counts": sev, "status_counts": st, "top_findings": top,
            "ai_summary": (report["ai"]["analysis"] or {}).get("executive_summary") if report else None,
            "ai_personas": [{"key": p["key"], "name": p["name"], "verdict": (p["result"] or {}).get("verdict")}
                            for p in report["ai"]["personas"]] if report else [],
            "rule_personas": database.get_personas(latest["id"]) if latest else [],
            "agents": [{"agent": r["agent"], "status": r["status"], "verdict": r["verdict"], "engine": r["engine"],
                        "issues": sum(1 for o in (r["result"] or {}).get("observations", []) if o["type"] == "issue")}
                       for r in database.get_agent_runs(latest["id"])] if latest else [],
            "is_demo": bool(site.get("is_demo")),
            "comparison": report["comparison"] if report else None,
            "recent_audits": audits[:8],
        }

    # ---------------------------------------------------------------- שליטה בבדיקה: עצירה וחידוש
    @app.post("/api/audits/{audit_id}/stop")
    def stop_audit(audit_id: str, ctx: Ctx = Depends(current)):
        a = _audit_or_404(audit_id, ctx)
        if a["status"] not in ("queued", "running") and not any(r["status"] == "running" for r in database.get_agent_runs(audit_id)):
            raise HTTPException(409, "הבדיקה לא רצה כרגע")
        if a["status"] == "queued":
            database.update_audit(audit_id, status="stopped", error="נעצר לפני שהתחיל")
        database.update_audit(audit_id, cancel_requested=1)
        database.add_event(audit_id, "info", "התקבלה בקשת עצירה מהמשתמש")
        return {"ok": True}

    @app.post("/api/audits/{audit_id}/resume", status_code=202)
    async def resume_audit(audit_id: str, ctx: Ctx = Depends(current)):
        a = _audit_or_404(audit_id, ctx)
        runs = database.get_agent_runs(audit_id)
        if a["status"] != "done" or not any(r["status"] in ("interrupted", "failed", "queued") for r in runs):
            raise HTTPException(409, "אין סוכנים לחידוש בבדיקה הזו")
        t = asyncio.create_task(the_runner.resume_agents(audit_id))
        the_runner._tasks.add(t)
        t.add_done_callback(the_runner._tasks.discard)
        return {"ok": True}

    # ---------------------------------------------------------------- Live Mission Control (SSE)
    @app.get("/api/audits/{audit_id}/stream")
    async def stream(audit_id: str, request: Request, after: int = 0, ctx: Ctx = Depends(current)):
        """שידור חי של מצב הבדיקה: אירועים חדשים, סוכנים, התקדמות. רק נתונים אמיתיים מהמסד."""
        import json as _json
        from fastapi.responses import StreamingResponse
        _audit_or_404(audit_id, ctx)

        async def gen():
            last = after
            idle_done = 0
            while not await request.is_disconnected():
                a = database.get_audit(audit_id, ctx.account_id)
                evs = database.get_events(audit_id, last, 200)
                if evs:
                    last = evs[-1]["id"]
                runs = database.get_agent_runs(audit_id)
                payload = {"status": a["status"], "ai_status": a.get("ai_status"), "started_at": a.get("started_at"),
                           "finished_at": a.get("finished_at"), "error": a.get("error"), "progress": a.get("progress") or [],
                           "start_url": a["start_url"], "score": a.get("score"),
                           "agents": [{k: r[k] for k in ("agent", "engine", "status", "actions", "current_url", "last_action",
                                                       "last_screenshot_id", "verdict", "error", "started_at", "finished_at")} for r in runs],
                           "events": evs}
                yield f"id: {last}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                settled = a["status"] in ("done", "failed", "stopped") and a.get("ai_status") not in ("pending", "running") \
                    and not any(r["status"] in ("running", "queued") for r in runs)
                idle_done = idle_done + 1 if settled else 0
                if idle_done >= 2:
                    yield "event: end\ndata: {}\n\n"
                    return
                await asyncio.sleep(0.8)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- Fix Studio
    @app.get("/api/audits/{audit_id}/fixes")
    def audit_fixes(audit_id: str, ctx: Ctx = Depends(current)):
        from .fixstudio import service
        a = _audit_or_404(audit_id, ctx)
        if a["status"] != "done":
            raise HTTPException(409, "Fix Studio זמין אחרי שהבדיקה מסתיימת")
        return {"audit": {k: a[k] for k in ("id", "site_url", "site_name", "start_url", "score", "finished_at", "is_demo")},
                "fixes": service.list_fixes(database, a), "screenshots": database.list_screenshots(audit_id)}

    @app.post("/api/findings/{finding_id}/preview")
    async def fix_preview(finding_id: str, ctx: Ctx = Depends(current)):
        from .fixstudio import service
        f = database.get_finding(finding_id, ctx.account_id)
        if not f:
            raise HTTPException(404, "הממצא לא נמצא")
        a = database.get_audit(f["audit_id"], ctx.account_id)
        a["_allow_private"] = bool(a.get("is_demo"))
        return await service.make_preview(database, a, f)

    @app.patch("/api/findings/{finding_id}/fix")
    def fix_status(finding_id: str, body: FixStatusIn, ctx: Ctx = Depends(current)):
        from .fixstudio.service import FIX_STATUSES
        if body.status not in FIX_STATUSES:
            raise HTTPException(400, "סטטוס לא חוקי")
        if not database.set_fix_status(finding_id, body.status, ctx.account_id):
            raise HTTPException(404, "הממצא לא נמצא")
        return {"id": finding_id, "fix_status": body.status}

    # ---------------------------------------------------------------- Business OS: פרופיל, CEO, אישורים, ציר זמן
    from .business.routes import register as register_business
    register_business(app, database, the_runner, browser_available)

    # ---------------------------------------------------------------- אתרים + Smart Monitor + התראות
    @app.get("/api/sites")
    def sites(ctx: Ctx = Depends(current)):
        return {"sites": database.sites_overview(ctx.account_id), "plan": plans.plan_of(ctx.account)}

    @app.post("/api/sites", status_code=201)
    def add_site(body: SiteIn, ctx: Ctx = Depends(current)):
        from .research.analyzer import assert_public_host, normalize_url
        if not body.confirm_permission:
            raise HTTPException(400, "יש לאשר שאתם הבעלים של האתר או שיש לכם הרשאה לבדוק אותו")
        try:
            url = normalize_url(body.url)
            if not config.DEV_ALLOW_PRIVATE_TARGETS:
                assert_public_host(url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}".lower()
        if not database.find_site(ctx.account_id, origin):
            usage = database.usage(ctx.account_id)
            if usage["sites"] >= plans.plan_of(ctx.account)["sites"]:
                raise HTTPException(402, f"המסלול {plans.plan_of(ctx.account)['name']} מאפשר עד {plans.plan_of(ctx.account)['sites']} אתרים")
        site = database.get_or_create_site(origin, ctx.account_id)
        database.authorize_site(site["id"], ctx.user_id)
        return database.get_site(site["id"], ctx.account_id)

    @app.put("/api/sites/{site_id}/monitor")
    def set_monitor(site_id: str, body: MonitorIn, ctx: Ctx = Depends(current)):
        from . import monitor as mon
        site = database.get_site(site_id, ctx.account_id)
        if not site:
            raise HTTPException(404, "האתר לא נמצא")
        allowed = plans.plan_of(ctx.account)["monitor"]
        if body.frequency not in mon.FREQ_DAYS:
            raise HTTPException(400, "תדירות לא חוקית")
        if body.frequency not in allowed:
            raise HTTPException(402, f"התדירות הזו לא כלולה במסלול. זמין: {', '.join(allowed)}")
        database.upsert_monitor(site_id, ctx.account_id, body.frequency, body.enabled, mon.next_run(body.frequency))
        return database.get_monitor(site_id)

    @app.get("/api/sites/{site_id}/progress")
    def site_progress(site_id: str, ctx: Ctx = Depends(current)):
        site = database.get_site(site_id, ctx.account_id)
        if not site:
            raise HTTPException(404, "האתר לא נמצא")
        hist = database.site_history(site_id)
        notes = [n for n in database.list_notifications(ctx.account_id, 200) if n["site_id"] == site_id]
        first, last = (hist[0], hist[-1]) if hist else (None, None)
        return {"site": site, "monitor": database.get_monitor(site_id), "history": hist, "changes": notes,
                "summary": {"audits": len(hist), "first_score": first and first["score"], "last_score": last and last["score"],
                            "delta": (last["score"] - first["score"]) if hist and first["score"] is not None and last["score"] is not None else None,
                            "fixed": sum(len((n["data"] or {}).get("rule_ids", [])) for n in notes if n["kind"] == "fixed_issues"),
                            "new": sum(len((n["data"] or {}).get("rule_ids", [])) for n in notes if n["kind"] == "new_issues")}}

    @app.get("/api/notifications")
    def notifications(ctx: Ctx = Depends(current)):
        items = database.list_notifications(ctx.account_id)
        return {"items": items, "unread": sum(1 for n in items if not n["read_at"])}

    @app.post("/api/notifications/read")
    def notifications_read(ctx: Ctx = Depends(current)):
        database.mark_notifications_read(ctx.account_id)
        return {"ok": True}

    # ---------------------------------------------------------------- Demo Experience
    @app.post("/api/demo/start", status_code=202)
    def demo_start(ctx: Ctx = Depends(current)):
        """בדיקה אמיתית של חנות הדמו של P1 (מסומנת כדמו בכל מקום).
        אבטחה: הכתובת נלקחת מהגדרות השרת בלבד — לא מכותרת Host של הבקשה (שהלקוח שולט בה),
        אחרת אפשר היה לכוון את הדפדפן לכתובת פנימית (SSRF)."""
        url = config.DEMO_STORE_URL
        try:
            return the_runner.enqueue(url, ctx.account, ctx.user_id, demo=True)
        except plans.QuotaError as e:
            raise HTTPException(402, e.message)

    @app.post("/demo-store/cart/add")
    def demo_cart_add():
        return {"ok": True}

    # ---------------------------------------------------------------- ניהול פלטפורמה
    @app.get("/api/admin/overview")
    def admin_overview(ctx: Ctx = Depends(require_admin)):
        return {**database.admin_overview(), "plans": plans.PLANS}

    @app.patch("/api/admin/accounts/{account_id}")
    def admin_set_plan(account_id: str, body: PlanIn, ctx: Ctx = Depends(require_admin)):
        if body.plan not in plans.PLANS:
            raise HTTPException(400, "מסלול לא קיים")
        if not database.get_account(account_id):
            raise HTTPException(404, "החשבון לא נמצא")
        database.update_account(account_id, plan=body.plan)
        log.info("plan changed by admin", extra={"account_id": account_id, "user_id": ctx.user_id})
        return {"id": account_id, "plan": body.plan}

    # ---------------------------------------------------------------- עוזר AI (צ'אט)
    @app.get("/api/conversations")
    def list_conversations(ctx: Ctx = Depends(current)):
        return database.list_conversations(ctx.account_id)

    @app.post("/api/conversations", status_code=201)
    def create_conversation(ctx: Ctx = Depends(current)):
        return database.create_conversation(ctx.account_id, ctx.user_id)

    @app.get("/api/conversations/{conv_id}")
    def get_conversation(conv_id: str, ctx: Ctx = Depends(current)):
        conv = database.get_conversation(conv_id, ctx.account_id)
        if not conv:
            raise HTTPException(404, "השיחה לא נמצאה")
        return {**conv, "items": to_display(database.get_messages(conv_id))}

    @app.delete("/api/conversations/{conv_id}", status_code=204)
    def delete_conversation(conv_id: str, ctx: Ctx = Depends(current)):
        if not database.delete_conversation(conv_id, ctx.account_id):
            raise HTTPException(404, "השיחה לא נמצאה")

    @app.post("/api/conversations/{conv_id}/messages")
    async def send_message(conv_id: str, body: MessageIn, ctx: Ctx = Depends(current)):
        if not database.get_conversation(conv_id, ctx.account_id):
            raise HTTPException(404, "השיחה לא נמצאה")
        try:
            notice = await app.state.agent.send(conv_id, body.text, ctx.account_id)
        except AgentError as e:
            raise HTTPException(e.status, e.message)
        conv = database.get_conversation(conv_id, ctx.account_id)
        return {**conv, "notice": notice, "items": to_display(database.get_messages(conv_id))}

    @app.get("/api/research/{report_id}")
    def get_research(report_id: str, ctx: Ctx = Depends(current)):
        rep = database.get_report(report_id, ctx.account_id)
        if not rep:
            raise HTTPException(404, "הדוח לא נמצא")
        return rep

    # ---------------------------------------------------------------- ממשק
    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # PWA: ה-manifest וה-service worker בשורש האתר כדי שה-scope יכסה את כל האפליקציה
    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    app.mount("/demo-store", StaticFiles(directory=STATIC / "demo-store", html=True), name="demo-store")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
