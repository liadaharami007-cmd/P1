"""P1 CEO — שיחת פתיחה מונחית ("מה תרצה להשיג היום?") → משימה (mission) עם תוכנית שבה כל צעד מסומן ביכולת אמיתית.

engine=rules: זיהוי כוונה לפי מילות מפתח, שאלות קבועות לכל מסלול, תוכנית שנבנית רק מיכולות שקיימות במערכת.
כשמנוע מודל פעיל — אפשר להוסיף שכבת שיחה חופשית (consult) מעל אותו מנגנון; בלי מנוע אומרים זאת במפורש.
"""
from __future__ import annotations

import json
import re
import uuid
from urllib.parse import urlparse

from ..db import Database
from . import actions, brain, ceo, store

INTENTS = {
    "start": "לפתוח עסק", "grow": "להגדיל את העסק", "website": "לבנות או לשפר אתר",
    "marketing": "שיווק, תוכן ופרסום", "manage": "לנהל את העסק עם P1", "consult": "להתייעץ עם P1",
    "agency": "סוכנות / משרד פרסום עם לקוחות", "today": "מה עושים היום",
}
KEYWORDS = [  # הסדר חשוב: ספציפי לפני כללי
    ("agency", r"משרד פרסום|סוכנות|לקוחות שלי|ללקוחות שלנו|agency|clients"),
    ("today", r"מה עושים היום|מה לעשות היום|מה הצעד הבא|מה עכשיו|today|next step"),
    ("start", r"לפתוח עסק|להקים עסק|רעיון|עסק חדש|start a business|new business|idea"),
    ("website", r"אתר|דף נחיתה|חנות אונליין|website|landing|site"),
    ("marketing", r"שיווק|פרסום|קמפיין|תוכן|סרטון|מודעה|לידים|marketing|ads|campaign|content|video"),
    ("grow", r"להגדיל|מכירות|להרוויח|רווח|לא מצליח|צמיחה|grow|sales|profit|revenue"),
    ("manage", r"לנהל|ניהול|אוטומצי|לחסוך זמן|manage|automat"),
]


def classify(text: str) -> dict:
    t = (text or "").strip().lower()
    for intent, pat in KEYWORDS:
        if re.search(pat, t, re.I):
            return {"intent": intent, "label": INTENTS[intent], "source": "rules", "matched": re.search(pat, t, re.I).group(0)}
    return {"intent": "consult", "label": INTENTS["consult"], "source": "rules", "matched": None}


# שאלות: id, שאלה, סוג (text/textarea/choice/multi/url/number/yesno), אפשרויות, שדה בפרופיל (או None), חובה
def _q(qid, q, kind, field=None, options=None, required=True, hint=None):
    return {"id": qid, "q": q, "kind": kind, "field": field, "options": options or [], "required": required, "hint": hint}


BT = [[k, v] for k, v in (("ecommerce", "חנות אונליין"), ("services", "נותן שירות"), ("local", "עסק מקומי"), ("leads", "עסק שמקבל פניות"), ("other", "אחר"))]
GOALS = [[k, v] for k, v in (("more_sales", "יותר מכירות"), ("more_leads", "יותר פניות"), ("fix_site", "אתר שעובד בלי תקלות"),
                             ("save_time", "לחסוך זמן"), ("reduce_ad_waste", "פחות בזבוז על פרסום"), ("better_reputation", "מוניטין וביקורות"))]
CH = [[k, v] for k, v in (("google_ads", "Google Ads"), ("meta_ads", "פייסבוק/אינסטגרם ממומן"), ("seo", "חיפוש בגוגל"), ("social_organic", "רשתות חברתיות"),
                          ("whatsapp", "וואטסאפ"), ("email", "דיוור"), ("referrals", "המלצות"), ("offline", "עסק פיזי"))]
SITE_Q = [_q("website", "מה כתובת האתר? (אם אין — השאירו ריק)", "url", "website", required=False),
          _q("permission", "האתר שלכם, או שיש לכם הרשאה לבדוק אותו?", "yesno", required=False,
             hint="P1 גולש באתר כמו לקוח ועוצר לפני תשלום. בלי אישור — לא בודקים.")]
