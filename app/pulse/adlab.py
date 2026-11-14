"""ClientPulse — ניתוח מודעות: מה לשפר בהצעה, בקופי ובקריאייטיב.

שתי שכבות:
1. כללים (תמיד): השוואת כל מודעה לממוצע של הלקוח (CTR, המרה, עלות לליד, תדירות) + בדיקת טקסט (הצעה, מספר, קריאה לפעולה, אורך).
2. Gemini (כשמחובר): הצעות קופי חדשות שנכתבות רק מתוך המודעה, הענף והבעיה שזוהתה.
מודעות דמו נוצרות באופן עקבי מנתוני הלקוח ומסומנות דמו. לקוח אמיתי: מודעות יגיעו מחיבור Meta (לא מחובר עדיין).
"""
from __future__ import annotations

import random
import re

from .engine import money

OFFER = re.compile(r"\d|%|₪|חינם|מתנה|הנחה|מבצע|בלעדי|ללא עלות|מחיר")
CTA = re.compile(r"השאירו|השאר|לחצו|הזמינו|קבעו|צרו קשר|התקשרו|הירשמו|לפרטים|שלחו|בדקו|קבלו")
FORMATS = ["תמונה", "וידאו", "קרוסלה"]
COPY = [  # (כותרת, טקסט, הצעה) — תבניות דמו ריאליסטיות, חלקן חלשות בכוונה
    ("{ind} ברמה אחרת", "אנחנו {ind} עם ניסיון של שנים, שירות מקצועי ואמין. נשמח לעמוד לשירותכם.", ""),
    ("ייעוץ ראשון חינם", "מחפשים {ind} שאפשר לסמוך עליו? קבעו ייעוץ ראשון חינם — בלי התחייבות. השאירו פרטים ונחזור תוך שעה.", "ייעוץ חינם"),
    ("20% הנחה החודש בלבד", "רק עד סוף החודש: 20% הנחה ללקוחות חדשים. לחצו על הכפתור והשאירו פרטים.", "20% הנחה"),
    ("למה כולם בוחרים בנו?", "כי אנחנו הכי טובים. בואו לראות בעצמכם.", ""),
    ("מעל 1,200 לקוחות מרוצים", "הצטרפו ל-1,200 לקוחות שכבר בחרו בנו. קבלו הצעת מחיר תוך 24 שעות — השאירו פרטים עכשיו.", "הצעת מחיר ב-24 שעות"),
]


def demo_ads(client: dict, r: dict) -> list[dict]:
    """מודעות דמו עקביות לכל לקוח, שמתחלקות את ביצועי 7 הימים האחרונים שלו (כך שהסכום תואם לתיק הלקוח)."""
    p = client.get("params") or {}
    rng = random.Random(p.get("seed", 1) * 13 + 7)
    n = 3 + rng.randint(0, 2)
    picks = rng.sample(range(len(COPY)), n)
    weights = [rng.uniform(0.5, 1.6) for _ in range(n)]
    tot = sum(weights)
    rec = r["rec"]
    cause = (p.get("scn") or {}).get("cause")
    ads = []
    for k, idx in enumerate(picks):
        h, t, offer = COPY[idx]
        share = weights[k] / tot
        spend = rec["spend"] * share
        impr = max(1, round(rec["impr"] * share))
        ctr_m = (0.55 if idx in (0, 3) else 1.25 if idx in (1, 4) else 1.0) * rng.uniform(0.85, 1.15)
        cvr_m = (1.35 if offer else 0.7) * rng.uniform(0.85, 1.15)
        freq = round(rng.uniform(1.4, 2.6) + (2.6 if k == 0 and cause == "ctr" else 0) + (1.5 if idx in (0, 3) else 0), 1)
        clicks = max(0, round(impr * (rec["ctr"] or 0.01) * ctr_m))
        leads = max(0, round(clicks * (rec["cvr"] or 0.05) * cvr_m))
        ads.append({"id": f"{client['id']}-ad{k + 1}", "name": f"מודעה {k + 1} · {FORMATS[(idx + k) % 3]}", "format": FORMATS[(idx + k) % 3],
                    "headline": h.format(ind=client.get("industry") or ""), "text": t.format(ind=client.get("industry") or ""),
                    "offer": offer, "days": 6 + rng.randint(0, 40), "spend": round(spend), "impressions": impr, "clicks": clicks,
                    "leads": leads, "frequency": freq, "is_demo": True})
    return ads


