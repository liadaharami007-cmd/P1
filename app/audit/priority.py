"""סדר עדיפויות שקוף: מה לעשות קודם.

ציון עדיפות = משקל חומרה × מכפיל השפעה משוערת ÷ מאמץ משוער לפי סוג התיקון.
זה כלי מיון, לא תחזית: הוא לא מבטיח שיפור מכירות ולא מכיל אחוזים מומצאים.
"""
from __future__ import annotations

SEV = {"critical": 100, "high": 60, "medium": 30, "low": 10}
IMP = {"high": 1.5, "medium": 1.0, "low": 0.6}
EFFORT = {"content": 1.0, "design": 1.0, "ux": 1.2, "flow": 1.5, "technical": 1.3}


def rank(findings: list[dict], kind_of: dict[str, str]) -> list[tuple[str, int]]:
    """מחזיר [(finding_id, priority 1..N)] — רק לממצאים שנבדקו בפועל; השערות AI אחריהם."""
    def score(f):
        s = SEV[f["severity"]] * IMP[f["impact"]] / EFFORT.get(kind_of.get(f["id"], "ux"), 1.2)
        return s * (0.5 if f["source"] == "ai" else 1.0)
    ordered = sorted(findings, key=score, reverse=True)
    return [(f["id"], i + 1) for i, f in enumerate(ordered)]