QUESTIONS = {
    "start": [_q("offer", "מה הרעיון? מה תמכרו או איזה שירות תיתנו?", "textarea", "offer"),
              _q("audience", "מי הלקוח? תארו אדם אחד שהיה קונה", "textarea", "audience"),
              _q("price_range", "כמה זה יעלה ללקוח (בערך)?", "text", "price_range", required=False),
              _q("competitors", "מי עוד מוכר משהו דומה? (אם לא ידוע — כתבו 'לא יודע')", "textarea", "competitors", required=False),
              _q("channels", "איך הלקוחות הראשונים ישמעו עליכם?", "multi", "channels", CH, required=False),
              _q("budget", "כמה כסף אתם מוכנים להשקיע בהתחלה? (₪, לא חובה)", "number", None, required=False),
              _q("usps", "למה שיבחרו בכם ולא במתחרה?", "textarea", "usps", required=False)],
    "grow": [_q("business_name", "איך קוראים לעסק?", "text", "business_name"),
             _q("business_type", "איזה סוג עסק?", "choice", "business_type", BT),
             _q("offer", "מה אתם מוכרים, בקצרה?", "textarea", "offer"),
             _q("goals", "מה הכי חשוב עכשיו?", "multi", "goals", GOALS), *SITE_Q,
             _q("channels", "מאיפה מגיעים לקוחות היום?", "multi", "channels", CH, required=False)],
    "website": [_q("business_name", "איך קוראים לעסק?", "text", "business_name"),
                _q("business_type", "איזה סוג עסק?", "choice", "business_type", BT), *SITE_Q,
                _q("site_goal", "מה האתר צריך להשיג?", "choice", None, [["sales", "מכירות"], ["leads", "פניות/לידים"], ["info", "הצגת העסק"]])],
    "marketing": [_q("business_name", "איך קוראים לעסק?", "text", "business_name"),
                  _q("offer", "מה אתם מוכרים?", "textarea", "offer"), _q("audience", "למי?", "textarea", "audience"),
                  _q("channels", "באילו ערוצים אתם משווקים היום?", "multi", "channels", CH, required=False),
                  _q("monthly_ad_budget", "תקציב פרסום חודשי (₪, לא חובה)", "number", "monthly_ad_budget", required=False), *SITE_Q],
    "manage": [_q("business_name", "איך קוראים לעסק?", "text", "business_name"),
               _q("business_type", "איזה סוג עסק?", "choice", "business_type", BT),
               _q("goals", "מה הכי חשוב לכם?", "multi", "goals", GOALS), *SITE_Q,
               _q("hours_on_site_per_month", "כמה שעות בחודש אתם משקיעים היום בבדיקות/תחזוקה של האתר? (לא חובה)", "number", "hours_on_site_per_month", required=False)],
    "agency": [_q("business_name", "איך קוראים לסוכנות?", "text", "business_name"),
               _q("clients_count", "כמה לקוחות פעילים יש לכם?", "number", None),
               _q("pain", "מה הכי לוקח לכם זמן היום?", "multi", None, [["site_checks", "בדיקת אתרים ודפי נחיתה"], ["reports", "הכנת דוחות ללקוחות"],
                                                                        ["broken", "תקלות שמתגלות מאוחר"], ["leads", "מעקב אחרי לידים"], ["content", "תוכן וקריאייטיב"]], required=False)],
    "consult": [_q("question", "על מה תרצו להתייעץ?", "textarea", None)],
    "today": [],
}


def questions_for(intent: str, profile: dict) -> list[dict]:
    """רק מה שחסר: שאלה שהתשובה עליה כבר בפרופיל — מדלגים (אלא אם היא הרשאה לאתר)."""
    qs = QUESTIONS.get(intent, QUESTIONS["consult"])
    out = []
    for q in qs:
        if q["field"] and profile.get(q["field"]) not in (None, "", []) and q["id"] != "website":
            continue
        if q["id"] == "website" and profile.get("website"):
            q = {**q, "default": profile["website"]}
        out.append(q)
    return out


