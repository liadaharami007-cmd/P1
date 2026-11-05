"""שירות הבדיקות: תור עבודות מתמיד במסד הנתונים + worker שמריץ בדיקות + שלב ניתוח AI.

זרימה: enqueue (אימות כתובת, SSRF, מכסות) → audits.status='queued'
        → worker לוקח מהתור → collector (דפדפן אמיתי) → rules → personas(כללים) → ציון → status='done'
        → שלב AI (אם מחובר ובמכסה): ניתוח + 5 סוכני לקוח → ai_status.
ה-worker רץ בתוך שרת ה-web כברירת מחדל; אפשר להריץ אותו כתהליך נפרד: python -m app.worker
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .. import config
from ..db import Database
from ..intelligence import analyst, personas_ai
from ..intelligence.client import IntelligenceError, configured, get_client
from ..logging_setup import log
from ..research.analyzer import BlockedURLError, assert_public_host, normalize_url
from ..saas import plans
from . import compare, personas, rules, scoring
from .collector import collect

AUDIT_TIMEOUT_S = 240


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditRunner:
    def __init__(self, db: Database, *, allow_private: bool = False, shot_root: Path | None = None,
                 ai_client=None):
        self.db = db
        self.allow_private = allow_private
        self.shot_root = shot_root or config.SCREENSHOT_DIR
        self._active = 0  # בדיקות שרצות כרגע בתהליך הזה (מוגבל ל-MAX_CONCURRENT_AUDITS)
        self._tasks: set[asyncio.Task] = set()
        self._wake = asyncio.Event()
        self._stop = False
        self._ai_client = ai_client  # לבדיקות; בייצור נוצר מהמפתח

    # ------------------------------------------------------------ תור
    def enqueue(self, raw_url: str, account: dict | None = None, user_id: str | None = None) -> dict:
        """מאמת ומכניס לתור. זורק ValueError (כתובת) או QuotaError (מכסה)."""
        url = normalize_url(raw_url)
        if not self.allow_private:
            assert_public_host(url)
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}".lower()
        account_id = account["id"] if account else None
        if account:
            usage = self.db.usage(account_id)
            plans.check_can_start_audit(account, usage, is_new_site=self.db.find_site(account_id, origin) is None)
        site = self.db.get_or_create_site(origin, account_id)
        audit = self.db.create_audit(site["id"], url, account_id, user_id)
        self.db.add_event(audit["id"], "info", "הבדיקה נכנסה לתור")
        self._wake.set()
        return audit

    def start(self, raw_url: str) -> dict:  # תאימות לאחור
        return self.enqueue(raw_url)

    async def worker(self) -> None:
        """לולאת ה-worker: לוקחת בדיקות מהתור לפי מקום פנוי."""
        log.info("audit worker started")
        while not self._stop:
            while self._active < config.MAX_CONCURRENT_AUDITS:  # יש מקום פנוי
                job = self.db.claim_next_queued()
                if not job:
                    break
                self._active += 1
                t = asyncio.create_task(self._guarded(job))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def _guarded(self, job: dict) -> None:
        try:
            site = self.db.get_audit(job["id"], any_account=True)
            await self.run(job["id"], site["site_id"], job["start_url"], claimed=True)
        finally:
            self._active -= 1
            self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    async def wait_all(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ------------------------------------------------------------ הרצת בדיקה
    async def run(self, audit_id: str, site_id: str, url: str, *, claimed: bool = False) -> None:
        progress: list[dict] = []

        async def on_progress(key: str, msg: str):
            progress.append({"key": key, "message": msg, "at": _now()})
            self.db.update_audit(audit_id, progress=progress)

        async def on_event(kind: str, msg: str, page_url: str | None, shot: str | None):
            self.db.add_event(audit_id, kind, msg, page_url, shot)

        def save_shot(label: str, device: str, page_url: str | None, path: str) -> str:
            return self.db.add_screenshot(audit_id, label, device, page_url, path)

        if not claimed:
            self.db.update_audit(audit_id, status="running", started_at=_now())
        self.db.add_event(audit_id, "info", "פותח דפדפן Chromium")
        log.info("audit started", extra={"audit_id": audit_id})
        try:
            collected = await asyncio.wait_for(
                collect(url, self.shot_root / audit_id, allow_private=self.allow_private, progress=on_progress,
                        save_screenshot=save_shot, on_event=on_event),
                timeout=AUDIT_TIMEOUT_S)
            await on_progress("analyze", "מנתח ממצאים ומחשב ציון…")
            steps = [asdict(s) for s in collected.steps]
            facts = collected.facts
            findings = rules.evaluate(facts, steps)
            persona_results = personas.simulate(facts)
            overall, cat_scores = scoring.score(findings, facts, steps)
            self.db.save_audit_results(audit_id, site_id, steps, findings, persona_results)
            title = (facts.get("home") or {}).get("html", {}).get("title")
            if title:
                self.db.set_site_name(site_id, title[:80])
            self.db.add_event(audit_id, "info", f"נמצאו {len(findings)} ממצאים. ציון: {overall if overall is not None else '—'}")
            self.db.update_audit(audit_id, status="done", score=overall, category_scores=cat_scores, facts=facts,
                                 finished_at=_now(), ai_status="pending")
            log.info("audit done", extra={"audit_id": audit_id})
        except asyncio.TimeoutError:
            self._fail(audit_id, f"הבדיקה חרגה מ-{AUDIT_TIMEOUT_S} שניות ונעצרה")
            return
        except BlockedURLError as e:
            self._fail(audit_id, str(e))
            return
        except Exception as e:  # noqa: BLE001
            log.exception("audit crashed", extra={"audit_id": audit_id})
            self._fail(audit_id, f"שגיאה פנימית בבדיקה: {type(e).__name__}: {str(e)[:300]}")
            return
        await self.run_ai(audit_id)

    def _fail(self, audit_id: str, error: str) -> None:
        self.db.add_event(audit_id, "error", error)
        self.db.update_audit(audit_id, status="failed", finished_at=_now(), error=error)

    # ------------------------------------------------------------ שלב AI
    async def run_ai(self, audit_id: str) -> str:
        audit = self.db.get_audit(audit_id, any_account=True)
        account = self.db.get_account(audit["account_id"]) if audit.get("account_id") else None
        if not (self._ai_client or configured()):
            self.db.update_audit(audit_id, ai_status="not_configured")
            self.db.add_event(audit_id, "ai", "ניתוח AI לא בוצע: חסר ANTHROPIC_API_KEY")
            return "not_configured"
        if account and not plans.can_run_ai(account, self.db.usage(account["id"])):
            self.db.update_audit(audit_id, ai_status="quota_exceeded")
            self.db.add_event(audit_id, "ai", "ניתוח AI לא בוצע: נוצלה מכסת ניתוחי ה-AI החודשית")
            return "quota_exceeded"
        self.db.update_audit(audit_id, ai_status="running")
        self.db.add_event(audit_id, "ai", "P1 Intelligence מנתח את הראיות + 5 סוכני לקוח מדומים…")
        client = self._ai_client or get_client()
        steps = self.db.get_steps(audit_id)
        findings = self.db.get_findings(audit_id)
        shots = self.db.list_screenshots(audit_id, with_paths=True)
        prev = self.db.previous_done_audit(audit)
        comp = compare.compare(prev, self.db.get_findings(prev["id"]), audit, findings) if prev else None
        creator = self.db.get_user(audit["created_by"]) if audit.get("created_by") else None
        lang = (creator or {}).get("locale", "he")
        self.db.clear_ai_results(audit_id)

        async def main_analysis():
            try:
                result, usage = await analyst.analyze(client, audit, steps, findings, shots, comp, lang)
                self.db.record_ai_run(audit_id=audit_id, account_id=audit.get("account_id"), kind="analysis",
                                      status="done", usage=usage, result=result)
                self.db.add_findings(audit_id, audit["site_id"], analyst.to_findings(result))
                return True
            except IntelligenceError as e:
                self.db.record_ai_run(audit_id=audit_id, account_id=audit.get("account_id"), kind="analysis",
                                      status="failed", error=e.message)
                self.db.add_event(audit_id, "error", f"ניתוח AI נכשל: {e.message}")
                return False

        async def persona_agents():
            res = await personas_ai.run_all(client, audit, steps, findings, shots, lang)
            ok = 0
            for key, (data, usage, err) in res.items():
                self.db.record_ai_run(audit_id=audit_id, account_id=audit.get("account_id"), kind=f"persona:{key}",
                                      status="done" if data else "failed", usage=usage, result=data, error=err)
                ok += bool(data)
            return ok

        main_ok, personas_ok = await asyncio.gather(main_analysis(), persona_agents())
        status = "done" if main_ok and personas_ok == len(personas_ai.PERSONAS) else ("partial" if main_ok or personas_ok else "failed")
        self.db.update_audit(audit_id, ai_status=status)
        self.db.add_event(audit_id, "ai", {"done": "ניתוח ה-AI הושלם", "partial": "ניתוח ה-AI הושלם חלקית",
                                           "failed": "ניתוח ה-AI נכשל"}[status])
        return status

    def delete(self, audit_id: str) -> None:
        self.db.delete_audit(audit_id)
        shutil.rmtree(self.shot_root / audit_id, ignore_errors=True)
