"""P1 Smart Monitor — בדיקות חוזרות לפי לוח זמנים, השוואה, זיהוי בעיות חדשות/שתוקנו, והתראות במערכת."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .audit import compare
from .db import Database
from .logging_setup import log
from .saas import plans

FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def now() -> datetime:
    return datetime.now(timezone.utc)


def next_run(frequency: str, from_: datetime | None = None) -> str:
    return ((from_ or now()) + timedelta(days=FREQ_DAYS[frequency])).isoformat()


def tick(db: Database, runner) -> list[str]:
    """מריץ את כל המעקבים שהגיע זמנם. מחזיר מזהי בדיקות שנוצרו. נקרא מה-worker כל דקה."""
    created = []
    for m in db.due_monitors(now().isoformat()):
        account = db.get_account(m["account_id"]) if m["account_id"] else None
        try:
            audit = runner.enqueue(m["site_url"], account, None, trigger="monitor")
            created.append(audit["id"])
            db.monitor_ran(m["site_id"], audit["id"], next_run(m["frequency"]))
            log.info("monitor audit queued", extra={"audit_id": audit["id"]})
        except plans.QuotaError as e:
            db.monitor_ran(m["site_id"], None, next_run(m["frequency"]))
            db.add_notification(m["account_id"], "monitor_skipped", "בדיקה מתוזמנת לא רצה", e.message, site_id=m["site_id"])
        except ValueError as e:
            db.monitor_ran(m["site_id"], None, next_run(m["frequency"]))
            db.add_notification(m["account_id"], "monitor_skipped", "בדיקה מתוזמנת לא רצה", str(e), site_id=m["site_id"])
    return created


def notify_changes(db: Database, audit_id: str) -> dict | None:
    """אחרי כל בדיקה: השוואה לבדיקה הקודמת → התראות על בעיות חדשות, בעיות שתוקנו ושינוי ציון."""
    audit = db.get_audit(audit_id, any_account=True)
    prev = db.previous_done_audit(audit)
    host = audit.get("site_name") or audit.get("site_url")
    acc = audit.get("account_id")
    if not prev:
        db.add_notification(acc, "first_audit", f"בדיקה ראשונה הושלמה · {host}",
                            f"ציון {audit.get('score')}. מעכשיו כל בדיקה תושווה לזו.", site_id=audit["site_id"], audit_id=audit_id)
        return None
    cmp = compare.compare(prev, db.get_findings(prev["id"]), audit, db.get_findings(audit_id))
    if cmp["new"]:
        db.add_notification(acc, "new_issues", f"{len(cmp['new'])} בעיות חדשות · {host}",
                            " · ".join(f["title"] for f in cmp["new"][:3]), site_id=audit["site_id"], audit_id=audit_id,
                            data={"rule_ids": [f["rule_id"] for f in cmp["new"]]})
    if cmp["fixed"]:
        db.add_notification(acc, "fixed_issues", f"{len(cmp['fixed'])} בעיות תוקנו · {host}",
                            " · ".join(f["title"] for f in cmp["fixed"][:3]), site_id=audit["site_id"], audit_id=audit_id,
                            data={"rule_ids": [f["rule_id"] for f in cmp["fixed"]]})
    d = cmp["score_delta"]
    if d:
        db.add_notification(acc, "score_change", f"הציון {'עלה' if d > 0 else 'ירד'} ב-{abs(d)} · {host}",
                            f"{cmp['before']['score']} → {cmp['after']['score']}", site_id=audit["site_id"], audit_id=audit_id)
    return cmp
