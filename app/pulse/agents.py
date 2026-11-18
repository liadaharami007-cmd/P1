"""צוות הסוכנים של ClientPulse — שישה תפקידים מתואמים מעל היכולות הקיימות (בלי כפילויות).

כל תפקיד ממופה לקוד שכבר קיים ועובד:
  monitor    בקרת לקוחות ורמזור   → engine.analyze_client + service.ops_overlay + service.alert_card
  campaigns  ניתוח קמפיינים        → adlab.analyze (מודעות) + קצב ניצול תקציב מול התקציב החודשי
  leads      ניתוח לידים           → leads_insight (כאן) — מצב · בעיה/הזדמנות · סיבה · נתונים · שיפור · איך · מדד הצלחה
  strategy   אסטרטגיה עסקית        → engine.opportunities + engine.recovery + service.suggestion + זיכרון הלקוח
  execution  ביצוע ומעקב           → משימות, אישורים (requires_approval), בדיקה חוזרת (service.verify_tasks)
  chief      מנהל ראשי             → מתעדף ומסכם לתמונה אחת: שלושת הדברים החשובים היום

המנוע היום מבוסס כללים וסטטיסטיקה (engine: rules). אין כאן מודל שפה; אם יחובר — Ask/Ads משתמשים בו לניסוח בלבד.
"""
from __future__ import annotations

from typing import Any

from ..db import Database
from . import adlab, engine
from . import service as S
from .engine import fmt_day, money
from .store import one, rows

ROLES = [
    {"id": "monitor", "name": "בקרת לקוחות ורמזור", "does": "בודק כל לקוח מול ההיסטוריה שלו וקובע אדום / צהוב / ירוק — רק עם סיבה ונתון.",
     "uses": "נתוני ביצועים יומיים, התחייבויות, קשר ושביעות רצון"},
    {"id": "campaigns", "name": "ניתוח קמפיינים", "does": "מזהה מודעות מנצחות ומודעות שצריך לשפר, וקצב ניצול תקציב.",
     "uses": "ביצועי מודעות 7 ימים, תקציב חודשי"},
    {"id": "leads", "name": "ניתוח לידים", "does": "מסביר מה קורה בלידים, למה, מה לשפר ואיך נמדוד הצלחה.",
     "uses": "לידים, הקלקות, המרה, מכירות"},
    {"id": "strategy", "name": "אסטרטגיה עסקית ושיווקית", "does": "הופך ממצא להמלצה — ובודק מה כבר נוסה אצל הלקוח בעבר.",
     "uses": "הזדמנויות, פוטנציאל, זיכרון הלקוח"},
    {"id": "execution", "name": "ביצוע ומעקב", "does": "פותח משימה, מגדיר אחראי ומועד, מבקש אישור לפעולה רגישה ובודק תוצאה.",
     "uses": "משימות, אישורים, בדיקה חוזרת"},
    {"id": "chief", "name": "מנהל ראשי", "does": "מרכז את כל הממצאים, מתעדף ומציג תמונה אחת ושלושה דברים להיום.",
     "uses": "הממצאים של כל הסוכנים"},
]
ENGINE = "rules"


def _wk(v: float | None) -> int:
    return round((v or 0) * 7)


