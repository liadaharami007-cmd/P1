"""Ask ClientPulse — הסוכן של המנהל.

שלב 1 (תמיד): מנוע כללים שעונה רק מנתוני המערכת — כוונה → שליפת נתונים → תשובה + ראיות + קישורים.
שלב 2 (רק כשיש מודל זמין ב-engines.py: Claude / Gemini / Ollama): המודל מנסח מחדש את אותה תשובה
מתוך העובדות שנשלפו בלבד. אם המודל נכשל — חוזרים לתשובת הכללים. התשובה מציינת איזה מנוע ענה.
"""
from __future__ import annotations

import json
import re

from ..db import Database
from . import engine, service as S
from .engine import money, pct, sgn

SUGGESTIONS = ["מה קורה היום במשרד?", "אילו לקוחות צריכים אותי?", "מה השתנה בשבוע האחרון?", "אילו עובדים עמוסים?",
               "איפה אנחנו מפסידים כסף?", "אילו לקוחות כדאי לפתח?", "מי הידרדר הכי הרבה?"]


def _match_client(q: str, run: dict) -> dict | None:
    best, bs = None, 0
    for r in run["results"]:
        name = r["name"]
        parts = [p for p in name.split() if len(p) > 1]
        sc = 0
        if name in q:
            sc = 100
        else:
            sur = parts[-1] if parts else name
            if sur in q:
                sc = len(sur) * 2 + sum(len(w) for w in parts[:-1] if len(w) > 2 and w in q)
        if sc > bs:
            best, bs = r, sc
    return best


