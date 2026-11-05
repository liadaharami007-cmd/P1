"""חישוב ציונים — שיטה מוגדרת ושקופה.

כללים:
1. רק ממצאים שנבדקו בפועל (source="measured") משפיעים על הציון. סימולציות והשערות AI לא.
2. כל חלק בדוח מתחיל ב-100. כל ממצא מוריד נקודות לפי חומרתו (PENALTY). מינימום 0.
3. הציון הכללי = ממוצע משוקלל (WEIGHTS) של החלקים שנבדקו בפועל בלבד.
4. חלק שלא נבדק (למשל קופה, כשלא נמצא מוצר) מקבל null — לא 100.
5. אם יש ממצא קריטי — הציון הכללי מוגבל ל-CRITICAL_CAP (אתר שאי אפשר לקנות בו אינו "בריא").
"""
from __future__ import annotations

from .rules import CATEGORIES

PENALTY = {"critical": 30, "high": 15, "medium": 7, "low": 3}
WEIGHTS = {"conversion": 25, "checkout": 25, "trust": 20, "ux_mobile": 15, "technical": 15}
CRITICAL_CAP = 49
VERSION = "2026.11-1"


def methodology() -> dict:
    return {"version": VERSION, "penalty": PENALTY, "weights": WEIGHTS, "critical_cap": CRITICAL_CAP,
            "categories": CATEGORIES, "counts_sources": ["measured"]}


def tested_categories(facts: dict, steps: list[dict]) -> set[str]:
    """אילו חלקים באמת נבדקו."""
    if not facts.get("home"):
        return {"technical"}  # האתר לא נטען — כשל טכני
    cats = {"conversion", "trust", "technical"}
    if facts.get("mobile"):
        cats.add("ux_mobile")
    if facts.get("product"):  # מסלול הרכישה נבדק רק אם נמצא מוצר
        cats.add("checkout")
    return cats


def score(findings: list[dict], facts: dict, steps: list[dict]) -> tuple[int | None, dict]:
    tested = tested_categories(facts, steps)
    cat_scores: dict[str, int | None] = {}
    for cat in CATEGORIES:
        if cat not in tested:
            cat_scores[cat] = None
            continue
        pen = sum(PENALTY[f["severity"]] for f in findings if f["category"] == cat and f["source"] == "measured")
        cat_scores[cat] = max(0, 100 - pen)
    scored = {c: v for c, v in cat_scores.items() if v is not None}
    if not scored:
        return None, cat_scores
    total_w = sum(WEIGHTS[c] for c in scored)
    overall = round(sum(v * WEIGHTS[c] for c, v in scored.items()) / total_w)
    if any(f["severity"] == "critical" and f["source"] == "measured" for f in findings):
        overall = min(overall, CRITICAL_CAP)
    return overall, cat_scores