# ------------------------------------------------------------------ סוכן לידים
def leads_insight(r: dict, client: dict) -> dict:
    """ניתוח לידים מלא ללקוח אחד. כל מספר מגיע מהנתונים; הסיבה היא השערה מסומנת ככזו."""
    rec, base = r["rec"], r["base"]
    ind = client.get("industry") or "העסק"
    now_w, norm_w = rec["leads"], _wk(base["dailyLeads"])
    types = {a["type"] for a in r["alerts"]}
    tgt = (r.get("goals") or {}).get("targetCpl")
    chg = (now_w / norm_w - 1) if norm_w else None
    state = (f"השבוע {now_w} לידים, לעומת כ-{norm_w} בשבוע רגיל" + (f" ({'+' if chg > 0 else ''}{round(chg * 100)}%)." if chg is not None else ".")
             if norm_w else f"השבוע {now_w} לידים. אין עדיין מספיק היסטוריה להשוואה.")
    data: list[str] = []

    def d(label: str, a: Any, b: Any) -> None:
        if a is not None and b is not None:
            data.append(f"{label}: {a} ← {b}")

    d("לידים בשבוע", norm_w, now_w)
    d("עלות לליד", money(base["cpl"]) if base["cpl"] else None, money(rec["cpl"]) if rec["cpl"] else None)
    d("המרה מקליק לליד", f"{base['cvr'] * 100:.1f}%" if base["cvr"] else None, f"{rec['cvr'] * 100:.1f}%" if rec["cvr"] is not None else None)
    d("שיעור הקלקה", f"{base['ctr'] * 100:.2f}%" if base["ctr"] else None, f"{rec['ctr'] * 100:.2f}%" if rec["ctr"] is not None else None)
    s28 = r.get("sales28")
    order = ["data", "no_leads", "cvr", "ctr", "spend_up", "cpl", "goal", "trend", "no_sales"]
    first = r["alerts"][0]["type"] if r["alerts"] else None
    pk = first if first in order else next((t for t in order if t in types), None)

    if r["status"] == "nodata" or pk == "data":
        return {"kind": "problem", "state": "הנתונים לא מתעדכנים, ולכן אי אפשר לנתח את הלידים כרגע.", "headline": "לחבר מחדש את מקור הנתונים",
                "cause": "החיבור למערכת הפרסום נקטע או שהייבוא לא רץ.", "data": data, "improve": "להחזיר נתונים יומיים כדי שהבקרה תעבוד.",
                "how": ["לבדוק את החיבור / הייבוא", "לוודא שהיום האחרון מופיע בנתונים"], "measure": "נתונים של אתמול מופיעים מחר בבוקר."}
    if pk == "no_leads":
        return {"kind": "problem", "state": state, "headline": "להחזיר את זרימת הלידים",
                "cause": f"יש הקלקות ({rec['clicks']} השבוע) אבל אין לידים — כנראה טופס / דף נחיתה / מעקב המרות לא עובדים, לא הקמפיין עצמו.",
                "data": data, "improve": f"תיקון הקליטה מחזיר את הלידים מהתנועה שכבר משולמת — כ-{norm_w} לידים בשבוע אצל {client['name']}.",
                "how": ["לשלוח ליד בדיקה מהטופס ולוודא שהוא מגיע", "לפתוח את דף הנחיתה בנייד ובמחשב", "לבדוק שאירוע ההמרה (פיקסל) עדיין נשלח"],
                "measure": "ליד ראשון תוך 24 שעות מהתיקון, וחזרה לכ-" + str(norm_w) + " לידים בשבוע תוך שבוע."}
    if pk == "cvr":
        return {"kind": "problem", "state": state, "headline": "לשפר את ההמרה בדף",
                "cause": "אנשים ממשיכים להקליק, אבל פחות מהם משאירים פרטים — ההצעה או הדף כנראה פחות משכנעים מבעבר.",
                "data": data, "improve": f"להתאים את ההצעה בדף להבטחה שבמודעה, בשפה של {ind}.",
                "how": ["להשוות את ההצעה במודעה למה שכתוב בדף", "לקצר את הטופס לשם + טלפון", "להוסיף הוכחה חברתית (המלצות) מעל הטופס"],
                "measure": f"המרה מקליק לליד חוזרת ל-{base['cvr'] * 100:.1f}% תוך 7 ימים." if base["cvr"] else "המרה עולה תוך 7 ימים."}
    if pk == "ctr":
        return {"kind": "problem", "state": state, "headline": "לרענן את המודעות",
                "cause": "פחות אנשים מקליקים על המודעות — סימן לשחיקה (אותו קהל רואה את אותה מודעה שוב ושוב).",
                "data": data, "improve": "קריאייטיב חדש מחזיר את תשומת הלב ומוריד את העלות לליד.",
                "how": ["להעלות 2–3 קריאייטיבים חדשים", "לבחון כותרת עם תועלת או מספר", "לעצור את המודעה עם התדירות הגבוהה ביותר"],
                "measure": f"שיעור הקלקה חוזר ל-{base['ctr'] * 100:.2f}% והעלות לליד יורדת." if base["ctr"] else "שיעור הקלקה עולה."}
    if pk == "spend_up":
        a0 = next(a for a in r["alerts"] if a["type"] == "spend_up")
        return {"kind": "problem", "state": state, "headline": "לכוון את התקציב ללידים",
                "cause": a0["what"] + " התקציב הנוסף הולך לקהל או למודעות שלא ממירים.",
                "data": data, "improve": "להחזיר את התקציב לרמה הקודמת או להעביר את התוספת רק למודעה המנצחת.",
                "how": ["לבדוק מתי ואיפה הוגדל התקציב", "להעביר את התוספת למודעה עם העלות לליד הנמוכה ביותר", "לבדוק שוב אחרי 3 ימים"],
                "measure": f"עלות לליד חוזרת לכ-{money(base['cpl'])} בלי לאבד לידים." if base["cpl"] else "עלות לליד יורדת."}
    if pk in ("cpl", "goal"):
        return {"kind": "problem", "state": state, "headline": "להוריד את העלות לליד",
                "cause": "כל ליד עולה יותר מבעבר — תחרות על הקהל, קהל רחב מדי או תקציב שהוגדל מהר מדי.",
                "data": data, "improve": "להעביר תקציב למודעות ולקהלים שמביאים ליד בזול, ולצמצם את היקרים.",
                "how": ["לזהות את המודעה / הקהל עם העלות הגבוהה ביותר", "להעביר 20% מהתקציב למודעה המנצחת", "לבדוק שינויי תקציב אחרונים"],
                "measure": (f"עלות לליד חוזרת לכ-{money(base['cpl'])}" + (f" (יעד {money(tgt)})" if tgt else "") + " תוך 7 ימים.") if base["cpl"] else "עלות לליד יורדת."}
    if pk == "trend":
        return {"kind": "problem", "state": state, "headline": "לעצור את הירידה ההדרגתית",
                "cause": "אין שבר חד — הביצועים נשחקים לאט כבר כמה שבועות. בדרך כלל קריאייטיב ישן או קהל שמוצה.",
                "data": data, "improve": "רענון קטן עכשיו זול יותר מטיפול בבעיה גדולה בעוד חודש.",
                "how": ["לבדוק מתי הוחלף הקריאייטיב לאחרונה", "להרחיב קהל או להוסיף קהל דומה", "להשוות שבוע מול שבוע אחרי השינוי"],
                "measure": "המגמה נעצרת: שבוע הבא לא חלש מהשבוע."}
    if pk == "no_sales" or (s28 and s28["leads"] >= 20 and (s28.get("closeRate") or 0) < 0.03):
        return {"kind": "problem", "state": state, "headline": "להפוך לידים למכירות",
                "cause": "הלידים מגיעים, אבל לא נסגרים — איכות הלידים או מהירות הטיפול בהם אצל הלקוח.",
                "data": data + ([f"מכירות ב-28 ימים: {s28['sales']} מתוך {s28['leads']} לידים"] if s28 else []),
                "improve": "מענה תוך 5 דקות לליד מכפיל את הסיכוי לסגירה; כדאי לבדוק עם הלקוח מי מטפל בלידים.",
                "how": ["לשאול את הלקוח מי מטפל בלידים ותוך כמה זמן", "להציע מענה אוטומטי ב-WhatsApp", "לסנן לידים לא רלוונטיים בטופס (שאלה אחת)"],
                "measure": "שיעור סגירה חוזר לרמה הקודמת תוך שבועיים."}
    ops = engine.opportunities(r, client)
    if r.get("improved") or ops:
        o = ops[0] if ops else None
        return {"kind": "opportunity", "state": state, "headline": "הזדמנות לגדול" if (r.get("improved") or (o and o["kind"] in ("scale", "budget_headroom"))) else o["title"],
                "cause": r["improved"]["what"] if r.get("improved") else o["evidence"], "data": data,
                "improve": o["action"] if o else "להגדיל תקציב בהדרגה כל עוד העלות לליד יציבה.",
                "how": ["להגדיל תקציב ב-10–20% בקמפיין הטוב ביותר", "לבדוק את העלות לליד אחרי 4 ימים", "להמשיך רק אם העלות נשארת ביעד"],
                "measure": (o or {}).get("potential") or "יותר לידים באותה עלות לליד."}
    return {"kind": "stable", "state": state, "headline": "יציב", "cause": "אין שינוי מובהק מול הרמה הרגילה של הלקוח.", "data": data,
            "improve": "לשמור על הקיים ולבדוק פעם בשבוע.", "how": [], "measure": "הרמה נשמרת."}


