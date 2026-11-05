"""Fix Studio — קטלוג תיקונים.

לכל ממצא נבנית הצעת תיקון מוחשית: מה לשנות (טקסט / מבנה / עיצוב / קוד), ואילו פעולות להחיל
בעותק מבודד של העמוד כדי לייצר תצוגה מקדימה אמיתית (sandbox.py).

מנוע: "templates" — תבניות מקצועיות של CRO שמתמלאות בנתונים שנמצאו בפועל בעמוד (שם מוצר, יתרונות
שכתובים באתר, מחיר). כשמידע חסר — מופיע מציין מקום מסומן [להשלמה] ולא ערך מומצא.
כשמנוע שפה מחובר (Claude / Ollama) אפשר להוסיף שכתוב חכם — ראו app/llm.
"""
from __future__ import annotations

import html
import re
from typing import Any, Callable

PH = "[להשלמה]"  # מציין מקום: מידע שבעל העסק צריך למלא — לעולם לא ממציאים

KIND_OF_CATEGORY = {"conversion": "content", "checkout": "flow", "trust": "content", "ux_mobile": "ux", "technical": "technical"}

# יתרונות נפוצים שאפשר לזהות בטקסט האמיתי של האתר
USP_PATTERNS = [
    (r"משלוח\s+חינם(?:\s+(?:בהזמנה\s+|בקנייה\s+)?מעל\s+(?:₪\s?)?\d[\d,]*(?:\s?(?:ש\"ח|₪))?)?", None),
    (r"free\s+shipping(?:\s+(?:on\s+orders\s+)?over\s+[$€£₪]?\d[\d,]*)?", None),
    (r"החזר[הות]*\s+(?:\S+\s+){0,2}?(?:עד\s+)?\d+\s+(?:יום|ימים)", None), (r"\d+[- ]day\s+returns?", None),
    (r"אחריות\s+(?:ל|של\s+)?(?:\d+\s+)?(?:שנה|שנתיים|שנים|חודשים)", None), (r"\d+[- ]year\s+warranty", None),
    (r"(?:תוצרת|מיוצר|תפור)\w*\s+(?:ב)?ישראל", None), (r"made\s+in\s+\w+", None),
    (r"כותנה\s+אורגנית|organic\s+cotton|טבעי\s+100%|100%\s+\w+", None),
    (r"משלוח\s+(?:מהיר|אקספרס|תוך\s+\d+[-–]?\d*\s+ימי?\s*עסקים?)", None), (r"delivery\s+in\s+\d+[-–]?\d*\s+days", None),
    (r"\d[\d,]*\+?\s+(?:לקוחות|ביקורות|customers|reviews)", None),
]


def find_usps(texts: list[str], limit: int = 3) -> list[str]:
    found: list[str] = []
    blob = " ".join(t for t in texts if t)
    for pat, _ in USP_PATTERNS:
        m = re.search(pat, blob, re.I)
        if m:
            v = re.sub(r"\s+", " ", m.group(0)).strip(" .,-")
            if v and v.lower() not in {x.lower() for x in found}:
                found.append(v)
        if len(found) >= limit:
            break
    return found


def _ctx(facts: dict) -> dict:
    """נתונים אמיתיים מהבדיקה שמשמשים למילוי התבניות."""
    ex = facts.get("page_excerpts") or {}
    prod = facts.get("product") or {}
    home = facts.get("home") or {}
    name = (prod.get("h1") or prod.get("jsonld_name") or "").strip()
    site_title = ((home.get("html") or {}).get("title") or "").split("|")[0].split("-")[0].strip()
    price = prod.get("jsonld_price") or prod.get("og_price") or prod.get("itemprop_price")
    return {"product": name, "site": site_title, "price": price, "usps": find_usps([ex.get("product", ""), ex.get("home", "")]),
            "returns_days": _first(r"(\d+)\s*(?:יום|ימים|days)", ex.get("product", "") + " " + ex.get("home", "")),
            "free_ship_from": _first(r"משלוח\s+חינם\s+(?:בהזמנה\s+)?מעל\s+(?:₪\s*)?(\d[\d,]*)", ex.get("product", "") + " " + ex.get("home", "")),
            "phones": (home.get("html") or {}).get("phones") or []}


