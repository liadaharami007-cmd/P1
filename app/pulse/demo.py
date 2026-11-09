"""ClientPulse — ספק נתוני דמו (מסומן "דמו" בכל מקום).

מייצר 90 ימי היסטוריה עקביים ל-50 לקוחות לפי תרחישים (זינוק עלות, אפס לידים, שחיקה, שיפור, נתונים חסרים, לידים בלי מכירות...).
הנתונים נכתבים לאותה טבלה שספק אמיתי (CSV / Meta / Google) כותב אליה — כך שמנוע הניתוח לא יודע ולא צריך לדעת מאיפה הם באו.
"Demo Lab" מוסיף 'ops' לנתוני לקוח (למשל ירידת המרה מיום X) ומסנכרן מחדש — המנוע רץ מחדש על הנתונים בפועל.
"""
from __future__ import annotations

import math
import random

from .engine import iso_of

TEAM = [
    {"id": "niv", "name": "ניב", "role": "בעלים", "approver": True},
    {"id": "yuval", "name": "יובל", "role": "מנהל תפעול", "approver": True},
    {"id": "dana", "name": "דנה", "role": "מנהלת קמפיינים", "approver": False},
    {"id": "omer", "name": "עומר", "role": "מנהל קמפיינים", "approver": False},
]
TYPES = ["מרפאת שיניים", "סטודיו פילאטיס", "משרד עורכי דין", 'שיווק נדל"ן', "מכון כושר", "קבלן שיפוצים", 'משרד רו"ח', "מטבחים",
         "קוסמטיקה", "גני אירועים", "סוכנות ביטוח", "אנרגיה סולארית", "אופטיקה", "פיזיותרפיה", "קורסים אונליין", "השכרת רכב",
         "בית ספר לנהיגה", "רהיטים", "מיזוג אוויר", "מרפאה אסתטית"]
NAMES = ["כהן", "לוי", "מזרחי", "פרץ", "ביטון", "אברהם", "פרידמן", "אזולאי", "דהן", "אוחנה", "שפירא", "גבאי", "חדד", "רוזן", "קפלן",
         "עמר", "בן דוד", "סויסה", "טל", "נחום", "אשכנזי", "ברק", "שלום", "גולן", "יוסף"]
SCEN = [("healthy", 24), ("cpl_spike", 5), ("no_leads", 4), ("gradual", 5), ("improved", 4), ("low_data", 3), ("multi", 2),
        ("data_gap", 1), ("no_sales", 2)]
CAUSES = ["cvr", "cpm", "ctr", "cvr", "cpm"]
OWNERS = ["dana", "omer", "dana", "omer", "yuval"]

# תרחישי Demo Lab (מופעלים על לקוח ירוק שנבחר)
SCENARIOS = [
    {"id": "cpl", "name": "עלות לליד מזנקת", "desc": "ההמרה מקליק לליד צונחת ב-3 הימים האחרונים", "op": {"op": "cpl", "pct": 140}, "back": 2},
    {"id": "zero_leads", "name": "קמפיין מפסיק להביא לידים", "desc": "יומיים בלי לידים, למרות שיש הקלקות", "op": {"op": "zero_leads"}, "back": 1},
    {"id": "gradual", "name": "שחיקה הדרגתית", "desc": "ה-CTR נשחק כ-2% ביום במשך 3 שבועות", "op": {"op": "erode", "pct": 2}, "back": 21},
    {"id": "spend", "name": "הוצאות עולות בלי שיפור", "desc": "תקציב +70% בשבוע, אותה כמות לידים", "op": {"op": "spend", "pct": 70}, "back": 6},
    {"id": "disconnect", "name": "חיבור הנתונים מתנתק", "desc": "יומיים בלי נתונים מהמקור", "op": {"op": "disconnect"}, "back": 1},
    {"id": "no_sales", "name": "לידים בלי מכירות", "desc": "הלידים ממשיכים, המכירות נעצרות (שבועיים)", "op": {"op": "no_sales"}, "back": 13},
    {"id": "improve", "name": "ביצועי לקוח משתפרים", "desc": "ההמרה משתפרת ב-45% בשבוע האחרון", "op": {"op": "improve", "pct": 45}, "back": 6},
    {"id": "ignored", "name": "עובד לא מטפל במשימה דחופה", "desc": "משימה אדומה עוברת את מועד היעד (השעון מתקדם יומיים)", "special": True},
]


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def build_clients(T0: int, seed: int = 206) -> list[dict]:
    rng = random.Random(seed)
    scen = [s for s, n in SCEN for _ in range(n)]
    rng.shuffle(scen)
    spike_n = 0
    out = []
    for i, sc in enumerate(scen):
        cpm, ctr = 25 + rng.random() * 35, 0.008 + rng.random() * 0.02
        s: dict = {"start": None}
        if sc == "low_data":
            cpl, lpd = 120 + rng.random() * 80, 0.25 + rng.random() * 0.15
        elif sc == "gradual":
            cpl, lpd = 40 + rng.random() * 40, 40 + rng.random() * 15
        elif sc in ("cpl_spike", "improved", "multi", "no_sales"):
            cpl, lpd = 30 + rng.random() * 120, 12 + rng.random() * 10
        else:
            cpl, lpd = 30 + rng.random() * 120, 4 + rng.random() * 16
        if sc == "no_leads" and lpd < 6:
            lpd = 6
        cvr = cpm / (1000 * ctr * cpl)
        if sc == "cpl_spike":
            s["days"] = 3 + (i % 2)
            s["start"] = T0 - s["days"] + 1
            s["mult"] = 2.3 + rng.random() * 0.5
            s["cause"] = CAUSES[spike_n % len(CAUSES)]
            spike_n += 1
        elif sc == "no_leads":
            s["start"] = T0 - (i % 2)
        elif sc == "improved":
            s["start"], s["mult"] = T0 - 6, 0.58 + rng.random() * 0.06
        elif sc == "gradual":
            s["start"] = T0 - 20
        elif sc == "multi":
            s["start"] = T0 - 6
        elif sc == "data_gap":
            s["start"] = T0 - 1
        elif sc == "no_sales":
            s["start"] = T0 - 13
        daily = cpl * lpd
        industry = TYPES[(i * 7) % len(TYPES)]
        deal = {"מטבחים": 18000, "אנרגיה סולארית": 35000, 'שיווק נדל"ן': 25000, "גני אירועים": 40000}.get(industry, 2500)
        fee = round((1500 + daily * 30.4 * 0.12) / 100) * 100
        out.append({
            "id": f"c{i + 1}", "name": f"{industry} {NAMES[(i * 11 + 3) % len(NAMES)]}", "industry": industry, "owner": OWNERS[i % len(OWNERS)],
            "scenario": sc, "target_cpl": round(cpl * (1.1 + rng.random() * 0.2)),
            "monthly_budget": round(daily * 30.4 * (1.05 + rng.random() * 0.15) / 100) * 100,
            "fee_monthly": fee, "hours_monthly": round(6 + rng.random() * 18 + (8 if sc in ("multi", "cpl_spike") else 0)),
            "hourly_cost": 120, "other_costs_monthly": round(rng.random() * 400 / 50) * 50,
            "platforms": ["Meta"] if i % 3 else ["Meta", "Google"],
            "params": {"cpm": cpm, "ctr": ctr, "cvr": cvr, "daily": daily, "close": 0.06 + rng.random() * 0.12, "deal": deal,
                       "seed": (seed * 31 + i * 7919) & 0xFFFFFFFF, "scn": s, "scenario": sc},
        })
    return out