# ------------------------------------------------------------------ סוכן קמפיינים
def campaigns_insight(r: dict, client: dict) -> dict:
    g = r.get("goals") or {}
    bud = g.get("monthlyBudget")
    pace = r["rec"]["dailySpend"] * 30.4
    budget = {"monthly": bud, "pace": round(pace), "use": round(pace / bud * 100) if bud else None}
    if not client.get("is_demo"):
        return {"connected": False, "missing": "חיבור Meta Ads / Google Ads ברמת מודעה (קיים רק סיכום יומי)", "budget": budget}
    a = adlab.analyze(adlab.demo_ads(client, r), client.get("industry"))
    ads = a["ads"]
    good = [x for x in ads if x["tone"] == "green"]
    fix = [x for x in ads if x["recs"]]
    top = next((x for x in ads if x["recs"]), None)
    return {"connected": True, "demo": True, "budget": budget, "count": len(ads), "good": len(good), "fix": len(fix),
            "best": a["summary"]["winner"], "headline": a["summary"]["headline"], "cpl": a["summary"]["avg"]["cpl"],
            "top_fix": {"id": top["id"], "name": top["name"], "issue": top["recs"][0]["issue"], "why": top["recs"][0]["why"], "do": top["recs"][0]["do"],
                        "headline": top["headline"], "text": top["text"], "frequency": top["frequency"], "cpl": top["cpl"],
                        "alt_creative": next((x["do"] for x in top["recs"] if x["area"] == "קריאייטיב"), "להעלות גרסה עם תמונה של תוצאה / לפני-אחרי"),
                        "alt_audience": ("להרחיב קהל או קהל דומה (Lookalike) ללקוחות קיימים — התדירות גבוהה" if top["frequency"] >= 3
                                         else "לבחון קהל דומה (Lookalike) ללידים שנסגרו")} if top else None}


