"""חמשת סוכני הלקוח. כל סוכן גולש בעצמו (לחיצות אמיתיות), במסלול משלו, לפי המטרה שלו.

מנוע ההחלטות כרגע: RuleBrain (כללים קבועים) — לכן הם מוצגים כ"סוכני לקוח מבוססי כללים", לא כ-AI.
"""
from __future__ import annotations

import re
import time

from playwright.async_api import Error as PWError

from ..audit.collector import PRICE_RE, TRUST_LINKS
from .base import AgentContext, AgentResult

AGENTS = {
    "trust": {"name_he": "סוכן אמון", "name_en": "Trust Agent", "device": "desktop", "emoji": "🛡️",
              "goal_he": "בודק אמינות: מדיניות החזרות ומשלוחים, פרטי העסק, דרכי קשר וביקורות.",
              "goal_en": "Checks credibility: returns & shipping policies, business details, contact options and reviews."},
    "fast_buyer": {"name_he": "קונה מהיר", "name_en": "Fast Buyer", "device": "desktop", "emoji": "⚡",
                   "goal_he": "מנסה להגיע מהבית לקופה במינימום לחיצות וסופר כמה פעולות נדרשו.",
                   "goal_en": "Tries to get from home to checkout in as few clicks as possible and counts the steps."},
    "price": {"name_he": "רגיש למחיר", "name_en": "Price-Sensitive", "device": "desktop", "emoji": "🏷️",
              "goal_he": "בודק מחיר, מבצעים, עלות משלוח, סכום בעגלה ושדה קופון.",
              "goal_en": "Checks price, discounts, shipping cost, cart totals and a coupon field."},
    "confused": {"name_he": "קונה מבולבל", "name_en": "Confused Buyer", "device": "desktop", "emoji": "🤔",
                 "goal_he": "מנסה להבין את המוצר: פותח לשוניות ואקורדיונים ומחפש מפרט, יתרונות ושאלות נפוצות.",
                 "goal_en": "Tries to understand the product: opens tabs/accordions, looks for specs, benefits and FAQ."},
    "mobile_ad": {"name_he": "הגיע מפרסומת בטלפון", "name_en": "Mobile Ad Visitor", "device": "mobile", "emoji": "📱",
                  "goal_he": "נוחת ישירות בעמוד מוצר בטלפון (כמו מפרסומת) ובודק מה רואים במסך הראשון ואיך קונים.",
                  "goal_en": "Lands directly on a product page on mobile (like from an ad) and checks the first screen and the path to buy."},
}


async def _open_product(ctx: AgentContext, start: dict, r: AgentResult, via_click: bool) -> bool:
    """מגיע לעמוד מוצר: בלחיצות מהבית (כמו לקוח) או ישירות לכתובת שנמצאה."""
    if via_click:
        a, label = await ctx.product_link()
        if not a:
            c, clabel = await ctx.category_link()
            if c and await ctx.click(c, clabel or "קטגוריה"):
                a, label = await ctx.product_link()
        if a and await ctx.click(a, label or "מוצר"):
            return True
        r.info("לא נמצא קישור למוצר בלחיצה — עובר לכתובת המוצר שזוהתה בבדיקה")
    if start.get("product_url"):
        return await ctx.goto(start["product_url"], "פותח עמוד מוצר")
    return False