def rules_answer(db: Database, acc: str, q: str) -> dict:
    run = S.analysis(db, acc)
    tm = S.team_map(db, acc)
    q = (q or "").strip()
    out: dict = {"text": "", "evidence": [], "links": [], "intent": "unknown", "follow": []}
    cl = _match_client(q, run)

    def link(label: str, route: str):
        out["links"].append({"label": label, "route": route})
    if not run["results"]:
        out["text"] = "אין עדיין לקוחות במערכת. הוסיפו לקוח וייבאו נתונים (CSV), או הפעילו את סביבת הדמו."
        link("לקוחות", "clients")
        return out
    if cl and re.search(r"פגיש|סיכום ל", q):
        out["intent"] = "meeting"
        rep = report_brief(db, acc, cl)
        out["text"] = f"טיוטת סיכום לפגישה עם {cl['name']} (מנתוני 30 הימים האחרונים):"
        out["evidence"] = rep
        link("פתח את תיק הלקוח", f"client/{cl['id']}")
        link("הפק דוח ללקוח", f"report/{cl['id']}")
        return out
    if cl and re.search(r"למה|מדוע|סיבה|תסביר|הסבר", q):
        out["intent"] = "why"
        a = cl["alerts"][0] if cl["alerts"] else None
        if not a:
            out["text"] = f"אצל {cl['name']} לא זוהתה כרגע חריגה. העלות לליד ב-7 הימים האחרונים היא {money(cl['rec']['cpl'])} לעומת {money(cl['base']['cpl'])} קודם."
        else:
            inv = engine.investigate(cl, a)
            h = inv["hypotheses"][0]
            out["text"] = f"{cl['name']}: {a['what']} ההסבר שהנתונים תומכים בו ביותר: {h['text']} ({h['support']})."
            out["evidence"] = [f"עובדה · {f['label']}: {f['before']} ← {f['after']} ({sgn(f['change'])})" for f in inv["facts"]
                               if f["change"] is not None and abs(f["change"]) >= 0.1]
            out["evidence"] += [f"המלצה · {p['text']}" for p in inv["plan"][:2]]
            out["evidence"].append("לא נבדק · " + inv["unknown"][0])
        link("פתח את תיק הלקוח", f"client/{cl['id']}")
        out["follow"] = [f"תכין לי סיכום לפגישה עם {cl['name']}"]
        return out
    if re.search(r"היום במשרד|מה קורה|תמונת מצב|בוקר", q):
        out["intent"] = "today"
        c = run["counts"]
        s = S.summary_text(db, acc, run)
        out["text"] = f"{c['green']} תקינים, {c['yellow']} במעקב, {c['red']} דחופים ו-{c['improved']} שהשתפרו. " + s["plain"].split(".")[0] + "."
        for x in s["top"]:
            out["evidence"].append(x["text"])
            link(x["text"][:40] + "…", x["route"])
        out["follow"] = ["מה השתנה בשבוע האחרון?", "אילו עובדים עמוסים?"]
        return out
    if re.search(r"דחו|צריכים אותי|הכי חשוב|בעיות|עדיפות|מה כדאי לעשות", q):
        out["intent"] = "urgent"
        top = S.top_actions(db, acc, run, 5)
        out["text"] = "הפעולות החשובות כרגע, לפי חומרה, תקציב, משך ומצב טיפול:" if top else "אין כרגע בעיות פתוחות."
        for i, x in enumerate(top):
            r = run["byId"][x["clientId"]]
            out["evidence"].append(f"{i + 1}. {x['text']} — {x['why']} (הוצאה 7 ימים: {money(r['rec']['spend'])})")
            link(r["name"], x["route"])
        return out
    if re.search(r"השתנה|שבוע האחרון|אתמול|חדש", q):
        out["intent"] = "changes"
        ref = run["ref"]
        evs = S.rows(db, "SELECT * FROM pulse_events WHERE account_id=? AND day>=? AND type IN ('alert','cleared','verified','verify_failed','task') ORDER BY id DESC LIMIT 40",
                     (acc, ref - 6))
        kinds = {"alert": 0, "cleared": 0, "verified": 0, "task": 0, "verify_failed": 0}
        for e in evs:
            kinds[e["type"]] = kinds.get(e["type"], 0) + 1
        out["text"] = (f"ב-7 הימים האחרונים: {kinds['alert']} חריגות חדשות, {kinds['cleared']} חזרו לתקין, {kinds['task']} פעולות במשימות, "
                       f"{kinds['verified']} תיקונים אומתו בנתונים.")
        out["evidence"] = [f"{engine.fmt_day(e['day'])} · {e['text']}" for e in evs[:8]]
        link("ציר הזמן במרכז הפיקוד", "home")
        return out
    if re.search(r"עובד|עמוס|משימ|לא טיפל|מי ", q):
        out["intent"] = "team"
        wl = [m for m in S.workload(db, acc) if m["open"] or m["clients"]]
        wl.sort(key=lambda m: -(m["open"] * 2 + m["late"] * 5))
        late = sum(m["late"] for m in wl)
        out["text"] = (f"{late} משימות באיחור. " if late else "אין משימות באיחור. ") + "עומס לפי עובד (משימות פתוחות ולקוחות באחריות):"
        out["evidence"] = [f"{m['name']}: {m['open']} פתוחות ({m['not_started']} לא התחילו, {m['late']} באיחור, {m['red']} דחופות) · {m['clients']} לקוחות" for m in wl]
        link("צוות ומשימות", "team")
        return out
    if re.search(r"השתפר|שיפור|הצלח", q):
        out["intent"] = "improved"
        imp = [r for r in run["results"] if r["improved"]]
        out["text"] = f"{len(imp)} לקוחות השתפרו משמעותית ב-7 הימים האחרונים:" if imp else "לא זוהו כרגע לקוחות עם שיפור מובהק."
        for r in imp:
            out["evidence"].append(f"{r['name']}: עלות לליד {money(r['base']['cpl'])} ← {money(r['rec']['cpl'])} ({sgn(r['improved']['change'])}), {r['rec']['leads']} לידים")
            link(r["name"], f"client/{r['id']}")
        return out
    if re.search(r"לפתח|להרחיב|הזדמנו|אפסייל|upsell", q, re.I):
        out["intent"] = "opportunities"
        ops = [(r, o) for r in run["results"] for o in engine.opportunities(r, run["clients"][r["id"]])]
        out["text"] = f"זוהו {len(ops)} הזדמנויות מבוססות נתונים:" if ops else "לא זוהו כרגע הזדמנויות מבוססות נתונים."
        for r, o in ops[:8]:
            out["evidence"].append(f"{r['name']} · {o['title']} — {o['evidence']}")
            link(r["name"], f"client/{r['id']}")
        return out
    if re.search(r"מפסיד|כסף|תקציב|הוצא|רווח", q):
        out["intent"] = "money"
        losers = sorted([r for r in run["results"] if r["excess"] > 0], key=lambda r: -r["excess"])[:4]
        low = []
        for r in run["results"]:
            f = engine.profitability(run["clients"][r["id"]], r)
            if f and f["margin"] is not None and f["margin"] < 0.2:
                low.append((r, f))
        out["text"] = (f"בשבוע האחרון ההוצאה העודפת המשוערת מחריגות היא {money(run['excess'])} (כסף של הלקוחות), "
                       f"ו-{len(low)} לקוחות ברווחיות נמוכה מ-20% לסוכנות.")
        out["evidence"] = ["הוצאה עודפת = הוצאת 7 ימים פחות (לידים × עלות לליד היסטורית), רק ללקוחות עם חריגת עלות"]
        out["evidence"] += [f"{r['name']}: הוצאה עודפת {money(r['excess'])}" for r in losers]
        out["evidence"] += [f"{r['name']}: רווחיות {round(f['margin'] * 100)}% ({money(f['profit'])} בחודש)" for r, f in low[:4]]
        for r in losers:
            link(r["name"], f"client/{r['id']}")
        link("רווחיות", "profit")
        return out
    if re.search(r"הידרדר|החמיר|הכי גרוע", q):
        out["intent"] = "worst"
        c = sorted(({"r": r, "ch": r["weeks"][3]["cpl"] / r["weeks"][2]["cpl"] - 1} for r in run["results"]
                    if not r["lowData"] and r["weeks"][2]["cpl"] and r["weeks"][3]["cpl"]), key=lambda x: -x["ch"])[:3]
        if not c:
            out["text"] = "אין מספיק נתונים להשוואה שבועית."
            return out
        out["text"] = f"הלקוח שהידרדר הכי הרבה השבוע: {c[0]['r']['name']}. העלות לליד שלו עלתה ב-{pct(c[0]['ch'])}% לעומת השבוע הקודם."
        for x in c:
            out["evidence"].append(f"{x['r']['name']}: {money(x['r']['weeks'][2]['cpl'])} ← {money(x['r']['weeks'][3]['cpl'])} ({sgn(x['ch'])})")
            link(x["r"]["name"], f"client/{x['r']['id']}")
        return out
    if cl:
        out["intent"] = "client"
        out["text"] = f"{cl['name']}: {S.SL[cl['status']]}" + (". " + "; ".join(a["title"] for a in cl["alerts"]) if cl["alerts"] else "") + "."
        out["evidence"] = [f"עלות לליד 7 ימים: {money(cl['rec']['cpl'])} (קודם {money(cl['base']['cpl'])})", f"לידים 7 ימים: {cl['rec']['leads']}",
                           f"ציון בריאות: {cl['health']['score']}", f"אחראי: {(tm.get(cl['owner']) or {}).get('name', '—')}"]
        link("פתח את תיק הלקוח", f"client/{cl['id']}")
        out["follow"] = [f"למה {cl['name']} במצב הזה?", f"תכין לי סיכום לפגישה עם {cl['name']}"]
        return out
    out["text"] = ("לא זיהיתי את השאלה. אני עונה רק מתוך נתוני המערכת. אפשר לשאול: מה קורה היום, מי צריך אותי, מה השתנה, מי עמוס, "
                   "איפה מפסידים כסף, את מי כדאי לפתח, למה [שם לקוח] התייקר, או סיכום לפגישה עם [שם לקוח].")
    out["follow"] = SUGGESTIONS[:4]
    return out


