"""מנוע הכללים — הופך עובדות שנמדדו לממצאים (בעיות) עם הסבר ודרך תיקון.

כל ממצא כאן הוא source="measured": הוא נובע ישירות ממשהו שהדפדפן ראה.
ההמלצות כתובות מראש על ידינו (ידע מקצועי ב-CRO), לא נוצרו ע"י AI.
`impact` הוא הערכה איכותית (high/medium/low) — לא מספר מומצא.
"""
from __future__ import annotations

from typing import Any

# חמשת חלקי הדוח (הסדר כאן = הסדר בתצוגה)
CATEGORIES = {
    "conversion": "מוכנות להמרה",
    "checkout": "חיכוך בתהליך הרכישה",
    "trust": "אמון ואמינות",
    "ux_mobile": "חוויית משתמש ומובייל",
    "technical": "בעיות טכניות",
}
CATEGORIES_EN = {
    "conversion": "Conversion Readiness",
    "checkout": "Checkout Friction",
    "trust": "Trust & Credibility",
    "ux_mobile": "UX & Mobile Experience",
    "technical": "Technical Issues",
}

# שיוך כל כלל לחלק בדוח — טבלה אחת שקופה (מוצגת גם במתודולוגיה)
RULE_CATEGORY = {
    "site_unreachable": "technical", "slow_lcp": "technical", "medium_lcp": "technical", "heavy_page": "technical",
    "js_errors": "technical", "broken_resources": "technical", "broken_links": "technical", "no_product_schema": "technical",
    "layout_shift": "ux_mobile", "entry_popup": "ux_mobile", "mobile_overflow": "ux_mobile",
    "small_tap_targets": "ux_mobile", "mobile_atc_below_fold": "ux_mobile", "mobile_popup": "ux_mobile",
    "no_viewport": "ux_mobile", "no_search": "ux_mobile", "search_broken": "ux_mobile",
    "no_product_found": "conversion", "no_price": "conversion", "few_images": "conversion",
    "no_shipping_info_pdp": "conversion", "thin_product_page": "conversion",
    "no_reviews": "trust", "no_returns_info_pdp": "trust", "no_returns_policy": "trust", "no_shipping_policy": "trust",
    "no_privacy_policy": "trust", "no_terms": "trust", "no_contact_page": "trust", "no_https": "trust",
    "atc_missing": "checkout", "atc_failed": "checkout", "atc_no_feedback": "checkout", "cart_unreachable": "checkout",
    "cart_empty_after_add": "checkout", "no_checkout_button": "checkout", "checkout_failed": "checkout",
    "forced_login": "checkout", "long_checkout": "checkout", "payment_methods_hidden": "checkout",
}
_HTML_CATEGORY = {"SEO": "technical", "תוכן": "conversion", "מובייל": "ux_mobile", "המרות": "conversion",
                  "שיווק": "technical", "נגישות": "ux_mobile", "מהירות": "technical", "אמון": "trust",
                  "זמינות": "technical"}
# בעיות HTML שמכוסות טוב יותר ע"י בדיקות הדפדפן
_HTML_SKIP = {"no_viewport"}


def _f(rule_id, category, severity, impact, title, detail, why, fix_steps, evidence=None) -> dict:
    category = RULE_CATEGORY.get(rule_id, category)
    return {"rule_id": rule_id, "source": "measured", "category": category, "severity": severity,
            "impact": impact, "title": title, "detail": detail, "why_it_matters": why,
            "fix_steps": fix_steps, "evidence": evidence or {}}