# ================================================================ 1. סוכן אמון
async def trust_agent(ctx: AgentContext, start: dict) -> AgentResult:
    r = AgentResult()
    if not await ctx.goto(start["home_url"], "נכנס לעמוד הבית"):
        r.issue("עמוד הבית לא נטען")
        r.decide_verdict(True)
        return r
    await ctx.shot("home")
    home_text = await ctx.text()
    pages = {}
    for key, label in (("returns", "החזרות"), ("shipping", "משלוחים"), ("contact", "צור קשר"), ("about", "אודות")):
        ctx.check()
        a, txt = await ctx.link_matching(TRUST_LINKS[key])
        if not a:
            r.issue(f"לא מצאתי קישור ל{label}")
            pages[key] = {"found": False}
            continue
        if not await ctx.click(a, txt or label):
            pages[key] = {"found": True, "opened": False}
            continue
        text = await ctx.main_text()
        words = len(text.split())
        has_numbers = bool(re.search(r"\d", text))
        pages[key] = {"found": True, "opened": True, "words": words, "has_numbers": has_numbers, "url": ctx.page.url}
        await ctx.shot(key)
        if words < 40:  # נספר רק תוכן העמוד (בלי תפריט ופוטר)
            r.issue(f"עמוד '{label}' קיים אבל כמעט ריק ({words} מילים)")
        elif key in ("returns", "shipping") and not has_numbers:
            r.issue(f"עמוד '{label}' לא מציין מספרים (ימים / עלות)")
        else:
            r.ok(f"עמוד {label} ברור ({words} מילים)")
        await ctx.goto(start["home_url"], "חוזר לעמוד הבית")
    contact_text = home_text + " " + " ".join(str(v) for v in pages.values())
    business = bool(re.search(r"ח\.?\s?פ\.?|ע\.?\s?מ\.?|עוסק\s+מורשה|company\s+(no|number|reg)|VAT|רחוב|\bst\.|street", home_text, re.I))
    phone = bool(re.search(r"0\d{1,2}[- ]?\d{7}|\+972|tel:", contact_text))
    (r.ok if business else r.issue)("פרטי העסק (ח.פ / כתובת) " + ("מופיעים" if business else "לא מופיעים בעמוד הבית"))
    (r.ok if phone else r.issue)("מספר טלפון " + ("נמצא" if phone else "לא נמצא"))
    if await _open_product(ctx, start, r, via_click=True):
        t = await ctx.main_text()
        reviews = bool(re.search(r"ביקורות|חוות\s+דעת|reviews?|★", t, re.I))
        (r.ok if reviews else r.issue)("ביקורות בעמוד המוצר " + ("נמצאו" if reviews else "לא נמצאו"))
        await ctx.shot("product")
    r.metrics = {"policy_pages": pages, "business_details": business, "phone": phone}
    r.decide_verdict(hard_issue=not pages.get("returns", {}).get("found"))
    return r


# ================================================================ 2. קונה מהיר
async def fast_buyer(ctx: AgentContext, start: dict) -> AgentResult:
    r = AgentResult()
    t0 = time.perf_counter()
    clicks = 0
    if not await ctx.goto(start["home_url"], "נכנס לעמוד הבית"):
        r.issue("עמוד הבית לא נטען")
        r.decide_verdict(True)
        return r
    before = ctx.actions
    if not await _open_product(ctx, start, r, via_click=True):
        r.issue("לא הצלחתי להגיע למוצר")
        r.decide_verdict(True)
        return r
    clicks += ctx.actions - before
    await ctx.shot("product")
    await ctx.select_required_options()
    atc = await ctx.atc()
    if not atc:
        r.issue("אין כפתור 'הוספה לסל' גלוי")
        r.metrics = {"clicks": clicks, "reached_checkout": False}
        r.decide_verdict(True)
        return r
    clicks += 1
    await ctx.click(atc, "הוספה לסל")
    await ctx.shot("after-add")
    ck = await ctx.checkout_button()  # מגירת עגלה עם כפתור קופה?
    if not ck:
        a, label = await ctx.cart_link()
        if a:
            clicks += 1
            await ctx.click(a, label or "סל")
        else:
            await ctx.goto(start["home_url"].rstrip("/") + "/cart", "לא מצאתי קישור לסל — מנסה /cart")
            r.issue("קישור לסל לא נמצא — נדרש ניחוש כתובת")
        ck = await ctx.checkout_button()
    reached = False
    if ck:
        clicks += 1
        await ctx.click(ck, "מעבר לקופה")
        txt = await ctx.text()
        reached = bool(re.search(r"checkout|קופה|תשלום|payment", ctx.page.url + " " + txt[:2000], re.I))
        await ctx.shot("checkout")
    secs = round(time.perf_counter() - t0, 1)
    r.metrics = {"clicks": clicks, "reached_checkout": reached, "seconds": secs, "page_actions": ctx.actions}
    if reached:
        (r.ok if clicks <= 4 else r.issue)(f"הגעתי לקופה ב-{clicks} לחיצות ({secs} שנ')")
    else:
        r.issue(f"לא הגעתי לקופה אחרי {clicks} לחיצות")
    await ctx.log("info", "עוצר לפני מילוי פרטים — לא מבצעים הזמנה")
    r.decide_verdict(hard_issue=not reached)
    return r


