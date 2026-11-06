"""P1 CEO — המנהל העסקי: מדד בריאות, תוכנית צמיחה, 3 הפעולות הבאות, דוח שבועי והוכחת ערך.

עקרונות:
- engine="rules": כל מסקנה כאן נגזרת בשקיפות מנתונים שנמדדו (בדיקות אתר) או שבעל העסק הזין. אין המצאות.
- כשאין מספיק מידע — אומרים "אין מספיק מידע" ומציינים מה חסר, במקום לנחש.
- סיכום בשפה טבעית ע"י מודל (ai_brief) רק כשמנוע אמיתי פעיל; אחרת ai_status=not_configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from ..audit.compare import compare
from ..db import Database
from ..saas import plans
from . import brain, store

# אומדן שקוף: כמה דקות לוקח לאדם לעבור ידנית על אתר במחשב ובטלפון, כמו בדיקה אחת של P1.
# זה אומדן (לא מדידה) — מוצג כך בממשק, ובעל העסק יכול להחליף אותו בערך משלו בפרופיל.
ASSUMED_MANUAL_MINUTES_PER_AUDIT = 60

W = {"high": 3, "medium": 2, "low": 1}
STALE_DAYS = 14


def _parse(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url if "://" in url else "https://" + url)
    return (p.netloc or "").lower().removeprefix("www.") or None


# ---------------------------------------------------------------- תמונת מצב
def snapshot(db: Database, account: dict) -> dict:
    aid = account["id"]
    prof = store.get_profile(db, aid)
    data = prof["data"] if prof else {}
    sites = db.sites_overview(aid)
    want = _origin(data.get("website"))
    site = next((s for s in sites if _origin(s["url"]) == want), None) if want else None
    site = site or (sites[0] if sites else None)
    audits = db.list_audits(aid, site["id"]) if site else []
    done = [a for a in audits if a["status"] == "done"]
    latest = db.get_audit(done[0]["id"], aid) if done else None
    findings = db.get_findings(latest["id"]) if latest else []
    previous = db.get_audit(done[1]["id"], aid) if len(done) > 1 else None
    cmp = compare(previous, db.get_findings(previous["id"]), latest, findings) if previous and latest else None
    return {"account": account, "profile": data, "profile_updated_at": prof["updated_at"] if prof else None,
            "completeness": brain.completeness(data), "sites": sites, "site": site, "audits": audits, "done": done,
            "latest": latest, "findings": findings, "comparison": cmp,
            "monitor": db.get_monitor(site["id"]) if site else None, "actions": store.list_actions(db, aid)}


# ---------------------------------------------------------------- Business Health Score
DOMAIN_NEEDS = {
    "marketing": "חיבור Google Analytics / Google Ads / Meta Ads · עוד לא זמין במערכת",
    "sales": "חיבור לחנות (Shopify / WooCommerce) או למערכת CRM · עוד לא זמין במערכת",
    "support": "חיבור WhatsApp Business או מערכת פניות · עוד לא זמין במערכת",
    "profit": "נתוני הכנסות והוצאות מהנהלת החשבונות · עוד לא זמין במערכת",
    "operations": "חיבור מערכת תורים/הזמנות · עוד לא זמין במערכת",
}


def health(snap: dict) -> dict:
    L = snap["latest"]
    domains = []
    if L:
        domains.append({"id": "website", "status": "measured", "score": L["score"], "source": "measured",
                        "basis": f"בדיקת דפדפן אמיתית מ-{(L.get('finished_at') or '')[:10]}",
                        "audit_id": L["id"]})
    else:
        domains.append({"id": "website", "status": "no_data", "score": None, "source": None,
                        "missing": "להריץ בדיקת אתר ראשונה"})
    for d, need in DOMAIN_NEEDS.items():
        domains.append({"id": d, "status": "no_data", "score": None, "source": None, "missing": need})
    scores = [x["score"] for x in snap["done"] if x.get("score") is not None]
    if len(scores) >= 2:
        domains.append({"id": "growth", "status": "measured", "score": None, "source": "measured",
                        "trend": scores[0] - scores[1], "basis": f"שינוי ציון האתר בין {len(scores)} בדיקות אחרונות"})
    else:
        domains.append({"id": "growth", "status": "no_data", "score": None, "source": None,
                        "missing": "לפחות שתי בדיקות של אותו אתר (מגמה)"})
    measured = [x for x in domains if x["status"] == "measured" and x["score"] is not None]
    enough = len(measured) >= 3
    return {"domains": domains, "overall": round(sum(x["score"] for x in measured) / len(measured)) if enough else None,
            "overall_reason": None if enough else
            "אין מספיק מידע כדי לקבוע ציון בריאות עסקי כולל. כרגע נמדד רק האתר — שאר התחומים דורשים חיבורי נתונים."}


# ---------------------------------------------------------------- תוכנית צמיחה + One-Click Growth
def _item(key: str, title: str, why: str, *, impact: str, effort: str, confidence: str, minutes: int,
          kind: str, risk: str = "none", evidence: str | None = None, link: str | None = None, payload: dict | None = None,
          area: str = "website") -> dict:
    score = round(W[impact] * W[confidence] * 10 / W[effort]) - {"none": 0, "low": 1, "medium": 3, "high": 6}[risk]
    return {"key": key, "title": title, "why": why, "impact": impact, "effort": effort, "confidence": confidence,
            "minutes": minutes, "risk": risk, "cost": "none", "evidence": evidence, "kind": kind, "link": link,
            "payload": payload or {}, "priority_score": score, "area": area, "source": "rules"}


def plan(snap: dict) -> dict:
    items: list[dict] = []
    comp, site, L, acc = snap["completeness"], snap["site"], snap["latest"], snap["account"]
    if not comp["ready"]:
        items.append(_item("profile", "להשלים את פרופיל העסק",
                           "בלי להכיר את העסק (קהל, מטרות, הצעה) המערכת לא יכולה לתעדף נכון. לוקח כ-3 דקות.",
                           impact="medium", effort="low", confidence="high", minutes=3, kind="link", link="#/business",
                           area="brain"))
    if not site:
        items.append(_item("add_site", "להוסיף את האתר של העסק ולהריץ בדיקה ראשונה",
                           "בדיקה אמיתית בדפדפן מגלה מה מפריע ללקוחות לקנות או לפנות.",
                           impact="high", effort="low", confidence="high", minutes=3, kind="link", link="#/audits"))
    elif not L or (_parse(L.get("finished_at")) or datetime.min.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc) - timedelta(days=STALE_DAYS):
        items.append(_item(f"audit:{site['id']}", "להריץ בדיקת אתר עדכנית" if L else "להריץ בדיקת אתר ראשונה",
                           "הבדיקה האחרונה ישנה מ-14 יום — אתרים משתנים ונשברים." if L else "עוד אין בדיקה שהסתיימה לאתר.",
                           impact="high", effort="low", confidence="high", minutes=3, kind="run_audit",
                           payload={"site_id": site["id"], "url": (L or {}).get("start_url") or site["url"]}))
    if L:
        applied = [f for f in snap["findings"] if f["source"] == "measured" and f.get("fix_status") == "applied"]
        if applied:
            items.append(_item(f"verify:{L['id']}", f"לוודא שהתיקונים עבדו ({len(applied)})",
                               "סימנתם תיקונים כמיושמים. בדיקה חוזרת מודדת אם הבעיה באמת נעלמה מהאתר.",
                               impact="high", effort="low", confidence="high", minutes=3, kind="verify_fix",
                               payload={"site_id": site["id"], "audit_id": L["id"], "url": L.get("start_url") or site["url"],
                                        "finding_ids": [f["id"] for f in applied]}))
        approved = [f for f in snap["findings"] if f["source"] == "measured" and f.get("fix_status") == "approved"]
        if approved:
            items.append(_item(f"apply:{L['id']}", f"ליישם באתר {len(approved)} תיקונים שאישרתם",
                               "חבילות התיקון מוכנות. אחרי שמי שמתחזק את האתר מיישם אותן — סמנו 'יושם' ו-P1 יבדוק שהבעיה באמת נעלמה.",
                               impact="high", effort="medium", confidence="high", minutes=30, kind="link", link="#/approvals"))
        open_f = [f for f in snap["findings"] if f["source"] == "measured" and f.get("fix_status") == "proposed"]
        open_f.sort(key=lambda f: f.get("priority") or 999)
        for f in open_f[:5]:
            items.append(_item(f"fix:{f['id']}", f"לתקן: {f['title']}", f.get("why_it_matters") or f.get("detail") or "",
                               impact=f.get("impact") or "medium",
                               effort={"critical": "low", "high": "low"}.get(f["severity"], "medium"),
                               confidence="high", minutes=20, kind="fix_package", risk="none",
                               evidence=f"נמדד בבדיקה מ-{(L.get('finished_at') or '')[:10]} · חומרה: {f['severity']}",
                               payload={"finding_id": f["id"], "audit_id": L["id"]}, area=f["category"]))
    mon = snap["monitor"]
    if site and not (mon and mon.get("enabled")):
        allowed = plans.plan_of(acc)["monitor"]
        freq = next((f for f in ("daily", "weekly", "monthly") if f in allowed), "monthly")
        items.append(_item(f"monitor:{site['id']}", "להפעיל שמירה קבועה על האתר",
                           f"בדיקה אוטומטית ({freq}) מגלה תקלות חדשות לפני שהלקוחות מגלים אותן, ושולחת התראה.",
                           impact="medium", effort="low", confidence="high", minutes=1, kind="enable_monitor",
                           payload={"site_id": site["id"], "frequency": freq}))
    # פעולות שכבר ממתינות/רצות — מחוברות לפריט כדי שהכפתור יפתח אותן ולא ייצור כפילות
    open_by_key = {a["payload"].get("key"): a for a in snap["actions"] if a["status"] in ("proposed", "approved", "executing")}
    for it in items:
        a = open_by_key.get(it["key"])
        it["open_action"] = {"id": a["id"], "status": a["status"]} if a else None
    items.sort(key=lambda x: -x["priority_score"])
    return {"engine": "rules", "items": items, "top3": items[:3],
            "method": "עדיפות = השפעה × ביטחון ÷ מאמץ, פחות סיכון. ההשפעה והחומרה מגיעות מממצאים שנמדדו בפועל."}


# ---------------------------------------------------------------- הוכחת ערך (Growth Proof)
def proof(db: Database, snap: dict) -> dict:
    aid = snap["account"]["id"]
    with db._conn() as c:
        audits_done = c.execute("SELECT COUNT(*) FROM audits WHERE account_id=? AND status='done'", (aid,)).fetchone()[0]
        steps = c.execute("""SELECT COUNT(*) FROM audit_events e JOIN audits a ON a.id=e.audit_id
                             WHERE a.account_id=? AND e.kind IN ('click','navigate','select','type','scroll','loaded')""", (aid,)).fetchone()[0]
        dur = c.execute("""SELECT started_at, finished_at FROM audits WHERE account_id=? AND status='done'
                           AND started_at IS NOT NULL AND finished_at IS NOT NULL""", (aid,)).fetchall()
    machine_minutes = round(sum(((_parse(r["finished_at"]) - _parse(r["started_at"])).total_seconds() for r in dur
                                 if _parse(r["finished_at"]) and _parse(r["started_at"])), 0.0) / 60, 1)
    # תקלות שנפתרו — לפי השוואה בין כל שתי בדיקות עוקבות של אותו אתר (מדידה, לא הצהרה)
    fixed_verified: list[dict] = []
    for s in snap["sites"]:
        done = [a for a in db.list_audits(aid, s["id"]) if a["status"] == "done"]
        for newer, older in zip(done, done[1:]):
            n, o = db.get_audit(newer["id"], aid), db.get_audit(older["id"], aid)
            for f in compare(o, db.get_findings(o["id"]), n, db.get_findings(n["id"]))["fixed"]:
                fixed_verified.append({**f, "site": s["url"], "verified_at": n.get("finished_at"), "audit_id": n["id"]})
    actions_done = [a for a in snap["actions"] if a["status"] == "done"]
    manual = snap["profile"].get("manual_minutes_per_audit") or ASSUMED_MANUAL_MINUTES_PER_AUDIT
    return {
        "audits_done": audits_done, "browser_steps": steps, "machine_minutes": machine_minutes,
        "issues_fixed_verified": fixed_verified, "actions_done": len(actions_done),
        "time_saved_estimate": {"minutes": audits_done * manual, "kind": "estimate",
                                "assumption": f"{manual} דקות עבודה ידנית לכל בדיקה (אומדן, לא מדידה)"},
        "revenue_claim": None,
        "revenue_note": "P1 לא מייחס שינוי בהכנסות בלי חיבור לנתוני מכירות ומדידה מבוקרת.",
    }


# ---------------------------------------------------------------- ציר זמן (Growth Timeline)
def timeline(db: Database, snap: dict, limit: int = 100) -> list[dict]:
    aid = snap["account"]["id"]
    out = [{"at": r["created_at"], "kind": r["kind"], "title": r["title"], "detail": r["detail"],
            "ref_type": r["ref_type"], "ref_id": r["ref_id"]} for r in store.list_activity(db, aid, limit)]
    for s in snap["sites"]:
        for a in db.list_audits(aid, s["id"]):
            if a["status"] in ("done", "failed"):
                out.append({"at": a.get("finished_at") or a["created_at"], "kind": f"audit_{a['status']}",
                            "title": ("בדיקת אתר הסתיימה" if a["status"] == "done" else "בדיקת אתר נכשלה") + f" · {s['url']}",
                            "detail": f"ציון {a['score']}" if a.get("score") is not None else (a.get("error") or ""),
                            "ref_type": "audit", "ref_id": a["id"]})
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return out[:limit]


# ---------------------------------------------------------------- דוח שבועי (Weekly CEO Report)
def weekly(db: Database, snap: dict, days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    period = [a for a in snap["audits"] if (a.get("finished_at") or a["created_at"]) >= since]
    tl = [e for e in timeline(db, snap, 300) if (e["at"] or "") >= since]
    cmp = snap["comparison"]
    p = plan(snap)
    lines = []
    if not snap["latest"]:
        lines.append("עוד אין בדיקת אתר שהסתיימה — אין על מה לדווח. הצעד הראשון: להריץ בדיקה.")
    else:
        L = snap["latest"]
        lines.append(f"ציון האתר בבדיקה האחרונה: {L['score']}/100.")
        if cmp and cmp["score_delta"] is not None:
            lines.append(f"שינוי מהבדיקה הקודמת: {cmp['score_delta']:+d} נקודות · {len(cmp['fixed'])} בעיות נעלמו · {len(cmp['new'])} בעיות חדשות.")
        open_n = sum(1 for f in snap["findings"] if f["source"] == "measured" and f.get("fix_status") in ("proposed", "approved"))
        lines.append(f"בעיות פתוחות שנמדדו: {open_n}.")
    return {"engine": "rules", "since": since, "audits_in_period": len(period),
            "events_in_period": len(tl), "summary": lines, "next_actions": p["top3"], "comparison": cmp}


# ---------------------------------------------------------------- סיכום מנהלים ע"י מודל (רק כשמנוע אמיתי פעיל)
BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "insufficient_data": {"type": "array", "items": {"type": "string"}},
        "advice": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "properties": {"title": {"type": "string"}, "why": {"type": "string"},
                                                             "based_on": {"type": "string"}},
                                              "required": ["title", "why", "based_on"]}},
    },
    "required": ["summary", "insufficient_data", "advice"],
}
BRIEF_SYSTEM = ("אתה P1 CEO — יועץ עסקי לבעלי עסקים קטנים בישראל. כתוב בעברית פשוטה וקצרה. "
                "השתמש אך ורק בנתונים שקיבלת (פרופיל שהזין בעל העסק + ממצאים שנמדדו בדפדפן). "
                "אסור להמציא מספרים, אחוזי המרה, הכנסות או תוצאות. כשחסר מידע — כתוב זאת ב-insufficient_data. "
                "בכל עצה ציין ב-based_on על איזה נתון היא מבוססת.")


async def ai_brief(db: Database, snap: dict, engine) -> dict:
    import json as _json
    p = plan(snap)
    facts = {"profile": snap["profile"], "latest_score": (snap["latest"] or {}).get("score"),
             "findings": [{"title": f["title"], "severity": f["severity"], "category": f["category"], "status": f.get("fix_status")}
                          for f in snap["findings"] if f["source"] == "measured"][:25],
             "comparison": snap["comparison"], "rules_plan": [{"title": i["title"], "why": i["why"]} for i in p["top3"]]}
    data, usage = await engine.structured(system=BRIEF_SYSTEM, schema=BRIEF_SCHEMA, effort="medium", max_tokens=4000,
                                          content=[{"type": "text", "text": _json.dumps(facts, ensure_ascii=False)}])
    db.record_ai_run(audit_id=None, account_id=snap["account"]["id"], kind="ceo_brief", status="done", model=usage.model,
                     usage=usage, result=data)
    return {"engine": getattr(engine, "id", "ai"), "model": usage.model, "source": "ai", **data}
