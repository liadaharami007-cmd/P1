"""מקור אמת אחד: אילו חיבורים ויכולות קיימים ובאיזה מצב.

סטטוס יכולת:  works = עובד ונבדק · partial = בנוי חלקית (למשל עובד מבוסס כללים ומחכה למנוע מודל) · unavailable = לא זמין עדיין.
סטטוס חיבור:   connected = ממומש ומוגדר · not_configured = ממומש, חסרים מפתחות/הגדרות · not_built = עוד לא נבנה במערכת.
אין כאן שום יכולת שמוצגת כעובדת בלי קוד ובדיקות מאחוריה.
"""
from __future__ import annotations

import os

from ..intelligence import engines


def _env(*names: str) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


def integrations() -> list[dict]:
    eng = engines.status()
    by_id = {e["id"]: e for e in eng["engines"]}
    from ..saas import billing, recovery
    prov = billing.get_provider()
    items = [
        {"id": "claude", "name": "Claude API (Anthropic)", "category": "ai", "built": True,
         "connected": bool(by_id.get("anthropic", {}).get("available")), "missing": _env("ANTHROPIC_API_KEY"),
         "unlocks": "ניתוח AI של בדיקות, סיכום מנהלים, שיחה חופשית עם P1 CEO", "cost": "בתשלום לפי שימוש",
         "how": "console.anthropic.com → API Keys → להוסיף ANTHROPIC_API_KEY לקובץ ‎.env בשרת"},
        {"id": "ollama", "name": "Ollama (מודל מקומי)", "category": "ai", "built": True,
         "connected": bool(by_id.get("ollama", {}).get("available")), "missing": [] if by_id.get("ollama", {}).get("available") else ["שרת Ollama פעיל"],
         "unlocks": "ניתוח AI בלי עלות, על מחשב/שרת שלכם", "cost": "חינם",
         "how": "להתקין Ollama, להריץ ollama pull qwen2.5:7b-instruct, להגדיר P1_OLLAMA_URL"},
        {"id": "paddle", "name": "Paddle (תשלומים ומנויים)", "category": "billing", "built": True,
         "connected": prov.configured() and prov.name == "paddle", "missing": prov.missing() if prov.name == "paddle" else ["P1_BILLING_PROVIDER=paddle", *prov.missing()],
         "unlocks": "גביית מנוי חודשי/שנתי, חשבוניות, ניהול מנוי", "cost": "עמלה לכל עסקה",
         "how": "חשבון Paddle → Sandbox → מוצרים ומחירים → API key + Notification destination ל-/api/billing/webhook"},
        {"id": "email", "name": "שרת מייל (SMTP)", "category": "messaging", "built": True,
         "connected": recovery.email_configured(), "missing": _env("P1_SMTP_HOST", "P1_SMTP_FROM"),
         "unlocks": "שחזור סיסמה במייל (בהמשך: התראות ודוחות במייל)", "cost": "יש מסלולים חינמיים",
         "how": "ספק SMTP כלשהו (Brevo / Resend / Gmail) → P1_SMTP_HOST, P1_SMTP_USER, P1_SMTP_PASSWORD, P1_SMTP_FROM"},
    ]
    for iid, name, cat, unlocks in (
        ("shopify", "Shopify", "store", "נתוני מכירות והזמנות אמיתיים, ותיקונים באתר באישור (עם גיבוי ושחזור)"),
        ("wordpress", "WordPress / WooCommerce", "store", "נתוני חנות ותיקוני תוכן באישור"),
        ("ga4", "Google Analytics 4", "analytics", "כניסות, מקורות תנועה, משפך המרה — ניתוח נטישות על נתונים אמיתיים"),
        ("google_ads", "Google Ads", "ads", "ביצועי קמפיינים, זיהוי בזבוז תקציב"),
        ("meta_ads", "Meta Ads (פייסבוק/אינסטגרם)", "ads", "ביצועי מודעות וקריאייטיב"),
        ("whatsapp", "WhatsApp Business", "messaging", "התראות לבעל העסק, ובהסכמה — מענה ללקוחות"),
        ("crm", "CRM (HubSpot / Pipedrive / monday)", "crm", "ניהול לידים ומעקב אחרי פניות"),
    ):
        items.append({"id": iid, "name": name, "category": cat, "built": False, "connected": False, "missing": [],
                      "unlocks": unlocks, "cost": "—", "how": "החיבור עוד לא נבנה במערכת — בתוכנית העבודה"})
    for i in items:
        i["status"] = "connected" if i["built"] and i["connected"] else "not_configured" if i["built"] else "not_built"
    return items


