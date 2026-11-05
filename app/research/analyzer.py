"""חוקר אתרים — מוריד אתר אמיתי ובודק בעיות שפוגעות במכירות.

כל הממצאים כאן מבוססים על בדיקה אמיתית של ה-HTML, הכותרות וזמני התגובה.
אין כאן ניחושים: אם משהו לא נבדק — הוא לא מופיע בדוח.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "P1-AI-SiteResearch/0.1 (+https://github.com/liadaharami007-cmd/P1)"
MAX_HTML_BYTES = 5_000_000
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

SEVERITY_WEIGHT = {"high": 15, "medium": 7, "low": 3}

CTA_WORDS = [
    "צור קשר", "צרו קשר", "קנה", "קנו", "הזמן", "הזמינו", "לרכישה", "להזמנה", "הרשמה", "הירשמו",
    "שלח", "שלחו", "לפרטים", "קבע", "קבעו", "התחל", "נסו", "הוסף לסל", "תיאום",
    "buy", "order", "contact", "book", "get started", "sign up", "subscribe", "add to cart",
    "shop", "get a quote", "schedule", "join", "request a demo", "free trial",
]

TRACKERS = {
    "Google Analytics": [r"googletagmanager\.com/gtag/js", r"google-analytics\.com", r"gtag\("],
    "Google Tag Manager": [r"googletagmanager\.com/gtm\.js", r"GTM-[A-Z0-9]+"],
    "Meta Pixel": [r"connect\.facebook\.net/.+/fbevents\.js", r"fbq\("],
    "TikTok Pixel": [r"analytics\.tiktok\.com"],
    "Hotjar": [r"static\.hotjar\.com"],
    "Microsoft Clarity": [r"clarity\.ms"],
    "LinkedIn Insight": [r"snap\.licdn\.com"],
}

PLATFORMS = {
    "WordPress": [r"wp-content/", r"wp-includes/"],
    "Shopify": [r"cdn\.shopify\.com", r"Shopify\.theme"],
    "Wix": [r"static\.wixstatic\.com", r"wix\.com"],
    "Webflow": [r"webflow\.com", r"data-wf-site"],
    "Squarespace": [r"squarespace\.com"],
    "WooCommerce": [r"woocommerce"],
    "Next.js": [r"/_next/static/"],
}


class BlockedURLError(ValueError):
    """כתובת שאסור לגשת אליה (רשת פנימית וכו')."""


@dataclass
class Issue:
    id: str
    severity: str  # high / medium / low
    category: str
    title: str
    detail: str
    sales_impact: str
    recommendation: str


@dataclass
class Report:
    requested_url: str
    ok: bool
    final_url: str | None = None
    error: str | None = None
    status_code: int | None = None
    response_ms: int | None = None
    html_bytes: int | None = None
    redirects: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    score: int | None = None
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- אבטחה
def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("לא התקבלה כתובת אתר")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"כתובת לא תקינה: {raw}")
    return raw


def _is_private_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not addr.is_global


def assert_public_host(url: str) -> None:
    """מונע גישה לכתובות פנימיות (localhost, רשת ביתית, ענן) — הגנת SSRF."""
    host = urlparse(url).hostname or ""
    if host.lower() in ("localhost",) or host.lower().endswith(".local"):
        raise BlockedURLError(f"אסור לחקור כתובת פנימית: {host}")
    try:
        ipaddress.ip_address(host)
        if _is_private_ip(host):
            raise BlockedURLError(f"אסור לחקור כתובת IP פנימית: {host}")
        return
    except ValueError as e:
        if isinstance(e, BlockedURLError):
            raise
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return  # ייתכן שה-DNS נפתר רק דרך proxy; הבקשה עצמה תיכשל אם הדומיין לא קיים
    for info in infos:
        if _is_private_ip(info[4][0]):
            raise BlockedURLError(f"הדומיין {host} מצביע לכתובת פנימית")


