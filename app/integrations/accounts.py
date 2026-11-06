"""חיבורים לכל לקוח בנפרד: כל עסק מחבר את החשבונות שלו, הפרטים נשמרים מוצפנים (Fernet/AES), ונבדקים מול הספק.

- מפתח ההצפנה: P1_SECRET_KEY (בייצור — חובה, כסוד בשרת). בפיתוח: נוצר אוטומטית ב-data/secret.key (לא ב-git).
- סודות לעולם לא חוזרים ל-API/לממשק — רק "מוגדר" + 4 תווים אחרונים.
- קוד הטמעה לטפסים (embed): מפתח ציבורי לכל עסק; כל טופס באתר של הלקוח (כל פלטפורמה) נשלח ל-P1 → ליד ב-CRM.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from .. import config
from ..business import store
from ..db import Database
from . import connectors as cn

# ספק → שדות (שם, תווית, סוד?) + מה הוא פותח + איך משיגים
PROVIDERS: dict[str, dict] = {
    "wordpress": {"name": "WordPress", "fields": [("WP_URL", "כתובת האתר", False), ("WP_USER", "שם משתמש", False),
                                                    ("WP_APP_PASSWORD", "Application Password", True)],
                  "how": "בניהול WordPress: Users → Profile → Application Passwords → יצירה", "test": "wordpress_pages",
                  "unlocks": "קריאת עמודי האתר"},
    "woocommerce": {"name": "WooCommerce", "fields": [("WOO_URL", "כתובת החנות", False), ("WOO_KEY", "Consumer key", False),
                                                        ("WOO_SECRET", "Consumer secret", True)],
                    "how": "WooCommerce → Settings → Advanced → REST API → Add key (הרשאת Read)", "test": "woocommerce_summary",
                    "unlocks": "נתוני הזמנות ומוצרים אמיתיים"},
    "shopify": {"name": "Shopify", "fields": [("SHOPIFY_STORE_DOMAIN", "כתובת החנות (xxx.myshopify.com)", False),
                                              ("SHOPIFY_ADMIN_TOKEN", "Admin API token", True)],
                "how": "Shopify Admin → Settings → Apps → Develop apps → הרשאות read_orders, read_products", "test": "shopify_summary",
                "unlocks": "נתוני הזמנות ומוצרים אמיתיים"},
    "ga4": {"name": "Google Analytics 4", "fields": [("GA4_PROPERTY_ID", "Property ID (מספר)", False)],
            "how": "לוחצים 'התחברות עם Google' ואז מזינים Property ID (ב-GA4: Admin → Property settings)", "test": "ga4",
            "unlocks": "כניסות, מקורות תנועה ורכישות אמיתיים — לכל אתר", "oauth": "google"},
    "whatsapp": {"name": "WhatsApp Business", "fields": [("WHATSAPP_PHONE_NUMBER_ID", "Phone number ID", False),
                                                         ("WHATSAPP_TOKEN", "Access token (קבוע)", True)],
                 "how": "developers.facebook.com → App → WhatsApp → API Setup (מספר עסקי מאומת)", "test": None,
                 "unlocks": "שליחת תשובות ללקוחות באישור"},
}


def _fernet() -> Fernet:
    secret = os.environ.get("P1_SECRET_KEY")
    if not secret:
        path = config.DATA_DIR / "secret.key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_urlsafe(48))
            os.chmod(path, 0o600)
        secret = path.read_text().strip()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def save(db: Database, account_id: str, provider: str, values: dict[str, str]) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("ספק לא מוכר")
    fields = {f[0] for f in PROVIDERS[provider]["fields"]} | ({"GA4_REFRESH_TOKEN"} if provider == "ga4" else set())
    old = load(db, account_id, provider) or {}
    creds = {k: str(v).strip() for k, v in values.items() if k in fields and str(v or "").strip()}
    merged = {**old, **creds}  # שדה סודי שלא נשלח שוב — נשמר הערך הקודם
    missing = [f[1] for f in PROVIDERS[provider]["fields"] if not merged.get(f[0])]
    if PROVIDERS[provider].get("oauth") and not merged.get("GA4_REFRESH_TOKEN"):
        missing.append("התחברות עם Google")
    if missing:
        raise ValueError("חסר: " + ", ".join(missing))
    token = _fernet().encrypt(json.dumps(merged).encode()).decode()
    with db._conn() as c:
        c.execute("""INSERT INTO connections (account_id, provider, creds_enc, status, created_at, updated_at) VALUES (?,?,?, 'saved', ?, ?)
                     ON CONFLICT(account_id, provider) DO UPDATE SET creds_enc=excluded.creds_enc, status='saved', last_error=NULL, updated_at=excluded.updated_at""",
                  (account_id, provider, token, store.now(), store.now()))
    store.log(db, account_id, "connection_saved", f"נשמר חיבור: {PROVIDERS[provider]['name']}")
    return test(db, account_id, provider)


def load(db: Database, account_id: str, provider: str) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT creds_enc FROM connections WHERE account_id=? AND provider=?", (account_id, provider)).fetchone()
    if not r or not r["creds_enc"]:
        return None
    try:
        return json.loads(_fernet().decrypt(r["creds_enc"].encode()))
    except InvalidToken:
        return None  # המפתח הוחלף — צריך לחבר מחדש


def test(db: Database, account_id: str, provider: str) -> dict:
    cfg = load(db, account_id, provider)
    fn = PROVIDERS[provider]["test"]
    status, err, data = "connected", None, None
    if cfg is None:
        status, err = "error", "אין פרטי חיבור שמורים"
    elif fn:
        try:
            if fn == "ga4":
                from . import google
                data = google.ga4_summary(cfg=cfg)
            else:
                data = getattr(cn, fn)(cfg=cfg)
        except Exception as e:  # noqa: BLE001 — כל כשל נשמר ומוצג
            status, err = "error", str(e)[:300]
    else:
        status = "saved"  # אין בדיקת קריאה בטוחה (WhatsApp) — נבדק בשליחה הראשונה באישור
    with db._conn() as c:
        c.execute("UPDATE connections SET status=?, last_error=?, last_test_at=?, meta_json=? WHERE account_id=? AND provider=?",
                  (status, err, store.now(), json.dumps(data, ensure_ascii=False) if data is not None else None, account_id, provider))
    return get_public(db, account_id, provider)


def remove(db: Database, account_id: str, provider: str) -> bool:
    with db._conn() as c:
        return c.execute("DELETE FROM connections WHERE account_id=? AND provider=?", (account_id, provider)).rowcount > 0


def get_public(db: Database, account_id: str, provider: str) -> dict:
    """מה שמותר להציג: סטטוס, שגיאה, שדות לא-סודיים, וסיומת של סודות. אף פעם לא הסוד עצמו."""
    with db._conn() as c:
        r = c.execute("SELECT status, last_error, last_test_at, meta_json FROM connections WHERE account_id=? AND provider=?",
                      (account_id, provider)).fetchone()
    p = PROVIDERS[provider]
    cfg = load(db, account_id, provider) or {}
    fields = [{"key": k, "label": lbl, "secret": sec, "value": None if sec else cfg.get(k),
               "hint": ("••••" + cfg[k][-4:]) if sec and cfg.get(k) else None} for k, lbl, sec in p["fields"]]
    oauth = None
    if p.get("oauth") == "google":
        from . import google
        oauth = {"ready": google.configured(), "linked": bool(cfg.get("GA4_REFRESH_TOKEN")),
                 "missing": None if google.configured() else "בעל P1 צריך להגדיר פעם אחת P1_GOOGLE_CLIENT_ID + P1_GOOGLE_CLIENT_SECRET"}
    return {"provider": provider, "name": p["name"], "how": p["how"], "unlocks": p["unlocks"], "fields": fields, "oauth": oauth,
            "status": r["status"] if r else "not_connected", "error": r["last_error"] if r else None,
            "tested_at": r["last_test_at"] if r else None, "data": json.loads(r["meta_json"]) if r and r["meta_json"] else None}


def overview(db: Database, account_id: str) -> list[dict]:
    return [get_public(db, account_id, p) for p in PROVIDERS]


# ---------------------------------------------------------------- קוד הטמעה לטפסים (עובד על כל אתר)
def embed_key(db: Database, account_id: str, rotate: bool = False) -> str:
    with db._conn() as c:
        r = c.execute("SELECT embed_key FROM embed_keys WHERE account_id=?", (account_id,)).fetchone()
        if r and not rotate:
            return r["embed_key"]
        key = "p1_" + secrets.token_urlsafe(18)
        c.execute("INSERT INTO embed_keys (account_id, embed_key, created_at) VALUES (?,?,?) "
                  "ON CONFLICT(account_id) DO UPDATE SET embed_key=excluded.embed_key, created_at=excluded.created_at", (account_id, key, store.now()))
    return key


def account_for_key(db: Database, key: str) -> str | None:
    with db._conn() as c:
        r = c.execute("SELECT account_id FROM embed_keys WHERE embed_key=?", (key,)).fetchone()
    return r["account_id"] if r else None


def embed_snippet(key: str) -> str:
    return f'<script src="{config.PUBLIC_URL}/embed.js" data-p1-key="{key}" defer></script>'
