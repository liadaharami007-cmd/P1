"""השוואת Before/After בין שתי בדיקות של אותו אתר — חישוב דטרמיניסטי מהנתונים בלבד."""
from __future__ import annotations

from .rules import CATEGORIES


def compare(before: dict, before_findings: list[dict], after: dict, after_findings: list[dict]) -> dict:
    def measured(fs):
        return {f["rule_id"]: f for f in fs if f["source"] == "measured"}

    b, a = measured(before_findings), measured(after_findings)
    bc, ac = before.get("category_scores") or {}, after.get("category_scores") or {}
    categories = {}
    for c in CATEGORIES:
        bv, av = bc.get(c), ac.get(c)
        categories[c] = {"before": bv, "after": av, "delta": (av - bv) if bv is not None and av is not None else None}
    pick = lambda f: {"rule_id": f["rule_id"], "title": f["title"], "severity": f["severity"], "category": f["category"]}
    return {
        "before": {"id": before["id"], "score": before.get("score"), "at": before.get("finished_at")},
        "after": {"id": after["id"], "score": after.get("score"), "at": after.get("finished_at")},
        "score_delta": (after["score"] - before["score"]) if before.get("score") is not None and after.get("score") is not None else None,
        "categories": categories,
        "fixed": [pick(f) for k, f in b.items() if k not in a],
        "new": [pick(f) for k, f in a.items() if k not in b],
        "persisting": [pick(f) for k, f in a.items() if k in b],
    }