# ------------------------------------------------------------------ זיכרון עסקי
def memory(db: Database, acc: str, cid: str, run: dict) -> dict:
    """מה כבר קרה אצל הלקוח: בעיות קודמות, מה נעשה, מה עבד. משמש את סוכן האסטרטגיה כדי לא להתחיל מאפס."""
    past = rows(db, "SELECT key, type, title, status, first_day, cleared_day FROM pulse_alerts WHERE account_id=? AND client_id=? ORDER BY first_day DESC LIMIT 20",
                (acc, cid))
    tasks = S.all_tasks(db, acc, cid)
    done = [t for t in tasks if t.get("verification")]
    open_c = rows(db, "SELECT text, due_day FROM pulse_commitments WHERE account_id=? AND client_id=? AND status='open' ORDER BY due_day LIMIT 5", (acc, cid))
    items = []
    for t in done[:4]:
        v = t["verification"]
        items.append({"day": fmt_day(v["day"]), "text": t["title"].split(" · ")[0], "result": "עבד — אומת בנתונים" if v["ok"] else "לא הספיק — הבעיה חזרה / נשארה",
                      "ok": bool(v["ok"]), "type": (t.get("alert_key") or ":").split(":")[1], "step": (t.get("plan") or [{}])[0].get("text")})
    recurring: dict[str, int] = {}
    for p in past:
        if p["status"] in ("cleared", "resolved"):
            recurring[p["type"]] = recurring.get(p["type"], 0) + 1
    return {"history": items, "recurring": recurring, "commitments": [{"text": c["text"], "due": fmt_day(c["due_day"])} for c in open_c],
            "past_count": sum(1 for p in past if p["status"] in ("cleared", "resolved"))}


def _adapt(mem: dict, kind: str | None) -> str | None:
    if not kind:
        return None
    prev = next((h for h in mem["history"] if h["type"] == kind), None)
    n = mem["recurring"].get(kind, 0)
    if prev and prev["ok"]:
        return f"זה קרה כבר ב-{prev['day']} ונפתר אחרי: {prev['step'] or prev['text']}. כדאי להתחיל מאותו צעד."
    if prev:
        return f"בפעם הקודמת ({prev['day']}) הפעולה \"{prev['step'] or prev['text']}\" לא הספיקה — הפעם כדאי לנסות את הצעד הבא בתוכנית."
    if n >= 2:
        return f"הבעיה הזו חזרה {n} פעמים — כדאי לטפל בשורש, לא רק בתסמין."
    return None