def departments() -> list[dict]:
    """6 מחלקות תחת P1 CEO. הסטטוס של יכולות שתלויות במודל מתעדכן לפי המנוע הפעיל."""
    ai = engines.status()["active"] != "rules"
    W, P, U = "works", "partial", "unavailable"
    ai_dep = W if ai else P
    return [
        {"id": "web", "name": "אתרים והמרות", "capabilities": [
            ("בדיקת אתר בדפדפן אמיתי (מחשב + iPhone)", W, "#/audits", ""),
            ("5 לקוחות מדומים גולשים (ממהר, חשדן, מחיר, מבולבל, מובייל)", ai_dep, "#/audits", "מבוסס כללים; ניתוח מודל כשמנוע מחובר"),
            ("בדיקת טפסי לידים, WhatsApp וטלפון", W, "#/audits", "לא שולח טפסים"),
            ("בדיקת סל וקופה (עוצר לפני תשלום)", W, "#/audits", ""),
            ("Fix Studio: הצעת תיקון + לפני/אחרי", W, "#/fix", "תבניות; שכתוב AI כשמנוע מחובר"),
            ("אימות תיקון בבדיקה חוזרת", W, "#/approvals", ""),
            ("תיקון ישיר באתר מחובר", U, "#/integrations", "דורש חיבור Shopify/WordPress"),
            ("ניתוח נטישות על נתוני תנועה", U, "#/integrations", "דורש Google Analytics"),
            ("בניית אתר / דף נחיתה", U, None, "בתוכנית"),
            ("ניסויי A/B", U, None, "דורש אתר מחובר + נתוני תנועה"),
        ]},
        {"id": "marketing", "name": "שיווק ותוכן", "capabilities": [
            ("אסטרטגיה, מודעות, לוח תוכן ותסריטי וידאו (טיוטות)", W if ai else P, "#/studio?tab=marketing", "" if ai else "בנוי — מחכה למנוע AI (Gemini חינם)"),
            ("ניתוח ביצועי קמפיינים", U, "#/integrations", "דורש Google Ads / Meta Ads"),
            ("יצירת וידאו", U, None, "דורש שירות וידאו מחובר"),
        ]},
        {"id": "sales", "name": "מכירות ולקוחות", "capabilities": [
            ("בדיקה שערוצי הפנייה עובדים (טפסים/WhatsApp)", W, "#/audits", ""),
            ("ניהול לידים: רשימה, סטטוסים, פניות שמחכות", W, "#/leads", "הזנה ידנית; קליטה אוטומטית דורשת WhatsApp/CRM"),
            ("סיווג פנייה + טיוטת תשובה (לא נשלחת)", W if ai else P, "#/leads", "" if ai else "מחכה למנוע AI"),
            ("סוכן שירות לקוחות על מידע העסק (מסוף בדיקה)", W if ai else P, "#/studio?tab=support", "וידג'ט באתר — בתוכנית"),
            ("ניהול ביקורות ומוניטין", U, None, "בתוכנית"),
        ]},
        {"id": "finance", "name": "כספים ורווחיות", "capabilities": [
            ("מחשבון חיסכון (ROI) עם הנחות שקופות", W, "#/value", ""),
            ("ניתוח הכנסות, הוצאות ורווחיות", U, "#/integrations", "דורש נתוני מכירות/הנהלת חשבונות"),
        ]},
        {"id": "research", "name": "מחקר והזדמנויות", "capabilities": [
            ("בדיקת רעיון עסקי (רשימת מוכנות)", W, "#/ceo?intent=start", "מבוסס כללים: מה חסר בתוכנית"),
            ("ייעוץ עם P1 CEO על בסיס נתוני העסק", W if ai else P, "#/studio?tab=consult", "" if ai else "מחכה למנוע AI"),
            ("מחקר מתחרים ושוק", U, None, "דורש חיפוש באינטרנט — בתוכנית"),
        ]},
        {"id": "ops", "name": "אוטומציות וניהול", "capabilities": [
            ("3 הפעולות הבאות + מרכז אישורים", W, "#/", ""),
            ("שמירה קבועה ובדיקות מתוזמנות", W, "#/sites", ""),
            ("התראות במערכת", W, "#/", ""),
            ("דוח שבועי + ציר צמיחה", W, "#/timeline", ""),
            ("מצב סוכנות: לקוחות, דוחות, מה דורש טיפול", W, "#/agency", ""),
            ("התראות לוואטסאפ/מייל", U, "#/integrations", "דורש WhatsApp Business / SMTP"),
            ("צוות והרשאות לכמה משתמשים", U, None, "בתוכנית"),
        ]},
    ]


def departments_json() -> list[dict]:
    return [{**d, "capabilities": [{"name": n, "status": s, "link": l, "note": note} for n, s, l, note in d["capabilities"]]}
            for d in departments()]