def evaluate(facts: dict, steps: list[dict]) -> list[dict]:
    by_key = {s["key"]: s for s in steps}

    def ev(step_key: str, **extra: Any) -> dict:
        s = by_key.get(step_key) or {}
        return {"screenshot_id": s.get("screenshot_id"), "page_url": s.get("page_url"), **extra}

    out: list[dict] = []
    home = facts.get("home")
    if not home:
        out.append(_f("site_unreachable", "journey", "critical", "high", "האתר לא נטען",
                      facts.get("home_error") or "הדפדפן לא הצליח לטעון את עמוד הבית.",
                      "אם האתר לא נטען — אין מכירות בכלל.",
                      ["בדקו שהאתר פעיל ושהכתובת נכונה", "בדקו את שרת האחסון ותעודת ה-SSL"], ev("home")))
        return out

    # ---------------- מהירות
    t = home["timing"]
    lcp = t.get("lcp") or t.get("load") or home.get("load_ms", 0)
    if lcp > 4000:
        out.append(_f("slow_lcp", "speed", "high", "high", f"התוכן המרכזי מופיע רק אחרי {lcp / 1000:.1f} שניות",
                      f"LCP (זמן הופעת התוכן הגדול) = {lcp / 1000:.1f} שנ' במחשב. היעד של גוגל: עד 2.5 שנ'.",
                      "מבקרים רבים עוזבים לפני שהם רואים את המוצר. מהירות היא אחד הגורמים החזקים ביותר לשיעור ההמרה.",
                      ["דחסו תמונות והמירו ל-WebP/AVIF", "הגדירו preload לתמונה הראשית",
                       "הסירו אפליקציות/תוספים שלא בשימוש", "השתמשו ב-CDN ובמטמון"], ev("home", lcp_ms=lcp)))
    elif lcp > 2500:
        out.append(_f("medium_lcp", "speed", "medium", "medium", f"זמן הופעת התוכן המרכזי: {lcp / 1000:.1f} שניות",
                      f"LCP = {lcp / 1000:.1f} שנ'. היעד: עד 2.5 שנ'.",
                      "עיכוב של שנייה-שתיים מספיק כדי להוריד המרות, במיוחד בסלולר.",
                      ["דחסו את התמונה הראשית", "צמצמו סקריפטים שנטענים לפני התוכן"], ev("home", lcp_ms=lcp)))
    if t.get("cls", 0) > 0.25:
        out.append(_f("layout_shift", "ux", "medium", "medium", "התוכן קופץ בזמן הטעינה",
                      f"CLS = {t['cls']} (היעד: מתחת ל-0.1).",
                      "כשהעמוד זז, לקוחות לוחצים על הדבר הלא נכון ומתעצבנים.",
                      ["הגדירו גובה ורוחב קבועים לתמונות ולבאנרים", "אל תכניסו באנרים מעל תוכן קיים אחרי הטעינה"], ev("home")))
    if home.get("transfer_kb", 0) > 5000:
        out.append(_f("heavy_page", "speed", "medium", "medium", f"עמוד הבית כבד: כ-{home['transfer_kb'] // 1024}MB",
                      f"{home['resources']} משאבים, כ-{home['transfer_kb']}KB שנמדדו.",
                      "בגלישה סלולרית עמוד כבד נטען לאט ושורף חבילת גלישה.",
                      ["דחסו תמונות", "טענו תמונות בגלילה (lazy loading)", "הסירו סקריפטים מיותרים"], ev("home")))

    # ---------------- שגיאות
    if facts.get("js_errors"):
        out.append(_f("js_errors", "ux", "medium", "medium", f"{len(facts['js_errors'])} שגיאות JavaScript בעמודים",
                      "; ".join(facts["js_errors"][:3]),
                      "שגיאות קוד יכולות לשבור כפתורים, עגלות ותפריטים בלי שבעל העסק יודע.",
                      ["פתחו את כלי המפתחים (F12) ← Console ובדקו את השגיאות", "עדכנו/השביתו תוסף שגורם לשגיאה"],
                      ev("home", errors=facts["js_errors"][:10])))
    if facts.get("failed_requests"):
        out.append(_f("broken_resources", "ux", "low" if len(facts["failed_requests"]) < 3 else "medium", "low",
                      f"{len(facts['failed_requests'])} קבצים/עמודים באתר מחזירים שגיאה",
                      "; ".join(facts["failed_requests"][:3]),
                      "קבצים חסרים גורמים לתמונות שבורות ולתקלות תצוגה.",
                      ["תקנו או הסירו את ההפניות לקבצים החסרים"], ev("home", requests=facts["failed_requests"][:10])))

    # ---------------- חלון קופץ
    if home.get("overlay"):
        out.append(_f("entry_popup", "ux", "medium", "medium", "חלון קופץ מכסה את המסך בכניסה",
                      f"חלון מכסה כ-{home['overlay']['cover']}% מהמסך: \"{home['overlay']['text'][:80]}\"",
                      "לקוח שנכנס ורואה חלון במקום מוצר — חלק עוזבים מיד, במיוחד בטלפון.",
                      ["הציגו את החלון רק אחרי גלילה או זמן שהייה", "הקטינו אותו לפס תחתון"], ev("home")))

    # ---------------- מובייל
    mob = facts.get("mobile")
    if mob:
        if mob.get("horizontal_overflow"):
            out.append(_f("mobile_overflow", "mobile", "high", "high", "בטלפון העמוד רחב מהמסך (גלילה הצידה)",
                          f"רוחב התוכן {mob['scroll_width']}px במסך של {mob['viewport_width']}px.",
                          "אתר ש'זז' הצידה בטלפון נראה שבור ולא מקצועי — ורוב הקונים גולשים מהטלפון.",
                          ["מצאו את האלמנט הרחב (תמונה/טבלה/באנר) והגדירו max-width: 100%"],
                          ev("mobile")))
        if mob.get("small_tap_targets", 0) > 15:
            out.append(_f("small_tap_targets", "mobile", "low", "low", f"{mob['small_tap_targets']} כפתורים/קישורים קטנים מדי לאצבע",
                          "אלמנטים לחיצים קטנים מ-24 פיקסלים במסך הטלפון.",
                          "לחיצות שגויות מתסכלות ומאטות את הקנייה.",
                          ["הגדילו כפתורים לגובה 44px לפחות", "הוסיפו ריווח בין קישורים"], ev("mobile")))
        if mob.get("atc_above_fold") is False:
            out.append(_f("mobile_atc_below_fold", "mobile", "medium", "high", "בטלפון כפתור 'הוספה לסל' לא נראה בלי גלילה",
                          f"הכפתור נמצא {mob.get('atc_position_px')}px מראש העמוד — מתחת לגובה המסך הראשון.",
                          "הכפתור הכי חשוב בחנות צריך להיות זמין מיד. כל גלילה מאבדת קונים.",
                          ["הוסיפו כפתור 'הוספה לסל' דביק בתחתית המסך במובייל",
                           "קצרו את מה שמופיע מעל הכפתור (גלריה ענקית, טקסטים)"],
                          {"screenshot_id": mob.get("product_screenshot")}))
        if mob.get("overlay") and not home.get("overlay"):
            out.append(_f("mobile_popup", "mobile", "medium", "medium", "בטלפון חלון קופץ מכסה את המסך",
                          f"כ-{mob['overlay']['cover']}% מהמסך מכוסה בכניסה.",
                          "בטלפון קשה לסגור חלונות — הרבה גולשים פשוט יוצאים.",
                          ["הציגו את החלון רק במחשב או אחרי גלילה"], ev("mobile")))

    # ---------------- מסע רכישה
    prod = facts.get("product")
    if not prod:
        ps = by_key.get("product", {})
        out.append(_f("no_product_found", "journey", "medium", "medium", "לא הצלחנו להגיע לעמוד מוצר",
                      ps.get("detail", ""),
                      "אם הסוכן האוטומטי לא מוצא מוצר מעמוד הבית — גם חלק מהלקוחות לא ימצאו. "
                      "(אם האתר אינו חנות, אפשר להתעלם מממצא זה.)",
                      ["ודאו שבעמוד הבית יש קישורים ישירים למוצרים/קטגוריות פופולריים",
                       "השתמשו במבנה כתובות סטנדרטי (/products/ או /product/)"], ev("home")))
    else:
        if not prod.get("price_visible"):
            out.append(_f("no_price", "journey", "high", "high", "לא נמצא מחיר בעמוד המוצר",
                          "לא זוהה מחיר בטקסט, בנתונים המובנים או בתגיות המוצר.",
                          "לקוח שלא רואה מחיר לא יקנה — ולרוב לא יטרח לשאול.",
                          ["הציגו מחיר בולט ליד שם המוצר", "הוסיפו נתוני Product מובנים עם offers.price"], ev("product")))
        if prod.get("large_images", 0) < 2:
            out.append(_f("few_images", "ux", "medium", "medium", f"מעט תמונות מוצר ({prod.get('large_images', 0)})",
                          "נספרו תמונות גדולות (150px ומעלה) בעמוד המוצר.",
                          "באונליין הלקוח לא יכול לגעת במוצר — תמונות הן התחליף. מעט תמונות = יותר התלבטות.",
                          ["הוסיפו 4–6 תמונות: חזית, צד, פרטים, שימוש בפועל", "שקלו סרטון קצר"], ev("product")))
        if not prod.get("mentions_reviews"):
            out.append(_f("no_reviews", "trust", "medium", "high", "אין ביקורות או חוות דעת בעמוד המוצר",
                          "לא נמצאו ביקורות, דירוג כוכבים או המלצות.",
                          "ביקורות של לקוחות אחרים הן מהגורמים החזקים ביותר לאמון והחלטת קנייה.",
                          ["התקינו מערכת ביקורות (למשל Judge.me / Yotpo / ביקורות WooCommerce)",
                           "שלחו ללקוחות קודמים בקשה לביקורת"], ev("product")))
        if not prod.get("mentions_shipping"):
            out.append(_f("no_shipping_info_pdp", "trust", "medium", "medium", "אין מידע על משלוח בעמוד המוצר",
                          "המילים משלוח/shipping לא מופיעות בעמוד המוצר.",
                          "עלות וזמן משלוח לא ידועים הם סיבה מרכזית לנטישת עגלות.",
                          ["הוסיפו שורה קצרה ליד הכפתור: עלות משלוח, זמן הגעה, משלוח חינם מעל סכום"], ev("product")))
        if not prod.get("mentions_returns"):
            out.append(_f("no_returns_info_pdp", "trust", "low", "medium", "אין מידע על החזרות בעמוד המוצר",
                          "לא הוזכרו החזרות/החלפות בעמוד המוצר.",
                          "מדיניות החזרה ברורה מורידה את הסיכון שהלקוח מרגיש.",
                          ["הוסיפו 'החזרה/החלפה עד X ימים' ליד כפתור הקנייה"], ev("product")))
        if prod.get("description_chars", 0) < 1500:
            out.append(_f("thin_product_page", "ux", "low", "medium", "מעט מידע בעמוד המוצר",
                          f"כ-{prod.get('description_chars')} תווים בכל העמוד.",
                          "לקוח שלא מקבל תשובות (מידות, חומרים, שימוש) — עוזב לחפש בגוגל ולא תמיד חוזר.",
                          ["הוסיפו תיאור עם יתרונות, מפרט, מידות והוראות שימוש", "הוסיפו שאלות נפוצות למוצר"], ev("product")))
        if not prod.get("jsonld_product"):
            out.append(_f("no_product_schema", "seo", "low", "low", "אין נתוני מוצר מובנים (Schema Product)",
                          "לא נמצא JSON-LD מסוג Product.",
                          "בלי זה גוגל לא מציג מחיר, זמינות וכוכבים בתוצאות החיפוש.",
                          ["הוסיפו JSON-LD מסוג Product עם name, image, offers, aggregateRating"], ev("product")))

        atc = facts.get("add_to_cart", {})
        st = by_key.get("add_to_cart", {})
        if not atc.get("found"):
            out.append(_f("atc_missing", "journey", "critical", "high", "לא נמצא כפתור 'הוספה לסל'",
                          st.get("detail", ""), "בלי כפתור קנייה ברור — אין מכירה.",
                          ["הוסיפו כפתור בולט עם טקסט ברור ('הוספה לסל')", "ודאו שהוא לא מוסתר עד בחירת אפשרות"], ev("product")))
        elif st.get("status") == "failed":
            out.append(_f("atc_failed", "journey", "critical", "high", "ההוספה לסל לא עבדה",
                          st.get("detail", ""), "לקוח שמנסה לקנות ונתקע — הולך למתחרה.",
                          ["נסו בעצמכם להוסיף מוצר לסל ממחשב ומטלפון", "בדקו שגיאות JavaScript ותוספים שהותקנו לאחרונה"],
                          ev("add_to_cart")))
        elif st.get("status") == "warning":
            out.append(_f("atc_no_feedback", "journey", "medium", "medium", "אין אישור ברור אחרי 'הוספה לסל'",
                          st.get("detail", ""),
                          "לקוח שלא בטוח שהמוצר נוסף לוחץ שוב, מתבלבל או עוזב.",
                          ["הציגו הודעה/מגירת עגלה אחרי הוספה", "עדכנו את מונה הסל בכותרת"], ev("add_to_cart")))

        cart = facts.get("cart", {})
        cst = by_key.get("cart", {})
        if cart and not cart.get("reached"):
            out.append(_f("cart_unreachable", "journey", "high", "high", "לא הצלחנו להגיע לעגלה",
                          cst.get("detail", ""), "אם קשה למצוא את העגלה — הקנייה לא מושלמת.",
                          ["הוסיפו אייקון סל בולט בכותרת עם מונה פריטים"], ev("cart")))
        elif cart.get("empty"):
            out.append(_f("cart_empty_after_add", "journey", "critical", "high", "העגלה ריקה אחרי הוספת מוצר",
                          cst.get("detail", ""), "המוצר 'נעלם' — הלקוח לא יכול לקנות.",
                          ["בדקו עוגיות/סשן ותוספי מטמון שמונעים שמירת סל", "נסו את התהליך בדפדפן נקי"], ev("cart")))
        ck = facts.get("checkout", {})
        kst = by_key.get("checkout", {})
        if cart.get("reached") and not cart.get("empty"):
            if not ck.get("button_found"):
                out.append(_f("no_checkout_button", "journey", "critical", "high", "אין כפתור מעבר לקופה בעגלה",
                              kst.get("detail", ""), "לקוח עם מוצרים בעגלה לא יודע איך לשלם.",
                              ["הוסיפו כפתור 'מעבר לקופה' בולט בראש ובתחתית העגלה"], ev("cart")))
            elif not ck.get("reached"):
                out.append(_f("checkout_failed", "journey", "critical", "high", "המעבר לקופה לא עבד",
                              kst.get("detail", ""), "זו הנקודה הכי יקרה לאבד בה לקוח — הוא כבר החליט לקנות.",
                              ["בדקו את כפתור הקופה ואת חיבור סליקת התשלום"], ev("checkout")))
            else:
                if ck.get("login_required"):
                    out.append(_f("forced_login", "journey", "high", "high", "חובה להירשם כדי לקנות",
                                  "בקופה נמצא שדה סיסמה ולא נמצאה אפשרות קנייה כאורח.",
                                  "הרשמה כפויה היא אחת הסיבות המוכרות ביותר לנטישת קופה.",
                                  ["אפשרו קנייה כאורח", "הציעו הרשמה רק אחרי התשלום"], ev("checkout")))
                if ck.get("fields", 0) > 16:
                    out.append(_f("long_checkout", "journey", "medium", "medium", f"טופס קופה ארוך ({ck['fields']} שדות)",
                                  "נספרו שדות גלויים בעמוד הקופה הראשון.",
                                  "כל שדה מיותר מוסיף חיכוך ומעלה נטישה.",
                                  ["הסירו שדות לא הכרחיים (חברה, שורת כתובת 2)", "הפעילו השלמה אוטומטית לכתובת"], ev("checkout")))
                if not ck.get("payment_methods"):
                    out.append(_f("payment_methods_hidden", "trust", "low", "medium", "לא ראינו אמצעי תשלום בכניסה לקופה",
                                  "לא זוהו אזכורים של אשראי/ביט/PayPal/Apple Pay בעמוד הקופה הראשון.",
                                  "לקוחות רוצים לדעת מראש שאפשר לשלם בדרך הנוחה להם.",
                                  ["הציגו לוגואים של אמצעי התשלום בעגלה ובקופה"], ev("checkout")))

    # ---------------- חיפוש
    search = facts.get("search", {})
    if search and not search.get("available"):
        out.append(_f("no_search", "ux", "low", "medium", "אין חיפוש באתר",
                      "לא נמצאה תיבת חיפוש בעמוד הבית.",
                      "לקוחות שיודעים מה הם רוצים משתמשים בחיפוש — ונוטים לקנות יותר.",
                      ["הוסיפו חיפוש בולט בכותרת (גם במובייל)"], ev("home")))
    elif search.get("tested") and not search.get("works"):
        out.append(_f("search_broken", "ux", "medium", "medium", "החיפוש לא מוצא מוצר שקיים באתר",
                      by_key.get("search", {}).get("detail", ""),
                      "לקוח שמחפש מוצר קיים ומקבל 'אין תוצאות' — מניח שאין לכם אותו.",
                      ["בדקו את הגדרות החיפוש", "שקלו חיפוש חכם (Algolia / Searchanise / Doofinder)"], ev("search")))

    # ---------------- אמון
    tl = facts.get("trust_links", {})
    trust_rules = [
        ("returns", "no_returns_policy", "high", "high", "לא נמצא קישור למדיניות החזרות",
         "חוסר ודאות לגבי החזרה הוא סיבה מרכזית לא לקנות אונליין. בישראל חלה גם חובה חוקית לפרט מדיניות ביטול עסקה.",
         ["צרו עמוד 'החזרות וביטול עסקה' ברור", "קשרו אליו מהפוטר ומעמוד המוצר"]),
        ("shipping", "no_shipping_policy", "medium", "medium", "לא נמצא קישור למידע על משלוחים",
         "לקוחות רוצים לדעת מתי ובכמה המוצר יגיע לפני שהם מוסיפים לסל.",
         ["צרו עמוד משלוחים עם זמנים ועלויות", "קשרו אליו מהפוטר"]),
        ("privacy", "no_privacy_policy", "medium", "low", "לא נמצא קישור למדיניות פרטיות",
         "נדרש לפי חוק הגנת הפרטיות ומשפיע על תחושת הביטחון בהשארת פרטים.",
         ["הוסיפו עמוד מדיניות פרטיות וקישור בפוטר"]),
        ("terms", "no_terms", "low", "low", "לא נמצא קישור לתקנון האתר",
         "תקנון מגן על העסק ומראה רצינות.", ["הוסיפו תקנון וקישור בפוטר"]),
        ("contact", "no_contact_page", "medium", "medium", "לא נמצא קישור ל'צור קשר'",
         "לקוח שלא רואה דרך לפנות לעסק חושש שאין מי שיענה לו אם תהיה בעיה.",
         ["הוסיפו עמוד צור קשר וקישור בולט בכותרת/פוטר", "הציגו טלפון/וואטסאפ"]),
    ]
    if tl:
        for key, rid, sev, imp, title, why, fix in trust_rules:
            if not tl.get(key):
                out.append(_f(rid, "trust", sev, imp, title, "חיפשנו קישור כזה בכל הקישורים בעמוד הבית.", why, fix, ev("home")))
    if not facts.get("https"):
        out.append(_f("no_https", "trust", "critical", "high", "האתר לא מאובטח (HTTPS)",
                      f"הכתובת הסופית: {facts.get('final_url')}",
                      "הדפדפן מציג 'לא מאובטח' — לקוחות לא ישאירו פרטי אשראי.",
                      ["התקינו תעודת SSL והפנו את כל התנועה ל-https"], ev("home")))

    # ---------------- קישורים שבורים (בקשה אמיתית לכל קישור)
    links = facts.get("links") or {}
    if links.get("broken"):
        b = links["broken"]
        out.append(_f("broken_links", "technical", "high" if len(b) > 2 else "medium", "medium",
                      f"{len(b)} קישורים שבורים באתר",
                      f"מתוך {links['checked']} קישורים פנימיים שנבדקו: " + ", ".join(
                          f"{x['url']} ({x['status'] or 'אין תגובה'})" for x in b[:4]),
                      "לקוח שלוחץ ומגיע לעמוד שגיאה מאבד אמון — וגוגל מוריד את דירוג האתר.",
                      ["תקנו את הקישורים או הפנו אותם (301) לעמוד הנכון", "הסירו קישורים לעמודים שנמחקו"],
                      ev("links", broken=b[:10])))

    # ---------------- בדיקות HTML (מהחוקר הבסיסי, על ה-HTML שהדפדפן רינדר)
    existing = {f["rule_id"] for f in out}
    for issue in home.get("html_issues", []):
        if issue["id"] in _HTML_SKIP or issue["id"] in existing:
            continue
        if issue["id"] == "no_contact" and "no_contact_page" in existing:
            continue
        sev = issue["severity"]
        out.append(_f(f"html_{issue['id']}", _HTML_CATEGORY.get(issue["category"], "ux"), sev, sev,
                      issue["title"], issue["detail"], issue["sales_impact"], [issue["recommendation"]], ev("home")))
    if not home.get("html", {}).get("has_viewport", True) and mob and mob.get("horizontal_overflow"):
        pass  # כבר מכוסה ע"י mobile_overflow
    elif not home.get("html", {}).get("has_viewport", True):
        out.append(_f("no_viewport", "mobile", "high", "high", "האתר לא מוגדר למובייל (viewport)",
                      "חסרה תגית meta viewport.", "בטלפון האתר יוצג מוקטן וקשה לשימוש.",
                      ['הוסיפו <meta name="viewport" content="width=device-width, initial-scale=1">'], ev("mobile")))

    for f in out:  # שיוך סופי לחלקי הדוח לפי הטבלה השקופה
        f["category"] = RULE_CATEGORY.get(f["rule_id"], f["category"])
        if f["category"] not in CATEGORIES:
            f["category"] = "technical"
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out.sort(key=lambda f: (order[f["severity"]], f["category"]))
    return out