# ------------------------------------------------------------------ תיק תובנות ללקוח (כל הסוכנים יחד)
def client_insight(db: Database, acc: str, cid: str) -> dict | None:
    run = S.analysis(db, acc)
    r = run["byId"].get(cid)
    if not r:
        return None
    c = run["clients"][cid]
    tm = S.team_map(db, acc)
    states = S.alert_rows(db, acc, cid)
    a = r["alerts"][0] if r["alerts"] else None
    card = S.alert_card(db, acc, run, r, a, states.get(a["key"]), S.open_task_for(db, acc, a["key"]), tm) if a else None
    t = one(db, "SELECT recheck_day, requires_approval, status FROM pulse_tasks WHERE id=?", (card["task_id"],)) if card and card.get("task_id") else None
    leads = leads_insight(r, c)
    camp = campaigns_insight(r, c)
    mem = memory(db, acc, cid, run)
    kind = a["type"] if a else None
    sug = S.suggestion(r, c)
    rec_text = (leads["improve"] if leads["kind"] != "stable" else card["next"] if card
                else (sug or {}).get("action") or (sug or {}).get("text"))
    adapt = _adapt(mem, kind)
    owner = (card or {}).get("owner") or r["owner"]
    sensitive = bool(t and t["requires_approval"])
    monitor = {"status": r["status"], "title": a["title"] if a else ("שיפור מובהק" if r.get("improved") else "תקין"),
               "what": a["what"] if a else (r["improved"]["what"] if r.get("improved") else "אין חריגה מול הרמה הרגילה של הלקוח."),
               "when": card["started_label"] if card else None, "days_open": card["days_open"] if card else None,
               "cause": (card["explanations"][0] if card and card["explanations"] else leads["cause"]),
               "evidence": card["evidence"][:3] if card else leads["data"][:3],
               "owner": tm.get(owner, {}).get("name", "לא שויך"),
               "recheck": fmt_day(t["recheck_day"]) if t and t["recheck_day"] else (fmt_day(run["ref"] + (1 if r["status"] == "red" else 3)) if a else None),
               "handled": card["handled"] if card else None, "improved": card["improved"] if card else None,
               "todo": leads["how"] if leads["kind"] != "stable" else ([card["next"], *card["check"]][:3] if card else [])}
    execution = {"task_id": (card or {}).get("task_id"), "task_status": (card or {}).get("task_status"), "owner": monitor["owner"],
                 "needs_approval": sensitive, "key": a["key"] if a else None}
    chief = " ".join(x for x in [
        f"{monitor['title']}.",
        leads["cause"] if leads["kind"] != "stable" else "",
        f"מומלץ: {rec_text.rstrip('.')}." if rec_text else "",
        adapt or "",
        (f"אחראי: {monitor['owner']}" + (f", בדיקה חוזרת ב-{monitor['recheck']}." if monitor["recheck"] else ".")) if a else "",
    ] if x)
    return {"client": {"id": c["id"], "name": c["name"], "industry": c.get("industry"), "is_demo": bool(c.get("is_demo")), "owner": r["owner"]},
            "engine": ENGINE, "monitor": monitor, "leads": leads, "campaigns": camp,
            "strategy": {"recommendation": rec_text, "adapt": adapt, "potential": (r.get("recovery") or {}).get("text"),
                         "potential_leads": (r.get("recovery") or {}).get("leads_week"), "opportunities": engine.opportunities(r, c)[:2]},
            "execution": execution, "memory": mem, "chief": chief}


