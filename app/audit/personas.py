"""Invisible Customer — סימולציית לקוחות.

חשוב: זו *סימולציה מבוססת כללים*, לא לקוחות אמיתיים ולא מודל AI.
כל "לקוח" הוא רשימת ציפיות מוגדרת מראש, שנבדקת מול הנתונים שהדפדפן מדד בפועל.
כך כל הערה של הלקוח המדומה ניתנת לאימות — אפשר להצביע על העובדה שגרמה לה.
בעתיד (עם Claude API) נוסיף שכבה שבה מודל "משחק" את הלקוח על בסיס צילומי המסך.
"""
from __future__ import annotations

from typing import Callable

PERSONAS = {
    "skeptic": {"name": "הלקוח החשדן", "goal": "רוצה להיות בטוח שהחנות אמינה לפני שהוא משאיר כרטיס אשראי"},
    "bargain": {"name": "מחפש המחיר", "goal": "רוצה לדעת מהר כמה זה עולה כולל משלוח, ולמצוא מבצע"},
    "hesitant": {"name": "המתלבט", "goal": "מתעניין, אבל צריך שכנוע וביטחון שאפשר להחזיר"},
    "rushed": {"name": "הממהר", "goal": "יודע מה הוא רוצה ורוצה לסיים קנייה בטלפון תוך דקה"},
    "researcher": {"name": "החוקר", "goal": "רוצה להבין לעומק את המוצר לפני החלטה"},
}

# (תנאי שמצביע על בעיה, טקסט החסם בגוף ראשון, חסם 'קשה' = עוזב מיד)
Check = tuple[Callable[[dict], bool], str, bool]


def _g(f: dict, *path, default=None):
    cur = f
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return default if cur is None else cur


def _journey_ok(f: dict) -> bool:
    return bool(_g(f, "checkout", "reached"))


def _lcp(f: dict) -> int:
    t = _g(f, "home", "timing", default={})
    return t.get("lcp") or t.get("load") or 0


CHECKS: dict[str, list[Check]] = {
    "skeptic": [
        (lambda f: not f.get("https"), "האתר מסומן 'לא מאובטח' — לא אכניס פה כרטיס אשראי.", True),
        (lambda f: not _g(f, "trust_links", "returns"), "לא מצאתי מדיניות החזרות. מה אם המוצר לא יתאים?", False),
        (lambda f: not _g(f, "trust_links", "contact") and not _g(f, "home", "html", "phones") and not _g(f, "home", "html", "whatsapp_link"),
         "אין טלפון, וואטסאפ או 'צור קשר'. אם תהיה בעיה — למי אפנה?", True),
        (lambda f: "product" in f and not _g(f, "product", "mentions_reviews"), "אין ביקורות של לקוחות אחרים. איך אדע שזה טוב?", False),
        (lambda f: not _g(f, "trust_links", "about"), "לא ברור מי עומד מאחורי החנות.", False),
        (lambda f: not _g(f, "trust_links", "privacy"), "אין מדיניות פרטיות — מה יעשו עם הפרטים שלי?", False),
    ],
    "bargain": [
        (lambda f: "product" in f and not _g(f, "product", "price_visible"), "לא רואה מחיר. לא אשאל — אעבור לאתר אחר.", True),
        (lambda f: "product" in f and not _g(f, "product", "mentions_shipping") and not _g(f, "cart", "mentions_shipping_cost"),
         "לא ברור כמה עולה המשלוח. אני חושש מהפתעה בקופה.", False),
        (lambda f: not _g(f, "search", "available"), "אין חיפוש — קשה להשוות בין מוצרים.", False),
        (lambda f: "product" in f and not _g(f, "product", "mentions_discount"), "לא ראיתי מבצעים או קופונים.", False),
    ],
    "hesitant": [
        (lambda f: "product" in f and not _g(f, "product", "mentions_reviews"), "בלי חוות דעת קשה לי להחליט.", False),
        (lambda f: not _g(f, "trust_links", "returns") and "product" in f and not _g(f, "product", "mentions_returns"),
         "לא ברור אם אפשר להחזיר. זה מה שעוצר אותי.", True),
        (lambda f: "product" in f and _g(f, "product", "large_images", default=0) < 3, "אין מספיק תמונות כדי לדמיין את המוצר.", False),
        (lambda f: not _g(f, "home", "html", "whatsapp_link") and not _g(f, "home", "html", "phones"),
         "הייתי רוצה לשאול שאלה מהירה בוואטסאפ — אין אפשרות.", False),
    ],
    "rushed": [
        (lambda f: _lcp(f) > 4000, "האתר איטי מדי. אין לי זמן לחכות.", True),
        (lambda f: _g(f, "mobile", "overlay") is not None and bool(_g(f, "mobile", "overlay")), "קופץ לי חלון מעצבן בכניסה.", False),
        (lambda f: _g(f, "mobile", "atc_above_fold") is False, "בטלפון צריך לגלול כדי למצוא את כפתור הקנייה.", False),
        (lambda f: "product" in f and _g(f, "add_to_cart", "found") is False, "איפה כפתור הקנייה?!", True),
        (lambda f: "product" in f and "cart" in f and not _journey_ok(f), "נתקעתי בדרך לקופה.", True),
        (lambda f: bool(_g(f, "checkout", "login_required")), "מבקשים ממני להירשם. אין לי כוח — יוצא.", True),
        (lambda f: _g(f, "checkout", "fields", default=0) > 16, "יותר מדי שדות למלא בקופה.", False),
        (lambda f: bool(_g(f, "mobile", "horizontal_overflow")), "האתר זז הצידה בטלפון, נראה שבור.", False),
    ],
    "researcher": [
        (lambda f: "product" in f and _g(f, "product", "description_chars", default=0) < 1500, "אין מספיק מידע על המוצר.", True),
        (lambda f: "product" in f and not _g(f, "product", "has_table"), "לא מצאתי מפרט טכני מסודר.", False),
        (lambda f: "product" in f and _g(f, "product", "large_images", default=0) < 3, "רוצה לראות את המוצר מכל הכיוונים.", False),
        (lambda f: not _g(f, "trust_links", "faq") and not _g(f, "product", "mentions_faq"), "אין שאלות נפוצות.", False),
        (lambda f: "product" in f and not _g(f, "product", "mentions_reviews"), "אין ביקורות שמספרות איך המוצר בשימוש אמיתי.", False),
    ],
}

