"""AI Customer Simulation — 5 סוכני Claude שכל אחד מגלם סוג לקוח.

חשוב: אלה לקוחות *מדומים*. כל סוכן צופה בראיות האמיתיות מהמסלול שהדפדפן ביצע
(צילומי מסך, טקסט, שלבים) ומדווח מנקודת המבט של הפרסונה. אין כאן נתוני התנהגות של לקוחות אמיתיים.
"""
from __future__ import annotations

import asyncio
from typing import Any

from . import evidence
from .client import IntelligenceError, Usage

PERSONAS: dict[str, dict] = {
    "price_seeker": {"name": "מחפש המחיר המשתלם", "devices": ("desktop",),
                     "brief": "אתה לקוח שמחפש את העסקה המשתלמת ביותר. אתה משווה מחירים, בודק עלויות משלוח, מחפש מבצעים וקופונים, וחושש מעלויות נסתרות בקופה."},
    "wary_newcomer": {"name": "חושש מאתר לא מוכר", "devices": ("desktop",),
                      "brief": "מעולם לא שמעת על החנות הזו. אתה חושש מהונאה. אתה מחפש סימני אמינות: פרטי חברה, טלפון, ביקורות אמיתיות, מדיניות החזרות, אבטחת תשלום."},
    "in_a_hurry": {"name": "ממהר להזמין", "devices": ("mobile", "desktop"),
                   "brief": "אתה יודע מה אתה רוצה ויש לך דקה אחת. כל לחיצה מיותרת, חלון קופץ, טעינה איטית או טופס ארוך יגרמו לך לעזוב."},
    "unclear_benefits": {"name": "לא מבין את יתרונות המוצר", "devices": ("desktop",),
                         "brief": "המוצר נראה לך מעניין אבל אתה לא בטוח מה מיוחד בו ולמה הוא שווה את המחיר. אתה מחפש הסבר ברור, יתרונות, השוואה ותשובות לשאלות."},
    "mobile_ad_visitor": {"name": "הגיע מפרסומת בטלפון", "devices": ("mobile",),
                          "brief": "לחצת על מודעה באינסטגרם ונחתת באתר בטלפון. הקשב שלך קצר, אתה גולל מהר, ורוצה להבין תוך שניות מה מוצע ואיך קונים."},
}

S = {"type": "string"}
ARR = {"type": "array", "items": S}
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["understood", "caught_attention", "confusing", "distrust", "purchase_issues", "improvements",
                       "verdict", "verdict_reason"],
          "properties": {"understood": S, "caught_attention": ARR, "confusing": ARR, "distrust": ARR,
                         "purchase_issues": ARR, "improvements": ARR,
                         "verdict": {"type": "string", "enum": ["likely_buy", "hesitant", "likely_leave"]},
                         "verdict_reason": S}}

SYSTEM_TMPL = """אתה סוכן סימולציה של P1 AI שמגלם לקוח מדומה בחנות אונליין.
הפרסונה שלך: {brief}

קיבלת ראיות אמיתיות מגלישה שבוצעה בדפדפן אוטומטי באתר (צילומי מסך, טקסט מהעמודים ושלבי מסע הרכישה).
דווח מנקודת המבט של הפרסונה, בגוף ראשון, בעברית פשוטה:
- understood: מה הבנת שהאתר/המוצר מציע (משפט-שניים).
- caught_attention: מה משך את תשומת ליבך.
- confusing: מה בלבל אותך.
- distrust: מה גרם לך לחוסר אמון.
- purchase_issues: בעיות שנתקלת בהן בדרך לקנייה (על בסיס שלבי המסע והצילומים).
- improvements: מה היה גורם לך לקנות (הצעות קונקרטיות).
התבסס רק על מה שמופיע בראיות. אם לא ראית משהו (למשל הקופה לא נבדקה) — אמור זאת ואל תמציא. אל תמציא מספרים או סטטיסטיקות.
{lang_line}"""


async def run_one(engine: Any, key: str, audit: dict, steps: list[dict], findings: list[dict],
                  screenshots: list[dict], lang: str = "he") -> tuple[dict, Usage]:
    p = PERSONAS[key]
    content = evidence.build(audit, steps, findings, screenshots, None, max_images=4, devices=p["devices"])
    content.append({"type": "text", "text": "דווח על החוויה שלך באתר הזה במבנה המבוקש."})
    return await engine.structured(system=SYSTEM_TMPL.format(brief=p["brief"], lang_line="Write all text values in English." if lang == "en" else "כתוב בעברית."), content=content,
                                 schema=SCHEMA, effort="low", max_tokens=8000)


async def run_all(engine: Any, audit: dict, steps: list[dict], findings: list[dict], screenshots: list[dict],
                  lang: str = "he") -> dict[str, tuple[dict | None, Usage | None, str | None]]:
    async def safe(key):
        try:
            data, usage = await run_one(engine, key, audit, steps, findings, screenshots, lang)
            return key, (data, usage, None)
        except IntelligenceError as e:
            return key, (None, None, e.message)
    results = await asyncio.gather(*(safe(k) for k in PERSONAS))
    return dict(results)