# ---------------------------------------------------------------- תוכנית
def _step(title, dept, status, why, *, action=None, link=None, minutes=None, approval=False, note=None):
    return {"title": title, "department": dept, "status": status, "why": why, "action": action, "link": link,
            "minutes": minutes, "needs_approval": approval, "note": note}


def readiness(answers: dict, profile: dict) -> dict:
    """בדיקת מוכנות לרעיון עסקי — כללים שקופים: מה כבר מוגדר ומה חסר לפני שמשקיעים כסף."""
    a = {**profile, **answers}
    checks = [
        ("offer", "מה מוכרים — מוגדר", bool(a.get("offer") and len(a["offer"]) >= 15)),
        ("audience", "לקוח יעד מוגדר", bool(a.get("audience") and len(a["audience"]) >= 10)),
        ("price", "מחיר משוער", bool(a.get("price_range"))),
        ("competitors", "מכירים את המתחרים", bool(a.get("competitors") and "לא יודע" not in a["competitors"])),
        ("channel", "יש דרך להגיע ללקוחות הראשונים", bool(a.get("channels"))),
        ("usp", "יש סיבה לבחור בכם", bool(a.get("usps"))),
        ("budget", "תקציב התחלתי מוגדר", a.get("budget") not in (None, "", 0, "0")),
    ]
    done = sum(1 for *_, ok in checks if ok)
    return {"score": round(100 * done / len(checks)), "checks": [{"id": i, "label": l, "ok": ok} for i, l, ok in checks],
            "engine": "rules", "note": "זו בדיקת שלמות של התוכנית לפי כללים — לא תחזית הצלחה. ניתוח שוק אמיתי דורש מנוע מודל ומחקר."}