# ------------------------------------------------------------------ תדריך המנהל הראשי
def team_brief(db: Database, acc: str) -> dict:
    run = S.analysis(db, acc)
    ref = run["ref"]
    res = list(run["byId"].values())
    tm = S.team_map(db, acc)
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in ("red", "yellow", "green", "nodata")}
    states = S.alert_rows(db, acc)
    # מנהל ראשי: שתי בעיות עם ההשפעה הגדולה ביותר + ההזדמנות הגדולה ביותר
    probs = sorted([r for r in res if r["alerts"]], key=lambda r: -(r["alerts"][0]["priority"] + ((r.get("recovery") or {}).get("leads_week") or 0)))
    top: list[dict] = []
    for r in probs:
        if len(top) == 2:
            break
        a = r["alerts"][0]
        t = S.open_task_for(db, acc, a["key"])
        if t and t["status"] not in ("new",):
            continue  # כבר בטיפול — לא "דבר חשוב להיום"
        card = S.alert_card(db, acc, run, r, a, states.get(a["key"]), t, tm)
        li = leads_insight(r, run["clients"][r["id"]])
        if any(x["headline"] == li["headline"] for x in top):
            continue  # מגוון: לא אותה בעיה פעמיים בשלושת הדברים של היום
        top.append({"kind": "problem", "client_id": r["id"], "client": r["name"], "severity": a["severity"], "key": a["key"],
                    "headline": li["headline"], "why": card["what"], "data": card["changed"][:2],
                    "action": li["how"][0] if li["how"] else card["next"], "gain": card["potential"], "gain_leads": card["potential_leads"],
                    "owner": card["owner_name"], "task_id": card["task_id"], "task_status": card["task_status"],
                    "chain": ["בקרה", "לידים", "אסטרטגיה", "ביצוע"]})
    opp_best = None
    for r in res:
        if r["status"] != "green":
            continue
        for o in engine.opportunities(r, run["clients"][r["id"]]):
            score = 2 if o["kind"] in ("scale", "budget_headroom") else 1
            if not opp_best or score > opp_best[0]:
                opp_best = (score, r, o)
    if opp_best:
        _, r, o = opp_best
        top.append({"kind": "opportunity", "client_id": r["id"], "client": r["name"], "severity": "green", "key": None,
                    "headline": o["title"], "why": o["evidence"], "data": [], "action": o["action"], "gain": o.get("potential"), "gain_leads": None,
                    "owner": tm.get(r["owner"], {}).get("name", "לא שויך"), "task_id": None, "task_status": None,
                    "chain": ["קמפיינים", "אסטרטגיה", "ביצוע"]})
    # קמפיינים בעייתיים (רק לקוחות עם נתוני מודעות)
    camp_issues = 0
    for r in res:
        if r["status"] in ("red", "yellow") and run["clients"][r["id"]].get("is_demo"):
            ci = campaigns_insight(r, run["clients"][r["id"]])
            camp_issues += 1 if ci.get("fix") else 0
    opps = sum(len(engine.opportunities(r, run["clients"][r["id"]])) for r in res)
    week = ref - 7
    detected = one(db, "SELECT COUNT(*) n FROM pulse_alerts WHERE account_id=? AND first_day>?", (acc, week))["n"]
    handled = one(db, "SELECT COUNT(*) n FROM pulse_tasks WHERE account_id=? AND done_day IS NOT NULL AND done_day>?", (acc, week))["n"]
    verified = one(db, "SELECT COUNT(*) n FROM pulse_verifications WHERE account_id=? AND ok=1 AND day>?", (acc, week))["n"]
    closed = one(db, "SELECT COUNT(*) n FROM pulse_tasks WHERE account_id=? AND status='closed' AND closed_day>?", (acc, week))["n"]
    w = S.ws(db, acc)
    per = w["settings"]["assumptions"]["minPerClient"]
    line = (f"{cnt['red']} לקוחות דורשים התערבות, {cnt['yellow']} במעקב, {cnt['green']} תקינים." if res else "אין עדיין לקוחות.")
    findings = {"monitor": cnt["red"] + cnt["yellow"], "campaigns": camp_issues, "leads": sum(1 for r in res if r["alerts"]),
                "strategy": opps, "execution": len(S.open_tasks(db, acc)), "chief": len(top)}
    return {"ref": ref, "ref_label": fmt_day(ref), "engine": ENGINE, "counts": cnt, "clients": len(res), "line": line, "top": top,
            "value": {"detected": detected, "handled": handled, "verified": verified, "closed": closed, "opportunities": opps,
                      "scan_ms": round(run.get("ms") or 0, 1), "manual_min": per * len(res), "per_client": per},
            "agents": [{**x, "findings": findings[x["id"]]} for x in ROLES]}


