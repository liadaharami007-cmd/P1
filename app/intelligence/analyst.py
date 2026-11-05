"""P1 Intelligence — Claude כמנוע החשיבה: מקבל ראיות מהבדיקה ומפיק ניתוח, המלצות ותוכנית פעולה.

הפרדה מחייבת:
- ממצאים שנמדדו (measured) מגיעים מהמנוע — Claude לא משנה אותם.
- ai_findings = השערות של Claude על בסיס הראיות (נשמרות עם source="ai" ורמת ביטחון). לא נכנסות לציון.
- אסור להמציא מספרים (אחוזי המרה/נטישה/שיפור).
"""
from __future__ import annotations

from typing import Any

from . import evidence
from .client import Usage

CATS = ["conversion", "checkout", "trust", "ux_mobile", "technical"]
SEV = ["critical", "high", "medium", "low"]
LVL = ["high", "medium", "low"]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


S = {"type": "string"}
SCHEMA = _obj({
    "executive_summary": S,
    "conversion_readiness": S,
    "top_strengths": {"type": "array", "items": S},
    "ai_findings": {"type": "array", "items": _obj({
        "title": S, "category": {"type": "string", "enum": CATS}, "severity": {"type": "string", "enum": SEV},
        "impact": {"type": "string", "enum": LVL}, "observation": S,
        "evidence_refs": {"type": "array", "items": S}, "why_it_matters": S,
        "recommendation": S, "confidence": {"type": "string", "enum": LVL},
    })},
    "copy_suggestions": {"type": "array", "items": _obj({
        "area": {"type": "string", "enum": ["headline", "product_page", "cta", "cart", "checkout", "trust", "other"]},
        "current_text": S, "suggested_text": S, "rationale": S,
    })},
    "action_plan": {"type": "array", "items": _obj({
        "priority": {"type": "integer"}, "title": S, "why_first": S,
        "related_refs": {"type": "array", "items": S},
        "effort": {"type": "string", "enum": LVL}, "expected_effect": S,
    })},
    "comparison_notes": S,
})

SYSTEM = """אתה P1 Intelligence — מומחה בכיר ל-CRO, חוויית משתמש ומסחר אלקטרוני, שעובד עבור בעל חנות אונליין.
קיבלת ראיות מבדיקה אוטומטית אמיתית שבוצעה בדפדפן: שלבי מסע רכישה, ממצאים שנמדדו, עובדות טכניות, טקסט מעמודים וצילומי מסך.

כללים מחייבים:
1. כתוב בעברית פשוטה ומקצועית, לבעל עסק (לא למפתח).
2. התבסס רק על הראיות. כל ai_finding חייב להפנות לראיה ב-evidence_refs (תווית צילום מסך כמו "product/desktop", מזהה ממצא שנמדד כמו "no_reviews", או שם שלב).
3. ai_findings הם תובנות שלך שאינן כבר ברשימת measured_findings: בהירות הצעת הערך, היררכיה חזותית, ניסוח, אמון, חיכוך שנראה בצילומים. אל תחזור על ממצאים שנמדדו.
4. אסור להמציא מספרים: לא אחוזי המרה, לא אחוזי נטישה, לא "שיפור של X%", לא נתוני מכירות. השפעה מתוארת רק כ-high/medium/low ובמילים.
5. confidence משקף כמה הראיות תומכות בטענה. אם משהו לא נראה בראיות — אל תטען אותו.
6. copy_suggestions: הצעות ניסוח ספציפיות לאתר הזה. current_text יהיה ציטוט מהראיות או "" אם אין.
7. action_plan: 3–7 צעדים לפי סדר עדיפויות (priority 1 = ראשון), שמשלבים ממצאים שנמדדו ותובנות AI. related_refs מפנה למזהים.
8. comparison_notes: אם יש השוואה לבדיקה קודמת — פרש מה השתפר ומה החמיר על בסיס הנתונים שקיבלת. אם אין — "".
9. אם הבדיקה לא הגיעה לעמוד מוצר או לקופה — ציין זאת ואל תנחש מה יש שם."""

LANG_LINE = {"he": "כתוב את כל הטקסטים בעברית.", "en": "Write all text values in English (the evidence may be in Hebrew)."}


async def analyze(engine: Any, audit: dict, steps: list[dict], findings: list[dict], screenshots: list[dict],
                  comparison: dict | None, lang: str = "he") -> tuple[dict, Usage]:
    content = evidence.build(audit, steps, findings, screenshots, comparison)
    content.append({"type": "text", "text": "נתח את הראיות והחזר את הדוח במבנה המבוקש."})
    return await engine.structured(system=SYSTEM + "\n" + LANG_LINE.get(lang, LANG_LINE["he"]), content=content, schema=SCHEMA, effort="medium")


def to_findings(result: dict) -> list[dict]:
    """ממיר השערות AI לממצאים עם source="ai" (לא משפיעים על הציון)."""
    out = []
    for i, f in enumerate(result.get("ai_findings", [])):
        out.append({
            "rule_id": f"ai_{i + 1}", "source": "ai", "category": f["category"] if f["category"] in CATS else "conversion",
            "severity": f["severity"], "impact": f["impact"], "title": f["title"], "detail": f["observation"],
            "why_it_matters": f["why_it_matters"], "fix_steps": [f["recommendation"]],
            "evidence": {"refs": f.get("evidence_refs", []), "confidence": f["confidence"]},
        })
    return out
