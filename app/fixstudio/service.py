"""Fix Studio — שירות: הצעות תיקון, תצוגות מקדימות וסטטוס יישום."""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..db import Database
from . import catalog
from .sandbox import render_preview

FIX_STATUSES = ("proposed", "approved", "applied", "rejected")


def page_url_for(audit: dict, finding: dict, page: str) -> str | None:
    facts = audit.get("facts") or {}
    if page == "product" and (facts.get("product") or {}).get("url"):
        return facts["product"]["url"]
    if page == "cart" and (facts.get("cart") or {}).get("url"):
        return facts["cart"]["url"]
    if page == "home":
        return facts.get("final_url") or audit["start_url"]
    return (finding.get("evidence") or {}).get("page_url") or facts.get("final_url") or audit["start_url"]


def list_fixes(db: Database, audit: dict) -> list[dict]:
    facts = audit.get("facts") or {}
    previews = db.latest_previews(audit["id"])
    out = []
    for f in db.get_findings(audit["id"]):
        if f["source"] not in ("measured", "ai"):
            continue
        fix = catalog.propose(f, facts)
        out.append({"finding": f, "fix": fix, "preview": previews.get(f["id"])})
    out.sort(key=lambda x: (x["finding"].get("priority") or 999, x["finding"]["source"] != "measured"))
    return out


async def make_preview(db: Database, audit: dict, finding: dict, shot_root: Path | None = None) -> dict:
    fix = catalog.propose(finding, audit.get("facts") or {})
    pv = fix["preview"]
    base = {"finding_id": finding["id"], "audit_id": audit["id"], "account_id": audit.get("account_id")}
    if not pv.get("supported"):
        db.add_fix_preview(**base, status="unsupported", error="לתיקון הזה אין תצוגה חזותית (תיקון טכני/תהליכי)")
        return db.latest_previews(audit["id"])[finding["id"]]
    url = page_url_for(audit, finding, pv.get("page", "home"))
    out_dir = (shot_root or config.SCREENSHOT_DIR) / audit["id"] / f"fix-{finding['id'][:12]}"
    try:
        res = await render_preview(url, pv, out_dir, allow_private=config.DEV_ALLOW_PRIVATE_TARGETS or audit.get("_allow_private", False))
    except Exception as e:  # noqa: BLE001 — כל כשל נשמר ומוצג למשתמש
        db.add_fix_preview(**base, status="failed", device=pv.get("device", "desktop"), page_url=url, error=str(e)[:300])
        return db.latest_previews(audit["id"])[finding["id"]]
    before = db.add_screenshot(audit["id"], "fix-before", res["device"], url, res["before"])
    after = db.add_screenshot(audit["id"], "fix-after", res["device"], url, res["after"])
    ok = any(a["ok"] for a in res["applied"])
    db.add_fix_preview(**base, status="done" if ok else "failed", device=res["device"], page_url=url, before_shot=before,
                       after_shot=after, applied=res["applied"],
                       error=None if ok else "האלמנט שצריך לתקן לא נמצא בעמוד כרגע — ייתכן שהעמוד השתנה מאז הבדיקה")
    return db.latest_previews(audit["id"])[finding["id"]]