def _first(pat: str, text: str) -> str | None:
    m = re.search(pat, text or "", re.I)
    return m.group(1) if m else None


def _e(s: Any) -> str:
    return html.escape(str(s or ""))


# ---------------------------------------------------------------- רכיבי HTML לתצוגה המקדימה
def trust_strip_html(c: dict, shipping: bool = True, returns: bool = True) -> str:
    items = []
    if shipping:
        items.append(f"🚚 משלוח חינם מעל ₪{_e(c['free_ship_from'])}" if c["free_ship_from"] else f"🚚 משלוח: {PH} (עלות וזמן הגעה)")
    if returns:
        items.append(f"↩️ החזרה עד {_e(c['returns_days'])} ימים" if c["returns_days"] else f"↩️ החזרה עד {PH} ימים")
    items.append("🔒 תשלום מאובטח")
    lis = "".join(f'<li style="display:flex;gap:6px;align-items:center">{i}</li>' for i in items)
    return (f'<ul data-p1-fix style="list-style:none;margin:12px 0;padding:12px 14px;border:1px solid #d7e8dc;'
            f'background:#f3faf5;border-radius:10px;display:flex;flex-direction:column;gap:6px;font:500 14px/1.4 system-ui,Arial;color:#14532d">{lis}</ul>')


def footer_links_html(missing: list[str]) -> str:
    names = {"returns": "החזרות וביטול עסקה", "shipping": "משלוחים", "privacy": "מדיניות פרטיות", "terms": "תקנון", "contact": "צור קשר"}
    links = " · ".join(f'<a href="#" style="color:#1d4ed8">{names[m]}</a>' for m in missing if m in names)
    return (f'<div data-p1-fix style="margin:24px auto;padding:14px 16px;border-top:2px solid #e5e7eb;font:500 14px system-ui,Arial;'
            f'text-align:center;background:#fafafa">{links}</div>')


def reviews_block_html(c: dict) -> str:
    return (f'<section data-p1-fix style="margin:16px 0;padding:14px;border:1px dashed #c7c7d1;border-radius:10px;font:14px system-ui,Arial;background:#fff">'
            f'<div style="font-weight:700;margin-bottom:6px">★★★★★ {PH} ({PH} ביקורות)</div>'
            f'<div style="color:#555">“{PH} — ציטוט של לקוח אמיתי”</div>'
            f'<div style="color:#888;font-size:12px;margin-top:6px">מקום לביקורות אמיתיות בלבד (למשל Judge.me / Yotpo)</div></section>')


def headline_variants(c: dict) -> list[str]:
    name = c["product"] or c["site"] or PH
    u = c["usps"]
    v = []
    if u:
        v.append(f"{name} — {u[0]}" + (f" · {u[1]}" if len(u) > 1 else ""))
    v.append(f"{name}: {PH} (התועלת המרכזית ללקוח)")
    v.append(f"{PH} (התוצאה שהלקוח מקבל) — עם {name}")
    return v[:3]


# ---------------------------------------------------------------- מחוללי תיקון
Gen = Callable[[dict, dict], dict]


def _base(f: dict, kind: str, summary: str, steps: list[str], **kw) -> dict:
    out = {"kind": kind, "summary": summary, "steps": steps, "copy": [], "structure": [], "design": [], "code": None,
           "preview": {"supported": False}, "engine": "templates"}
    out.update(kw)
    return out


def _pv(device: str, page: str, mark: str | None, ops: list[dict]) -> dict:
    return {"supported": True, "device": device, "page": page, "mark": mark, "ops": ops}


