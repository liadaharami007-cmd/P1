"""ClientPulse — מנוע הרמזור (בלי DOM, בלי DB). הועבר מ-ClientPulse 2.0 (JS) לשרת ושודרג.

עקרונות:
- כל זיהוי מבוסס מבחן סטטיסטי מול ההיסטוריה של הלקוח עצמו (לא אחוז שינוי בודד) — מונע אדום על רעש.
- כל התראה מפרידה: עובדות (numbers) · השערות (investigate) · המלצות (plan).
- ספים ניתנים להתאמה לכל לקוח (thresholds_json) — רק מפתחות מוכרים, בטווח סביר.
- ציון בריאות שקוף: 100 פחות קנסות מפורטים. כל קנס עם סיבה.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

# ---------------------------------------------------------------- עזרי תאריכים ופורמט
def day_idx(iso: str) -> int:
    return (date.fromisoformat(iso) - date(1970, 1, 1)).days


def iso_of(idx: int) -> str:
    return date.fromordinal(date(1970, 1, 1).toordinal() + idx).isoformat()


def fmt_day(idx: int) -> str:
    d = date.fromordinal(date(1970, 1, 1).toordinal() + idx)
    return f"{d.day}.{d.month}"


def today_idx() -> int:
    return (datetime.now(timezone.utc).date() - date(1970, 1, 1)).days


def money(x: float | None) -> str:
    return "—" if x is None else f"₪{round(x):,}"


def pct(x: float) -> int:
    return round(x * 100)


def sgn(x: float) -> str:
    return ("+" if x > 0 else "") + f"{pct(x)}%"


# ---------------------------------------------------------------- ספים
THRESHOLDS: dict[str, float] = {
    "minMaterialDaily": 60, "cplYellow": 0.25, "cplRed": 0.5, "zYellow": -2.5, "zRed": -3,
    "zeroPYellow": 0.05, "zeroPRed": 0.01, "spendYellow": 0.3, "spendRed": 0.6,
    "ctrYellow": 0.25, "ctrRed": 0.45, "ctrZ": -3, "ctrMinClicks": 200,
    "trendSlope": 0.06, "trendZ": 2.2, "trendMinLeads": 25, "trendMinLevel": 0.08,
    "improveCpl": -0.25, "improveZ": 3, "improveMinLeads": 10, "lowDataLeads": 20, "goalOver": 0.3,
    "cvrDropYellow": 0.35, "cvrMinLeads": 30,
}
# ספים שמותר למשתמש לשנות לכל לקוח (בעברית לממשק) + טווח מותר
EDITABLE = {
    "cplYellow": ("עלייה בעלות לליד שמדליקה צהוב", 0.1, 2.0),
    "cplRed": ("עלייה בעלות לליד שמדליקה אדום", 0.2, 3.0),
    "goalOver": ("חריגה מיעד העלות לליד", 0.05, 2.0),
    "spendYellow": ("עליית הוצאה בלי לידים (צהוב)", 0.1, 3.0),
    "ctrYellow": ("ירידת CTR (צהוב)", 0.1, 0.9),
    "minMaterialDaily": ("הוצאה יומית מינימלית לאדום (₪)", 0, 5000),
}


def thresholds_for(overrides: dict | None) -> dict[str, float]:
    t = dict(THRESHOLDS)
    for k, v in (overrides or {}).items():
        if k in EDITABLE:
            lo, hi = EDITABLE[k][1], EDITABLE[k][2]
            try:
                t[k] = min(hi, max(lo, float(v)))
            except (TypeError, ValueError):
                pass
    return t


# ---------------------------------------------------------------- סטטיסטיקה
def stats(ds: list[dict]) -> dict[str, Any]:
    s: dict[str, Any] = {"n": len(ds), "spend": 0.0, "leads": 0, "clicks": 0, "impr": 0, "sales": 0, "revenue": 0.0,
                         "has_sales": any(d.get("sales") is not None for d in ds)}
    for d in ds:
        s["spend"] += d["spend"] or 0
        s["leads"] += d["leads"] or 0
        s["clicks"] += d["clicks"] or 0
        s["impr"] += d["impressions"] or 0
        s["sales"] += d.get("sales") or 0
        s["revenue"] += d.get("revenue") or 0
    s["cpl"] = s["spend"] / s["leads"] if s["leads"] else None
    s["ctr"] = s["clicks"] / s["impr"] if s["impr"] else None
    s["cpc"] = s["spend"] / s["clicks"] if s["clicks"] else None
    s["cpm"] = s["spend"] / s["impr"] * 1000 if s["impr"] else None
    s["cvr"] = s["leads"] / s["clicks"] if s["clicks"] else None
    s["dailySpend"] = s["spend"] / s["n"] if s["n"] else 0
    s["dailyLeads"] = s["leads"] / s["n"] if s["n"] else 0
    if s["has_sales"]:
        s["closeRate"] = s["sales"] / s["leads"] if s["leads"] else None
        s["cac"] = s["spend"] / s["sales"] if s["sales"] else None
        s["roas"] = s["revenue"] / s["spend"] if s["spend"] else None
    return s


def win(days: list[dict], ref: int, frm: int, to: int) -> list[dict]:
    return [d for d in days if frm <= ref - d["_i"] <= to]


def conf(abs_z: float) -> str:
    return "גבוהה" if abs_z >= 4 else "בינונית" if abs_z >= 3 else "נמוכה"


def _prep(days: list[dict]) -> list[dict]:
    out = []
    for d in days:
        d = dict(d)
        d["_i"] = day_idx(d["date"])
        out.append(d)
    out.sort(key=lambda d: d["_i"])
    return out


# ---------------------------------------------------------------- ניתוח לקוח
def analyze_client(c: dict, days: list[dict], ref: int) -> dict:
    T = thresholds_for(c.get("thresholds"))
    days = _prep(days)
    alerts: list[dict] = []
    info: list[str] = []
    base, rec = stats(win(days, ref, 7, 27)), stats(win(days, ref, 0, 6))
    material = rec["dailySpend"] >= T["minMaterialDaily"]
    low_data = base["leads"] < T["lowDataLeads"]

    def cap(sev: str) -> str:
        return "yellow" if (not material and sev == "red") else sev

    last = days[-1]["_i"] if days else None
    lag = 99 if last is None else ref - last
    CMP = "7 הימים האחרונים מול 21 הימים שלפניהם"

    if lag >= 1:
        alerts.append({"type": "data", "severity": "red" if lag >= 2 else "yellow", "durationDays": min(lag, 99), "confidence": "גבוהה",
                       "period": "עד " + fmt_day(ref), "title": "לא התקבלו נתונים " + ("מאתמול" if lag == 1 else f"{lag} ימים" if lag < 99 else "בכלל"),
                       "what": "הנתון האחרון שהתקבל ממקור הנתונים הוא מ-" + (fmt_day(last) if last is not None else "—") + ".",
                       "numbers": [["ימים ללא נתונים", "0", str(lag if lag < 99 else "—")]],
                       "why": "בלי נתונים אי אפשר לבקר את הלקוח, וכל בעיה אחרת אצלו נשארת בלתי נראית.", "immediate": lag >= 2})

    base_cpl = base["cpl"]
    if base_cpl and not low_data:
        best = None
        for w in (3, 7):
            s = stats(win(days, ref, 0, w - 1))
            if not s["spend"]:
                continue
            exp = s["spend"] / base_cpl
            z = (s["leads"] - exp) / math.sqrt(max(exp + exp * exp / base["leads"], 1))
            chg = (s["spend"] / s["leads"]) / base_cpl - 1 if s["leads"] else math.inf
            sev = "red" if (chg >= T["cplRed"] and z <= T["zRed"]) else "yellow" if (chg >= T["cplYellow"] and z <= T["zYellow"]) else None
            if sev and (not best or (sev == "red" and best["sev"] != "red")):
                best = {"sev": sev, "w": w, "s": s, "exp": exp, "chg": chg, "z": z}
        if best:
            sev = cap(best["sev"])
            cur = best["s"]["spend"] / best["s"]["leads"] if best["s"]["leads"] else None
            alerts.append({"type": "cpl", "severity": sev, "durationDays": best["w"], "window": best["w"], "confidence": conf(-best["z"]),
                           "z": round(best["z"], 2), "period": f"{best['w']} הימים האחרונים מול 21 הימים שלפניהם",
                           "title": "עלות לליד זינקה" if sev == "red" else "עלות לליד עולה",
                           "what": f"העלות לליד ב-{best['w']} הימים האחרונים היא {money(cur)}, לעומת {money(base_cpl)} בממוצע לפני כן.",
                           "numbers": [["עלות לליד", money(base_cpl), money(cur), sgn(best["chg"]) if math.isfinite(best["chg"]) else ""],
                                       ["לידים בתקופה", f"~{round(best['exp'])} צפויים", str(best["s"]["leads"])]],
                           "why": f"התקבלו {best['s']['leads']} לידים לעומת כ-{round(best['exp'])} שהיו צפויים לפי ההוצאה. הסטייה מובהקת סטטיסטית ולא רעש יומי.",
                           "immediate": sev == "red"})
    if base_cpl and days:
        streak, s_spend, s_clicks = 0, 0.0, 0
        for d in reversed(days):
            if d["leads"] == 0 and d["spend"] > 0:
                streak += 1
                s_spend += d["spend"]
                s_clicks += d["clicks"]
            else:
                break
        if streak:
            exp_l = s_spend / base_cpl
            pz = math.exp(-exp_l)
            zs = "red" if pz <= T["zeroPRed"] else "yellow" if pz <= T["zeroPYellow"] else None
            if zs:
                zs = cap(zs)
                alerts.append({"type": "no_leads", "severity": zs, "durationDays": streak,
                               "confidence": "גבוהה" if pz < 0.001 else "בינונית" if pz < 0.01 else "נמוכה",
                               "period": f"{streak} ימים אחרונים", "streakClicks": s_clicks, "streakSpend": s_spend,
                               "title": "אין לידים " + ("מאתמול" if streak == 1 else f"כבר {streak} ימים"),
                               "what": f"הוצאו {money(s_spend)} ונרשמו {s_clicks} הקלקות מאז הליד האחרון, אבל לא נכנס אף ליד.",
                               "numbers": [["לידים צפויים", f"~{exp_l:.1f}", "0"], ["הוצאה ללא לידים", "", money(s_spend)]],
                               "why": "לפי הביצועים הרגילים, הסיכוי לאפס לידים במקרה הוא " + ("פחות מ-0.1%" if pz < 0.001 else f"{pz * 100:.1f}%") + ".",
                               "immediate": zs == "red"})
    if base["dailySpend"] and rec["n"] >= 4 and material:
        s_up = rec["dailySpend"] / base["dailySpend"] - 1
        l_up = rec["dailyLeads"] / base["dailyLeads"] - 1 if base["dailyLeads"] else 0
        ss = "red" if (s_up >= T["spendRed"] and l_up <= 0.05) else "yellow" if (s_up >= T["spendYellow"] and l_up < s_up * 0.5) else None
        if ss:
            alerts.append({"type": "spend_up", "severity": ss, "durationDays": 7, "confidence": "בינונית" if rec["n"] >= 6 else "נמוכה", "period": CMP,
                           "title": "ההוצאה עלתה בלי תוספת לידים מתאימה",
                           "what": f"ההוצאה היומית עלתה ב-{pct(s_up)}%, ואילו הלידים ליום השתנו ב-{sgn(l_up)}.",
                           "numbers": [["הוצאה יומית", money(base["dailySpend"]), money(rec["dailySpend"]), sgn(s_up)],
                                       ["לידים ליום", f"{base['dailyLeads']:.1f}", f"{rec['dailyLeads']:.1f}"]],
                           "why": "התקציב הנוסף לא מייצר תוצאה בהתאם, וזה כסף של הלקוח.", "immediate": ss == "red"})
    if base["ctr"] and rec["impr"] and base["clicks"] >= T["ctrMinClicks"]:
        exp_c = rec["impr"] * base["ctr"]
        zc = (rec["clicks"] - exp_c) / math.sqrt(exp_c) if exp_c else 0
        cd = 1 - (rec["ctr"] or 0) / base["ctr"]
        cs = "red" if (cd >= T["ctrRed"] and zc <= T["ctrZ"]) else "yellow" if (cd >= T["ctrYellow"] and zc <= T["ctrZ"]) else None
        if cs:
            alerts.append({"type": "ctr", "severity": cap(cs), "durationDays": 7, "confidence": conf(-zc), "period": CMP,
                           "title": "ירידה בשיעור ההקלקה", "what": f"ה-CTR ירד ב-{pct(cd)}% בשבוע האחרון.",
                           "numbers": [["CTR", f"{base['ctr'] * 100:.2f}%", f"{(rec['ctr'] or 0) * 100:.2f}%", f"-{pct(cd)}%"]],
                           "why": "ירידה בהקלקות היא סימן מוקדם. היא נוטה להקדים עלייה בעלות לליד.", "immediate": False})
    # ירידה בהמרה מקליק לליד (חדש ב-OS): מזהה בעיית דף נחיתה/טופס גם כשה-CPL עוד לא קפץ
    if base["cvr"] and rec["clicks"] and base["leads"] >= T["cvrMinLeads"] and not any(a["type"] in ("cpl", "no_leads") for a in alerts):
        exp_l2 = rec["clicks"] * base["cvr"]
        zv = (rec["leads"] - exp_l2) / math.sqrt(max(exp_l2, 1))
        drop = 1 - (rec["cvr"] or 0) / base["cvr"]
        if drop >= T["cvrDropYellow"] and zv <= -3:
            alerts.append({"type": "cvr", "severity": "yellow", "durationDays": 7, "confidence": conf(-zv), "period": CMP,
                           "title": "ירידה בהמרה מקליק לליד", "what": f"פחות מבקרים הופכים לליד: {(base['cvr']) * 100:.1f}% ← {(rec['cvr'] or 0) * 100:.1f}%.",
                           "numbers": [["המרה מקליק לליד", f"{base['cvr'] * 100:.1f}%", f"{(rec['cvr'] or 0) * 100:.1f}%", f"-{pct(drop)}%"],
                                       ["לידים", f"~{round(exp_l2)} צפויים", str(rec["leads"])]],
                           "why": "התנועה מגיעה אבל לא ממירה. בדרך כלל זה דף נחיתה, טופס או הצעה — ושווה לבדוק לפני שהעלות לליד מזנקת.",
                           "immediate": False})
    weeks = [stats(win(days, ref, a, b)) for a, b in ((21, 27), (14, 20), (7, 13), (0, 6))]
    if all(w["leads"] >= T["trendMinLeads"] for w in weeks):
        ws = [w["leads"] for w in weeks]
        ys = [math.log(w["cpl"]) for w in weeks]
        W = sum(ws)
        xm = sum(w * k for k, w in enumerate(ws)) / W
        ym = sum(w * ys[k] for k, w in enumerate(ws)) / W
        sxx = sum(w * (k - xm) ** 2 for k, w in enumerate(ws))
        sxy = sum(w * (k - xm) * (ys[k] - ym) for k, w in enumerate(ws))
        slope = sxy / sxx
        zt = slope / math.sqrt(1 / sxx)
        level = weeks[3]["cpl"] / weeks[0]["cpl"] - 1
        if slope >= T["trendSlope"] and zt >= T["trendZ"] and level >= T["trendMinLevel"] and not any(a["type"] == "cpl" for a in alerts):
            wk = math.exp(slope) - 1
            alerts.append({"type": "trend", "severity": "yellow", "durationDays": 21, "confidence": "גבוהה" if zt >= 3.5 else "בינונית",
                           "period": "4 שבועות אחרונים", "early": True, "title": "מגמת הידרדרות הדרגתית",
                           "what": "העלות לליד עולה ברציפות: " + " ← ".join(money(w["cpl"]) for w in weeks) + f" (כ-{sgn(wk)} בשבוע).",
                           "numbers": [["עלות לליד לפני 4 שבועות", "", money(weeks[0]["cpl"])], ["עלות לליד השבוע", "", money(weeks[3]["cpl"]), sgn(level)]],
                           "why": f"עוד לא משבר. אבל אם הקצב יימשך, העלות תעלה בעוד כ-{pct((1 + wk) ** 2 - 1)}% תוך שבועיים.", "immediate": False})
    tgt = (c.get("goals") or {}).get("targetCpl")
    if tgt and rec["cpl"] and rec["leads"] >= 10 and rec["cpl"] > tgt * (1 + T["goalOver"]) and not any(a["type"] in ("cpl", "trend") for a in alerts):
        alerts.append({"type": "goal", "severity": "yellow", "durationDays": 7, "confidence": "בינונית", "period": "7 ימים אחרונים מול יעד הלקוח",
                       "title": "עלות לליד מעל היעד",
                       "what": f"העלות לליד ({money(rec['cpl'])}) גבוהה ב-{pct(rec['cpl'] / tgt - 1)}% מהיעד שסוכם ({money(tgt)}).",
                       "numbers": [["עלות לליד מול יעד", money(tgt), money(rec["cpl"]), sgn(rec["cpl"] / tgt - 1)]],
                       "why": "גם בלי שינוי חד, הלקוח לא מקבל את מה שהובטח לו, וזה סיכון לנטישה.", "immediate": False})
    # לידים בלי מכירות — רק כשיש נתוני מכירות (CRM / ייבוא). בלי נתונים: לא מחשבים.
    b_s, r_s = stats(win(days, ref, 0, 27)), None
    if b_s["has_sales"]:
        r_s = stats(win(days, ref, 0, 13))
        prev = stats(win(days, ref, 14, 55))
        if r_s["leads"] >= 20 and r_s["sales"] == 0 and prev.get("closeRate"):
            exp_sales = r_s["leads"] * prev["closeRate"]
            if math.exp(-exp_sales) <= 0.05:
                alerts.append({"type": "no_sales", "severity": "yellow", "durationDays": 14, "confidence": "בינונית" if exp_sales < 5 else "גבוהה",
                               "period": "14 ימים אחרונים מול 6 השבועות שלפניהם", "title": "לידים נכנסים אבל לא נסגרות מכירות",
                               "what": f"{r_s['leads']} לידים בשבועיים האחרונים ואף מכירה, כשבעבר נסגרו כ-{prev['closeRate'] * 100:.0f}% מהלידים.",
                               "numbers": [["שיעור סגירה", f"{prev['closeRate'] * 100:.0f}%", "0%"], ["מכירות צפויות", f"~{exp_sales:.1f}", "0"]],
                               "why": "הקמפיין 'נראה טוב' בכמות לידים, אבל העסק של הלקוח לא מרוויח — כנראה איכות לידים או טיפול בלידים.",
                               "immediate": False})
    improved = None
    if base_cpl and not low_data and rec["leads"] >= T["improveMinLeads"] and rec["spend"]:
        exp_i = rec["spend"] / base_cpl
        zi = (rec["leads"] - exp_i) / math.sqrt(exp_i + exp_i * exp_i / base["leads"])
        ci = rec["cpl"] / base_cpl - 1
        if ci <= T["improveCpl"] and zi >= T["improveZ"]:
            improved = {"change": ci, "confidence": conf(zi), "period": CMP,
                        "what": f"העלות לליד ירדה ב-{abs(pct(ci))}% ({money(base_cpl)} ← {money(rec['cpl'])}). השבוע נכנסו {rec['leads']} לידים, לעומת כ-{round(base['dailyLeads'] * 7)} בשבוע רגיל."}
    if low_data:
        info.append(f"מעט נתונים: {base['leads']} לידים ב-3 השבועות שלפני. הספים הורחבו כדי לא להתריע על רעש.")

    rank = {"red": 2, "yellow": 1}
    status = "green"
    for a in alerts:
        if rank[a["severity"]] > rank.get(status, 0):
            status = a["severity"]
    for a in alerts:
        a["key"] = f"{c['id']}:{a['type']}"
        a["priority"] = round((1000 if a["severity"] == "red" else 100) + math.log10(1 + rec["spend"]) * 20
                              + min(a["durationDays"], 14) * 5 + (50 if a["immediate"] else 0), 1)
    alerts.sort(key=lambda a: -a["priority"])
    costly = any(a["type"] in ("cpl", "spend_up", "no_leads", "goal") for a in alerts)
    excess = max(0.0, rec["spend"] - rec["leads"] * base_cpl) if (costly and base_cpl and not low_data) else 0.0
    res = {"id": c["id"], "name": c["name"], "industry": c.get("industry"), "owner": c.get("owner"), "goals": c.get("goals") or {},
           "is_demo": bool(c.get("is_demo")), "status": status, "improved": improved, "lowData": low_data, "info": info,
           "alerts": alerts, "priority": alerts[0]["priority"] + 10 * (len(alerts) - 1) if alerts else (50 if improved else 0),
           "base": base, "rec": rec, "weeks": weeks, "excess": excess, "lastIdx": last, "lag": lag, "days": days,
           "sales28": b_s if b_s["has_sales"] else None}
    res["health"] = health_score(res, T)
    return res


def health_score(r: dict, T: dict | None = None) -> dict:
    """ציון בריאות שקוף 0–100. כל קנס מופיע ברשימה עם סיבה — אין 'קופסה שחורה'."""
    w_conf = {"גבוהה": 1.0, "בינונית": 0.8, "נמוכה": 0.6}
    parts = []
    for a in r["alerts"]:
        base = 40 if a["severity"] == "red" else 15
        if a["type"] == "data":
            base = 25 if a["severity"] == "red" else 10
        parts.append({"label": a["title"], "points": -round(base * w_conf.get(a["confidence"], 0.8))})
    tgt = (r.get("goals") or {}).get("targetCpl")
    rc = r["rec"]["cpl"]
    if tgt and rc and rc > tgt and not any(a["type"] == "goal" for a in r["alerts"]):
        parts.append({"label": "עלות לליד מעל היעד", "points": -round(min(15, (rc / tgt - 1) * 40))})
    if r.get("improved"):
        parts.append({"label": "שיפור מובהק בעלות לליד", "points": 0})
    score = max(0, min(100, 100 + sum(p["points"] for p in parts)))
    return {"score": score, "parts": [p for p in parts if p["points"]],
            "formula": "100 פחות קנס לכל התראה פתוחה (אדום 40, צהוב 15, חוסר נתונים 10–25) × רמת הביטחון (גבוהה 1, בינונית 0.8, נמוכה 0.6), ועוד קנס על חריגה מהיעד (עד 15).",
            "confidence": "נמוכה" if r["lowData"] else "גבוהה" if r["rec"]["n"] >= 7 else "בינונית"}


def analyze_portfolio(items: list[tuple[dict, list[dict]]], ref: int) -> dict:
    t0 = datetime.now().timestamp()
    results = [analyze_client(c, d, ref) for c, d in items]
    results.sort(key=lambda r: -r["priority"])
    counts = {"green": 0, "yellow": 0, "red": 0, "improved": 0}
    excess = spend30 = 0.0
    for r in results:
        counts[r["status"]] += 1
        if r["improved"]:
            counts["improved"] += 1
        excess += r["excess"]
        spend30 += sum(d["spend"] for d in r["days"] if ref - d["_i"] < 30)
    return {"results": results, "byId": {r["id"]: r for r in results}, "counts": counts, "excess": excess, "spend30": spend30,
            "ms": round((datetime.now().timestamp() - t0) * 1000, 1), "ref": ref}


# ---------------------------------------------------------------- חקירה: עובדות / השערות / בדיקות / תוכנית / מדד הצלחה
def investigate(r: dict, a: dict) -> dict:
    w = a.get("window") or 7
    ref = r["lastIdx"] if r["lastIdx"] is not None else 0
    cur = stats([d for d in r["days"] if 0 <= ref - d["_i"] < w])
    b = r["base"]
    facts, hyp, checks, plan, unknown = [], [], [], [], []

    def f(label: str, x, y, fmt):
        if x is not None and y is not None:
            facts.append({"label": label, "before": fmt(x), "after": fmt(y), "change": (y / x - 1) if x else None})

    P2 = lambda v: f"{v * 100:.2f}%"  # noqa: E731
    P1 = lambda v: f"{v * 100:.1f}%"  # noqa: E731
    f("הוצאה יומית", b["dailySpend"], cur["dailySpend"], money)
    f("לידים ליום", b["dailyLeads"], cur["dailyLeads"], lambda v: f"{v:.1f}")
    f("עלות לליד (CPL)", b["cpl"], cur["cpl"], money)
    f("עלות לאלף חשיפות (CPM)", b["cpm"], cur["cpm"], money)
    f("שיעור הקלקה (CTR)", b["ctr"], cur["ctr"], P2)
    f("עלות להקלקה (CPC)", b["cpc"], cur["cpc"], lambda v: f"₪{v:.2f}")
    f("המרה מקליק לליד", b["cvr"], cur["cvr"], P1)
    drivers = []
    if all((b["cpm"], cur["cpm"], b["ctr"], cur["ctr"], b["cvr"], cur["cvr"])):
        lc = {"cpm": math.log(cur["cpm"] / b["cpm"]), "ctr": -math.log(cur["ctr"] / b["ctr"]), "cvr": -math.log(cur["cvr"] / b["cvr"])}
        tot = sum(abs(v) for v in lc.values()) or 1
        drivers = sorted(({"k": k, "v": v, "share": abs(v) / tot} for k, v in lc.items()), key=lambda d: -d["v"])
    exp_lc = cur["clicks"] * b["cvr"] if b["cvr"] else None
    z_cvr = (cur["leads"] - exp_lc) / math.sqrt(max(exp_lc, 1)) if exp_lc else 0
    exp_cl = cur["impr"] * b["ctr"] if b["ctr"] else None
    z_ctr = (cur["clicks"] - exp_cl) / math.sqrt(max(exp_cl, 1)) if exp_cl else 0
    cpm_up = cur["cpm"] / b["cpm"] - 1 if b["cpm"] and cur["cpm"] else 0

    def H(text, evidence, support, share=0.0):
        hyp.append({"text": text, "evidence": evidence, "support": support, "share": share})

    d_share = {d["k"]: (d["share"] if d["v"] > 0 else 0) for d in drivers}
    t = a["type"]
    if t == "data":
        H("החיבור למקור הנתונים נותק, פג תוקף ההרשאה או שהחשבון הושהה", f"לא התקבלו נתונים {a['durationDays']} ימים ברציפות.", "לא ניתן לאמת בלי גישה ל-API של המקור", 1)
        checks += ["בדוק את סטטוס החיבור והרשאות הגישה של חשבון המודעות", "בדוק אם הקמפיינים הושהו או אם יש בעיית תשלום"]
        plan.append({"text": "לחדש את החיבור או את ההרשאה למקור הנתונים", "actionType": "check"})
    elif t == "no_leads":
        if b["dailyLeads"] and a.get("streakClicks", 0) > 0:
            H("הקליקים ממשיכים להגיע, אבל לידים לא נרשמים. זה חשד חזק לתקלה בטופס, בדף הנחיתה או בקליטת הלידים",
              f"{a['streakClicks']} הקלקות ו-{money(a['streakSpend'])} הוצאה, עם 0 לידים.", "נתמך בנתונים", 0.9)
        else:
            H("המודעות כנראה לא מוצגות (אין הקלקות)", "אפס הקלקות בתקופה.", "נתמך בנתונים", 0.9)
        checks += ["שלח ליד בדיקה בטופס ובדוק שהוא מגיע ליעד (CRM, מייל או וובהוק)", "בדוק שדף הנחיתה נטען בנייד ובמחשב (אפשר דרך בדיקת אתר ב-P1)"]
        plan += [{"text": "לתקן את קליטת הלידים או את דף הנחיתה", "actionType": "check"},
                 {"text": "אם התקלה לא נמצאת תוך שעות: להשהות את הקמפיין כדי לעצור הוצאה", "actionType": "campaign_change"}]
    elif t == "no_sales":
        H("איכות הלידים ירדה או שהטיפול בלידים אצל הלקוח נתקע", "לידים ממשיכים להיכנס, מכירות לא נסגרות.", "נתמך בנתונים", 0.8)
        checks += ["בדוק עם הלקוח מי מטפל בלידים ותוך כמה זמן", "עבור על 10 לידים אחרונים: האם הם רלוונטיים?"]
        plan += [{"text": "לקבוע שיחה עם הלקוח על איכות ותהליך הטיפול בלידים", "actionType": "client_message"},
                 {"text": "לסנן קהל / להוסיף שאלת סינון בטופס", "actionType": "campaign_change"}]
    else:
        if d_share.get("cvr", 0) > 0.25 and z_cvr <= -2 or t == "cvr":
            H("פחות הקלקות הופכות ללידים. בעיה אפשרית בדף הנחיתה, בטופס, בהצעה או באיכות התנועה",
              f"המרה מקליק לליד: {P1(b['cvr'] or 0)} ← {P1(cur['cvr'] or 0)} ({round(d_share.get('cvr', 0) * 100)}% מהשינוי ב-CPL).", "נתמך בנתונים", max(d_share.get("cvr", 0), 0.6 if t == "cvr" else 0))
        if d_share.get("ctr", 0) > 0.25 and z_ctr <= -2:
            H("המודעות מושכות פחות הקלקות. ייתכן שחיקת קריאייטיב או שינוי בקהל",
              f"CTR: {P2(b['ctr'])} ← {P2(cur['ctr'])} ({round(d_share['ctr'] * 100)}% מהשינוי ב-CPL). אין נתוני שינויי קריאייטיב, כך שהסיבה המדויקת לא אומתה.", "נתמך חלקית", d_share["ctr"])
        if d_share.get("cpm", 0) > 0.25 and cpm_up >= 0.2:
            H("עלות החשיפה עלתה. ייתכן תחרות במכרז, קהל מצומצם או עונתיות", f"CPM: {money(b['cpm'])} ← {money(cur['cpm'])} ({sgn(cpm_up)}).", "נתמך בנתונים", d_share["cpm"])
        if t == "spend_up" and b["dailySpend"] and b["dailyLeads"]:
            H("התקציב הנוסף הגיע לקהל שממיר פחות (תשואה פוחתת)",
              f"הוצאה {sgn(cur['dailySpend'] / b['dailySpend'] - 1)}, לידים {sgn(cur['dailyLeads'] / b['dailyLeads'] - 1)}.", "נתמך בנתונים", 0.5)
        if not hyp:
            H("השינוי מפוזר בין כמה מדדים ואין לו גורם יחיד ברור", "אף מדד במשפך לא מסביר לבדו את רוב השינוי.", "לא חד-משמעי", 0.2)
        hyp.sort(key=lambda h: -h["share"])
        top = hyp[0]["text"]
        if "נחיתה" in top or "טופס" in top:
            checks += ["שלח ליד בדיקה ובדוק את זמן הטעינה של דף הנחיתה", "השווה את איכות התנועה לפי מיקום מודעה"]
            plan.append({"text": "לתקן או לבצע A/B לדף הנחיתה ולטופס", "actionType": "check"})
        if "קריאייטיב" in top or "הקלקות" in top or any("קריאייטיב" in h["text"] for h in hyp):
            checks.append("בדוק מתי הוחלף הקריאייטיב לאחרונה ומה התדירות (Frequency)")
            plan.append({"text": "להעלות 2–3 קריאייטיבים חדשים ולבחון אותם מול הקיימים", "actionType": "campaign_change"})
        if "חשיפה" in top:
            checks.append("בדוק את גודל הקהל ושינויים בטירגוט")
            plan.append({"text": "להרחיב קהל או לשנות אסטרטגיית הצעת מחיר", "actionType": "campaign_change"})
        if t == "spend_up":
            checks.append("מי העלה את התקציב ומתי")
            plan.append({"text": "להחזיר את התקציב לרמה הקודמת עד שהביצועים יתייצבו", "actionType": "budget_change"})
        if t in ("trend", "goal"):
            plan.append({"text": "לעדכן את הלקוח על המגמה ועל תוכנית הפעולה", "actionType": "client_message"})
        if not plan:
            plan.append({"text": "לבדוק ידנית את הקמפיינים הפעילים", "actionType": "check"})
        if t == "cpl" and a["severity"] == "red":
            plan.append({"text": "להוריד זמנית את התקציב ב-30% עד שהתקלה תאותר", "actionType": "budget_change"})
    unknown.append("שינויים שבוצעו בחשבון (קריאייטיב, טירגוט, תקציב): יומן השינויים של פלטפורמת הפרסום לא מחובר")
    if not (r.get("sales28")):
        unknown.append("איכות הלידים ושיעור הסגירה: אין נתוני מכירות (CRM לא מחובר)")
    target = b["cpl"] * 1.15 if b["cpl"] else None
    if t == "data":
        success = {"text": "נתונים מתקבלים שוב באופן יומי", "days": 1}
    elif t == "no_leads":
        success = {"text": f"לידים נכנסים שוב (לפחות {max(1, math.floor(b['dailyLeads'] * 0.6))} ביום)", "days": 2}
    elif t == "no_sales":
        success = {"text": "לפחות מכירה אחת נסגרת מהלידים החדשים", "days": 7}
    else:
        success = {"text": f"עלות לליד חוזרת עד {money(target)} (עד 15% מעל הממוצע) לאורך 3 ימים", "days": 3, "targetCpl": target}
    return {"facts": facts, "drivers": drivers, "hypotheses": hyp, "checks": checks, "plan": plan, "unknown": unknown,
            "success": success, "engine": "rules"}


def eval_success(r: dict, kind: str, success: dict, done_day: int, ref: int) -> dict:
    after = [d for d in r["days"] if done_day < d["_i"] <= ref]
    s = stats(after)
    res: dict[str, Any] = {"cpl": s["cpl"], "leads": s["leads"], "dailyLeads": s["dailyLeads"], "spend": s["spend"], "days": len(after)}
    if kind == "data":
        res["ok"] = r["lastIdx"] == ref
    elif kind == "no_leads":
        res["ok"] = bool(after) and s["leads"] >= max(1, math.floor(r["base"]["dailyLeads"] * len(after) * 0.5))
    elif kind == "no_sales":
        res["ok"] = s["sales"] > 0
    else:
        res["ok"] = bool(s["cpl"] and success.get("targetCpl") and s["cpl"] <= success["targetCpl"] and s["leads"] >= 5)
    return res


# ---------------------------------------------------------------- הזדמנויות · סיכון · רווחיות
def opportunities(r: dict, client: dict) -> list[dict]:
    out = []
    g = r.get("goals") or {}
    if r.get("improved"):
        out.append({"kind": "scale", "title": "שיפור מובהק — לבחון הגדלת תקציב הדרגתית", "evidence": r["improved"]["what"],
                    "action": "להציע ללקוח הגדלת תקציב של 10–20% לשבועיים עם מעקב על העלות לליד", "potential": None})
    tgt, bud = g.get("targetCpl"), g.get("monthlyBudget")
    if r["status"] == "green" and not r["lowData"] and tgt and r["rec"]["cpl"] and r["rec"]["cpl"] <= tgt * 0.85 and bud:
        monthly_spend = r["rec"]["dailySpend"] * 30.4
        if monthly_spend < bud * 0.9:
            extra = bud - monthly_spend
            out.append({"kind": "budget_headroom", "title": "התקציב לא מנוצל והעלות לליד מתחת ליעד",
                        "evidence": f"קצב הוצאה {money(monthly_spend)} לחודש מתוך {money(bud)}; עלות לליד {money(r['rec']['cpl'])} מול יעד {money(tgt)}.",
                        "action": "לנצל את יתרת התקציב בקמפיין הטוב ביותר",
                        "potential": f"עד ~{round(extra / r['rec']['cpl'])} לידים נוספים בחודש אם העלות לליד תישאר דומה (הערכה ליניארית, לא הבטחה)"})
    if r.get("sales28") and r["sales28"]["leads"] >= 20 and (r["sales28"].get("closeRate") or 0) < 0.03:
        out.append({"kind": "lead_handling", "title": "הרבה לידים, מעט מכירות — שירות ניהול לידים / אוטומציית מענה",
                    "evidence": f"{r['sales28']['leads']} לידים ו-{r['sales28']['sales']} מכירות ב-28 ימים.",
                    "action": "להציע ללקוח מענה מהיר ללידים (WhatsApp/טלפון) ומעקב סגירות", "potential": None})
    if client.get("website") is None and r["status"] != "green" and any(a["type"] in ("no_leads", "cvr") for a in r["alerts"]):
        out.append({"kind": "site_check", "title": "חשד לבעיה באתר — להציע בדיקת דף נחיתה",
                    "evidence": "ההמרה מקליק לליד ירדה או שאין לידים למרות הקלקות.",
                    "action": "להוסיף את כתובת האתר ללקוח ולהריץ בדיקת אתר ב-P1", "potential": None})
    fin = profitability(client, r)
    if fin and fin.get("margin") is not None and fin["margin"] < 0.2:
        out.append({"kind": "pricing", "title": "רווחיות נמוכה בלקוח — לבחון תמחור או היקף עבודה",
                    "evidence": f"רווחיות {round(fin['margin'] * 100)}% (הכנסה {money(fin['fee'])}, עלויות {money(fin['costs'])}).",
                    "action": "לבדוק אם השעות בפועל מצדיקות עדכון ריטיינר או צמצום היקף", "potential": None})
    return out


def profitability(client: dict, r: dict | None = None) -> dict | None:
    fee = client.get("fee_monthly")
    if not fee:
        return None
    hours, rate, other = client.get("hours_monthly") or 0, client.get("hourly_cost") or 0, client.get("other_costs_monthly") or 0
    labor = hours * rate
    costs = labor + other
    return {"fee": fee, "labor": labor, "other": other, "costs": costs, "profit": fee - costs, "margin": (fee - costs) / fee if fee else None,
            "hours": hours, "complete": bool(hours and rate),
            "ad_spend_30": round(sum(d["spend"] for d in r["days"] if r["lastIdx"] is not None and r["lastIdx"] - d["_i"] < 30)) if r else None}


def churn_risk(r: dict, alert_rows: list[dict], open_tasks: list[dict], ref: int) -> dict:
    """אינדיקציית סיכון (לא חיזוי מוכח): נקודות שקופות מנתונים שקיימים במערכת."""
    if len(r["days"]) < 14:
        return {"level": "unknown", "score": None, "reasons": ["פחות מ-14 ימי נתונים — אין מספיק בסיס"]}
    pts, reasons = 0, []
    if r["status"] == "red":
        pts += 3
        reasons.append("סטטוס אדום כרגע")
    hist = [a for a in alert_rows if ref - (a["first_day"] or ref) <= 60]
    if len(hist) >= 3:
        pts += 2
        reasons.append(f"{len(hist)} התראות ב-60 הימים האחרונים")
    old = [a for a in alert_rows if a["status"] not in ("cleared", "resolved") and ref - a["first_day"] >= 5]
    if old:
        pts += 2
        reasons.append(f"התראה פתוחה כבר {max(ref - a['first_day'] for a in old)} ימים")
    late = [t for t in open_tasks if t.get("due_day") is not None and t["due_day"] < ref]
    if late:
        pts += 2
        reasons.append(f"{len(late)} משימות באיחור")
    tgt = (r.get("goals") or {}).get("targetCpl")
    w = r["weeks"]
    if tgt and all(x["cpl"] and x["cpl"] > tgt for x in w[2:]):
        pts += 2
        reasons.append("עלות לליד מעל היעד שבועיים ברציפות")
    if any(a["type"] == "trend" for a in r["alerts"]):
        pts += 1
        reasons.append("מגמת הידרדרות")
    level = "high" if pts >= 6 else "medium" if pts >= 3 else "low"
    return {"level": level, "score": pts, "reasons": reasons or ["אין סימני סיכון בנתונים הקיימים"],
            "note": "אינדיקציה מנתוני ביצועים ותפעול בלבד — לא כולל שביעות רצון הלקוח"}
