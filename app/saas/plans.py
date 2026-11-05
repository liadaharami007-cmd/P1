"""מסלולי מנוי ומכסות. המחירים יוגדרו בעתיד — כרגע רק המגבלות פעילות (ואכיפתן אמיתית)."""
from __future__ import annotations

PLANS: dict[str, dict] = {
    "free": {"name": "Free", "sites": 1, "audits_per_month": 10, "ai_analyses_per_month": 3,
             "concurrent_audits": 1, "members": 1, "pdf": True, "monitor": ["monthly"]},
    "pro": {"name": "Pro", "sites": 5, "audits_per_month": 100, "ai_analyses_per_month": 50,
            "concurrent_audits": 2, "members": 3, "pdf": True, "monitor": ["weekly", "monthly"]},
    "agency": {"name": "Agency", "sites": 25, "audits_per_month": 500, "ai_analyses_per_month": 300,
               "concurrent_audits": 3, "members": 10, "pdf": True, "monitor": ["daily", "weekly", "monthly"]},
}


class QuotaError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def plan_of(account: dict) -> dict:
    return PLANS.get(account.get("plan") or "free", PLANS["free"])


def check_can_start_audit(account: dict, usage: dict, is_new_site: bool) -> None:
    p = plan_of(account)
    if is_new_site and usage["sites"] >= p["sites"]:
        raise QuotaError(f"המסלול {p['name']} מאפשר עד {p['sites']} אתרים. שדרגו מסלול כדי להוסיף אתר.", "sites_limit")
    if usage["audits"] >= p["audits_per_month"]:
        raise QuotaError(f"ניצלתם את {p['audits_per_month']} הבדיקות של החודש במסלול {p['name']}.", "audits_limit")
    if usage["running"] >= p["concurrent_audits"]:
        raise QuotaError("כבר רצה בדיקה בחשבון. המתינו לסיומה.", "concurrency_limit")


def can_run_ai(account: dict, usage: dict) -> bool:
    return usage["ai_analyses"] < plan_of(account)["ai_analyses_per_month"]