def analyze(ads: list[dict], industry: str | None = None) -> dict:
    """ציון לכל מודעה + המלצות בשלושה תחומים: הצעה, קופי, קריאייטיב. כל המלצה עם הנתון שמאחוריה."""
    if not ads:
        return {"ads": [], "summary": None}
    sp = sum(a["spend"] for a in ads)
    im = sum(a["impressions"] for a in ads)
    cl = sum(a["clicks"] for a in ads)
    ld = sum(a["leads"] for a in ads)
    avg = {"ctr": cl / im if im else None, "cvr": ld / cl if cl else None, "cpl": sp / ld if ld else None}
    out = []
    for a in ads:
        ctr = a["clicks"] / a["impressions"] if a["impressions"] else None
        cvr = a["leads"] / a["clicks"] if a["clicks"] else None
        cpl = a["spend"] / a["leads"] if a["leads"] else None
        recs = []
        text = f"{a['headline']} {a['text']}"
        has_offer, has_cta, ln = bool(OFFER.search(text)), bool(CTA.search(a["text"])), len(a["text"])
        # הצעה
        if not has_offer:
            recs.append({"area": "הצעה", "issue": "אין הצעה ברורה", "why": "לא מופיע מספר, מחיר, הטבה או סיבה לפעול עכשיו.",
                         "do": "להוסיף הצעה מוחשית (ייעוץ חינם, הנחה מוגבלת בזמן, הצעת מחיר תוך 24 שעות)."})
        elif cvr is not None and avg["cvr"] and cvr < avg["cvr"] * 0.7 and a["clicks"] >= 30:
            recs.append({"area": "הצעה", "issue": "ההצעה לא ממירה", "why": f"המרה מקליק לליד {cvr * 100:.1f}% מול {avg['cvr'] * 100:.1f}% בממוצע.",
                         "do": "לבדוק שההצעה במודעה זהה לדף הנחיתה, ולחדד את ההצעה."})
        # קופי
        if not has_cta:
            recs.append({"area": "קופי", "issue": "אין קריאה לפעולה", "why": "הטקסט לא אומר לקורא מה לעשות.",
                         "do": "לסיים במשפט פעולה ברור: \"השאירו פרטים ונחזור תוך שעה\"."})
        if ln > 280:
            recs.append({"area": "קופי", "issue": "טקסט ארוך מדי", "why": f"{ln} תווים — רוב הקוראים לא מגיעים לסוף.", "do": "לקצר לשניים-שלושה משפטים עם ההצעה בהתחלה."})
        if ctr is not None and avg["ctr"] and ctr < avg["ctr"] * 0.7 and a["impressions"] >= 1000:
            recs.append({"area": "קופי", "issue": "כותרת חלשה", "why": f"CTR {ctr * 100:.2f}% מול {avg['ctr'] * 100:.2f}% בממוצע של הלקוח.",
                         "do": "כותרת עם תועלת או מספר במקום סיסמה כללית."})
        # קריאייטיב
        if a["frequency"] >= 3.5:
            recs.append({"area": "קריאייטיב", "issue": "שחיקה", "why": f"תדירות {a['frequency']} — אותם אנשים רואים את המודעה שוב ושוב.",
                         "do": "להעלות 2–3 קריאייטיבים חדשים או להרחיב קהל."})
        if ctr is not None and avg["ctr"] and ctr < avg["ctr"] * 0.6 and a["format"] == "תמונה" and a["impressions"] >= 1000:
            recs.append({"area": "קריאייטיב", "issue": "הוויזואל לא עוצר גלילה", "why": "CTR נמוך במיוחד במודעת תמונה.",
                         "do": "לבחון וידאו קצר או תמונה עם פנים/תוצאה לפני-אחרי."})
        best = cpl is not None and avg["cpl"] and cpl <= avg["cpl"] * 0.8 and a["leads"] >= 5
        bad = (cpl is not None and avg["cpl"] and cpl >= avg["cpl"] * 1.6) or (a["leads"] == 0 and a["spend"] >= 300)
        verdict = "מנצחת — להגדיל תקציב" if best and not recs else "לעצור או לשכתב" if bad else "לשפר" if recs else "תקינה"
        tone = "green" if verdict.startswith("מנצחת") else "red" if bad else "yellow" if recs else "green"
        out.append({**a, "ctr": ctr, "cvr": cvr, "cpl": cpl, "verdict": verdict, "tone": tone, "recs": recs,
                    "checks": {"הצעה": has_offer, "קריאה לפעולה": has_cta, "אורך סביר": 40 <= ln <= 280}})
    rank = {"red": 0, "yellow": 1, "green": 2}
    out.sort(key=lambda x: (rank[x["tone"]], -(x["spend"])))
    waste = sum(a["spend"] - a["leads"] * avg["cpl"] for a in out if a["tone"] == "red" and avg["cpl"] and a["spend"] > a["leads"] * avg["cpl"])
    winners = [a for a in out if a["verdict"].startswith("מנצחת")]
    summary = {"avg": avg, "spend": sp, "leads": ld, "to_fix": sum(1 for a in out if a["recs"]),
               "waste": round(waste) if waste > 0 else 0, "winner": winners[0]["name"] if winners else None,
               "headline": (f"{sum(1 for a in out if a['tone'] == 'red')} מודעות לעצור או לשכתב" if any(a["tone"] == "red" for a in out)
                            else f"{sum(1 for a in out if a['recs'])} מודעות לשפר" if any(a["recs"] for a in out) else "כל המודעות תקינות"),
               "note": f"עלות לליד ממוצעת {money(avg['cpl'])} · השוואה בין מודעות של אותו לקוח, 7 ימים אחרונים"}
    return {"ads": out, "summary": summary}


COPY_SCHEMA = {"type": "object", "properties": {"variants": {"type": "array", "items": {"type": "object", "properties": {
    "headline": {"type": "string"}, "text": {"type": "string"}, "why": {"type": "string"}},
    "required": ["headline", "text", "why"], "additionalProperties": False}}}, "required": ["variants"], "additionalProperties": False}
COPY_SYSTEM = ("אתה קופירייטר ביצועים למודעות פייסבוק ואינסטגרם בעברית. כתוב 3 גרסאות קופי משופרות למודעה. "
               "השתמש רק בעובדות שבמודעה המקורית ובפרטי העסק שנמסרו — אל תמציא מחירים, אחוזי הנחה, מספר לקוחות או הבטחות שלא הופיעו. "
               "אם צריך הצעה ואין — כתוב [הצעה להשלמה] במקום להמציא. כל גרסה: כותרת עד 40 תווים, טקסט עד 200 תווים עם קריאה לפעולה, "
               "ו-why: משפט אחד שמסביר מה תוקן לפי הבעיות שזוהו.")
