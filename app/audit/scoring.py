"""חישוב ציון בריאות — רק מממצאים שנמדדו בפועל (לא מסימולציות ולא מהשערות)."""
from __future__ import annotations

from .rules import CATEGORIES

PENALTY = {"critical": 30, "high": 15, "medium": 7, "low": 3}
WEIGHTS = {"journey": 30, "trust": 20, "speed": 15, "mobile": 15, "ux": 10, "seo": 10}


def tested_categories(facts: dict, steps: list[dict]) -> set[str]:
    """אילו קטגוריות באמת נבדקו. קטגוריה שלא נבדקה לא מקבלת ציון (ולא 100 מזויף)."""
    if not facts.get("home"):
        return {"journey"}  # האתר לא נטען — זה כשל מסע רכישה
    cats = {"trust", "speed", "ux", "seo"}
    if facts.get("mobile"):
        cats.add("mobile")
    statuses = {s["key"]: s["status"] for s in steps}
    if statuses.get("product") in ("passed", "failed") or facts.get("product"):
        cats.add("journey")
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
    scored = {c: s for c, s in cat_scores.items() if s is not None}
    if not scored:
        return None, cat_scores
    total_w = sum(WEIGHTS[c] for c in scored)
    overall = round(sum(s * WEIGHTS[c] for c, s in scored.items()) / total_w)
    # בעיה קריטית במסע הרכישה מגבילה את הציון — אתר שאי אפשר לקנות בו אינו "בריא"
    if any(f["severity"] == "critical" for f in findings):
        overall = min(overall, 49)
    return overall, cat_scores