def fix_trust_pdp(f, c):
    ship = f["rule_id"] == "no_shipping_info_pdp"
    return _base(f, "content", "להוסיף ליד כפתור הקנייה פס אמון קצר: משלוח, החזרות ותשלום מאובטח.",
                 ["להוסיף מתחת לכפתור 'הוספה לסל' 2–3 שורות קצרות", "לנסח מספרים מדויקים (ימים, סכומים) — לא 'מהיר' או 'קל'",
                  "לקשר כל שורה לעמוד המדיניות המלא"],
                 copy=[{"label": "פס אמון", "text": " · ".join(re.sub("<[^>]+>", "", x) for x in re.findall(r"<li[^>]*>(.*?)</li>", trust_strip_html(c, ship, True)))}],
                 design=["רקע ירוק עדין + אייקונים — מושך עין בלי להתחרות בכפתור", "מיקום: מתחת לכפתור הקנייה, באותו רוחב"],
                 preview=_pv("desktop", "product", "atc", [{"op": "insert_after", "target": "atc", "html": trust_strip_html(c, True, True)}]))


def fix_mobile_atc(f, c):
    label = "הוספה לסל"
    price = f" · ₪{_e(c['price'])}" if c["price"] else ""
    bar = (f'<div data-p1-fix style="position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:#fff;'
           f'box-shadow:0 -4px 16px rgba(0,0,0,.12);padding:10px 12px;display:flex;gap:10px;align-items:center;font:600 15px system-ui,Arial">'
           f'<span style="flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">{_e(c["product"] or "")}{price}</span>'
           f'<button style="background:#111;color:#fff;border:0;border-radius:10px;padding:12px 18px;font:700 15px system-ui,Arial">{label}</button></div>')
    return _base(f, "ux", "כפתור 'הוספה לסל' דביק בתחתית המסך בטלפון — זמין תמיד בלי לגלול.",
                 ["להוסיף פס תחתון קבוע במובייל עם שם המוצר, מחיר וכפתור", "הכפתור מפעיל את אותו טופס הוספה לסל", "להסתיר את הפס כשהכפתור המקורי נראה במסך"],
                 design=["גובה ~64px, צל עדין למעלה", "כפתור בניגודיות גבוהה, רוחב אגודל (44px+)"],
                 code={"lang": "css", "snippet": "@media (max-width: 768px) {\n  .p1-sticky-atc { position: fixed; inset-inline: 0; bottom: 0; z-index: 50; }\n}"},
                 preview=_pv("mobile", "product", "atc", [{"op": "append_body", "html": bar}]))


def fix_popup(f, c):
    mobile = f["rule_id"] == "mobile_popup"
    bar = ('<div data-p1-fix style="position:fixed;bottom:0;left:0;right:0;z-index:2147483646;background:#111;color:#fff;'
           'padding:10px 14px;font:500 14px system-ui,Arial;text-align:center">🎁 10% הנחה להצטרפות לניוזלטר — <u>להרשמה</u> ✕</div>')
    return _base(f, "ux", "להחליף את החלון שמכסה את המסך בפס קטן שלא מסתיר את המוצר, ולהציג אותו רק אחרי גלילה או זמן שהייה.",
                 ["לבטל הצגה מיידית בכניסה", "להציג אחרי 30 שניות / 50% גלילה / כוונת יציאה", "בטלפון: פס תחתון במקום חלון מלא"],
                 design=["פס תחתון בגובה ~44px עם כפתור סגירה ברור"],
                 preview=_pv("mobile" if mobile else "desktop", "home", "overlay", [{"op": "hide_overlays"}, {"op": "append_body", "html": bar}]))


def fix_headline(f, c):
    v = headline_variants(c)
    sub = (f"{c['usps'][0]}" if c["usps"] else PH) + " · " + (f"{c['usps'][1]}" if len(c["usps"]) > 1 else "החזרה קלה " + PH)
    block = (f'<div data-p1-fix style="font:400 16px/1.5 system-ui,Arial;color:#333;margin:6px 0 14px">{_e(sub)}</div>')
    return _base(f, "content", "כותרת שאומרת מה המוצר ומה הלקוח מרוויח, ומתחתיה שורת יתרונות קצרה.",
                 ["כותרת = מה זה + התועלת המרכזית", "שורת משנה עם 2 יתרונות קונקרטיים מהאתר", "לבדוק שהכותרת נראית במסך הראשון בטלפון"],
                 copy=[{"label": f"כותרת — גרסה {i + 1}", "text": x} for i, x in enumerate(v)] + [{"label": "שורת משנה", "text": sub}],
                 structure=["כותרת (H1): מוצר + תועלת", "שורת משנה: 2 יתרונות", "מחיר + כפתור קנייה", "פס אמון"],
                 preview=_pv("desktop", "product" if c["product"] else "home", "h1",
                             [{"op": "set_text", "target": "h1", "text": v[0]}, {"op": "insert_after", "target": "h1", "html": block}]))