def build_plan(db: Database, account: dict, user_id: str | None, intent: str, answers: dict) -> dict:
    prof = (store.get_profile(db, account["id"]) or {"data": {}})["data"]
    ai = ceo_engine_active()
    steps: list[dict] = []
    site = None
    url = (answers.get("website") or prof.get("website") or "").strip()
    if url and answers.get("permission") in (True, "yes", "כן", 1, "1"):
        site = _authorize_site(db, account, user_id, url)
    if intent == "start":
        r = readiness(answers, prof)
        steps.append(_step(f"בדיקת מוכנות לרעיון: {r['score']}%", "research", "works",
                           "מה כבר מוגדר בתוכנית ומה חסר לפני שמשקיעים כסף.", note=r["note"]))
        for c in r["checks"]:
            if not c["ok"]:
                steps.append(_step(f"להשלים: {c['label']}", "research", "works", "חסר בתוכנית — כדאי לסגור לפני השקעה.", link="#/business"))
        steps.append(_step("מחקר מתחרים ושוק", "research", "partial" if ai else "unavailable",
                           "השוואת מחירים והצעות של מתחרים.", note=None if ai else "דורש מנוע מודל + גישה לאינטרנט"))
        steps.append(_step("בניית דף נחיתה ראשון", "web", "unavailable", "כדי לבדוק ביקוש לפני השקעה גדולה.", note="Website Builder בתוכנית"))
        return {"intent": intent, "steps": steps, "readiness": r, "engine": "rules"}
    if intent == "agency":
        steps.append(_step("לפתוח את מסך הסוכנות: כל הלקוחות, מי דורש טיפול, דוחות מוכנים", "ops", "works",
                           "רואים במבט אחד את כל האתרים של הלקוחות.", link="#/agency"))
        steps.append(_step("להוסיף לקוחות עם אתר (באישור הלקוח) ולהריץ בדיקה לכל אחד", "web", "works",
                           "בדיקה בדפדפן אמיתי + טפסים/WhatsApp + PDF ללקוח.", link="#/agency", minutes=3))
        steps.append(_step("שמירה קבועה על כל אתר + התראה כשמשהו נשבר", "ops", "works", "תקלה מתגלה לפני שהלקוח מתקשר.", link="#/sites"))
        steps.append(_step("דוחות ללקוחות (PDF)", "ops", "works", "דוח מוכן להעברה לכל לקוח אחרי כל בדיקה.", link="#/agency"))
        steps.append(_step("מעקב לידים של הלקוחות", "sales", "unavailable", "", note="דורש חיבור CRM / WhatsApp Business"))
        steps.append(_step("ניתוח קמפיינים של הלקוחות", "marketing", "unavailable", "", note="דורש Google Ads / Meta Ads"))
        return {"intent": intent, "steps": steps, "engine": "rules", "suggest_demo": True}
    if intent == "consult":
        steps.append(_step("שיחה חופשית עם P1", "ops", "works" if ai else "unavailable", "תשובה מותאמת לעסק שלכם.",
                           link="#/assistant", note=None if ai else "דורש מנוע מודל (Claude או Ollama). בינתיים — בחרו מסלול מונחה."))
        return {"intent": intent, "steps": steps, "engine": "rules"}
    # grow / website / marketing / manage — מסלול שמבוסס על אתר
    if site:
        item = {"key": f"audit:{site['id']}", "kind": "run_audit", "title": "בדיקת האתר בדפדפן אמיתי (מחשב + iPhone)",
                "why": "5 לקוחות מדומים, טפסים ו-WhatsApp, סל וקופה — עם צילומי מסך.", "payload": {"site_id": site["id"], "url": url}}
        a = actions.propose(db, account, user_id, item)
        steps.append(_step(item["title"], "web", "works", item["why"], action={"id": a["id"], "status": a["status"]}, minutes=3, approval=True))
        steps.append(_step("Fix Studio: תיקון מוצע + לפני/אחרי לכל בעיה", "web", "works", "אחרי שהבדיקה מסתיימת.", link="#/fix"))
        steps.append(_step("שמירה קבועה + התראות", "ops", "works", "בדיקה חוזרת אוטומטית; מוצע במרכז הפיקוד אחרי הבדיקה.", link="#/"))
    elif url:
        steps.append(_step("בדיקת האתר", "web", "works", "צריך אישור שהאתר שלכם/שיש הרשאה — אפשר לאשר במסך 'אתרים'.", link="#/sites"))
    else:
        steps.append(_step("בניית אתר / דף נחיתה", "web", "unavailable", "אין עדיין אתר לבדוק.", note="Website Builder בתוכנית"))
    if intent in ("grow", "marketing"):
        steps.append(_step("ניתוח משפך המכירה על נתוני תנועה", "web", "unavailable", "", note="דורש חיבור Google Analytics"))
        steps.append(_step("אסטרטגיית שיווק, קופי ותסריטים", "marketing", "works" if ai else "unavailable", "", note=None if ai else "דורש מנוע מודל"))
        steps.append(_step("ניתוח קמפיינים ובזבוז תקציב", "marketing", "unavailable", "", note="דורש Google Ads / Meta Ads"))
    if intent in ("grow", "manage"):
        steps.append(_step("ניתוח רווחיות", "finance", "unavailable", "", note="דורש נתוני מכירות / הנהלת חשבונות"))
        steps.append(_step("דוח שבועי + ציר צמיחה", "ops", "works", "מה בוצע, מה נמדד ומה הלאה.", link="#/timeline"))
    return {"intent": intent, "steps": steps, "engine": "rules", "site_id": site["id"] if site else None}


def ceo_engine_active() -> bool:
    from ..intelligence import engines
    return engines.status()["active"] != "rules"


def _authorize_site(db: Database, account: dict, user_id: str | None, raw: str) -> dict:
    from .. import config
    from ..research.analyzer import assert_public_host, normalize_url
    from ..saas import plans
    url = normalize_url(raw)
    if not config.DEV_ALLOW_PRIVATE_TARGETS and not url.startswith(config.PUBLIC_URL):
        assert_public_host(url)
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}".lower()
    if not db.find_site(account["id"], origin) and db.usage(account["id"])["sites"] >= plans.plan_of(account)["sites"]:
        raise ValueError(f"המסלול {plans.plan_of(account)['name']} מאפשר עד {plans.plan_of(account)['sites']} אתרים")
    site = db.get_or_create_site(origin, account["id"])
    db.authorize_site(site["id"], user_id)
    if url.startswith(config.PUBLIC_URL + "/demo-"):
        db.mark_demo_site(site["id"])
    return site


