"""שרת P1 AI — FastAPI.

הפעלה:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import Agent, AgentError, to_display
from .audit.rules import CATEGORIES
from .audit.runner import AuditRunner
from .db import Database
from .research.analyzer import analyze_url

STATIC = config.ROOT / "app" / "static"
FINDING_STATUSES = {"open", "in_progress", "done", "dismissed"}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class ResearchIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class AuditIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    confirm_permission: bool = False


class FindingStatusIn(BaseModel):
    status: str


def browser_available() -> tuple[bool, str | None]:
    if importlib.util.find_spec("playwright") is None:
        return False, "חבילת playwright לא מותקנת (pip install -r requirements.txt)"
    path = config.chromium_path()
    if path and not Path(path).exists():
        return False, f"הדפדפן לא נמצא בנתיב {path}"
    return True, None


def integrations(agent_ready: bool) -> list[dict]:
    """מצב החיבורים החיצוניים — אמת בלבד. אף חיבור לא מוצג כמחובר אם הוא לא."""
    return [
        {"id": "claude", "name": "Claude API (Anthropic)", "status": "connected" if agent_ready else "not_connected",
         "powers": "צ'אט העוזר, ובהמשך: ניתוח AI של צילומי מסך, לקוחות מדומים מבוססי AI, שירות לקוחות",
         "requires": "ANTHROPIC_API_KEY בקובץ .env"},
        {"id": "shopify", "name": "Shopify", "status": "planned",
         "powers": "נתוני מכירות, עגלות נטושות, מוצרים — התנהגות לקוחות אמיתית",
         "requires": "אפליקציית Shopify (Client ID + Secret) והתקנה בחנות"},
        {"id": "woocommerce", "name": "WooCommerce", "status": "planned",
         "powers": "הזמנות, מוצרים ולקוחות מחנות וורדפרס",
         "requires": "מפתחות REST API של WooCommerce (Consumer Key + Secret)"},
        {"id": "ga4", "name": "Google Analytics 4", "status": "planned",
         "powers": "משפך המרה אמיתי, מקורות תנועה, נקודות נטישה",
         "requires": "פרויקט Google Cloud עם OAuth והרשאת קריאה לנכס GA4"},
        {"id": "pagespeed", "name": "Google PageSpeed", "status": "planned",
         "powers": "מדדי Core Web Vitals של משתמשים אמיתיים (CrUX)",
         "requires": "מפתח API של Google (חינמי)"},
        {"id": "support", "name": "שירות לקוחות (וואטסאפ / צ'אט באתר)", "status": "planned",
         "powers": "בוט שעונה ללקוחות על בסיס מידע מאומת על העסק",
         "requires": "Claude API + WhatsApp Business API או הטמעת וידג'ט באתר"},
    ]


def create_app(db: Database | None = None, agent: Agent | None = None,
               runner: AuditRunner | None = None) -> FastAPI:
    database = db or Database(config.DB_PATH)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.fail_stale_audits()
        yield

    app = FastAPI(title="P1 AI", version="0.2.0", lifespan=lifespan)
    app.state.db = database
    app.state.agent = agent or Agent(database)
    app.state.runner = runner or AuditRunner(database, allow_private=config.DEV_ALLOW_PRIVATE_TARGETS)

    @app.get("/api/status")
    def status():
        """מה עובד ומה חסר — כדי שהממשק לא יציג יכולת שלא קיימת."""
        ai_ready = app.state.agent.ready
        b_ok, b_missing = browser_available()
        return {
            "model": config.MODEL,
            "capabilities": {
                "browser_audit": {"ready": b_ok, "missing": b_missing},
                "customer_simulation": {"ready": b_ok, "missing": b_missing, "mode": "rules"},
                "chat": {"ready": ai_ready, "missing": None if ai_ready else "ANTHROPIC_API_KEY"},
                "store_data": {"ready": False, "missing": "חיבור Shopify / WooCommerce (טרם נבנה)"},
                "conversation_storage": {"ready": True, "missing": None},
            },
            "categories": CATEGORIES,
        }

    @app.get("/api/integrations")
    def get_integrations():
        return integrations(app.state.agent.ready)

    # ---------- בדיקות אתר (Audits) ----------
    @app.post("/api/audits", status_code=202)
    async def start_audit(body: AuditIn):
        if not body.confirm_permission:
            raise HTTPException(400, "יש לאשר שאתם הבעלים של האתר או שיש לכם הרשאה לבדוק אותו")
        ok, missing = browser_available()
        if not ok:
            raise HTTPException(503, missing)
        try:
            return app.state.runner.start(body.url)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/audits")
    def list_audits(site_id: str | None = None):
        return app.state.db.list_audits(site_id)

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str):
        db_ = app.state.db
        audit = db_.get_audit(audit_id)
        if not audit:
            raise HTTPException(404, "הבדיקה לא נמצאה")
        return {**audit, "steps": db_.get_steps(audit_id), "findings": db_.get_findings(audit_id),
                "personas": db_.get_personas(audit_id), "screenshots": db_.list_screenshots(audit_id)}

    @app.delete("/api/audits/{audit_id}", status_code=204)
    def delete_audit(audit_id: str):
        audit = app.state.db.get_audit(audit_id)
        if not audit:
            raise HTTPException(404, "הבדיקה לא נמצאה")
        if audit["status"] in ("queued", "running"):
            raise HTTPException(409, "אי אפשר למחוק בדיקה שעדיין רצה")
        app.state.runner.delete(audit_id)

    @app.get("/api/screenshots/{shot_id}")
    def get_screenshot(shot_id: str):
        shot = app.state.db.get_screenshot(shot_id)
        if not shot or not Path(shot["path"]).exists():
            raise HTTPException(404, "צילום המסך לא נמצא")
        return FileResponse(shot["path"], media_type="image/jpeg",
                            headers={"Cache-Control": "private, max-age=86400"})

    @app.patch("/api/findings/{finding_id}")
    def update_finding(finding_id: str, body: FindingStatusIn):
        if body.status not in FINDING_STATUSES:
            raise HTTPException(400, "סטטוס לא חוקי")
        if not app.state.db.update_finding_status(finding_id, body.status):
            raise HTTPException(404, "הממצא לא נמצא")
        return {"id": finding_id, "status": body.status}

    @app.get("/api/tasks")
    def tasks():
        """כל הממצאים מהבדיקה האחרונה של כל אתר — לניהול משימות תיקון."""
        return app.state.db.list_open_findings(500)

    @app.get("/api/dashboard")
    def dashboard(site_id: str | None = None):
        db_ = app.state.db
        sites = db_.list_sites()
        if not sites:
            return {"sites": [], "site": None}
        site = next((s for s in sites if s["id"] == site_id), None)
        all_audits = db_.list_audits(None, 200)
        if not site:  # ברירת מחדל: האתר של הבדיקה האחרונה
            site = next((s for s in sites if all_audits and s["id"] == all_audits[0]["site_id"]), sites[0])
        audits = [a for a in all_audits if a["site_id"] == site["id"]]
        done = [a for a in audits if a["status"] == "done"]
        latest = db_.get_audit(done[0]["id"]) if done else None
        findings = db_.get_findings(latest["id"]) if latest else []
        personas = db_.get_personas(latest["id"]) if latest else []
        sev_counts = {s: 0 for s in ("critical", "high", "medium", "low")}
        status_counts = {s: 0 for s in FINDING_STATUSES}
        for f in findings:
            status_counts[f["status"]] += 1
            if f["status"] in ("open", "in_progress"):
                sev_counts[f["severity"]] += 1
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        impact = {"high": 0, "medium": 1, "low": 2}
        top = sorted([f for f in findings if f["status"] in ("open", "in_progress")],
                     key=lambda f: (order[f["severity"]], impact[f["impact"]]))[:6]
        return {
            "sites": sites, "site": site,
            "latest": {k: latest[k] for k in ("id", "score", "category_scores", "finished_at", "start_url")} if latest else None,
            "running": [a for a in audits if a["status"] in ("queued", "running")],
            "trend": [{"id": a["id"], "score": a["score"], "at": a["finished_at"]} for a in reversed(done)],
            "severity_counts": sev_counts, "status_counts": status_counts,
            "top_findings": top, "personas": personas,
            "recent_audits": audits[:8],
        }

    # ---------- שיחות (עוזר AI) ----------
    @app.get("/api/conversations")
    def list_conversations():
        return app.state.db.list_conversations()

    @app.post("/api/conversations", status_code=201)
    def create_conversation():
        return app.state.db.create_conversation()

    @app.get("/api/conversations/{conv_id}")
    def get_conversation(conv_id: str):
        conv = app.state.db.get_conversation(conv_id)
        if not conv:
            raise HTTPException(404, "השיחה לא נמצאה")
        return {**conv, "items": to_display(app.state.db.get_messages(conv_id))}

    @app.delete("/api/conversations/{conv_id}", status_code=204)
    def delete_conversation(conv_id: str):
        if not app.state.db.delete_conversation(conv_id):
            raise HTTPException(404, "השיחה לא נמצאה")

    @app.post("/api/conversations/{conv_id}/messages")
    async def send_message(conv_id: str, body: MessageIn):
        conv = app.state.db.get_conversation(conv_id)
        if not conv:
            raise HTTPException(404, "השיחה לא נמצאה")
        try:
            notice = await app.state.agent.send(conv_id, body.text)
        except AgentError as e:
            raise HTTPException(e.status, e.message)
        conv = app.state.db.get_conversation(conv_id)
        return {**conv, "notice": notice, "items": to_display(app.state.db.get_messages(conv_id))}

    # ---------- בדיקת HTML מהירה (בשימוש כלי הצ'אט) ----------
    @app.post("/api/research")
    async def research(body: ResearchIn):
        report = await analyze_url(body.url)
        report["id"] = app.state.db.save_report(report)
        return report

    @app.get("/api/research")
    def list_research():
        return app.state.db.list_reports()

    @app.get("/api/research/{report_id}")
    def get_research(report_id: str):
        rep = app.state.db.get_report(report_id)
        if not rep:
            raise HTTPException(404, "הדוח לא נמצא")
        return rep

    # ---------- ממשק ----------
    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