def fix_reviews(f, c):
    return _base(f, "content", "להציג דירוג וביקורות אמיתיות ליד המחיר ובלוק ביקורות בעמוד המוצר.",
                 ["להתקין מערכת ביקורות", "לשלוח ללקוחות קודמים בקשה לביקורת אחרי מסירה", "להציג דירוג ממוצע ליד שם המוצר"],
                 structure=["שורת כוכבים ליד הכותרת", "3 ביקורות בולטות מתחת לתיאור", "קישור לכל הביקורות"],
                 design=["לעולם לא להציג ביקורות לא אמיתיות — בתצוגה מופיעים מקומות ריקים בלבד"],
                 preview=_pv("desktop", "product", "atc", [{"op": "insert_after", "target": "atc", "html": reviews_block_html(c)}]))


def fix_trust_links(f, c):
    key = f["rule_id"].replace("no_", "").replace("_policy", "").replace("_page", "")
    return _base(f, "content", "ליצור עמוד מדיניות ברור ולקשר אליו מהפוטר ומעמוד המוצר.",
                 ["לכתוב עמוד קצר וברור (למה, כמה זמן, איך)", "לקשר מהפוטר בכל העמודים", "לקשר גם מעמוד המוצר ליד הכפתור"],
                 structure={"returns": ["תוך כמה ימים", "באילו תנאים", "איך מחזירים", "מתי מקבלים החזר כספי"],
                            "shipping": ["אזורי משלוח", "עלות", "זמני הגעה", "מעקב משלוח"],
                            "privacy": ["איזה מידע נאסף", "למה", "עם מי משותף", "איך מוחקים"],
                            "terms": ["פרטי העסק", "תנאי רכישה", "ביטול עסקה", "אחריות"],
                            "contact": ["טלפון / וואטסאפ", "אימייל", "שעות מענה", "כתובת / ח.פ."]}.get(key, []),
                 preview=_pv("desktop", "home", "footer", [{"op": "append_footer", "html": footer_links_html([key])}]))


def fix_tap_targets(f, c):
    css = "a, button, [role=button], input[type=submit] { min-height: 44px; min-width: 44px; }\nnav a, footer a { padding-block: 10px; display: inline-block; }"
    return _base(f, "ux", "להגדיל אזורי לחיצה ל-44px לפחות ולהוסיף ריווח בין קישורים בטלפון.", ["להוסיף את ה-CSS", "לבדוק תפריט ופוטר בטלפון"],
                 code={"lang": "css", "snippet": "@media (max-width: 768px) {\n  " + css.replace("\n", "\n  ") + "\n}"},
                 preview=_pv("mobile", "home", None, [{"op": "inject_css", "css": css}]))


def fix_overflow(f, c):
    css = "img, video, iframe, table { max-width: 100% !important; height: auto; } body { overflow-x: hidden; }"
    return _base(f, "ux", "למנוע מאלמנטים רחבים לחרוג מרוחב המסך בטלפון.", ["לאתר את האלמנט הרחב (DevTools → מצב טלפון)", "להגביל רוחב מקסימלי ל-100%"],
                 code={"lang": "css", "snippet": css}, preview=_pv("mobile", "home", None, [{"op": "inject_css", "css": css}]))


def fix_viewport(f, c):
    return _base(f, "technical", "להוסיף תגית viewport כדי שהאתר יוצג ברוחב הטלפון.", ["להוסיף לתבנית ה-HTML בתוך <head>"],
                 code={"lang": "html", "snippet": '<meta name="viewport" content="width=device-width, initial-scale=1">'},
                 preview=_pv("mobile", "home", None, [{"op": "add_viewport"}]))


