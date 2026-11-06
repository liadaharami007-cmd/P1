"""נתיבי API של Business OS. כל נתיב דורש משתמש מחובר ומסנן לפי החשבון שלו."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..db import Database
from ..intelligence import engines
from ..saas.auth import Ctx, current
from . import actions, brain, ceo, store


class ProfileIn(BaseModel):
    data: dict[str, Any]


class ActionIn(BaseModel):
    key: str


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
