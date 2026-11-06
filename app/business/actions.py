"""P1 Human Approval Center — פעולות שהמערכת מכינה ומבצעת רק אחרי אישור.

סוגי פעולות שקיימים היום (כולם בטוחים — אף אחד לא משנה את האתר החי):
- run_audit       הרצת בדיקת אתר בדפדפן (צורך בדיקה אחת מהמכסה).
- verify_fix      בדיקה חוזרת שמודדת אם תיקונים שסומנו כמיושמים באמת נעלמו מהאתר.
- enable_monitor  הפעלת שמירה קבועה (Smart Monitor).
- fix_package     חבילת תיקון מוכנה להעברה למי שמתחזק את האתר (טקסטים, קוד, שלבים). לא נוגעת באתר.
שינוי ישיר באתר חי ידרוש חיבור (Shopify / WordPress) + אישור + גיבוי + שחזור — עוד לא קיים, ולכן לא מוצג.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from ..audit.compare import compare
from ..db import Database
from ..fixstudio import catalog
from ..saas import plans
from . import store

KINDS = {
    "run_audit": {"risk": "none", "changes": ["תרוץ בדיקת אתר אחת בדפדפן (נספרת במכסה החודשית)",
                                              "הסוכנים גולשים כמו לקוחות ועוצרים בקופה — בלי למלא פרטים ובלי לקנות",
                                              "האתר עצמו לא משתנה"]},
    "verify_fix": {"risk": "none", "changes": ["תרוץ בדיקת אתר חוזרת (נספרת במכסה)",
                                               "בסיום — השוואה: אילו בעיות באמת נעלמו ואילו עדיין קיימות", "האתר עצמו לא משתנה"]},
    "enable_monitor": {"risk": "low", "changes": ["תופעל בדיקה אוטומטית קבועה של האתר לפי התדירות שבחרתם",
                                                  "כל בדיקה נספרת במכסה החודשית", "תקבלו התראה על בעיות חדשות, תיקונים ושינויי ציון",
                                                  "אפשר לכבות בכל רגע במסך 'אתרים'"]},
    "send_whatsapp": {"risk": "high", "changes": ["תישלח הודעת WhatsApp אמיתית ללקוח, מהמספר העסקי שלכם (WhatsApp Business API הרשמי)",
                                                  "לפי כללי WhatsApp: הודעה חופשית רק תוך 24 שעות מהודעת הלקוח", "אי אפשר לבטל הודעה שנשלחה"]},
    "send_email": {"risk": "high", "changes": ["יישלח מייל אמיתי ללקוח משרת המייל שהגדרתם", "אי אפשר לבטל מייל שנשלח"]},
    "publish_page": {"risk": "medium", "changes": ["הדף יפורסם בכתובת ציבורית בשרת של P1 (/p/…) — כל מי שיש לו את הקישור יוכל לראות אותו",
                                                   "הטופס בדף יתחיל לקלוט פניות אמיתיות ל-CRM", "אפשר לבטל פרסום בכל רגע"]},
    "fix_package": {"risk": "none", "changes": ["תיווצר חבילת תיקון להורדה: מה לשנות, טקסטים מוכנים וקוד לדוגמה",
                                                 "סטטוס התיקון יסומן 'אושר'", "האתר החי לא משתנה — את השינוי מבצע מי שמתחזק את האתר"]},
}


def propose(db: Database, ctx_account: dict, user_id: str | None, item: dict) -> dict:
    """יוצר פעולה מוצעת מתוך פריט בתוכנית. מחזיר פעולה קיימת אם כבר יש אחת פתוחה לאותו יעד."""
    kind = item["kind"]
    if kind not in KINDS:
        raise ValueError("לפריט הזה אין פעולה שניתן לבצע מכאן")
    aid = ctx_account["id"]
    existing = store.open_action_for(db, aid, kind, item["key"])
    if existing:
        return existing
    payload = {**item["payload"], "key": item["key"]}
    a = store.create_action(db, aid, kind=kind, title=item["title"], summary=item["why"], changes=KINDS[kind]["changes"],
                            risk=KINDS[kind]["risk"], payload=payload, source=item.get("source", "rules"),
                            site_id=payload.get("site_id"), user_id=user_id)
    store.log(db, aid, "action_proposed", f"הוכנה פעולה: {a['title']}", ref_type="action", ref_id=a["id"], user_id=user_id)
    return a


def reject(db: Database, action: dict, user_id: str | None) -> dict:
    if action["status"] != "proposed":
        raise ValueError("אפשר לדחות רק פעולה שממתינה לאישור")
    store.update_action(db, action["id"], action["account_id"], status="rejected", decided_at=store.now(), decided_by=user_id)
    store.log(db, action["account_id"], "action_rejected", f"נדחתה: {action['title']}", ref_type="action", ref_id=action["id"], user_id=user_id)
    return store.get_action(db, action["id"], action["account_id"])  # type: ignore[return-value]


def approve_and_execute(db: Database, runner, account: dict, user_id: str | None, action: dict) -> dict:
    """אישור אנושי → ביצוע. כל כשל נשמר על הפעולה ומוצג למשתמש."""
    if action["status"] != "proposed":
        raise ValueError("הפעולה כבר טופלה")
    aid = account["id"]
    store.update_action(db, action["id"], aid, status="executing", decided_at=store.now(), decided_by=user_id)
    store.log(db, aid, "action_approved", f"אושרה: {action['title']}", ref_type="action", ref_id=action["id"], user_id=user_id)
    try:
        result, final = _execute(db, runner, account, user_id, action)
        store.update_action(db, action["id"], aid, status=final, result=result,
                            executed_at=store.now() if final == "done" else None)
        if final == "done":
            store.log(db, aid, "action_done", f"בוצעה: {action['title']}", ref_type="action", ref_id=action["id"], user_id=user_id)
    except (ValueError, plans.QuotaError) as e:
        msg = getattr(e, "message", None) or str(e)
        store.update_action(db, action["id"], aid, status="failed", error=msg[:500])
        store.log(db, aid, "action_failed", f"נכשלה: {action['title']}", detail=msg[:300], ref_type="action", ref_id=action["id"])
    return refresh(db, store.get_action(db, action["id"], aid))  # type: ignore[arg-type]


def _site(db: Database, account: dict, site_id: str | None) -> dict:
    site = db.get_site(site_id, account["id"]) if site_id else None
    if not site:
        raise ValueError("האתר לא נמצא בחשבון")
    if not site.get("authorized_at"):
        raise ValueError("לאתר הזה אין אישור בעלות/הרשאה — אשרו אותו במסך 'אתרים'")
    return site


def _execute(db: Database, runner, account: dict, user_id: str | None, action: dict) -> tuple[dict, str]:
    k, p = action["kind"], action["payload"]
    if k in ("run_audit", "verify_fix"):
        site = _site(db, account, p.get("site_id"))
        audit = runner.enqueue(p.get("url") or site["url"], account, user_id, trigger="action", demo=bool(site.get("is_demo")))
        return {"audit_id": audit["id"]}, "executing"  # מסתיים כשהבדיקה מסתיימת (refresh)
    if k == "enable_monitor":
        from .. import monitor as mon
        site = _site(db, account, p.get("site_id"))
        freq = p.get("frequency", "monthly")
        if freq not in plans.plan_of(account)["monitor"]:
            raise ValueError("התדירות הזו לא כלולה במסלול")
        db.upsert_monitor(site["id"], account["id"], freq, True, mon.next_run(freq))
        return {"frequency": freq, "next_run_at": db.get_monitor(site["id"])["next_run_at"]}, "done"
    if k in ("send_whatsapp", "send_email"):
        from . import studio as _st
        lead = _st.get_lead(db, p["lead_id"], account["id"])
        if not lead:
            raise ValueError("הפנייה לא נמצאה")
        if k == "send_whatsapp":
            from ..integrations import connectors
            try:
                from ..integrations import accounts as _acc
                res = connectors.wa_send_text(lead["contact"] or "", p["body"], cfg=_acc.load(db, account["id"], "whatsapp"))
            except RuntimeError as e:
                raise ValueError(str(e))
        else:
            import re as _re
            from ..saas import recovery
            m = _re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", lead["contact"] or "")
            if not recovery.email_configured():
                raise ValueError("שליחת מייל לא מחוברת (חסר P1_SMTP_HOST / P1_SMTP_FROM)")
            if not m:
                raise ValueError("לפנייה אין כתובת מייל")
            recovery.send_email(m.group(0), "תשובה מ-" + (account.get("name") or "העסק"), p["body"])
            res = {"to": m.group(0)}
        _st.update_lead(db, lead["id"], account["id"], status="contacted")
        return res, "done"
    if k == "publish_page":
        from . import pages
        pg = pages.get(db, p["page_id"], account["id"])
        if not pg:
            raise ValueError("הדף לא נמצא")
        pages.set_status(db, pg["id"], account["id"], "published")
        from .. import config
        return {"url": f"{config.PUBLIC_URL}/p/{pg['id']}/", "page_id": pg["id"]}, "done"
    if k == "fix_package":
        f = db.get_finding(p["finding_id"], account["id"])
        if not f:
            raise ValueError("הממצא לא נמצא")
        audit = db.get_audit(f["audit_id"], account["id"])
        fix = catalog.propose(f, audit.get("facts") or {})
        db.set_fix_status(f["id"], "approved", account["id"])
        return {"finding": {k2: f.get(k2) for k2 in ("id", "title", "detail", "severity", "category", "rule_id", "why_it_matters")},
                "site_url": audit.get("site_url") or audit.get("start_url"), "fix": fix}, "done"
    raise ValueError("סוג פעולה לא נתמך")


def refresh(db: Database, action: dict) -> dict:
    """פעולות שמחכות לבדיקה: כשהבדיקה מסתיימת — מעדכנים סטטוס ותוצאה (כולל אימות תיקונים במדידה)."""
    if action["kind"] not in ("run_audit", "verify_fix") or action["status"] != "executing" or not action.get("result"):
        return action
    aid = action["account_id"]
    audit = db.get_audit(action["result"]["audit_id"], aid)
    if not audit or audit["status"] in ("queued", "running"):
        return action
    if audit["status"] != "done":
        store.update_action(db, action["id"], aid, status="failed", error=f"הבדיקה הסתיימה בסטטוס {audit['status']}: {audit.get('error') or ''}"[:500])
        return store.get_action(db, action["id"], aid)  # type: ignore[return-value]
    result = {**action["result"], "score": audit.get("score")}
    if action["kind"] == "verify_fix":
        before = db.get_audit(action["payload"]["audit_id"], aid)
        before_f = db.get_findings(before["id"])
        target = {f["rule_id"]: f for f in before_f if f["id"] in set(action["payload"].get("finding_ids", []))}
        after_rules = {f["rule_id"] for f in db.get_findings(audit["id"]) if f["source"] == "measured"}
        result["verified_fixed"] = [{"rule_id": r, "title": f["title"]} for r, f in target.items() if r not in after_rules]
        result["still_present"] = [{"rule_id": r, "title": f["title"]} for r, f in target.items() if r in after_rules]
        result["comparison"] = {k: v for k, v in compare(before, before_f, audit, db.get_findings(audit["id"])).items()
                                if k in ("score_delta", "fixed", "new")}
    store.update_action(db, action["id"], aid, status="done", result=result, executed_at=audit.get("finished_at") or store.now())
    title = action["title"] if action["kind"] == "run_audit" else \
        f"אימות תיקונים: {len(result['verified_fixed'])} נעלמו · {len(result['still_present'])} עדיין קיימים"
    store.log(db, aid, "action_done", f"הושלמה: {title}", ref_type="audit", ref_id=audit["id"])
    return store.get_action(db, action["id"], aid)  # type: ignore[return-value]


def package_html(action: dict) -> str:
    """חבילת תיקון כקובץ HTML עצמאי להורדה/שליחה למתחזק האתר."""
    r = action["result"] or {}
    f, fix = r.get("finding", {}), r.get("fix", {})
    e = html.escape
    steps = "".join(f"<li>{e(s)}</li>" for s in fix.get("steps", []))
    copy = "".join(f"<h3>{e(c.get('label', ''))}</h3><pre>{e(c.get('text', ''))}</pre>" for c in fix.get("copy", []))
    design = "".join(f"<li>{e(d)}</li>" for d in fix.get("design", []))
    code = f"<h2>קוד לדוגמה</h2><pre dir='ltr'>{e(fix['code'] if isinstance(fix.get('code'), str) else str(fix.get('code')))}</pre>" if fix.get("code") else ""
    ph = "<p class='warn'>בטקסט יש [להשלמה] — מידע שלא נמצא באתר. יש להשלים לפני פרסום (P1 לא ממציא פרטים).</p>" if fix.get("has_placeholders") else ""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>חבילת תיקון · {e(f.get('title', ''))}</title>
<style>body{{font:16px/1.7 system-ui,Arial,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#16161d}}
h1{{font-size:24px}}pre{{background:#f4f4f8;padding:12px;border-radius:8px;white-space:pre-wrap}}.muted{{color:#666}}
.warn{{background:#fff4d9;padding:10px;border-radius:8px}}</style></head><body>
<p class="muted">P1 AI · חבילת תיקון · {when} · {e(r.get('site_url') or '')}</p>
<h1>{e(f.get('title', ''))}</h1><p>{e(f.get('detail') or '')}</p>
<p><strong>למה זה חשוב:</strong> {e(f.get('why_it_matters') or '')}</p>
<h2>מה לעשות</h2><p>{e(fix.get('summary', ''))}</p><ol>{steps}</ol>{ph}{copy}
{f'<h2>עיצוב</h2><ul>{design}</ul>' if design else ''}{code}
<p class="muted">הממצא נמדד בדפדפן אמיתי. ההצעה נוצרה מתבנית (templates). אחרי היישום — הריצו ב-P1 "אימות תיקונים" כדי למדוד שהבעיה נעלמה.</p>
</body></html>"""
