"""P1 Agency Mode — סוכנות שיווק מנהלת כמה לקוחות: אתר לכל לקוח, בדיקות, דוחות, אישורים ומה דורש טיפול.

סביבת הדגמה: 15 לקוחות פיקטיביים (is_demo=1, מסומנים "דמו" בכל מקום). לכל אחד גרסה של חנות הדמו של P1
(/demo-clients/<slug>/) עם שילוב שונה של בעיות מכוונות — והבדיקה שרצה עליהם אמיתית לגמרי.
בדיקות הדמו לא נספרות במכסת הלקוח (הן רצות על התוכן של P1 עצמו).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from .. import config
from ..db import Database
from . import ceo, store

STATIC = Path(__file__).resolve().parent.parent / "static" / "demo-store"
DEMO_TRIGGER = "demo_agency"

# slug, שם, תחום, אילו בעיות תוקנו בגרסה הזו (כל השאר נשארות כמו בחנות הדמו)
DEMO_CLIENTS = [
    ("linen", "סדנת פשתן", "אופנה", set()),
    ("olive", "שמן זית הגליל", "מזון", {"popup"}),
    ("bloom", "פרחי בלום", "פרחים", {"popup", "wa", "tel"}),
    ("kids", "עולם הצעצוע", "צעצועים", {"h1"}),
    ("ceramic", "קרמיקה בעבודת יד", "עיצוב הבית", {"popup", "h1", "tel"}),
    ("coffee", "קלייה טרייה", "קפה", {"wa"}),
    ("yoga", "סטודיו נשימה", "כושר", {"popup", "wa", "tel", "form"}),
    ("pets", "חנות החיות של רוני", "חיות מחמד", {"form"}),
    ("wine", "יקב הגבעה", "יין", {"popup", "h1", "wa", "tel", "form"}),
    ("books", "הספרייה הקטנה", "ספרים", {"tel"}),
    ("jewel", "תכשיטי נועה", "תכשיטים", {"popup", "form"}),
    ("bike", "אופני העיר", "אופניים", {"h1", "wa"}),
    ("tea", "בית התה", "משקאות", {"popup", "tel", "form", "wa"}),
    ("garden", "משתלת השרון", "גינון", set()),
    ("bake", "מאפיית הבוקר", "מאפים", {"popup", "h1", "wa", "tel", "form", "returns"}),
]
DEMO = {c[0]: c for c in DEMO_CLIENTS}


def demo_page(slug: str, path: str) -> tuple[bytes, str] | None:
    """מחזיר (תוכן, סוג) לדף בגרסת הלקוח, או None. רק קבצים מתוך תיקיית חנות הדמו (בלי יציאה ממנה)."""
    c = DEMO.get(slug)
    if not c:
        return None
    rel = path.strip("/")
    if ".." in rel.split("/"):
        return None
    f = (STATIC / rel) if rel else STATIC
    if f.is_dir():
        f = f / "index.html"
    try:
        f.resolve().relative_to(STATIC.resolve())
    except ValueError:
        return None
    if not f.is_file():
        return None
    if f.suffix != ".html":
        return f.read_bytes(), "text/css" if f.suffix == ".css" else "application/octet-stream"
    html = f.read_text(encoding="utf-8")
    _, name, _, fixed = c
    html = html.replace("/demo-store/", f"/demo-clients/{slug}/").replace("סדנת פשתן", name)
    html = html.replace("חנות דמו של P1 AI — לא חנות אמיתית.", f"לקוח דמו של P1 AI ({name}) — לא עסק אמיתי.")
    if "popup" in fixed:
        html = re.sub(r'<div class="popup" id="pop">.*?</div>\n?', "", html, flags=re.S)
    if "wa" in fixed:
        html = html.replace("wa.me/0501234567", "wa.me/972501234567")
    if "tel" in fixed:
        html = html.replace("<nav>", '<nav><a href="tel:+97235551234">התקשרו אלינו</a>', 1)
    if "h1" in fixed:
        html = html.replace("<h1>ברוכים הבאים</h1>", f"<h1>{name} — מוצרים איכותיים עם משלוח חינם מעל 300 ש\"ח</h1>")
    if "form" in fixed:
        html = re.sub(r'<input name="(city|street|zip)"[^>]*>|<input name="birthday"[^>]*>|<input name="last"[^>]*>', "", html)
    if "returns" in fixed:
        pass  # נשמר לבחירה עתידית; הקישור להחזרות נשאר
    return html.encode(), "text/html; charset=utf-8"


# ---------------------------------------------------------------- לקוחות
def list_clients(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clients WHERE account_id=? ORDER BY is_demo, created_at", (account_id,))]


def get_client(db: Database, client_id: str, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT * FROM clients WHERE id=? AND account_id=?", (client_id, account_id)).fetchone()
    return dict(r) if r else None


def add_client(db: Database, account_id: str, name: str, url: str, industry: str | None, is_demo: bool = False) -> dict:
    cid = uuid.uuid4().hex
    with db._conn() as c:
        c.execute("INSERT INTO clients (id, account_id, name, url, industry, is_demo, created_at) VALUES (?,?,?,?,?,?,?)",
                  (cid, account_id, name[:120], url, (industry or "")[:80] or None, int(is_demo), store.now()))
    return get_client(db, cid, account_id)  # type: ignore[return-value]


def delete_client(db: Database, client_id: str, account_id: str) -> bool:
    with db._conn() as c:
        return c.execute("DELETE FROM clients WHERE id=? AND account_id=?", (client_id, account_id)).rowcount > 0


def queue_audit(db: Database, runner, account: dict, user_id: str | None, client: dict) -> dict:
    """בדיקה ללקוח. לקוח דמו — רץ על התוכן של P1 ולא נספר במכסה; לקוח אמיתי — דרך המסלול הרגיל (הרשאה + מכסה)."""
    if not client["is_demo"]:
        return runner.enqueue(client["url"], account, user_id)
    from urllib.parse import urlparse
    p = urlparse(client["url"])
    site = db.get_or_create_site(f"{p.scheme}://{p.netloc}".lower(), account["id"])
    db.authorize_site(site["id"], user_id)
    db.mark_demo_site(site["id"])
    audit = db.create_audit(site["id"], client["url"], account["id"], user_id, trigger=DEMO_TRIGGER)
    db.add_event(audit["id"], "info", f"בדיקת לקוח דמו ({client['name']}) נכנסה לתור")
    runner._wake.set()
    return audit


def seed_demo(db: Database, runner, account: dict, user_id: str | None) -> list[dict]:
    existing = {c["url"] for c in list_clients(db, account["id"]) if c["is_demo"]}
    created = []
    for slug, name, industry, _ in DEMO_CLIENTS:
        url = f"{config.PUBLIC_URL}/demo-clients/{slug}/"
        if url in existing:
            continue
        cl = add_client(db, account["id"], name, url, industry, is_demo=True)
        queue_audit(db, runner, account, user_id, cl)
        created.append(cl)
    store.log(db, account["id"], "agency_demo", f"נוצרה סביבת הדגמה לסוכנות: {len(created)} לקוחות דמו", user_id=user_id)
    return created


def remove_demo(db: Database, account_id: str) -> int:
    with db._conn() as c:
        return c.execute("DELETE FROM clients WHERE account_id=? AND is_demo=1", (account_id,)).rowcount


# ---------------------------------------------------------------- סקירה לסוכנות
def overview(db: Database, account: dict) -> dict:
    aid = account["id"]
    clients = list_clients(db, aid)
    with db._conn() as c:
        audits = [dict(r) for r in c.execute(
            "SELECT id, start_url, status, score, created_at, finished_at, started_at, error FROM audits WHERE account_id=? ORDER BY created_at DESC",
            (aid,))]
    actions = store.list_actions(db, aid)
    out = []
    for cl in clients:
        mine = [a for a in audits if (a["start_url"] or "").startswith(cl["url"].rstrip("/"))]
        done = [a for a in mine if a["status"] == "done"]
        latest = done[0] if done else None
        running = next((a for a in mine if a["status"] in ("queued", "running")), None)
        findings = db.get_findings(latest["id"]) if latest else []
        measured = [f for f in findings if f["source"] == "measured"]
        open_f = [f for f in measured if f.get("fix_status") in ("proposed", "approved")]
        crit = [f for f in open_f if f["severity"] in ("critical", "high")]
        pend = [a for a in actions if a["status"] == "proposed" and (a["payload"].get("url") or "").startswith(cl["url"].rstrip("/"))]
        reasons = []
        if mine and mine[0]["status"] == "failed":
            reasons.append("הבדיקה האחרונה נכשלה")
        if latest and latest["score"] is not None and latest["score"] < 60:
            reasons.append(f"ציון נמוך ({latest['score']})")
        if crit:
            reasons.append(f"{len(crit)} בעיות חמורות פתוחות")
        if not latest and not running:
            reasons.append("עוד לא נבדק")
        prev = done[1] if len(done) > 1 else None
        out.append({**cl, "latest": latest, "running": bool(running), "running_status": running["status"] if running else None,
                    "audits_done": len(done), "open_issues": len(open_f), "serious_issues": len(crit),
                    "top_issues": [f["title"] for f in sorted(open_f, key=lambda f: f.get("priority") or 999)[:3]],
                    "pending_actions": len(pend), "report_ready": bool(latest),
                    "score_delta": (latest["score"] - prev["score"]) if latest and prev and latest["score"] is not None and prev["score"] is not None else None,
                    "needs_attention": bool(reasons), "reasons": reasons})
    out.sort(key=lambda x: (not x["needs_attention"], -(x["serious_issues"]), x["name"]))
    done_all = [a for a in audits if a["status"] == "done" and any((a["start_url"] or "").startswith(c["url"].rstrip("/")) for c in clients)]
    minutes = ceo.ASSUMED_MANUAL_MINUTES_PER_AUDIT
    machine = 0.0
    for a in done_all:
        s, f = ceo._parse(a.get("started_at")), ceo._parse(a.get("finished_at"))
        if s and f:
            machine += (f - s).total_seconds()
    return {"clients": out, "totals": {
        "clients": len(out), "demo_clients": sum(1 for c in out if c["is_demo"]),
        "need_attention": sum(1 for c in out if c["needs_attention"]),
        "reports_ready": sum(1 for c in out if c["report_ready"]), "pending_actions": sum(c["pending_actions"] for c in out),
        "running": sum(1 for c in out if c["running"]), "audits_done": len(done_all),
        "machine_minutes": round(machine / 60, 1),
        "manual_minutes_estimate": len(done_all) * minutes,
        "estimate_note": f"אומדן: {minutes} דקות עבודה ידנית לכל בדיקה. זמן המכונה נמדד בפועל."}}
