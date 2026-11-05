"""מנהל הבדיקות — מריץ בדיקה ברקע, שומר התקדמות ותוצאות."""
from __future__ import annotations

import asyncio
import shutil
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .. import config
from ..db import Database
from ..research.analyzer import BlockedURLError, assert_public_host, normalize_url
from . import personas, rules, scoring
from .collector import collect

AUDIT_TIMEOUT_S = 240


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditRunner:
    def __init__(self, db: Database, *, allow_private: bool = False, shot_root: Path | None = None):
        self.db = db
        self.allow_private = allow_private
        self.shot_root = shot_root or config.SCREENSHOT_DIR
        self._sem = asyncio.Semaphore(config.MAX_CONCURRENT_AUDITS)
        self._tasks: set[asyncio.Task] = set()

    def start(self, raw_url: str) -> dict:
        """מאמת את הכתובת, יוצר רשומת בדיקה ומתחיל להריץ ברקע. זורק ValueError על כתובת לא תקינה."""
        url = normalize_url(raw_url)
        if not self.allow_private:
            assert_public_host(url)
        p = urlparse(url)
        site = self.db.get_or_create_site(f"{p.scheme}://{p.netloc}".lower())
        audit = self.db.create_audit(site["id"], url)
        task = asyncio.create_task(self.run(audit["id"], site["id"], url))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return audit

    async def wait_all(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def run(self, audit_id: str, site_id: str, url: str) -> None:
        progress: list[dict] = []

        async def on_progress(key: str, msg: str):
            progress.append({"key": key, "message": msg, "at": _now()})
            self.db.update_audit(audit_id, progress=progress)

        async with self._sem:
            self.db.update_audit(audit_id, status="running", started_at=_now())
            shot_dir = self.shot_root / audit_id

            def save_shot(label: str, device: str, page_url: str | None, path: str) -> str:
                return self.db.add_screenshot(audit_id, label, device, page_url, path)

            try:
                collected = await asyncio.wait_for(
                    collect(url, shot_dir, allow_private=self.allow_private, progress=on_progress,
                            save_screenshot=save_shot),
                    timeout=AUDIT_TIMEOUT_S,
                )
                await on_progress("analyze", "מנתח ממצאים ומריץ סימולציית לקוחות…")
                steps = [asdict(s) for s in collected.steps]
                facts = collected.facts
                findings = rules.evaluate(facts, steps)
                persona_results = personas.simulate(facts)
                overall, cat_scores = scoring.score(findings, facts, steps)
                self.db.save_audit_results(audit_id, site_id, steps, findings, persona_results)
                title = (facts.get("home") or {}).get("html", {}).get("title")
                if title:
                    self.db.set_site_name(site_id, title[:80])
                await on_progress("done", "הבדיקה הושלמה")
                self.db.update_audit(audit_id, status="done", score=overall, category_scores=cat_scores,
                                     facts=facts, finished_at=_now())
            except asyncio.TimeoutError:
                self.db.update_audit(audit_id, status="failed", finished_at=_now(),
                                     error=f"הבדיקה חרגה מ-{AUDIT_TIMEOUT_S} שניות ונעצרה")
            except BlockedURLError as e:
                self.db.update_audit(audit_id, status="failed", finished_at=_now(), error=str(e))
            except Exception as e:  # noqa: BLE001 — כל כשל צריך להירשם, לא להיעלם
                traceback.print_exc()
                self.db.update_audit(audit_id, status="failed", finished_at=_now(),
                                     error=f"שגיאה פנימית בבדיקה: {type(e).__name__}: {str(e)[:300]}")

    def delete(self, audit_id: str) -> bool:
        if not self.db.get_audit(audit_id):
            return False
        self.db.delete_audit(audit_id)
        shutil.rmtree(self.shot_root / audit_id, ignore_errors=True)
        return True
