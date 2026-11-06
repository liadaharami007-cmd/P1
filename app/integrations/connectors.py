"""חיבורים רשמיים בלבד (API של הספק). כל חיבור: configured() לפי משתני סביבה, ובדיקת חיבור אמיתית.

- WhatsApp Business Cloud API (Meta): שליחת הודעה ללקוח — רק דרך פעולה מאושרת במרכז האישורים;
  קליטת הודעות נכנסות (webhook חתום) → ליד ב-CRM. לפי כללי WhatsApp: הודעה חופשית מותרת רק תוך 24 שעות מהודעת הלקוח;
  מחוץ לחלון הזה נדרשת תבנית מאושרת ע"י Meta.
- Shopify Admin API (טוקן של custom app, קריאה בלבד): נתוני חנות והזמנות → store_data.
- WordPress REST API (Application Password): קריאת עמודים.
- מייל (SMTP): שליחת תשובה ללקוח — רק באישור.
שום חיבור לא מוצג כ"מחובר" בלי משתני סביבה + בדיקה מוצלחת.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import httpx

GRAPH = "https://graph.facebook.com/v21.0"


def env(*names: str) -> list[str]:
    return [n for n in names if not os.environ.get(n)]


# ---------------------------------------------------------------- WhatsApp
WA_VARS = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "P1_WHATSAPP_ACCOUNT_ID")


def wa_missing() -> list[str]:
    return env(*WA_VARS)


def wa_send_text(to: str, body: str, transport: httpx.BaseTransport | None = None) -> dict:
    if wa_missing():
        raise RuntimeError("WhatsApp לא מחובר: חסר " + ", ".join(wa_missing()))
    to = "".join(ch for ch in to if ch.isdigit())
    if to.startswith("0"):
        to = "972" + to[1:]
    with httpx.Client(timeout=20, transport=transport) as c:
        r = c.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
                   headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
                   json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4000]}})
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp החזיר {r.status_code}: {r.text[:200]}")
    return {"to": to, "message_id": (r.json().get("messages") or [{}])[0].get("id")}


def wa_verify_signature(body: bytes, header: str | None) -> bool:
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not secret or not header or not header.startswith("sha256="):
        return False
    return hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), header[7:])


def wa_parse_inbound(payload: dict) -> list[dict]:
    out = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in v.get("contacts", [])}
            for m in v.get("messages", []):
                text = (m.get("text") or {}).get("body") or f"[{m.get('type')}]"
                out.append({"from": m.get("from"), "name": names.get(m.get("from")) or m.get("from"), "text": text, "id": m.get("id")})
    return out


# ---------------------------------------------------------------- Shopify (קריאה בלבד)
SHOPIFY_VARS = ("SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_TOKEN")


def shopify_summary(transport: httpx.BaseTransport | None = None) -> dict:
    if env(*SHOPIFY_VARS):
        raise RuntimeError("Shopify לא מחובר: חסר " + ", ".join(env(*SHOPIFY_VARS)))
    base = f"https://{os.environ['SHOPIFY_STORE_DOMAIN']}/admin/api/2025-01"
    h = {"X-Shopify-Access-Token": os.environ["SHOPIFY_ADMIN_TOKEN"]}
    with httpx.Client(timeout=20, transport=transport, headers=h) as c:
        shop = c.get(f"{base}/shop.json")
        orders = c.get(f"{base}/orders/count.json", params={"status": "any"})
        products = c.get(f"{base}/products/count.json")
    for r in (shop, orders, products):
        if r.status_code >= 300:
            raise RuntimeError(f"Shopify החזיר {r.status_code}")
    return {"source": "store_data", "shop": shop.json()["shop"].get("name"), "orders": orders.json().get("count"),
            "products": products.json().get("count")}


# ---------------------------------------------------------------- WordPress (קריאה בלבד)
WP_VARS = ("WP_URL", "WP_USER", "WP_APP_PASSWORD")


def wordpress_pages(transport: httpx.BaseTransport | None = None) -> list[dict]:
    if env(*WP_VARS):
        raise RuntimeError("WordPress לא מחובר: חסר " + ", ".join(env(*WP_VARS)))
    with httpx.Client(timeout=20, transport=transport, auth=(os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])) as c:
        r = c.get(os.environ["WP_URL"].rstrip("/") + "/wp-json/wp/v2/pages", params={"per_page": 20, "_fields": "id,title,link,modified"})
    if r.status_code >= 300:
        raise RuntimeError(f"WordPress החזיר {r.status_code}")
    return [{"id": p["id"], "title": (p.get("title") or {}).get("rendered"), "link": p.get("link"), "modified": p.get("modified")} for p in r.json()]


def status() -> dict:
    from ..saas import recovery
    return {"whatsapp": not wa_missing(), "shopify": not env(*SHOPIFY_VARS), "wordpress": not env(*WP_VARS), "email": recovery.email_configured()}