# ================================================================ 3. רגיש למחיר
async def price_agent(ctx: AgentContext, start: dict) -> AgentResult:
    r = AgentResult()
    if not await _open_product(ctx, start, r, via_click=False):
        r.issue("לא הצלחתי לפתוח עמוד מוצר")
        r.decide_verdict(True)
        return r
    await ctx.shot("product")
    t = await ctx.main_text()
    price = PRICE_RE.search(t)
    compare_at = await ctx.page.locator("del, s, .compare-at, [class*=compare], [class*=was-price]").count()
    discount = bool(re.search(r"מבצע|הנחה|sale|discount|% off|חסכו", t, re.I))
    ship = bool(re.search(r"משלוח|shipping|delivery", t, re.I))
    (r.ok if price else r.issue)("מחיר " + (f"מוצג: {price.group(0)}" if price else "לא מוצג בעמוד המוצר"))
    r.info("נמצא מחיר מקורי מחוק (מבצע)" if compare_at else "אין מחיר השוואה / מבצע")
    (r.ok if ship else r.issue)("עלות/מדיניות משלוח " + ("מוזכרת בעמוד המוצר" if ship else "לא מוזכרת בעמוד המוצר"))
    await ctx.select_required_options()
    atc = await ctx.atc()
    cart_total = coupon = cart_ship = None
    if atc and await ctx.click(atc, "הוספה לסל"):
        a, label = await ctx.cart_link()
        if a:
            await ctx.click(a, label or "סל")
        else:
            await ctx.goto(start["home_url"].rstrip("/") + "/cart", "פותח את הסל")
        ct = await ctx.main_text()
        await ctx.shot("cart")
        cart_total = bool(re.search(r"סה\"?כ|סך\s+הכל|total|subtotal", ct, re.I)) or bool(PRICE_RE.search(ct))
        cart_ship = bool(re.search(r"משלוח|shipping", ct, re.I))
        coupon = bool(re.search(r"קופון|קוד\s+הנחה|coupon|promo|discount\s+code", ct, re.I)) or \
            await ctx.page.locator("input[name*=coupon i], input[name*=discount i], input[id*=coupon i]").count() > 0
        (r.ok if cart_total else r.issue)("הסכום בעגלה " + ("ברור" if cart_total else "לא מוצג"))
        (r.ok if cart_ship else r.issue)("עלות המשלוח " + ("מוצגת בעגלה" if cart_ship else "לא מוצגת בעגלה"))
        r.info("יש שדה קופון" if coupon else "אין שדה קופון בעגלה")
    else:
        r.issue("לא הצלחתי להוסיף לסל כדי לבדוק את הסכום")
    r.metrics = {"price_visible": bool(price), "compare_at": bool(compare_at), "discount_mention": discount,
                 "shipping_on_pdp": ship, "cart_total": cart_total, "cart_shipping": cart_ship, "coupon": coupon}
    r.decide_verdict(hard_issue=not price)
    return r


# ================================================================ 4. קונה מבולבל
async def confused_agent(ctx: AgentContext, start: dict) -> AgentResult:
    r = AgentResult()
    if not await _open_product(ctx, start, r, via_click=False):
        r.issue("לא הצלחתי לפתוח עמוד מוצר")
        r.decide_verdict(True)
        return r
    await ctx.shot("product")
    before = len((await ctx.main_text()).split())
    opened = 0
    toggles = ctx.page.locator("details:not([open]) > summary, [aria-expanded=false], [role=tab]")
    for i in range(min(await toggles.count(), 6)):
        el = toggles.nth(i)
        try:
            if await el.is_visible():
                label = ((await el.inner_text()) or "לשונית").strip()[:40]
                if await ctx.click(el, label, wait_nav=False):
                    opened += 1
                    await ctx.page.wait_for_timeout(300)
        except PWError:
            continue
    t = await ctx.main_text()
    after = len(t.split())
    specs = bool(re.search(r"מפרט|מידות|חומר|specifications?|dimensions|material", t, re.I)) or \
        await ctx.page.locator("table, dl").count() > 0
    faq = bool(re.search(r"שאלות\s+נפוצות|faq|שאלות\s+ותשובות", t, re.I))
    size = bool(re.search(r"מדריך\s+מידות|size\s+(guide|chart)|טבלת\s+מידות", t, re.I))
    benefits = len(re.findall(r"✓|✔|יתרון|מתאים\s+ל|benefit|ideal\s+for|perfect\s+for", t, re.I))
    if opened:
        await ctx.shot("expanded")
        r.info(f"פתחתי {opened} לשוניות/אקורדיונים — נחשפו {max(0, after - before)} מילים נוספות")
    (r.ok if after >= 250 else r.issue)(f"יש {after} מילים בעמוד המוצר")
    (r.ok if specs else r.issue)("מפרט/מידות/חומרים " + ("נמצאו" if specs else "לא נמצאו"))
    (r.ok if faq else r.issue)("שאלות נפוצות " + ("נמצאו" if faq else "לא נמצאו"))
    r.info("יש מדריך מידות" if size else "אין מדריך מידות")
    (r.ok if benefits >= 2 else r.issue)("היתרונות " + ("מודגשים" if benefits >= 2 else "לא מודגשים (אין רשימת יתרונות)"))
    r.metrics = {"words": after, "revealed_words": max(0, after - before), "toggles_opened": opened, "specs": specs,
                 "faq": faq, "size_guide": size, "benefit_markers": benefits}
    r.decide_verdict()
    return r