def act(db: Database, acc: str, client_id: str, key: str | None, title: str | None, by_name: str, can_approve: bool) -> dict:
    """סוכן הביצוע: הופך המלצה למשימה עם אחראי, מועד ובדיקה חוזרת. פעולה רגישה (תקציב / עצירת קמפיין / הודעה ללקוח) — ממתינה לאישור מנהל."""
    run = S.analysis(db, acc)
    if key:
        t = S.create_task(db, acc, run, key, by="user", by_name=by_name)
        msg = "נפתחה משימה" + (" — פעולה רגישה, תחכה לאישור מנהל לפני ביצוע" if t.get("requires_approval") else "")
    else:
        if client_id not in run["byId"] or not title:
            raise KeyError("לקוח לא נמצא")
        t = S.create_manual_task(db, acc, client_id, title, None, 7, by_name, source="opportunity")
        msg = "נפתחה משימת הזדמנות"
    S.bump(db, acc)
    return {"ok": True, "msg": f"{msg} · אחראי: {S.team_map(db, acc).get(t.get('assignee'), {}).get('name', 'לא שויך')}", "task": t}


# ------------------------------------------------------------------ לוח העבודה (Monday): קבוצה לכל קמפיינר
DEF_CHECK, DEF_CONTACT = 3, 14
STATUS_TXT = {"red": "לטיפול", "yellow": "לבדיקה", "green": "תקין", "nodata": "חסרים נתונים"}


def _last(db: Database, acc: str, sql_type: str, refs: tuple[str, ...]) -> dict[str, dict]:
    q = ",".join("?" * len(refs))
    out = {}
    for r in rows(db, f"SELECT client_id, MAX(day) d, COUNT(*) n FROM pulse_events WHERE account_id=? AND type=? AND ref IN ({q}) GROUP BY client_id",
                  (acc, sql_type, *refs)):
        out[r["client_id"]] = {"day": r["d"], "n": r["n"]}
    return out


def board(db: Database, acc: str) -> dict:
    """הלוח הראשי: מי צריך תשומת לב היום, וקבוצה לכל קמפיינר עם שורה ללקוח. כל עמודה מחושבת מנתונים אמיתיים במערכת."""
    run = S.analysis(db, acc)
    ref = run["ref"]
    tm = S.team_map(db, acc)
    checks = _last(db, acc, "check", ("campaign",))
    contacts = _last(db, acc, "note", ("call", "meeting"))
    tasks = S.open_tasks(db, acc)
    tby: dict[str, list] = {}
    for t in tasks:
        tby.setdefault(t["client_id"], []).append(t)
    states = S.alert_rows(db, acc)
    out_rows = []
    for r in run["byId"].values():
        c = run["clients"][r["id"]]
        a = r["alerts"][0] if r["alerts"] else None
        li = leads_insight(r, c)
        ce = c.get("check_every_days") or DEF_CHECK
        ke = c.get("contact_every_days") or DEF_CONTACT
        ck, ct = checks.get(r["id"]), contacts.get(r["id"])
        ck_ago = ref - ck["day"] if ck else None
        ct_ago = ref - ct["day"] if ct else None
        st_ = states.get(a["key"], {}) if a else {}
        ot = tby.get(r["id"], [])
        rec = li["how"][0] if li["kind"] == "problem" and li["how"] else li["improve"] if li["kind"] == "opportunity" else (
            "לחדש קשר עם הלקוח" if (ct_ago is None or ct_ago > ke) else "לשמור על הקיים")
        out_rows.append({
            "id": r["id"], "name": r["name"], "owner": r["owner"], "is_demo": r["is_demo"], "status": r["status"],
            "why": a["title"] if a else ("שיפור מובהק" if r.get("improved") else "אין חריגה מול הרמה הרגילה" if r["status"] == "green" else "חסרים נתונים"),
            "since": fmt_day(st_["first_day"]) if st_.get("first_day") is not None else None,
            "headline": li["headline"], "rec": rec, "priority": r["priority"],
            "leads": r["rec"]["leads"], "leads_norm": _wk(r["base"]["dailyLeads"]) if not r["lowData"] else None,
            "cpl": r["rec"]["cpl"], "cpl_norm": r["base"]["cpl"], "spend": round(r["rec"]["spend"]),
            "check": {"ago": ck_ago, "every": ce, "late": ck_ago is None or ck_ago > ce, "n": ck["n"] if ck else 0},
            "contact": {"ago": ct_ago, "every": ke, "late": ct_ago is None or ct_ago > ke},
            "tasks": len(ot), "tasks_late": sum(1 for t in ot if t.get("due_day") is not None and t["due_day"] < ref and t["status"] in ("new", "in_progress")),
            "approval": sum(1 for t in ot if t["status"] == "awaiting_approval"),
            "alert_key": a["key"] if a else None, "task_id": ot[0]["id"] if ot else None, "task_status": ot[0]["status"] if ot else None,
        })
    rank = {"red": 0, "yellow": 1, "nodata": 2, "green": 3}
    out_rows.sort(key=lambda x: (rank[x["status"]], -x["priority"]))
    groups = []
    for mid, m in tm.items():
        mine = [x for x in out_rows if x["owner"] == mid]
        if not mine:
            continue
        groups.append({"id": mid, "name": m["name"], "clients": len(mine),
                       "counts": {k: sum(1 for x in mine if x["status"] == k) for k in ("red", "yellow", "green", "nodata")},
                       "late_checks": sum(1 for x in mine if x["check"]["late"]), "late_contact": sum(1 for x in mine if x["contact"]["late"]),
                       "open_tasks": sum(x["tasks"] for x in mine), "rows": mine})
    orphan = [x for x in out_rows if x["owner"] not in tm]
    if orphan:
        groups.append({"id": "", "name": "ללא קמפיינר", "clients": len(orphan), "counts": {k: sum(1 for x in orphan if x["status"] == k) for k in ("red", "yellow", "green", "nodata")},
                       "late_checks": 0, "late_contact": 0, "open_tasks": 0, "rows": orphan})
    urgent = [x for x in out_rows if x["status"] == "red"][:8]
    today = [t for t in tasks if t.get("due_day") is not None and t["due_day"] <= ref and t["status"] in ("new", "in_progress", "awaiting_approval")]
    cnt = {k: sum(1 for x in out_rows if x["status"] == k) for k in ("red", "yellow", "green", "nodata")}
    return {"ref": ref, "ref_label": fmt_day(ref), "counts": cnt, "clients": len(out_rows), "urgent": urgent,
            "tasks_today": len(today), "approvals": sum(1 for t in tasks if t["status"] == "awaiting_approval"), "groups": groups, "engine": ENGINE}


