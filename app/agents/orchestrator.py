"""מריץ את חמשת סוכני הלקוח בדפדפן אחד (עד 2 במקביל), שומר כל פעולה ומצב חי במסד הנתונים."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from ..audit.browser import HostGuard, launch, new_context
from ..db import Database
from ..logging_setup import log
from .base import AGENT_TIMEOUT_S, AgentContext, RuleBrain, Stopped
from .customers import AGENTS, RUNNERS

PARALLEL = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_agents(db: Database, audit_id: str, start: dict, shot_root: Path, *, allow_private: bool = False,
                     only: list[str] | None = None) -> dict:
    """start = {home_url, product_url}. מחזיר {agent: result dict}. כשל של סוכן לא מפיל את האחרים."""
    brain = RuleBrain()
    keys = only or list(AGENTS)
    db.create_agent_runs(audit_id, keys, brain.engine)
    guard = HostGuard(allow_private)
    sem = asyncio.Semaphore(PARALLEL)
    results: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await launch(pw)
        try:
            async def one(key: str):
                meta = AGENTS[key]
                async with sem:
                    if db.is_cancel_requested(audit_id):
                        db.update_agent_run(audit_id, key, status="interrupted", error="נעצר ע\"י המשתמש")
                        return
                    db.update_agent_run(audit_id, key, status="running", started_at=_now())
                    device = pw.devices["iPhone 13"] | {"locale": "he-IL"} if meta["device"] == "mobile" else None
                    ctx_b = await new_context(browser, guard, device)
                    page = await ctx_b.new_page()

                    async def log_fn(kind, msg, url, shot):
                        db.add_event(audit_id, kind, msg, url, shot, ref=key, agent=key)

                    def save_shot(label, dev, url, path):
                        return db.add_screenshot(audit_id, label, dev, url, path)

                    ctx = AgentContext(key, page, meta["device"], shot_root / audit_id / "agents", log_fn, save_shot,
                                       lambda: db.is_cancel_requested(audit_id),
                                       lambda st: db.update_agent_run(audit_id, key, **st))
                    await ctx.log("info", f"{meta['name_he']} מתחיל · {brain.describe()}")
                    try:
                        res = await asyncio.wait_for(RUNNERS[key](ctx, start), timeout=AGENT_TIMEOUT_S)
                        if ctx.popups_closed:
                            res.issue(f"נאלצתי לסגור חלון קופץ {ctx.popups_closed} פעמים כדי להמשיך")
                        data = {"observations": res.observations, "metrics": res.metrics, "verdict": res.verdict,
                                "actions": ctx.actions, "engine": brain.engine}
                        results[key] = data
                        db.update_agent_run(audit_id, key, status="done", finished_at=_now(), verdict=res.verdict,
                                            actions=ctx.actions, result_json=json.dumps(data, ensure_ascii=False))
                        await ctx.log("step_passed", f"{meta['name_he']} סיים: {len([o for o in res.observations if o['type'] == 'issue'])} בעיות")
                    except Stopped:
                        db.update_agent_run(audit_id, key, status="interrupted", finished_at=_now(), error="נעצר ע\"י המשתמש")
                        await ctx.log("info", "הסוכן נעצר לבקשת המשתמש")
                    except asyncio.TimeoutError:
                        db.update_agent_run(audit_id, key, status="failed", finished_at=_now(), actions=ctx.actions,
                                            error=f"חרג מ-{AGENT_TIMEOUT_S} שניות")
                        await ctx.log("error", f"הסוכן חרג מ-{AGENT_TIMEOUT_S} שניות ונעצר")
                    except Exception as e:  # noqa: BLE001 — כשל של סוכן אחד לא מפיל את הבדיקה
                        log.exception("agent failed", extra={"audit_id": audit_id})
                        db.update_agent_run(audit_id, key, status="failed", finished_at=_now(), actions=ctx.actions,
                                            error=f"{type(e).__name__}: {str(e)[:200]}")
                        await ctx.log("error", f"הסוכן נכשל: {str(e)[:150]}")
                    finally:
                        await ctx_b.close()

            await asyncio.gather(*(one(k) for k in keys))
        finally:
            await browser.close()
    return results
