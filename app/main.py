"""שרת P1 AI — FastAPI.

הפעלה:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent import Agent, AgentError, to_display
from .db import Database
from .research.analyzer import analyze_url

STATIC = config.ROOT / "app" / "static"


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class ResearchIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


def create_app(db: Database | None = None, agent: Agent | None = None) -> FastAPI:
    app = FastAPI(title="P1 AI", version="0.1.0")
    app.state.db = db or Database(config.DB_PATH)
    app.state.agent = agent or Agent(app.state.db)

    @app.get("/api/status")
    def status():
        """מה עובד ומה חסר — כדי שהממשק לא יציג יכולת שלא קיימת."""
        ai_ready = app.state.agent.ready
        return {
            "model": config.MODEL,
            "capabilities": {
                "chat": {"ready": ai_ready,
                         "missing": None if ai_ready else "ANTHROPIC_API_KEY"},
                "website_research": {"ready": True, "missing": None},
                "conversation_storage": {"ready": True, "missing": None},
            },
        }

    # ---------- שיחות ----------
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

    # ---------- חקירת אתרים (עובד גם בלי מפתח AI) ----------
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
