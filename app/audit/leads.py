"""בדיקת ערוצי פנייה: טפסי לידים, קישורי WhatsApp, טלפון ומייל — במחשב ובטלפון.

בטיחות: לא ממלאים ולא שולחים אף טופס. רק קוראים את מבנה הדף בדפדפן (measured).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

CONTACT_JS = r"""
() => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const forms = [...document.querySelectorAll('form')].map((f) => {
    const inputs = [...f.querySelectorAll('input, textarea, select')].filter((i) => !['hidden', 'submit', 'button', 'image', 'reset'].includes((i.type || '').toLowerCase()));
    const vis = inputs.filter(visible);
    const types = vis.map((i) => (i.type || i.tagName).toLowerCase());
    const names = vis.map((i) => ((i.name || '') + ' ' + (i.id || '') + ' ' + (i.placeholder || '') + ' ' + (i.getAttribute('aria-label') || '')).toLowerCase());
    const labelled = vis.filter((i) => (i.id && document.querySelector(`label[for="${CSS.escape(i.id)}"]`)) || i.closest('label') || i.getAttribute('aria-label') || i.placeholder).length;
    const submit = f.querySelector('button:not([type=button]):not([type=reset]), input[type=submit], input[type=image]');
    const isSearch = (f.getAttribute('role') === 'search') || types.includes('search') || /search|q\b|חיפוש/.test((f.action || '') + ' ' + names.join(' ')) && vis.length <= 2;
    const r = f.getBoundingClientRect();
    return { fields: vis.length, required: vis.filter((i) => i.required || i.getAttribute('aria-required') === 'true').length,
      has_email: types.includes('email') || names.some((n) => /mail|מייל|דוא/.test(n)),
      has_tel: types.includes('tel') || names.some((n) => /phone|tel|טלפון|נייד/.test(n)),
      has_submit: !!(submit && visible(submit)), labelled, is_search: isSearch, visible: visible(f),
      action: f.getAttribute('action') || '', method: (f.getAttribute('method') || 'get').toLowerCase(), top: Math.round(r.top + scrollY) };
  });
  const links = [...document.querySelectorAll('a[href]')];
  const wa = links.filter((a) => /wa\.me|whatsapp\.com|^whatsapp:/i.test(a.getAttribute('href') || '')).map((a) => {
    const r = a.getBoundingClientRect();
    return { href: a.href, visible: visible(a), above_fold: visible(a) && r.top < vh && r.top >= 0, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60) };
  });
  const tel = links.filter((a) => (a.getAttribute('href') || '').toLowerCase().startsWith('tel:')).map((a) => {
    const r = a.getBoundingClientRect(); return { href: a.getAttribute('href'), visible: visible(a), above_fold: visible(a) && r.top < vh && r.top >= 0 }; });
  const mailto = links.filter((a) => (a.getAttribute('href') || '').toLowerCase().startsWith('mailto:')).length;
  return { url: location.href, viewport: [vw, vh], forms, whatsapp: wa, tel, mailto };
}
"""


def wa_number(href: str) -> str | None:
    """מחלץ את המספר מקישור WhatsApp (wa.me/<n>, api.whatsapp.com/send?phone=<n>, whatsapp://send?phone=<n>)."""
    try:
        p = urlparse(href)
    except ValueError:
        return None
    if p.netloc.endswith("wa.me"):
        n = p.path.strip("/").split("/")[0]
    else:
        n = (parse_qs(p.query).get("phone") or [""])[0]
    n = re.sub(r"[\s\-()+]", "", n)
    return n or None


def wa_valid(number: str | None) -> tuple[bool, str]:
    """WhatsApp דורש מספר בפורמט בינלאומי: ספרות בלבד, עם קידומת מדינה, בלי 0 בהתחלה (לדוגמה 972501234567)."""
    if not number:
        return False, "בקישור אין מספר טלפון"
    if not number.isdigit():
        return False, f"המספר '{number}' מכיל תווים שאינם ספרות"
    if number.startswith("0"):
        return False, f"המספר '{number}' בפורמט מקומי (מתחיל ב-0). WhatsApp דורש קידומת מדינה, למשל 972{number[1:]}"
    if not 10 <= len(number) <= 15:
        return False, f"המספר '{number}' באורך לא תקין ({len(number)} ספרות)"
    return True, ""


def summarize(desktop: dict | None, mobile: dict | None, contact_page: dict | None) -> dict:
    """מאחד את מה שנמדד לעובדות אחידות לכללים."""
    pages = [p for p in (desktop, contact_page) if p]
    lead_forms = [dict(f, page=p["url"]) for p in pages for f in p["forms"] if not f["is_search"] and f["fields"] >= 2]
    wa_links = {w["href"]: w for p in [*pages, *(x for x in [mobile] if x)] for w in p["whatsapp"]}
    wa = []
    for href in wa_links:
        n = wa_number(href)
        ok, why = wa_valid(n)
        wa.append({"href": href, "number": n, "valid": ok, "problem": why})
    m = mobile or {}
    quick_mobile = any(w["above_fold"] for w in m.get("whatsapp", [])) or any(t["above_fold"] for t in m.get("tel", []))
    any_mobile = bool(m.get("whatsapp") or m.get("tel"))
    return {"lead_forms": lead_forms, "whatsapp": wa, "tel_links": len((desktop or {}).get("tel", [])) + len(m.get("tel", [])),
            "mailto": (desktop or {}).get("mailto", 0), "mobile_quick_contact_above_fold": quick_mobile,
            "mobile_has_quick_contact": any_mobile, "contact_page_url": (contact_page or {}).get("url"),
            "checked_mobile": mobile is not None}


def rules(c: dict, ev_home: dict, ev_mobile: dict, f) -> list[dict]:
    """ממצאים measured מערוצי הפנייה. f = rules._f."""
    out = []
    for w in c["whatsapp"]:
        if not w["valid"]:
            out.append(f("whatsapp_link_invalid", "conversion", "high", "high", "קישור WhatsApp שבור",
                         w["problem"] + ".", "לקוח שלוחץ על וואטסאפ ומקבל שגיאה — לא ינסה שוב. זו פנייה שהולכת לאיבוד.",
                         ["לתקן את הקישור לפורמט https://wa.me/972XXXXXXXXX (בלי 0 ובלי מקפים)", "ללחוץ עליו מהטלפון ולוודא שנפתחת שיחה"],
                         {**ev_home, "href": w["href"]}))
            break
    for fm in c["lead_forms"]:
        if not fm["has_submit"]:
            out.append(f("lead_form_no_submit", "conversion", "high", "high", "בטופס הפנייה אין כפתור שליחה גלוי",
                         f"טופס עם {fm['fields']} שדות בעמוד {fm['page']} — לא נמצא כפתור שליחה שנראה על המסך.",
                         "לקוח שמילא פרטים ולא מוצא איך לשלוח — עוזב.", ["להוסיף כפתור שליחה בולט מתחת לשדות", "לבדוק מהטלפון"],
                         {**ev_home, "page_url": fm["page"]}))
            break
    long_forms = [fm for fm in c["lead_forms"] if fm["fields"] > 6]
    if long_forms:
        fm = long_forms[0]
        out.append(f("lead_form_too_long", "conversion", "medium", "medium", f"טופס הפנייה ארוך ({fm['fields']} שדות)",
                     f"בעמוד {fm['page']}.", "כל שדה נוסף מוריד את הסיכוי שאנשים ישלימו את הטופס.",
                     ["להשאיר שם + טלפון (+ הודעה אופציונלית)", "את שאר הפרטים לאסוף בשיחה"], {**ev_home, "page_url": fm["page"]}))
    no_channel = [fm for fm in c["lead_forms"] if not (fm["has_email"] or fm["has_tel"])]
    if no_channel and len(no_channel) == len(c["lead_forms"]):
        out.append(f("lead_form_no_contact_field", "conversion", "medium", "high", "בטופס אין שדה טלפון או מייל",
                     "לא נמצא שדה שבאמצעותו אפשר לחזור ללקוח.", "פנייה בלי דרך לחזור ללקוח היא ליד אבוד.",
                     ["להוסיף שדה טלפון (type=tel) או מייל (type=email)"], ev_home))
    unlabeled = [fm for fm in c["lead_forms"] if fm["labelled"] < fm["fields"]]
    if unlabeled:
        out.append(f("lead_form_unlabeled", "ux_mobile", "low", "low", "שדות בטופס בלי תווית",
                     f"{unlabeled[0]['fields'] - unlabeled[0]['labelled']} שדות בלי label/placeholder.",
                     "בלי תווית לא ברור מה למלא, וקוראי מסך לא יכולים להשתמש בטופס (נגישות).",
                     ["להוסיף label לכל שדה"], ev_home))
    if c["checked_mobile"] and not c["mobile_has_quick_contact"]:
        out.append(f("no_quick_contact_mobile", "conversion", "medium", "high", "בטלפון אין כפתור התקשרות או WhatsApp",
                     "בדף הבית בטלפון לא נמצא קישור tel: או WhatsApp.",
                     "רוב הגולשים מגיעים מהטלפון ומעדיפים ללחוץ ולהתקשר/לכתוב מאשר למלא טופס.",
                     ["להוסיף כפתור WhatsApp צף או 'התקשרו עכשיו' (tel:)"], ev_mobile))
    elif c["checked_mobile"] and not c["mobile_quick_contact_above_fold"]:
        out.append(f("quick_contact_below_fold_mobile", "ux_mobile", "low", "medium", "כפתור יצירת קשר לא נראה במסך הראשון בטלפון",
                     "יש קישור טלפון/WhatsApp, אבל צריך לגלול כדי להגיע אליו.", "מי שמגיע מפרסומת מחליט תוך שניות.",
                     ["להציג כפתור יצירת קשר קבוע (צף) בטלפון"], ev_mobile))
    return out
