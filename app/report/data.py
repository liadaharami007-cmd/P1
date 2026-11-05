"""הרכבת נתוני הדוח המלא — משותף ל-API, לממשק ול-PDF."""
from __future__ import annotations

from ..audit import compare, scoring
from ..db import Database
from ..intelligence.personas_ai import PERSONAS as AI_PERSONAS

ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
IMPACT = {"high": 0, "medium": 1, "low": 2}


def rule_based_plan(findings: list[dict], limit: int = 7) -> list[dict]:
    """תוכנית פעולה דטרמיניסטית (כשאין ניתוח AI): לפי חומרה ואז השפעה משוערת."""
    measured = sorted([f for f in findings if f["source"] == "measured" and f["status"] not in ("done", "dismissed")],
                      key=lambda f: (ORDER[f["severity"]], IMPACT[f["impact"]]))
    return [{"priority": i + 1, "title": f["title"], "why_first": f["why_it_matters"], "related_refs": [f["rule_id"]],
             "effort": None, "expected_effect": None, "first_step": f["fix_steps"][0] if f["fix_steps"] else ""}
            for i, f in enumerate(measured[:limit])]


def assemble(db: Database, audit: dict) -> dict:
    aid = audit["id"]
    findings = db.get_findings(aid)
    runs = db.get_ai_runs(aid)
    latest = {}
    for r in runs:  # הריצה האחרונה מכל סוג
        latest[r["kind"]] = r
    analysis = latest.get("analysis")
    ai_personas = []
    for key, meta in AI_PERSONAS.items():
        r = latest.get(f"persona:{key}")
        if r:
            ai_personas.append({"key": key, "name": meta["name"], "status": r["status"], "result": r["result"], "error": r["error"]})
    prev = db.previous_done_audit(audit) if audit["status"] == "done" else None
    comp = compare.compare(prev, db.get_findings(prev["id"]), audit, findings) if prev else None
    ai_cost = round(sum(r["cost_usd"] for r in runs), 4)
    return {
        **{k: v for k, v in audit.items() if k != "facts"},
        "facts": {k: v for k, v in (audit.get("facts") or {}).items() if k != "page_excerpts"},
        "steps": db.get_steps(aid),
        "agents": db.get_agent_runs(aid),
        "findings": findings,
        "personas": db.get_personas(aid),
        "screenshots": [x for x in db.list_screenshots(aid) if not x["label"].startswith(("fix-", "agent:"))],
        "ai": {
            "status": audit.get("ai_status"),
            "analysis": analysis["result"] if analysis and analysis["status"] == "done" else None,
            "analysis_error": analysis["error"] if analysis and analysis["status"] == "failed" else None,
            "personas": ai_personas,
            "cost_usd": ai_cost,
            "tokens": {"input": sum(r["input_tokens"] for r in runs), "output": sum(r["output_tokens"] for r in runs)},
            "model": next((r["model"] for r in runs if r["model"]), None),
        },
        "action_plan_rules": rule_based_plan(findings),
        "comparison": comp,
        "methodology": scoring.methodology(),
    }
