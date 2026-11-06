"""P1 Business Brain — הפרופיל העסקי של כל חשבון.

המידע מגיע רק ממה שבעל העסק הזין (source=user) או ממה שנמדד (בדיקות אתר). שום שדה לא "מנוחש".
"""
from __future__ import annotations

from typing import Any

BUSINESS_TYPES = ("ecommerce", "services", "local", "leads", "other")
GOALS = ("more_sales", "more_leads", "fix_site", "save_time", "reduce_ad_waste", "better_reputation")
CHANNELS = ("google_ads", "meta_ads", "seo", "social_organic", "whatsapp", "email", "referrals", "offline")

# שדות: (סוג, אורך מקסימלי, חובה לשלמות הפרופיל)
FIELDS: dict[str, tuple[str, int, bool]] = {
    "business_name": ("str", 120, True),
    "business_type": ("enum", 20, True),
    "industry": ("str", 120, True),
    "website": ("str", 300, True),
    "offer": ("text", 1500, True),            # מוצרים/שירותים עיקריים
    "audience": ("text", 1000, True),         # קהל יעד
    "goals": ("list", 6, True),
    "usps": ("text", 1000, False),            # יתרונות תחרותיים
    "competitors": ("text", 1000, False),
    "price_range": ("str", 200, False),
    "channels": ("list", 8, False),
    "monthly_ad_budget": ("num", 0, False),   # ₪ לחודש (לא חובה)
    "avg_order_value": ("num", 0, False),     # ₪ (לא חובה)
    "monthly_leads_or_orders": ("num", 0, False),
    "hours_on_site_per_month": ("num", 0, False),  # שעות עבודה ידנית על האתר — בסיס לחישוב חיסכון
    "hourly_value": ("num", 0, False),
    "notes": ("text", 2000, False),
}
ENUMS = {"business_type": BUSINESS_TYPES}
LISTS = {"goals": GOALS, "channels": CHANNELS}


def clean(raw: dict[str, Any]) -> dict:
    """מאמת ומנקה קלט. שדות לא מוכרים נזרקים; ערכים לא חוקיים מעלים ValueError."""
    out: dict[str, Any] = {}
    for key, (kind, limit, _req) in FIELDS.items():
        if key not in raw or raw[key] in (None, ""):
            continue
        v = raw[key]
        if kind in ("str", "text"):
            v = str(v).strip()
            if len(v) > limit:
                raise ValueError(f"השדה {key} ארוך מדי (עד {limit} תווים)")
            if v:
                out[key] = v
        elif kind == "enum":
            if v not in ENUMS[key]:
                raise ValueError(f"ערך לא חוקי בשדה {key}")
            out[key] = v
        elif kind == "list":
            items = [x for x in (v if isinstance(v, list) else [v]) if x in LISTS[key]]
            if items:
                out[key] = list(dict.fromkeys(items))
        elif kind == "num":
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"השדה {key} חייב להיות מספר") from None
            if n < 0 or n > 1e9:
                raise ValueError(f"ערך לא סביר בשדה {key}")
            out[key] = round(n, 2)
    return out


def completeness(data: dict | None) -> dict:
    data = data or {}
    required = [k for k, (_, _, req) in FIELDS.items() if req]
    missing = [k for k in required if not data.get(k)]
    optional = [k for k, (_, _, req) in FIELDS.items() if not req]
    filled_opt = sum(1 for k in optional if data.get(k) not in (None, "", []))
    pct = round(100 * (len(required) - len(missing)) / len(required) * 0.8 + 20 * filled_opt / len(optional))
    return {"percent": pct, "missing_required": missing, "ready": not missing}