def fix_atc_feedback(f, c):
    toast = ('<div data-p1-fix style="position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#14532d;color:#fff;'
             'padding:12px 18px;border-radius:12px;font:600 15px system-ui,Arial;box-shadow:0 8px 24px rgba(0,0,0,.2)">✓ המוצר נוסף לסל · <u>מעבר לסל</u></div>')
    return _base(f, "ux", "אחרי לחיצה על 'הוספה לסל' להציג אישור ברור + עדכון מונה הסל + קיצור לקופה.",
                 ["הודעת אישור / מגירת עגלה", "עדכון מונה הסל בכותרת", "כפתור 'מעבר לקופה' בהודעה"],
                 preview=_pv("desktop", "product", "atc", [{"op": "append_body", "html": toast}]))


def fix_price(f, c):
    block = f'<div data-p1-fix style="font:800 26px system-ui,Arial;margin:8px 0">₪{_e(c["price"]) if c["price"] else PH}</div>'
    return _base(f, "content", "להציג מחיר גדול וברור ליד שם המוצר.", ["מחיר מתחת לכותרת, לפני הכפתור", "אם יש מבצע — מחיר מקורי מחוק לידו"],
                 preview=_pv("desktop", "product", "h1", [{"op": "insert_after", "target": "h1", "html": block}]))


def fix_cta(f, c):
    btn = ('<a data-p1-fix href="#" style="display:inline-block;margin:14px 0;background:#111;color:#fff;padding:14px 26px;border-radius:12px;'
           'font:700 16px system-ui,Arial;text-decoration:none">לקנייה עכשיו ←</a>')
    return _base(f, "design", "להוסיף כפתור פעולה ראשי בולט במסך הראשון.", ["טקסט פעולה ברור", "צבע בניגודיות גבוהה", "מוביל לקטגוריה/מוצר מוביל"],
                 copy=[{"label": "טקסט כפתור", "text": x} for x in ("לקנייה עכשיו", "לצפייה בקולקציה", "למוצרים הנמכרים")],
                 preview=_pv("desktop", "home", "h1", [{"op": "insert_after", "target": "h1", "html": btn}]))


def fix_atc_prominence(f, c):
    css = ("[data-p1-target=atc] { background:#111 !important; color:#fff !important; font-size:17px !important; font-weight:700 !important;"
           " min-height:52px !important; min-width:240px !important; border-radius:12px !important; border:0 !important; }")
    return _base(f, "design", "להבליט את כפתור הקנייה: צבע בניגודיות גבוהה, גודל גדול יותר, טקסט ברור.",
                 ["צבע מלא בניגודיות 4.5:1 לפחות", "גובה 48px+ ורוחב מלא בטלפון", "אין עוד כפתור בולט שמתחרה בו"],
                 code={"lang": "css", "snippet": css.replace("[data-p1-target=atc]", ".add-to-cart")},
                 preview=_pv("desktop", "product", "atc", [{"op": "mark_target", "target": "atc"}, {"op": "inject_css", "css": css}]))


def fix_meta_description(f, c):
    desc = f"{c['product'] or c['site'] or PH} — " + (", ".join(c["usps"][:2]) if c["usps"] else PH) + ". הזמינו אונליין."
    return _base(f, "technical", "להוסיף תיאור לגוגל (meta description) שמזמין להקליק.", ["120–160 תווים", "תועלת + יתרון + קריאה לפעולה"],
                 copy=[{"label": "meta description", "text": desc}], code={"lang": "html", "snippet": f'<meta name="description" content="{_e(desc)}">'})


def fix_thin_product(f, c):
    return _base(f, "content", "להרחיב את עמוד המוצר במבנה שעונה על השאלות של הלקוח.", ["לכתוב לפי המבנה המוצע", "להשתמש בשפה של הלקוח, לא של היצרן"],
                 structure=["3 יתרונות עיקריים (נקודות)", "למי זה מתאים", "מפרט / מידות / חומרים (טבלה)", "מה בקופסה", "משלוח והחזרות", "שאלות נפוצות"],
                 copy=[{"label": "יתרונות שנמצאו באתר", "text": " · ".join(c["usps"]) or PH}])


def fix_images(f, c):
    return _base(f, "content", "להוסיף 4–6 תמונות מוצר שעונות על שאלות הלקוח.", ["חזית", "צד / גב", "תקריב לפרטים וחומרים", "בשימוש אמיתי", "מידות ביחס לאדם/חפץ"],
                 structure=["גלריה עם תמונות ממוזערות", "זום בלחיצה", "סרטון קצר (אופציונלי)"])


