"""חבילת ראיות לניתוח AI — רק מה שנמדד בפועל בבדיקה."""
from __future__ import annotations

import base64
import json
from pathlib import Path

KEY_SHOTS = [("home", "desktop"), ("product", "desktop"), ("after-add-to-cart", "desktop"), ("cart", "desktop"),
             ("checkout", "desktop"), ("home", "mobile"), ("product", "mobile")]


def _trim_facts(facts: dict) -> dict:
    """עובדות מתומצתות: בלי רשימות ארוכות ובלי טקסט מלא."""
    f = json.loads(json.dumps(facts or {}, ensure_ascii=False))
    f.pop("page_excerpts", None)
    for k in ("unreachable_resources", "blocked_hosts"):
        if k in f:
            f[k] = len(f[k])
    home = f.get("home") or {}
    home.pop("html_issues", None)
    if "html" in home:
        home["html"].pop("cta_texts", None)
    return f


def build(audit: dict, steps: list[dict], findings: list[dict], screenshots: list[dict],
          comparison: dict | None, max_images: int = 6, devices: tuple[str, ...] = ("desktop", "mobile")) -> list[dict]:
    """בונה את תוכן ההודעה ל-Claude: טקסט מובנה + צילומי מסך מסומנים."""
    measured = [{"id": x["rule_id"], "title": x["title"], "severity": x["severity"], "category": x["category"],
                 "detail": x["detail"][:300]} for x in findings if x["source"] == "measured"]
    excerpts = (audit.get("facts") or {}).get("page_excerpts", {})
    payload = {
        "site": audit.get("site_url"), "start_url": audit.get("start_url"),
        "score": audit.get("score"), "category_scores": audit.get("category_scores"),
        "journey_steps": [{"step": s["key"], "title": s["title"], "status": s["status"], "detail": s["detail"],
                           "url": s.get("page_url")} for s in steps],
        "measured_findings": measured,
        "facts": _trim_facts(audit.get("facts") or {}),
        "page_text_excerpts": excerpts,
        "comparison_with_previous_audit": comparison,
    }
    content: list[dict] = [{"type": "text", "text": "<audit_evidence>\n" + json.dumps(payload, ensure_ascii=False) + "\n</audit_evidence>"}]
    by_key = {(s["label"], s["device"]): s for s in screenshots}
    added = 0
    for label, device in KEY_SHOTS:
        if device not in devices or added >= max_images:
            continue
        shot = by_key.get((label, device))
        if not shot or not shot.get("path") or not Path(shot["path"]).exists():
            continue
        data = base64.standard_b64encode(Path(shot["path"]).read_bytes()).decode()
        content.append({"type": "text", "text": f"צילום מסך [{label}/{device}] מתוך {shot.get('page_url')}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        added += 1
    return content