def log_touch(db: Database, acc: str, cid: str, kind: str, text: str, by: str) -> dict:
    """תיעוד פעולת קמפיינר: 'check' = בדיקת קמפיין, 'call' / 'meeting' = תקשורת עם הלקוח. שני דברים שונים — נספרים בנפרד."""
    c = S.get_client(db, acc, cid)
    if not c:
        raise KeyError("לקוח לא נמצא")
    ref = S.ref_day(S.ws(db, acc))
    if kind == "check":
        S.ev(db, acc, ref, "check", "בדיקת קמפיין" + (": " + text[:120] if text else ""), cid, by, "campaign")
        msg = "נרשמה בדיקת קמפיין"
    else:
        from .store import exe, now
        exe(db, "INSERT INTO pulse_notes (account_id, client_id, kind, text, user_name, created_at) VALUES (?,?,?,?,?,?)",
            (acc, cid, kind, text or ("שיחה עם הלקוח" if kind == "call" else "פגישה עם הלקוח"), by, now()))
        S.ev(db, acc, ref, "note", ("תיעוד שיחה" if kind == "call" else "סיכום פגישה") + ": " + (text or "עדכון")[:80], cid, by, kind)
        msg = "נרשמה תקשורת עם הלקוח"
    S.bump(db, acc)
    return {"ok": True, "msg": msg}


def capabilities(ai_engine: str | None, insight: dict) -> list[dict]:
    """מה ה-AI יכול לעשות בפועל ללקוח הזה — רק מה שמחובר. השאר מסומן במפורש."""
    camp = insight["campaigns"]
    return [
        {"id": "task", "label": "להכין משימה לקמפיינר עם הצעדים", "status": "available"},
        {"id": "draft", "label": "לנסח עדכון ללקוח (טיוטה, לא נשלח)", "status": "available"},
        {"id": "copy", "label": "לכתוב קופי חלופי למודעה החלשה", "status": "available" if (ai_engine and camp.get("top_fix")) else "not_configured" if camp.get("top_fix") else "n/a",
         "needs": None if ai_engine else "מודל שפה (GEMINI_API_KEY בשרת)"},
        {"id": "verify", "label": "לבדוק אוטומטית אם התוצאה השתפרה אחרי הטיפול", "status": "available"},
        {"id": "budget", "label": "לשנות תקציב / לעצור מודעה בפועל", "status": "not_connected", "needs": "חיבור Meta Ads עם הרשאת ניהול · תמיד באישור מנהל"},
    ]