# ---------------------------------------------------------------- שמירה
def create_mission(db: Database, account: dict, user_id: str | None, intent: str, answers: dict) -> dict:
    if intent not in INTENTS:
        raise ValueError("מסלול לא מוכר")
    prof_row = store.get_profile(db, account["id"])
    prof = prof_row["data"] if prof_row else {}
    fields = {q["field"]: answers[q["id"]] for q in QUESTIONS.get(intent, []) if q["field"] and answers.get(q["id"]) not in (None, "", [])}
    if fields:
        merged = brain.clean({**prof, **fields})
        store.save_profile(db, account["id"], merged, user_id)
    missing = [q["q"] for q in questions_for(intent, prof) if q["required"] and answers.get(q["id"]) in (None, "", [])]
    if missing:
        raise ValueError("חסרה תשובה: " + missing[0])
    plan = build_plan(db, account, user_id, intent, answers)
    mid = uuid.uuid4().hex
    now = store.now()
    with db._conn() as c:
        c.execute("INSERT INTO missions (id, account_id, intent, title, status, answers_json, plan_json, created_by, created_at, updated_at) "
                  "VALUES (?,?,?,?, 'active', ?,?,?,?,?)", (mid, account["id"], intent, INTENTS[intent],
                                                          json.dumps(answers, ensure_ascii=False), json.dumps(plan, ensure_ascii=False), user_id, now, now))
    store.log(db, account["id"], "mission_created", f"משימה חדשה: {INTENTS[intent]}", ref_type="mission", ref_id=mid, user_id=user_id)
    return get_mission(db, mid, account["id"])  # type: ignore[return-value]


def _row(r) -> dict:
    d = dict(r)
    d["answers"] = json.loads(d.pop("answers_json"))
    d["plan"] = json.loads(d.pop("plan_json"))
    return d


def get_mission(db: Database, mid: str, account_id: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT * FROM missions WHERE id=? AND account_id=?", (mid, account_id)).fetchone()
    if not r:
        return None
    m = _row(r)
    for s in m["plan"]["steps"]:  # מצב עדכני של פעולות שנוצרו מהמשימה
        if s.get("action"):
            a = store.get_action(db, s["action"]["id"], account_id)
            if a:
                a = actions.refresh(db, a)
                s["action"] = {"id": a["id"], "status": a["status"], "audit_id": (a.get("result") or {}).get("audit_id")}
    return m


def list_missions(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM missions WHERE account_id=? ORDER BY created_at DESC LIMIT 20", (account_id,))]


def today(db: Database, account: dict) -> dict:
    """'מה עושים היום?' — 3 המלצות מתועדפות עם הסבר מלא."""
    p = ceo.plan(ceo.snapshot(db, account))
    meta = {"run_audit": ("בדיקה אחת מהמכסה החודשית", ["סוכני הלקוח (5)", "בודק טפסים/WhatsApp"], "תמונה עדכנית של מה מפריע ללקוחות"),
            "verify_fix": ("בדיקה אחת מהמכסה", ["סוכני הלקוח", "השוואת בדיקות"], "הוכחה במדידה שהתיקון עבד"),
            "enable_monitor": ("בדיקות חוזרות נספרות במכסה", ["Smart Monitor"], "תקלה חדשה מתגלה לפני הלקוחות"),
            "fix_package": ("ללא עלות", ["Fix Studio"], "חבילת תיקון מוכנה למי שמתחזק את האתר"),
            "link": ("ללא עלות", ["P1 CEO"], "")}
    items = []
    for it in p["top3"]:
        cost, agents, outcome = meta.get(it["kind"], meta["link"])
        items.append({**it, "cost_note": cost, "agents": agents, "outcome": outcome or it["why"],
                      "needs_approval": it["kind"] != "link"})
    return {"items": items, "method": p["method"], "engine": "rules"}