# ---------------------------------------------------------------- בדיקות
def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _has_word(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(r"\b" + re.escape(word) + r"\b", text) is not None
    return word in text


def _find_patterns(html: str, table: dict[str, list[str]]) -> list[str]:
    return [name for name, pats in table.items() if any(re.search(p, html, re.I) for p in pats)]


def analyze_html(html: str, base_url: str) -> tuple[dict, list[Issue]]:
    """ניתוח ה-HTML עצמו. פונקציה טהורה — קלה לבדיקה."""
    soup = BeautifulSoup(html, "html.parser")
    issues: list[Issue] = []
    host = urlparse(base_url).hostname or ""

    title = _text(soup.title)
    desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (desc_tag.get("content") or "").strip() if desc_tag else ""
    h1s = [_text(h) for h in soup.find_all("h1")]
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    html_tag = soup.find("html")
    lang = html_tag.get("lang") if html_tag else None
    robots_meta = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    og_tags = {m.get("property") for m in soup.find_all("meta", attrs={"property": re.compile("^og:")})}
    images = soup.find_all("img")
    imgs_no_alt = [i for i in images if not (i.get("alt") or "").strip()]
    forms = soup.find_all("form")
    links = soup.find_all("a", href=True)
    hrefs = [a["href"].strip() for a in links]
    tel = sorted({h[4:] for h in hrefs if h.lower().startswith("tel:")})
    mailto = sorted({h[7:].split("?")[0] for h in hrefs if h.lower().startswith("mailto:")})
    whatsapp = any(re.search(r"(wa\.me|api\.whatsapp\.com|whatsapp:)", h, re.I) for h in hrefs)
    internal_links, external_links = set(), set()
    for h in hrefs:
        if h.startswith(("#", "tel:", "mailto:", "javascript:")):
            continue
        absu = urljoin(base_url, h).split("#")[0]
        (internal_links if urlparse(absu).hostname == host else external_links).add(absu)
    clickables = [_text(el).lower() for el in soup.find_all(["a", "button"])]
    clickables += [(i.get("value") or "").lower() for i in soup.find_all("input", attrs={"type": "submit"})]
    ctas = sorted({c for c in clickables if c and len(c) < 60 and any(_has_word(c, w) for w in CTA_WORDS)})
    head = soup.head
    head_scripts = head.find_all("script", src=True) if head else []
    blocking_scripts = [s for s in head_scripts if not (s.has_attr("async") or s.has_attr("defer")
                                                        or s.get("type") == "module")]
    json_ld = soup.find_all("script", attrs={"type": "application/ld+json"})
    favicon = soup.find("link", rel=lambda v: v and "icon" in (v if isinstance(v, list) else [v]))
    body_text = _text(soup.body) if soup.body else _text(soup)
    trackers = _find_patterns(html, TRACKERS)
    platforms = _find_patterns(html, PLATFORMS)

    facts = {
        "title": title,
        "meta_description": description,
        "h1": h1s[:5],
        "lang": lang,
        "has_viewport": bool(viewport),
        "word_count": len(body_text.split()),
        "images": len(images),
        "images_without_alt": len(imgs_no_alt),
        "forms": len(forms),
        "internal_links": len(internal_links),
        "external_links": len(external_links),
        "phones": tel[:5],
        "emails": mailto[:5],
        "whatsapp_link": whatsapp,
        "cta_texts": ctas[:15],
        "tracking_tools": trackers,
        "platform": platforms,
        "open_graph_tags": sorted(t for t in og_tags if t),
        "structured_data_blocks": len(json_ld),
        "render_blocking_scripts": len(blocking_scripts),
        "has_favicon": bool(favicon),
    }

    def add(*args):
        issues.append(Issue(*args))

    if not title:
        add("no_title", "high", "SEO", "לאתר אין כותרת (title)",
            "תגית <title> חסרה או ריקה.",
            "גוגל מציג את הכותרת בתוצאות החיפוש. בלעדיה פחות אנשים לוחצים ומגיעים לאתר.",
            "הוסיפו כותרת של 30–60 תווים שכוללת את השירות/המוצר ואת שם העסק.")
    elif len(title) > 65 or len(title) < 15:
        add("title_length", "low", "SEO", "אורך הכותרת לא אופטימלי",
            f"אורך הכותרת {len(title)} תווים: \"{title[:80]}\"",
            "כותרת קצרה מדי לא מסבירה מה מוכרים; ארוכה מדי נחתכת בגוגל.",
            "שמרו על 30–60 תווים עם מילת המפתח החשובה בהתחלה.")
    if not description:
        add("no_meta_description", "medium", "SEO", "אין תיאור (meta description)",
            "תגית meta description חסרה.",
            "גוגל ימציא תקציר בעצמו — לרוב פחות משכנע, ופחות קליקים מגיעים לאתר.",
            "כתבו תיאור של 120–160 תווים שמסביר את היתרון ומזמין לפעולה.")
    if not h1s:
        add("no_h1", "medium", "תוכן", "אין כותרת ראשית (H1) בעמוד",
            "לא נמצאה תגית <h1>.",
            "מבקר שנכנס צריך להבין תוך שניות מה מוצע לו. בלי כותרת ראשית ברורה — הוא עוזב.",
            "הוסיפו H1 אחד שאומר בבירור מה העסק עושה ולמי.")
    elif len(h1s) > 1:
        add("multiple_h1", "low", "תוכן", f"יש {len(h1s)} כותרות H1",
            "; ".join(h[:50] for h in h1s[:4]),
            "מסר מפוזר מקשה על המבקר ועל גוגל להבין מה הדבר הכי חשוב בעמוד.",
            "השאירו H1 אחד והפכו את השאר ל-H2.")
    if not viewport:
        add("no_viewport", "high", "מובייל", "האתר לא מותאם למובייל (אין viewport)",
            "חסרה תגית <meta name=\"viewport\">.",
            "רוב הגולשים מגיעים מהטלפון. אתר שלא מותאם נראה קטן ושבור — והם עוזבים בלי לקנות.",
            "הוסיפו <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> ובדקו עיצוב רספונסיבי.")
    if not (tel or mailto or whatsapp or forms):
        add("no_contact", "high", "המרות", "אין דרך ליצור קשר מהעמוד",
            "לא נמצאו טלפון לחיץ, מייל, וואטסאפ או טופס.",
            "לקוח שמעוניין לא יודע איך לפנות — זה אובדן ישיר של לידים ומכירות.",
            "הוסיפו כפתור וואטסאפ / טלפון לחיץ וטופס קצר בראש העמוד.")
    elif not tel and not whatsapp:
        add("no_quick_contact", "medium", "המרות", "אין טלפון לחיץ או וואטסאפ",
            "נמצאו רק: " + ", ".join(x for x in ("טופס" if forms else "", "מייל" if mailto else "") if x),
            "בטלפון, לקוחות מעדיפים ללחוץ ולהתקשר/לשלוח הודעה. כל צעד נוסף מוריד פניות.",
            "הוסיפו קישור tel: ו/או wa.me בולט, במיוחד במובייל.")
    if not ctas:
        add("no_cta", "high", "המרות", "לא נמצא כפתור קריאה לפעולה (CTA)",
            "לא נמצאו כפתורים/קישורים עם טקסט כמו \"צור קשר\", \"הזמן\", \"קנה\".",
            "בלי הנחיה ברורה מה לעשות עכשיו — רוב המבקרים פשוט עוזבים.",
            "הוסיפו כפתור בולט עם פעולה ברורה (\"קבעו שיחת ייעוץ\", \"הזמינו עכשיו\").")
    if not trackers:
        add("no_tracking", "high", "שיווק", "אין כלי מדידה (Analytics / Pixel)",
            "לא זוהו Google Analytics, Tag Manager, Meta Pixel או כלים דומים.",
            "אי אפשר לדעת מאיפה מגיעים לקוחות ואיזה פרסום עובד — כסף שיווקי נשרף בעיוורון.",
            "התקינו Google Analytics 4 (דרך GTM) ו-Meta Pixel אם מפרסמים בפייסבוק/אינסטגרם.")
    if images and imgs_no_alt:
        sev = "medium" if len(imgs_no_alt) / len(images) > 0.5 else "low"
        add("img_alt", sev, "נגישות", f"{len(imgs_no_alt)} מתוך {len(images)} תמונות בלי טקסט חלופי",
            "תמונות ללא מאפיין alt.",
            "פוגע בנגישות (חובה חוקית בישראל לעסקים רבים) ובהופעה בחיפוש תמונות בגוגל.",
            "הוסיפו alt תיאורי לכל תמונה משמעותית.")
    if not og_tags:
        add("no_og", "low", "שיווק", "אין תגיות שיתוף לרשתות (Open Graph)",
            "לא נמצאו תגיות og:title / og:image.",
            "כשמשתפים את האתר בוואטסאפ/פייסבוק הוא מופיע בלי תמונה וכותרת מושכת — פחות קליקים.",
            "הוסיפו og:title, og:description, og:image.")
    if robots_meta and "noindex" in (robots_meta.get("content") or "").lower():
        add("noindex", "high", "SEO", "העמוד חסום לגוגל (noindex)",
            f"meta robots = {robots_meta.get('content')}",
            "גוגל לא יציג את העמוד בתוצאות — אין תנועה אורגנית בכלל.",
            "הסירו noindex אם העמוד אמור להופיע בגוגל.")
    if not lang:
        add("no_lang", "low", "נגישות", "לא הוגדרה שפת העמוד",
            "חסר מאפיין lang בתגית <html>.",
            "קוראי מסך ומנועי חיפוש עלולים לפרש את העמוד בשפה שגויה.",
            "הוסיפו <html lang=\"he\" dir=\"rtl\"> (או השפה המתאימה).")
    if len(blocking_scripts) > 5:
        add("blocking_scripts", "medium", "מהירות", f"{len(blocking_scripts)} סקריפטים חוסמים בטעינה",
            "סקריפטים ב-<head> בלי async/defer.",
            "העמוד מוצג לאט יותר; כל שנייה של עיכוב מורידה המרות.",
            "הוסיפו defer/async לסקריפטים שאינם קריטיים.")
    if not json_ld:
        add("no_structured_data", "low", "SEO", "אין נתונים מובנים (Schema.org)",
            "לא נמצא JSON-LD.",
            "פספוס של הצגה עשירה בגוגל (כוכבים, מחיר, שעות פתיחה) שמגדילה קליקים.",
            "הוסיפו LocalBusiness / Product / Organization ב-JSON-LD.")
    if not favicon:
        add("no_favicon", "low", "אמון", "אין אייקון לאתר (favicon)",
            "לא נמצא <link rel=\"icon\">.",
            "אתר בלי אייקון נראה פחות מקצועי בלשונית ובתוצאות החיפוש בנייד.",
            "הוסיפו favicon עם הלוגו.")
    if facts["word_count"] < 150:
        add("thin_content", "medium", "תוכן", "מעט מאוד טקסט בעמוד",
            f"נמצאו כ-{facts['word_count']} מילים בלבד (ייתכן שהתוכן נטען רק ב-JavaScript).",
            "מבקרים וגוגל לא מקבלים מספיק מידע כדי להשתכנע ולדרג את העמוד.",
            "הוסיפו הסבר על השירות, יתרונות, המלצות ושאלות נפוצות; ודאו שהתוכן קיים ב-HTML.")
    return facts, issues


def score_from_issues(issues: list[Issue]) -> int:
    return max(0, 100 - sum(SEVERITY_WEIGHT.get(i.severity, 0) for i in issues))


# ---------------------------------------------------------------- הרצה
async def _check_resource(client: httpx.AsyncClient, url: str) -> int | None:
    try:
        r = await client.get(url)
        return r.status_code
    except (httpx.HTTPError, BlockedURLError):
        return None


async def analyze_url(raw_url: str, *, allow_private: bool = False,
                      check_links: int = 10, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """חוקר כתובת אמיתית ומחזיר דוח (dict). לא זורק חריגות על כשל רשת — מחזיר ok=False עם הסבר."""
    try:
        url = normalize_url(raw_url)
        if not allow_private:
            assert_public_host(url)
    except ValueError as e:
        return Report(requested_url=raw_url, ok=False, error=str(e)).to_dict()

    report = Report(requested_url=url, ok=False)

    async def _guard(request: httpx.Request):  # בודק גם כל הפניה (redirect)
        if not allow_private:
            assert_public_host(str(request.url))

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [_guard]}, transport=transport, max_redirects=8,
    ) as client:
        start = time.perf_counter()
        try:
            resp = await client.get(url)
        except BlockedURLError as e:
            report.error = str(e)
            return report.to_dict()
        except httpx.HTTPError as e:
            report.error = f"לא הצלחתי להתחבר לאתר: {type(e).__name__}: {e}"
            return report.to_dict()
        elapsed = int((time.perf_counter() - start) * 1000)

        report.status_code = resp.status_code
        report.response_ms = elapsed
        report.final_url = str(resp.url)
        report.redirects = [str(r.url) for r in resp.history]
        content = resp.content[:MAX_HTML_BYTES]
        report.html_bytes = len(resp.content)
        issues: list[Issue] = []

        if resp.status_code >= 400:
            report.error = f"האתר החזיר שגיאה {resp.status_code}"
            issues.append(Issue("http_error", "high", "זמינות", f"העמוד מחזיר שגיאה {resp.status_code}",
                                f"בקשה ל-{url} החזירה {resp.status_code}.",
                                "לקוח שמגיע לעמוד שבור לא יקנה — וגם גוגל יוריד אותו מהתוצאות.",
                                "בדקו את השרת/הקישור ותקנו את העמוד."))
            report.issues = [asdict(i) for i in issues]
            report.score = score_from_issues(issues)
            return report.to_dict()

        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype.lower():
            report.error = f"הכתובת לא מחזירה דף HTML (content-type: {ctype})"
            return report.to_dict()

        html = content.decode(resp.encoding or "utf-8", errors="replace")
        final = str(resp.url)
        facts, issues = analyze_html(html, final)

        if urlparse(final).scheme != "https":
            issues.append(Issue("no_https", "high", "אמון", "האתר לא מאובטח (אין HTTPS)",
                                f"הכתובת הסופית היא {final}",
                                "דפדפנים מציגים \"לא מאובטח\" — לקוחות חוששים להשאיר פרטים או לשלם.",
                                "התקינו תעודת SSL (חינם ב-Let's Encrypt) והפנו את כל התנועה ל-https."))
        if elapsed > 3000:
            issues.append(Issue("slow", "high", "מהירות", f"השרת איטי: {elapsed / 1000:.1f} שניות לתגובה",
                                "זמן עד קבלת ה-HTML המלא (לא כולל תמונות וסקריפטים).",
                                "כל שנייה של המתנה מורידה משמעותית את אחוז הקונים; רבים עוזבים אחרי 3 שניות.",
                                "בדקו אחסון, מטמון (cache) ו-CDN."))
        elif elapsed > 1500:
            issues.append(Issue("slowish", "medium", "מהירות", f"זמן תגובה בינוני: {elapsed / 1000:.1f} שניות",
                                "זמן עד קבלת ה-HTML המלא.",
                                "עיכובים קטנים מצטברים לפחות המרות, במיוחד במובייל.",
                                "שקלו מטמון ו-CDN."))
        if report.html_bytes and report.html_bytes > 1_500_000:
            issues.append(Issue("heavy_html", "medium", "מהירות",
                                f"קובץ ה-HTML כבד: {report.html_bytes // 1024}KB",
                                "גודל ה-HTML בלבד, בלי תמונות.",
                                "עמוד כבד נטען לאט בסלולר.", "צמצמו קוד מוטמע וסקריפטים."))

        # robots.txt, sitemap.xml וקישורים פנימיים — במקביל
        origin = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
        soup = BeautifulSoup(html, "html.parser")
        host = urlparse(final).hostname
        internal = []
        for a in soup.find_all("a", href=True):
            h = a["href"].strip()
            if h.startswith(("#", "tel:", "mailto:", "javascript:")):
                continue
            absu = urljoin(final, h).split("#")[0]
            if urlparse(absu).hostname == host and absu.rstrip("/") != final.rstrip("/") and absu not in internal:
                internal.append(absu)
        to_check = internal[:check_links]
        results = await asyncio.gather(
            _check_resource(client, origin + "/robots.txt"),
            _check_resource(client, origin + "/sitemap.xml"),
            *[_check_resource(client, u) for u in to_check],
        )
        robots_status, sitemap_status, link_statuses = results[0], results[1], results[2:]
        facts["robots_txt"] = robots_status == 200
        facts["sitemap_xml"] = sitemap_status == 200
        broken = [u for u, s in zip(to_check, link_statuses) if s is None or s >= 400]
        facts["links_checked"] = len(to_check)
        facts["broken_links"] = broken
        if not facts["sitemap_xml"]:
            issues.append(Issue("no_sitemap", "low", "SEO", "לא נמצא sitemap.xml",
                                f"{origin}/sitemap.xml החזיר {sitemap_status}",
                                "גוגל מגלה עמודים חדשים לאט יותר.", "צרו מפת אתר ושלחו אותה ב-Search Console."))
        if not facts["robots_txt"]:
            issues.append(Issue("no_robots", "low", "SEO", "לא נמצא robots.txt",
                                f"{origin}/robots.txt החזיר {robots_status}",
                                "פחות שליטה על איך גוגל סורק את האתר.", "הוסיפו robots.txt בסיסי עם קישור ל-sitemap."))
        if broken:
            issues.append(Issue("broken_links", "high" if len(broken) > 2 else "medium", "זמינות",
                                f"{len(broken)} קישורים שבורים (מתוך {len(to_check)} שנבדקו)",
                                ", ".join(broken[:5]),
                                "לקוח שלוחץ ומגיע לשגיאה מאבד אמון ועוזב.", "תקנו או הסירו את הקישורים."))

        report.ok = True
        report.facts = facts
        order = {"high": 0, "medium": 1, "low": 2}
        issues.sort(key=lambda i: order.get(i.severity, 3))
        report.issues = [asdict(i) for i in issues]
        report.score = score_from_issues(issues)
        return report.to_dict()