# ================================================================ 5. הגיע מפרסומת בטלפון
async def mobile_ad_agent(ctx: AgentContext, start: dict) -> AgentResult:
    r = AgentResult()
    landing = start.get("product_url") or start["home_url"]
    sep = "&" if "?" in landing else "?"
    t0 = time.perf_counter()
    if not await ctx.goto(f"{landing}{sep}utm_source=p1_audit&utm_medium=paid_social", "נוחת מהפרסומת (טלפון)"):
        r.issue("דף הנחיתה לא נטען")
        r.decide_verdict(True)
        return r
    load_s = round(time.perf_counter() - t0, 1)
    await ctx.shot("landing")
    fold = await ctx.page.evaluate(r"""() => {
      const vh = innerHeight, inFold = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.top < vh && r.bottom > 0; };
      const h1 = document.querySelector('h1');
      const btn = [...document.querySelectorAll('button, a, input[type=submit]')].find((b) => /(הוסף|הוספה)\s*(ל)?(סל|עגלה)|add\s+to\s+(cart|bag)|קנה\s+עכשיו|buy\s+now/i.test(b.innerText || b.value || ''));
      const priceEl = [...document.querySelectorAll('body *')].find((e) => e.children.length === 0 && /(₪|\$|€)\s*\d|\d\s*(₪|ש"ח)/.test(e.textContent || ''));
      let overlay = false;
      for (const el of document.querySelectorAll('body *')) { const s = getComputedStyle(el); if (s.position === 'fixed') { const r = el.getBoundingClientRect(); if (r.width * r.height > innerWidth * vh * 0.45) { overlay = true; break; } } }
      return { h1: inFold(h1), atc: inFold(btn), price: inFold(priceEl), overlay, has_atc: !!btn };
    }""")
    (r.ok if fold["h1"] else r.issue)("הכותרת " + ("נראית במסך הראשון" if fold["h1"] else "לא נראית במסך הראשון"))
    (r.ok if fold["price"] else r.issue)("המחיר " + ("נראה במסך הראשון" if fold["price"] else "לא נראה במסך הראשון"))
    (r.ok if fold["atc"] else r.issue)("כפתור הקנייה " + ("במסך הראשון" if fold["atc"] else "לא במסך הראשון"))
    if fold["overlay"]:
        r.issue("חלון קופץ מכסה את המסך בנחיתה")
    scrolls = 0
    if not fold["atc"] and fold["has_atc"]:
        for _ in range(4):
            ctx.check()
            await ctx.page.mouse.wheel(0, 600)
            scrolls += 1
            ctx.actions += 1
            await ctx.log("scroll", f"גולל למטה ({scrolls})")
            await ctx.page.wait_for_timeout(400)
            if await ctx.page.evaluate(r"""() => [...document.querySelectorAll('button, a, input[type=submit]')].some((b) => { const r = b.getBoundingClientRect();
                return r.top >= 0 && r.top < innerHeight && /(הוסף|הוספה)\s*(ל)?(סל|עגלה)|add\s+to\s+(cart|bag)|קנה\s+עכשיו|buy\s+now/i.test(b.innerText || b.value || ''); })"""):
                break
        await ctx.shot("found-buy-button")
        r.info(f"נדרשו {scrolls} גלילות כדי להגיע לכפתור הקנייה")
    atc = await ctx.atc()
    added = False
    if atc:
        await ctx.select_required_options()
        added = await ctx.click(atc, "הוספה לסל (טלפון)")
        await ctx.shot("after-add")
    r.metrics = {"load_s": load_s, "above_fold": fold, "scrolls_to_buy": scrolls, "tapped_add_to_cart": added}
    r.decide_verdict(hard_issue=not fold["has_atc"])
    return r


RUNNERS = {"trust": trust_agent, "fast_buyer": fast_buyer, "price": price_agent, "confused": confused_agent,
           "mobile_ad": mobile_ad_agent}