def report_brief(db: Database, acc: str, r: dict) -> list[str]:
    tasks = [t for t in S.all_tasks(db, acc, r["id"])]
    done = [t for t in tasks if t["status"] == "closed" and t.get("verification") and t["verification"].get("ok")]
    lines = [f"מצב: {S.SL[r['status']]} · ציון בריאות {r['health']['score']}",
             f"7 ימים: הוצאה {money(r['rec']['spend'])}, {r['rec']['leads']} לידים, עלות לליד {money(r['rec']['cpl'])} (לעומת {money(r['base']['cpl'])})"]
    tgt = r["goals"].get("targetCpl")
    if tgt and r["rec"]["cpl"]:
        lines.append(f"מול היעד ({money(tgt)}): {sgn(r['rec']['cpl'] / tgt - 1)}")
    for a in r["alerts"][:3]:
        lines.append(f"נושא פתוח: {a['title']} — {a['what']}")
    for t in done[:3]:
        lines.append(f"טופל ואומת: {t['title']}")
    if r["improved"]:
        lines.append("הישג: " + r["improved"]["what"])
    lines.append("הצעדים הבאים: " + ("; ".join(engine.investigate(r, a)["plan"][0]["text"] for a in r["alerts"][:2]) if r["alerts"]
                                     else "שימור הביצועים ובחינת הרחבה הדרגתית"))
    return lines


SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}
SYSTEM = ("אתה Ask ClientPulse, עוזר למנהל משרד פרסום. ענה בעברית פשוטה ותמציתית (עד 4 משפטים). "
          "מותר להשתמש רק בעובדות שמופיעות ב-FACTS. אסור להמציא מספרים, שמות, סיבות או נתונים שלא מופיעים שם. "
          "אם חסר מידע — אמור מה חסר. הפרד בין עובדה, השערה והמלצה.")


async def ask(db: Database, acc: str, q: str, use_ai: bool = True) -> dict:
    base = rules_answer(db, acc, q)
    base["engine"] = "rules"
    if not use_ai or base["intent"] == "unknown":
        return base
    try:
        from ..intelligence import engines
        eng = engines.active_engine()
    except Exception:  # noqa: BLE001
        eng = None
    if not eng:
        return base
    facts = {"question": q, "answer_from_rules": base["text"], "evidence": base["evidence"]}
    try:
        data, _usage = await eng.structured(system=SYSTEM, content=[{"type": "text", "text": "FACTS:\n" + json.dumps(facts, ensure_ascii=False)}],
                                            schema=SCHEMA, effort="low", max_tokens=1200)
        txt = (data or {}).get("text", "").strip()
        if txt:
            base["text"] = txt
            base["engine"] = f"{eng.id} ({eng.model})"
    except Exception as e:  # noqa: BLE001
        base["engine_error"] = f"המודל לא זמין ({type(e).__name__}) — הוצגה תשובת מנוע הכללים"
    return base