POSITIVES: dict[str, list[tuple[Callable[[dict], bool], str]]] = {
    "skeptic": [(lambda f: bool(_g(f, "trust_links", "returns")), "יש מדיניות החזרות."),
                (lambda f: bool(_g(f, "product", "mentions_reviews")), "יש ביקורות."),
                (lambda f: bool(_g(f, "home", "html", "phones")) or bool(_g(f, "home", "html", "whatsapp_link")), "יש טלפון/וואטסאפ.")],
    "bargain": [(lambda f: bool(_g(f, "product", "price_visible")), "המחיר מוצג בבירור."),
                (lambda f: bool(_g(f, "product", "mentions_discount")), "יש מבצע/הנחה.")],
    "hesitant": [(lambda f: _g(f, "product", "large_images", default=0) >= 3, "יש מספיק תמונות."),
                 (lambda f: bool(_g(f, "product", "mentions_returns")), "כתוב שאפשר להחזיר.")],
    "rushed": [(lambda f: 0 < _lcp(f) <= 2500, "האתר נטען מהר."),
               (lambda f: _journey_ok(f) and not _g(f, "checkout", "login_required"), "הגעתי לקופה בלי להירשם.")],
    "researcher": [(lambda f: _g(f, "product", "description_chars", default=0) >= 1500, "יש תיאור מפורט."),
                   (lambda f: bool(_g(f, "product", "has_table")), "יש מפרט.")],
}


def simulate(facts: dict) -> list[dict]:
    results = []
    if not facts.get("home"):
        return results
    for key, checks in CHECKS.items():
        blockers, hard = [], False
        for cond, text, is_hard in checks:
            try:
                hit = cond(facts)
            except (TypeError, KeyError):
                hit = False
            if hit:
                blockers.append(text)
                hard = hard or is_hard
        positives = [text for cond, text in POSITIVES[key] if cond(facts)]
        verdict = "likely_leave" if hard or len(blockers) >= 3 else ("hesitant" if blockers else "likely_buy")
        results.append({"persona": key, "verdict": verdict, "blockers": blockers, "positives": positives})
    return results