def fix_guest_checkout(f, c):
    return _base(f, "flow", "לאפשר קנייה כאורח ולהציע הרשמה רק אחרי התשלום.",
                 ["Shopify: Settings → Checkout → Customer accounts: Optional", "WooCommerce: Settings → Accounts → Allow guest checkout", "להציע יצירת חשבון בעמוד התודה"])


def fix_long_checkout(f, c):
    return _base(f, "flow", "לקצר את טופס הקופה: להסיר שדות לא חיוניים ולהפעיל השלמה אוטומטית.",
                 ["להסיר: חברה, שורת כתובת 2, טלפון כפול", "autocomplete לכתובת", "לפצל לשלבים ברורים עם מחוון התקדמות"])


def fix_https(f, c):
    return _base(f, "technical", "להפעיל HTTPS ולהפנות אליו את כל התנועה.", ["תעודת SSL חינמית (Let's Encrypt / ספק האחסון)", "הפניה 301 מ-http ל-https"],
                 code={"lang": "nginx", "snippet": "server {\n  listen 80;\n  return 301 https://$host$request_uri;\n}"})


def fix_speed(f, c):
    return _base(f, "technical", "להאיץ את הופעת התוכן המרכזי.", ["דחיסת תמונות ל-WebP/AVIF", "preload לתמונה הראשית", "lazy loading לתמונות שמתחת למסך", "להסיר סקריפטים לא בשימוש"],
                 code={"lang": "html", "snippet": '<link rel="preload" as="image" href="/hero.webp">\n<img src="/product.webp" loading="lazy" width="800" height="800" alt="…">'})


def fix_broken_links(f, c):
    urls = [b["url"] for b in (f.get("evidence") or {}).get("broken", [])][:8]
    return _base(f, "technical", "לתקן או להפנות (301) כל קישור שבור.", ["לעדכן את הקישורים בתפריט/תוכן", "להגדיר הפניה לעמוד הקרוב ביותר"],
                 code={"lang": "text", "snippet": "\n".join(f"{u}  →  {PH}" for u in urls) or None})


def fix_search(f, c):
    bar = ('<div data-p1-fix style="margin:10px auto;max-width:520px"><input placeholder="חיפוש מוצרים…" style="width:100%;padding:12px 14px;border:1px solid #ccc;'
           'border-radius:10px;font:15px system-ui,Arial"></div>')
    return _base(f, "ux", "להוסיף שורת חיפוש בולטת בכותרת.", ["חיפוש בכותרת בכל העמודים", "בטלפון: אייקון שפותח שדה מלא"],
                 preview=_pv("desktop", "home", "header", [{"op": "insert_top", "html": bar}]))


def fix_policy_content(f, c):
    days = c["returns_days"] or PH
    draft = (f"החזרות: ניתן להחזיר מוצר תוך {days} ימים מקבלתו, באריזה המקורית. ההחזר הכספי יבוצע תוך {PH} ימי עסקים.\n"
             f"משלוחים: משלוח עד הבית תוך {PH} ימי עסקים. עלות: {('חינם מעל ₪' + c['free_ship_from']) if c['free_ship_from'] else PH}.\n"
             f"איך מחזירים: {PH} (טלפון / וואטסאפ / טופס).")
    return _base(f, "content", "לשכתב את עמוד המדיניות כך שיענה במספרים על השאלות של הלקוח.",
                 ["לפתוח בשורה אחת שמסכמת את ההבטחה", "מספרים מדויקים: ימים, עלויות, מי משלם", "שאלות ותשובות קצרות במקום טקסט משפטי"],
                 copy=[{"label": "טיוטת פתיחה לעמוד (למלא את המקומות המסומנים)", "text": draft}],
                 structure=["משפט הבטחה אחד", "כמה ימים / כמה עולה", "איך עושים את זה (3 צעדים)", "שאלות נפוצות"])