def _active(start: int | None, t: int, fixes: list[int]) -> bool:
    if start is None or t < start:
        return False
    return not any(start <= f <= t for f in fixes)


def gen_day(p: dict, t: int, ops: list[dict]) -> dict | None:
    rng = random.Random((p["seed"] ^ (t * 2654435761)) & 0xFFFFFFFFFFFF)
    fixes = [o["from"] for o in ops if o["op"] == "fix"]
    spM = cpmM = ctrM = cvrM = closeM = 1.0
    zero = gap = False
    s, sc = p["scn"], p["scenario"]
    if _active(s.get("start"), t, fixes):
        if sc == "cpl_spike":
            if s["cause"] == "cvr":
                cvrM /= s["mult"]
            elif s["cause"] == "cpm":
                cpmM *= s["mult"]
            else:
                ctrM /= s["mult"]
        elif sc == "gradual":
            ctrM /= 1.015 ** min(t - s["start"] + 1, 35)
        elif sc == "improved":
            cvrM /= s["mult"]
        elif sc == "multi":
            spM *= 1.7
            ctrM *= 0.6
            if t >= s["start"] + 3:
                cvrM /= 2.1
        elif sc == "no_leads":
            zero = True
        elif sc == "data_gap":
            gap = True
        elif sc == "no_sales":
            closeM = 0
    for o in ops:
        if o["op"] == "fix" or not _active(o["from"], t, fixes):
            continue
        k = o["op"]
        if k == "cpl":
            cvrM /= 1 + o["pct"] / 100
        elif k == "cpm":
            cpmM *= 1 + o["pct"] / 100
        elif k == "ctr":
            ctrM *= 1 - o["pct"] / 100
        elif k == "erode":
            ctrM /= (1 + o["pct"] / 100) ** min(t - o["from"] + 1, 35)
        elif k == "improve":
            cvrM /= 1 - o["pct"] / 100
        elif k == "spend":
            spM *= 1 + o["pct"] / 100
            cvrM /= 1 + o["pct"] / 100
        elif k == "zero_leads":
            zero = True
        elif k == "disconnect":
            gap = True
        elif k == "no_sales":
            closeM = 0
    spend = p["daily"] * spM * (1 + (rng.random() - 0.5) * 0.24)
    impr = round(spend / (p["cpm"] * cpmM) * 1000)
    clicks = _poisson(rng, impr * p["ctr"] * ctrM)
    leads = 0 if zero else _poisson(rng, clicks * p["cvr"] * cvrM)
    sales = sum(1 for _ in range(leads) if rng.random() < p["close"] * closeM)
    if gap:
        return None
    return {"date": iso_of(t), "spend": round(spend), "impressions": impr, "clicks": clicks, "leads": leads,
            "sales": sales, "revenue": round(sales * p["deal"] * (0.8 + rng.random() * 0.4))}


def gen_days(p: dict, frm: int, to: int, ops: list[dict]) -> list[dict]:
    return [d for t in range(frm, to + 1) if (d := gen_day(p, t, ops))]