def fix_business_details(f, c):
    block = (f'<div data-p1-fix style="padding:12px;text-align:center;font:13px system-ui,Arial;color:#444">'
             f'{_e(c["site"] or PH)} · ח.פ {PH} · {PH} (כתובת) · {_e(c["phones"][0]) if c["phones"] else PH} (טלפון)</div>')
    return _base(f, "content", "להציג בפוטר את פרטי העסק: שם, ח.פ / עוסק מורשה, כתובת וטלפון.", ["להוסיף שורה קבועה בפוטר"],
                 preview=_pv("desktop", "home", "footer", [{"op": "append_footer", "html": block}]))


def fix_cart_shipping(f, c):
    note = (f'<div data-p1-fix style="margin:12px 0;padding:12px 14px;background:#eef6ff;border:1px solid #cfe3fb;border-radius:10px;'
            f'font:500 14px system-ui,Arial;color:#1e3a5f">🚚 משלוח: {("חינם מעל ₪" + _e(c["free_ship_from"])) if c["free_ship_from"] else PH} · '
            f'זמן הגעה: {PH} ימי עסקים</div>')
    return _base(f, "flow", "להציג בעגלה את עלות המשלוח (או כמה חסר למשלוח חינם) לפני הקופה.",
                 ["שורת משלוח מעל כפתור הקופה", "אם יש סף חינם — 'עוד ₪X למשלוח חינם'"],
                 preview=_pv("desktop", "cart", "h1", [{"op": "insert_after", "target": "h1", "html": note}]))


def fix_steps(f, c):
    return _base(f, "flow", "לקצר את הדרך לקופה: קישורי מוצרים מעמוד הבית ומגירת עגלה עם 'לקופה'.",
                 ["מוצרים מובילים בעמוד הבית עם קישור ישיר", "אחרי 'הוספה לסל' — מגירה עם כפתור 'לקופה'", "כפתור 'קנה עכשיו' שמדלג על העגלה"])


GENERATORS: dict[str, Gen] = {
    "no_shipping_info_pdp": fix_trust_pdp, "no_returns_info_pdp": fix_trust_pdp,
    "mobile_atc_below_fold": fix_mobile_atc, "entry_popup": fix_popup, "mobile_popup": fix_popup,
    "unclear_headline": fix_headline, "weak_value_prop": fix_headline, "html_no_h1": fix_headline,
    "no_reviews": fix_reviews, "no_returns_policy": fix_trust_links, "no_shipping_policy": fix_trust_links,
    "no_privacy_policy": fix_trust_links, "no_terms": fix_trust_links, "no_contact_page": fix_trust_links,
    "small_tap_targets": fix_tap_targets, "mobile_overflow": fix_overflow, "no_viewport": fix_viewport,
    "atc_no_feedback": fix_atc_feedback, "no_price": fix_price, "html_no_cta": fix_cta, "atc_not_prominent": fix_atc_prominence,
    "html_no_meta_description": fix_meta_description, "thin_product_page": fix_thin_product, "few_images": fix_images,
    "forced_login": fix_guest_checkout, "long_checkout": fix_long_checkout, "no_https": fix_https,
    "slow_lcp": fix_speed, "medium_lcp": fix_speed, "broken_links": fix_broken_links, "no_search": fix_search,
    "agent_trust_thin_policy": fix_policy_content, "agent_no_business_details": fix_business_details,
    "agent_mobile_landing": fix_mobile_atc, "agent_info_missing": fix_thin_product, "html_thin_content": fix_thin_product,
    "shipping_unclear": fix_cart_shipping, "too_many_steps": fix_steps,
}


def propose(finding: dict, facts: dict) -> dict:
    gen = GENERATORS.get(finding["rule_id"])
    c = _ctx(facts)
    if gen:
        fix = gen(finding, c)
    else:  # ממצא בלי תבנית ייעודית — הצעת התיקון הכללית מהכלל עצמו
        fix = _base(finding, KIND_OF_CATEGORY.get(finding["category"], "ux"), finding["fix_steps"][0] if finding["fix_steps"] else "",
                    finding["fix_steps"])
    fix["rule_id"] = finding["rule_id"]
    fix["has_placeholders"] = PH in str(fix)
    fix["usps_found"] = c["usps"]
    return fix
