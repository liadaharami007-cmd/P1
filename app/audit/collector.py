"""אוסף הנתונים — מבקר באתר בדפדפן אמיתי ומתעד מה קרה בפועל.

הקובץ הזה רק *מודד ומתעד* (עובדות + צילומי מסך + שלבי מסע רכישה).
הוא לא מסיק מסקנות — את זה עושים rules.py ו-personas.py.

כללי בטיחות:
- לעולם לא ממלאים פרטים אישיים ולא מבצעים הזמנה. המסע נעצר בכניסה לקופה.
- כל בקשה מהדפדפן עוברת דרך HostGuard (חסימת כתובות פנימיות).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import Error as PWError
from playwright.async_api import TimeoutError as PWTimeout

from ..research.analyzer import analyze_html
from .browser import HostGuard, launch, new_context

ProgressCb = Callable[[str, str], Awaitable[None]]
# (kind, message, page_url, screenshot_id) — יומן פעולות חי של הסוכן
EventCb = Callable[[str, str, str | None, str | None], Awaitable[None]]

MAX_NAVIGATIONS = 30        # הגבלת משאבים: מספר מעברי עמוד מקסימלי לבדיקה
MAX_LINKS_TO_CHECK = 25     # קישורים פנימיים לבדיקת "קישור שבור"
EXCERPT_CHARS = 2500        # טקסט עמוד שנשמר כראיה לניתוח AI

# ---------------------------------------------------------------- תבניות זיהוי
PRODUCT_URL_RE = re.compile(r"/(products?|item|items|p|dp|מוצר|מוצרים|product-page)/[^/?#]{2,}", re.I)
PRODUCT_QS_RE = re.compile(r"[?&](product|product_id|add-to-cart)=", re.I)
CATEGORY_URL_RE = re.compile(r"/(collections?|categor(y|ies)|product-category|shop|store|catalog|חנות|קטגוריה)(/|$|\?)", re.I)
ATC_TEXT_RE = re.compile(r"(הוסף|הוספה|הוסיפו|הוסיפי)\s*(ל)?\s*(סל|עגלה|עגלת)|add\s+to\s+(cart|bag|basket)|קנה\s+עכשיו|קנו\s+עכשיו|buy\s+now|לרכישה|הזמינו\s+עכשיו", re.I)
CHECKOUT_TEXT_RE = re.compile(r"לקופה|מעבר\s+לקופה|המשך\s+לתשלום|המשך\s+לקופה|לתשלום|checkout|check\s+out|proceed\s+to", re.I)
CART_TEXT_RE = re.compile(r"^(סל|סל\s+הקניות|העגלה|עגלה|עגלת\s+קניות|cart|basket|bag|view\s+cart|לסל|לעגלה|צפייה\s+בסל|מעבר\s+לסל)\b", re.I)
EMPTY_CART_RE = re.compile(r"(הסל|העגלה|סל\s+הקניות)\s+(שלך\s+)?ריק|your\s+(cart|bag|basket)\s+is\s+(currently\s+)?empty|cart\s+is\s+empty|אין\s+מוצרים\s+בסל", re.I)
PRICE_RE = re.compile(r"(₪|ש\"ח|ש״ח|ils|nis|\$|€|£|usd|eur)\s*\d[\d,.]*|\d[\d,.]*\s*(₪|ש\"ח|ש״ח|ils|nis|\$|€|£)", re.I)
PAYMENT_RE = re.compile(r"paypal|apple\s*pay|google\s*pay|\bbit\b|ביט|visa|mastercard|כרטיס\s+אשראי|אשראי|תשלומים|klarna|shop\s*pay|amex", re.I)
TRUST_LINKS = {
    "returns": re.compile(r"החזר|החלפ|ביטול\s+עסקה|returns?|refund|exchange", re.I),
    "shipping": re.compile(r"משלוח|משלוחים|shipping|delivery", re.I),
    "privacy": re.compile(r"פרטיות|privacy", re.I),
    "terms": re.compile(r"תקנון|תנאי\s+שימוש|terms", re.I),
    "contact": re.compile(r"צור\s+קשר|צרו\s+קשר|contact", re.I),
    "about": re.compile(r"אודות|מי\s+אנחנו|about", re.I),
    "faq": re.compile(r"שאלות\s+נפוצות|faq", re.I),
    "accessibility": re.compile(r"נגישות|accessibility", re.I),
}

PERF_INIT_SCRIPT = """
window.__p1 = {lcp: 0, cls: 0};
try {
  new PerformanceObserver(l => { for (const e of l.getEntries()) window.__p1.lcp = e.startTime; })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__p1.cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""

PAGE_FACTS_JS = r"""
() => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource');
  // חלון קופץ שמכסה את המסך
  let overlay = null;
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if ((s.position === 'fixed' || s.position === 'sticky') && visible(el)) {
      const r = el.getBoundingClientRect();
      const cover = (Math.min(r.right, vw) - Math.max(r.left, 0)) * (Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh);
      if (cover > 0.45 && (el.innerText || '').trim().length > 0) { overlay = {cover: Math.round(cover * 100), text: el.innerText.trim().slice(0, 120)}; break; }
    }
  }
  const clickables = [...document.querySelectorAll('a[href], button, input[type=submit], [role=button]')].filter(visible);
  const small = clickables.filter(el => { const r = el.getBoundingClientRect(); return r.height < 24 || r.width < 24; }).length;
  const aboveFold = clickables.filter(el => el.getBoundingClientRect().top < vh).length;
  const searchInput = !!document.querySelector('input[type=search], input[name=q], input[name=s], input[name=search], input[placeholder*="חיפוש"], input[placeholder*="חפש"], input[placeholder*="earch"], [role=search] input');
  const navLinks = document.querySelectorAll('nav a[href], header a[href], [role=navigation] a[href]').length;
  return {
    timing: { ttfb: Math.round(nav.responseStart || 0), dom_ready: Math.round(nav.domContentLoadedEventEnd || 0),
              load: Math.round(nav.loadEventEnd || 0), lcp: Math.round((window.__p1 || {}).lcp || 0),
              cls: Math.round(((window.__p1 || {}).cls || 0) * 1000) / 1000 },
    resources: res.length,
    transfer_kb: Math.round((res.reduce((a, r) => a + (r.transferSize || 0), 0) + (nav.transferSize || 0)) / 1024),
    horizontal_overflow: document.documentElement.scrollWidth > vw + 2,
    scroll_width: document.documentElement.scrollWidth, viewport_width: vw,
    overlay, clickables: clickables.length, small_tap_targets: small, clickables_above_fold: aboveFold,
    has_search: searchInput, nav_links: navLinks,
    links: [...document.querySelectorAll('a[href]')].slice(0, 1500).map(a => ({href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80)})),
    text: (document.body ? document.body.innerText : '').slice(0, 60000),
  };
}
"""

PRODUCT_FACTS_JS = r"""
() => {
  const vh = window.innerHeight;
  const ld = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); const arr = Array.isArray(j) ? j : (j['@graph'] || [j]); ld.push(...arr); } catch (e) {}
  }
  const product = ld.find(x => x && (x['@type'] === 'Product' || (Array.isArray(x['@type']) && x['@type'].includes('Product'))));
  const og = (p) => (document.querySelector(`meta[property="${p}"]`) || {}).content || null;
  const imgs = [...document.querySelectorAll('img')].filter(i => { const r = i.getBoundingClientRect(); return r.width >= 150 && r.height >= 150; });
  const h1 = document.querySelector('h1');
  const itemprop = document.querySelector('[itemprop=price]');
  return {
    jsonld_product: !!product,
    jsonld_name: product ? product.name : null,
    jsonld_rating: !!(product && product.aggregateRating),
    jsonld_price: product && product.offers ? (Array.isArray(product.offers) ? product.offers[0].price : product.offers.price) || null : null,
    og_type: og('og:type'), og_price: og('product:price:amount') || og('og:price:amount'),
    itemprop_price: itemprop ? (itemprop.getAttribute('content') || itemprop.textContent || '').trim() : null,
    h1: h1 ? h1.innerText.trim().slice(0, 150) : null,
    large_images: imgs.length,
    has_table: !!document.querySelector('table, dl'),
    selects: document.querySelectorAll('form select').length,
    text: (document.body ? document.body.innerText : '').slice(0, 60000),
  };
}
"""


@dataclass
class Step:
    key: str
    title: str
    status: str = "skipped"  # passed / failed / warning / skipped
    detail: str = ""
    page_url: str | None = None
    duration_ms: int | None = None
    screenshot_id: str | None = None


@dataclass
class Collected:
    facts: dict = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    screenshots: list[dict] = field(default_factory=list)


class Collector:
    def __init__(self, start_url: str, shot_dir: Path, *, allow_private: bool = False,
                 progress: ProgressCb | None = None,
                 save_screenshot: Callable[[str, str, str | None, str], str] | None = None,
                 on_event: EventCb | None = None):
        self.start_url = start_url
        self.origin = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
        self.host = urlparse(start_url).hostname
        self.shot_dir = shot_dir
        self.guard = HostGuard(allow_private)
        self.progress = progress
        self.save_screenshot = save_screenshot  # (label, device, page_url, path) -> screenshot_id
        self.out = Collected()
        self.console_errors: list[str] = []
        self.js_errors: list[str] = []
        self.unreachable: list[str] = []  # משאבים שלא נטענו (רשת/חסימה) — לא נחשבים באג של האתר
        self.failed_requests: list[str] = []
        self.cart_signals: list[str] = []
        self.on_event = on_event
        self.navigations = 0
        self._logged_steps = 0
        self.excerpts: dict[str, str] = {}

    # ------------------------------------------------------------ עזר
    async def _report(self, key: str, msg: str):
        if self.progress:
            await self.progress(key, msg)

    async def _log(self, kind: str, message: str, url: str | None = None, shot: str | None = None):
        if self.on_event:
            await self.on_event(kind, message, url, shot)

    async def _flush_steps(self):
        """מתעד ביומן כל שלב שהסתיים מאז הקריאה הקודמת."""
        for st in self.out.steps[self._logged_steps:]:
            await self._log(f"step_{st.status}", f"{st.title}: {st.detail}", st.page_url, st.screenshot_id)
        self._logged_steps = len(self.out.steps)

    async def _excerpt(self, page: Page, key: str):
        try:
            txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
            self.excerpts[key] = re.sub(r"\s+", " ", txt)[:EXCERPT_CHARS]
        except PWError:
            pass

    def _step(self, key: str, title: str) -> Step:
        st = Step(key, title)
        self.out.steps.append(st)
        return st

    async def _shot(self, page: Page, label: str, device: str, full_page: bool = False) -> str | None:
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        path = self.shot_dir / f"{len(self.out.screenshots):02d}-{label}-{device}.jpg"
        try:
            await page.screenshot(path=str(path), type="jpeg", quality=70, full_page=full_page, timeout=15000)
        except PWError:
            return None
        sid = self.save_screenshot(label, device, page.url, str(path)) if self.save_screenshot else None
        self.out.screenshots.append({"id": sid, "label": label, "device": device, "page_url": page.url, "path": str(path)})
        await self._log("screenshot", f"צילום מסך: {label} ({'טלפון' if device == 'mobile' else 'מחשב'})", page.url, sid)
        return sid

    def _same_site(self, url: str) -> bool:
        h = urlparse(url).hostname or ""
        base = (self.host or "").removeprefix("www.")
        return h == self.host or h.removeprefix("www.") == base

    def _watch(self, page: Page):
        def on_console(m):
            if m.type != "error" or len(self.console_errors) >= 30:
                return
            # כשל טעינת משאב מדווח בנפרד (failed_requests / unreachable) — לא שגיאת קוד
            if "Failed to load resource" in m.text:
                return
            self.console_errors.append(m.text[:200])
        page.on("console", on_console)
        page.on("pageerror", lambda e: len(self.js_errors) < 30 and self.js_errors.append(str(e)[:200]))

        def on_failed(req):
            err = (req.failure or "")
            if len(self.unreachable) < 30:
                self.unreachable.append(f"{err} {req.url[:120]}")
        page.on("requestfailed", on_failed)

        def on_response(r):
            if r.status >= 400 and self._same_site(r.url) and len(self.failed_requests) < 30:
                self.failed_requests.append(f"{r.status} {r.url[:150]}")
        page.on("response", on_response)

        def on_request(req):
            u = req.url.lower()
            if req.method == "POST" and re.search(r"cart|basket|add-to-cart|add_to_cart|wc-ajax", u):
                self.cart_signals.append(f"POST {req.url[:120]}")
        page.on("request", on_request)

    @staticmethod
    async def _settle(page: Page, ms: int = 4000):
        try:
            await page.wait_for_load_state("networkidle", timeout=ms)
        except PWTimeout:
            pass

    async def _goto(self, page: Page, url: str) -> tuple[bool, str, int]:
        if self.navigations >= MAX_NAVIGATIONS:
            return False, "הגענו למגבלת מעברי העמוד לבדיקה אחת", 0
        self.navigations += 1
        await self._log("navigate", "פותח עמוד", url)
        t = time.perf_counter()
        try:
            resp = await page.goto(url, wait_until="load")
        except PWTimeout:
            await self._log("error", "הדף לא סיים להיטען תוך 45 שניות", url)
            return False, "הדף לא סיים להיטען תוך 45 שניות", int((time.perf_counter() - t) * 1000)
        except PWError as e:
            msg = str(e).split("\n")[0]
            if "ERR_BLOCKED_BY_CLIENT" in msg:
                msg = "הכתובת חסומה (כתובת פנימית)"
            await self._log("error", f"שגיאת טעינה: {msg[:150]}", url)
            return False, f"שגיאת טעינה: {msg[:200]}", int((time.perf_counter() - t) * 1000)
        await self._settle(page)
        ms = int((time.perf_counter() - t) * 1000)
        if resp is not None and resp.status >= 400:
            await self._log("error", f"השרת החזיר שגיאה {resp.status}", url)
            return False, f"השרת החזיר שגיאה {resp.status}", ms
        await self._log("loaded", f"העמוד נטען ({ms / 1000:.1f} שנ')", page.url)
        return True, "", ms

    # ------------------------------------------------------------ הרצה
    async def run(self) -> Collected:
        f = self.out.facts
        f["start_url"] = self.start_url
        f["blocked_hosts"] = self.guard.blocked
        async with async_playwright() as pw:
            browser = await launch(pw)
            try:
                desktop = await new_context(browser, self.guard)
                await desktop.add_init_script(PERF_INIT_SCRIPT)
                page = await desktop.new_page()
                self._watch(page)
                ok = await self._home(page)
                await self._flush_steps()
                if ok:
                    await self._excerpt(page, "home")
                    await self._trust(f["home"]["links"])
                    await self._links(desktop, f["home"]["links"])
                    await self._flush_steps()
                    product_url = await self._find_product(page)
                    if product_url:
                        await self._excerpt(page, "product")
                    await self._flush_steps()
                    if product_url:
                        await self._add_to_cart(page)
                        await self._flush_steps()
                        await self._cart_and_checkout(page)
                    else:
                        for key, title in (("add_to_cart", "הוספה לסל"), ("cart", "מעבר לסל"), ("checkout", "כניסה לקופה")):
                            st = self._step(key, title)
                            st.detail = "דולג — לא נמצא עמוד מוצר"
                    await self._flush_steps()
                    await self._search(page)
                    await self._flush_steps()
                    await self._log("device", "עובר לבדיקה בטלפון (iPhone 13)")
                    mobile = await new_context(browser, self.guard, pw.devices["iPhone 13"] | {"locale": "he-IL"})
                    await mobile.add_init_script(PERF_INIT_SCRIPT)
                    await self._mobile(mobile, f.get("product", {}).get("url"))
                    await mobile.close()
                    await self._flush_steps()
                await desktop.close()
            finally:
                await browser.close()
        f["console_errors"] = self.console_errors
        f["js_errors"] = self.js_errors
        f["unreachable_resources"] = self.unreachable
        f["failed_requests"] = self.failed_requests
        f["navigations"] = self.navigations
        f["page_excerpts"] = self.excerpts
        # הטקסט המלא משמש רק לניתוח — לא שומרים אותו
        for k in ("home", "product", "mobile"):
            if k in f:
                f[k].pop("text", None)
                f[k].pop("links", None)
        return self.out

    async def _home(self, page: Page) -> bool:
        await self._report("home", "טוען את עמוד הבית בדפדפן מחשב…")
        st = self._step("home", "טעינת עמוד הבית (מחשב)")
        ok, err, ms = await self._goto(page, self.start_url)
        st.duration_ms, st.page_url = ms, page.url
        st.screenshot_id = await self._shot(page, "home", "desktop")
        if not ok:
            st.status, st.detail = "failed", err
            self.out.facts["home_error"] = err
            return False
        data = await page.evaluate(PAGE_FACTS_JS)
        html = await page.content()
        html_facts, html_issues = analyze_html(html, page.url)
        self.out.facts["home"] = {**data, "url": page.url, "load_ms": ms, "html": html_facts,
                                  "html_issues": [i.__dict__ for i in html_issues]}
        self.out.facts["final_url"] = page.url
        self.out.facts["https"] = page.url.startswith("https://")
        st.status = "passed"
        lcp = data["timing"]["lcp"] or data["timing"]["load"]
        st.detail = f"נטען תוך {ms / 1000:.1f} שנ' (LCP {lcp / 1000:.1f} שנ'), {data['resources']} משאבים"
        return True

    async def _trust(self, links: list[dict]):
        st = self._step("trust", "דפי אמון ומדיניות")
        found: dict[str, str | None] = {}
        for key, rx in TRUST_LINKS.items():
            hit = next((l for l in links if rx.search(l["text"] or "") or rx.search(urlparse(l["href"]).path)), None)
            found[key] = hit["href"] if hit else None
        self.out.facts["trust_links"] = found
        missing = [k for k in ("returns", "shipping", "privacy", "terms", "contact") if not found[k]]
        st.status = "passed" if not missing else "warning"
        names = {"returns": "החזרות", "shipping": "משלוחים", "privacy": "פרטיות", "terms": "תקנון", "contact": "צור קשר"}
        st.detail = "נמצאו כל הקישורים החשובים" if not missing else "חסרים קישורים: " + ", ".join(names[m] for m in missing)

    async def _links(self, ctx: BrowserContext, links: list[dict]):
        """בדיקת קישורים שבורים: בקשה אמיתית לכל קישור פנימי (עד MAX_LINKS_TO_CHECK). לא עוקבים אחרי הפניות."""
        st = self._step("links", "בדיקת קישורים פנימיים")
        urls: list[str] = []
        for l in links:
            u = l["href"].split("#")[0]
            if (u and u not in urls and self._same_site(u) and u.startswith(("http://", "https://"))
                    and not re.search(r"logout|signout|add-to-cart|/cart/add|wp-admin|\?replytocom", u, re.I)):
                urls.append(u)
        urls = urls[:MAX_LINKS_TO_CHECK]
        await self._report("links", f"בודק {len(urls)} קישורים פנימיים…")
        sem = asyncio.Semaphore(5)

        async def check(u: str) -> tuple[str, int | None, str | None]:
            if not await self.guard.is_allowed(u):
                return u, None, "blocked"
            async with sem:
                try:
                    r = await ctx.request.get(u, max_redirects=0, timeout=12000)
                    return u, r.status, None
                except PWError as e:
                    return u, None, str(e).splitlines()[0][:100]
        results = await asyncio.gather(*(check(u) for u in urls))
        broken = [{"url": u, "status": code, "error": err} for u, code, err in results
                  if err != "blocked" and (code is None or code >= 400)]
        self.out.facts["links"] = {"checked": len(urls), "broken": broken}
        if not urls:
            st.status, st.detail = "skipped", "לא נמצאו קישורים פנימיים לבדיקה"
        elif broken:
            st.status = "failed" if len(broken) > 2 else "warning"
            st.detail = f"{len(broken)} מתוך {len(urls)} קישורים שבורים"
        else:
            st.status, st.detail = "passed", f"כל {len(urls)} הקישורים שנבדקו תקינים"

    def _product_candidates(self, links: list[dict]) -> tuple[list[str], list[str]]:
        products, categories, seen = [], [], set()
        for l in links:
            href = l["href"].split("#")[0]
            if not href or href in seen or not self._same_site(href):
                continue
            seen.add(href)
            path = urlparse(href).path + ("?" + urlparse(href).query if urlparse(href).query else "")
            if PRODUCT_URL_RE.search(path) or PRODUCT_QS_RE.search(path):
                products.append(href)
            elif CATEGORY_URL_RE.search(path):
                categories.append(href)
        return products, categories

    async def _looks_like_product(self, page: Page) -> tuple[bool, dict]:
        data = await page.evaluate(PRODUCT_FACTS_JS)
        atc = await self._find_atc(page)
        price = bool(data["jsonld_price"] or data["og_price"] or data["itemprop_price"] or PRICE_RE.search(data["text"][:20000]))
        score = sum([data["jsonld_product"], (data["og_type"] or "").startswith("product"), atc is not None, price])
        data["has_atc"] = atc is not None
        data["price_visible"] = price
        return score >= 2, data

    async def _find_product(self, page: Page) -> str | None:
        await self._report("product", "מחפש עמוד מוצר…")
        st = self._step("product", "מציאת עמוד מוצר")
        links = self.out.facts["home"]["links"]
        products, categories = self._product_candidates(links)
        tried = 0
        t0 = time.perf_counter()
        # אם אין קישורי מוצר בעמוד הבית — נכנסים לקטגוריה הראשונה
        for cat in categories[:2]:
            if products:
                break
            ok, _, _ = await self._goto(page, cat)
            if ok:
                more = await page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => ({href: a.href, text: (a.innerText||'').trim().slice(0,80)}))")
                products, _ = self._product_candidates(more)
        for url in products[:4]:
            tried += 1
            ok, err, ms = await self._goto(page, url)
            if not ok:
                continue
            is_product, data = await self._looks_like_product(page)
            if is_product:
                text = data.pop("text")
                low = text.lower()
                self.out.facts["product"] = {
                    **data, "url": page.url, "load_ms": ms,
                    "description_chars": len(text),
                    "mentions_shipping": bool(TRUST_LINKS["shipping"].search(text)),
                    "mentions_returns": bool(TRUST_LINKS["returns"].search(text)),
                    "mentions_reviews": bool(re.search(r"ביקורות|חוות\s+דעת|המלצות|reviews?|★|rating", text, re.I)) or data["jsonld_rating"],
                    "mentions_stock": bool(re.search(r"במלאי|אזל|in\s+stock|out\s+of\s+stock|נותרו", low)),
                    "mentions_faq": bool(TRUST_LINKS["faq"].search(text)),
                    "mentions_discount": bool(re.search(r"מבצע|הנחה|קופון|sale|discount|% off", low)),
                }
                st.status, st.page_url, st.duration_ms = "passed", page.url, int((time.perf_counter() - t0) * 1000)
                st.detail = f"נמצא מוצר: {data['h1'] or data['jsonld_name'] or page.url}"
                st.screenshot_id = await self._shot(page, "product", "desktop")
                return page.url
        st.status = "failed" if tried else "warning"
        st.detail = ("נבדקו קישורים שנראו כמו מוצרים, אך אף אחד לא נראה כעמוד מוצר תקין"
                     if tried else "לא נמצאו קישורים לעמודי מוצר — ייתכן שהאתר אינו חנות או בנוי במבנה לא סטנדרטי")
        self.out.facts["product_search"] = {"candidates": len(products), "categories": len(categories)}
        return None

    async def _find_atc(self, page: Page):
        selectors = [
            "button[name=add]", "button.single_add_to_cart_button", "form[action*='/cart/add'] [type=submit]",
            "[data-testid*=add-to-cart i]", "button[id*=add-to-cart i]", "button[class*=add-to-cart i]",
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if await loc.count() and await loc.is_visible():
                    return loc
            except PWError:
                continue
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=ATC_TEXT_RE).first
            try:
                if await loc.count() and await loc.is_visible():
                    return loc
            except PWError:
                continue
        loc = page.locator("input[type=submit]").filter(has=page.locator("xpath=self::*[contains(@value,'סל') or contains(translate(@value,'CART','cart'),'cart')]")).first
        try:
            if await loc.count() and await loc.is_visible():
                return loc
        except PWError:
            pass
        return None

    async def _add_to_cart(self, page: Page):
        await self._report("add_to_cart", "מנסה להוסיף מוצר לסל…")
        st = self._step("add_to_cart", "הוספה לסל")
        st.page_url = page.url
        atc = await self._find_atc(page)
        if atc is None:
            st.status, st.detail = "failed", "לא נמצא כפתור 'הוספה לסל' בעמוד המוצר"
            self.out.facts["add_to_cart"] = {"found": False}
            return
        # בחירת וריאציה (מידה/צבע) אם יש תפריט חובה ריק
        for sel in await page.locator("form select:visible").all():
            try:
                if not await sel.input_value():
                    opts = await sel.locator("option").all()
                    for o in opts[1:]:
                        v = await o.get_attribute("value")
                        if v and not await o.is_disabled():
                            await sel.select_option(v)
                            await self._log("select", f"בוחר אפשרות חובה: {(await o.text_content() or v).strip()[:40]}", page.url)
                            break
            except PWError:
                pass
        url_before = page.url
        signals_before = len(self.cart_signals)
        t = time.perf_counter()
        try:
            if await atc.is_disabled():
                st.status, st.detail = "failed", "כפתור 'הוספה לסל' מושבת (אולי המוצר אזל או שחובה לבחור אפשרות)"
                self.out.facts["add_to_cart"] = {"found": True, "clicked": False, "disabled": True}
                return
            label = ((await atc.text_content()) or (await atc.get_attribute("value")) or "").strip()[:40]
            await self._log("click", f"לוחץ על \"{label or 'הוספה לסל'}\"", page.url)
            await atc.click(timeout=10000)
        except PWError as e:
            st.status, st.detail = "failed", f"הלחיצה על 'הוספה לסל' נכשלה: {str(e).splitlines()[0][:150]}"
            self.out.facts["add_to_cart"] = {"found": True, "clicked": False}
            return
        await page.wait_for_timeout(2500)
        await self._settle(page, 3000)
        st.duration_ms = int((time.perf_counter() - t) * 1000)
        text = (await page.evaluate("() => document.body ? document.body.innerText : ''"))[:30000]
        signals = []
        if len(self.cart_signals) > signals_before:
            signals.append("נשלחה בקשה לעגלה")
        if page.url != url_before and re.search(r"cart|basket|סל|checkout", page.url, re.I):
            signals.append("עבר לעמוד העגלה")
        if re.search(r"נוסף\s+ל|התווסף|added\s+to\s+(your\s+)?(cart|bag|basket)|item\s+added", text, re.I):
            signals.append("הופיעה הודעת אישור")
        st.screenshot_id = await self._shot(page, "after-add-to-cart", "desktop")
        st.page_url = page.url
        self.out.facts["add_to_cart"] = {"found": True, "clicked": True, "signals": signals, "ms": st.duration_ms}
        if signals:
            st.status, st.detail = "passed", "המוצר נוסף לסל (" + ", ".join(signals) + ")"
        else:
            st.status, st.detail = "warning", "הכפתור נלחץ, אך לא זוהה אישור ברור שהמוצר נוסף לסל"

    async def _cart_and_checkout(self, page: Page):
        await self._report("cart", "בודק את העגלה…")
        st = self._step("cart", "מעבר לסל")
        t = time.perf_counter()
        cart_url = None
        if not re.search(r"/cart|basket|/סל", page.url, re.I):
            links = await page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => ({href: a.href, text: (a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,60)}))")
            hit = next((l["href"] for l in links if self._same_site(l["href"])
                        and (re.search(r"/cart/?$|/cart\?|/basket|/סל", urlparse(l["href"]).path, re.I) or CART_TEXT_RE.search(l["text"]))), None)
            cart_url = hit or self.origin + "/cart"
            ok, err, _ = await self._goto(page, cart_url)
            if not ok:
                st.status, st.detail, st.page_url = "failed", f"לא הצלחתי לפתוח את העגלה: {err}", cart_url
                self.out.facts["cart"] = {"reached": False}
                self._step("checkout", "כניסה לקופה").detail = "דולג — העגלה לא נפתחה"
                return
        st.duration_ms = int((time.perf_counter() - t) * 1000)
        st.page_url = page.url
        text = (await page.evaluate("() => document.body ? document.body.innerText : ''"))[:30000]
        empty = bool(EMPTY_CART_RE.search(text))
        st.screenshot_id = await self._shot(page, "cart", "desktop")
        await self._excerpt(page, "cart")
        self.out.facts["cart"] = {"reached": True, "url": page.url, "empty": empty,
                                  "mentions_shipping_cost": bool(re.search(r"משלוח|shipping", text, re.I))}
        if empty:
            st.status, st.detail = "failed", "העגלה ריקה אחרי ההוספה — המוצר לא נשמר בסל"
            self._step("checkout", "כניסה לקופה").detail = "דולג — העגלה ריקה"
            return
        st.status, st.detail = "passed", "העגלה נפתחה ויש בה פריטים"

        await self._report("checkout", "מנסה להגיע לקופה (בלי למלא פרטים)…")
        ck = self._step("checkout", "כניסה לקופה")
        btn = None
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=CHECKOUT_TEXT_RE).first
            try:
                if await loc.count() and await loc.is_visible():
                    btn = loc
                    break
            except PWError:
                pass
        if btn is None:
            loc = page.locator("[name=checkout], a[href*='checkout'], button[class*=checkout i]").first
            if await loc.count():
                btn = loc
        if btn is None:
            ck.status, ck.detail = "failed", "לא נמצא כפתור מעבר לקופה בעגלה"
            self.out.facts["checkout"] = {"button_found": False}
            return
        t = time.perf_counter()
        try:
            await self._log("click", f"לוחץ על \"{((await btn.text_content()) or 'מעבר לקופה').strip()[:40]}\"", page.url)
            await btn.click(timeout=10000)
            await page.wait_for_load_state("load", timeout=30000)
        except PWError:
            pass
        await self._settle(page, 5000)
        ck.duration_ms = int((time.perf_counter() - t) * 1000)
        ck.page_url = page.url
        info = await page.evaluate(r"""() => {
          const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
          const inputs = [...document.querySelectorAll('input, select, textarea')].filter(i => vis(i) && !['hidden','submit','button','checkbox','radio'].includes(i.type));
          return { fields: inputs.length, password: !!document.querySelector('input[type=password]'),
                   text: (document.body ? document.body.innerText : '').slice(0, 30000) };
        }""")
        text = info.pop("text")
        reached = bool(re.search(r"checkout|קופה|תשלום|payment", page.url + " " + text[:3000], re.I)) and info["fields"] > 0
        login_wall = info["password"] and not re.search(r"אורח|guest|ללא\s+הרשמה|continue\s+as", text, re.I)
        ck.screenshot_id = await self._shot(page, "checkout", "desktop")
        await self._excerpt(page, "checkout")
        self.out.facts["checkout"] = {
            "button_found": True, "reached": reached, "url": page.url, "fields": info["fields"],
            "login_required": login_wall, "payment_methods": sorted({m.group(0).lower() for m in PAYMENT_RE.finditer(text)})[:10],
        }
        if not reached:
            ck.status, ck.detail = "failed", "לחיצה על מעבר לקופה לא הובילה לעמוד תשלום"
        elif login_wall:
            ck.status, ck.detail = "warning", "הקופה דורשת התחברות/הרשמה — לא נמצאה אפשרות קנייה כאורח"
        else:
            ck.status, ck.detail = "passed", f"הגענו לקופה ({info['fields']} שדות למילוי). עצרנו כאן — לא הוזנו פרטים ולא בוצעה הזמנה"

    async def _search(self, page: Page):
        st = self._step("search", "חיפוש באתר")
        if not self.out.facts["home"].get("has_search"):
            st.status, st.detail = "warning", "לא נמצאה תיבת חיפוש בעמוד הבית"
            self.out.facts["search"] = {"available": False}
            return
        await self._report("search", "בודק את החיפוש באתר…")
        term = None
        prod = self.out.facts.get("product")
        if prod and (prod.get("h1") or prod.get("jsonld_name")):
            words = [w for w in re.split(r"\s+", prod.get("h1") or prod.get("jsonld_name")) if len(w) > 2]
            term = words[0] if words else None
        if not term:
            st.status, st.detail = "skipped", "יש תיבת חיפוש; לא נבדקה כי לא נמצא שם מוצר לחיפוש"
            self.out.facts["search"] = {"available": True, "tested": False}
            return
        ok, _, _ = await self._goto(page, self.out.facts["final_url"])
        box = page.locator("input[type=search], input[name=q], input[name=s], input[name=search], input[placeholder*='חיפוש'], input[placeholder*='חפש'], input[placeholder*='earch']").first
        try:
            if not await box.is_visible():
                for opener in await page.get_by_role("button", name=re.compile("חיפוש|search", re.I)).all():
                    if await opener.is_visible():
                        await opener.click()
                        break
            await self._log("type", f"מקליד בחיפוש: \"{term}\"", page.url)
            await box.fill(term, timeout=5000)
            url_before = page.url
            await box.press("Enter")
            await page.wait_for_timeout(2500)
            await self._settle(page)
        except PWError as e:
            st.status, st.detail = "warning", f"לא הצלחתי להשתמש בתיבת החיפוש ({str(e).splitlines()[0][:100]})"
            self.out.facts["search"] = {"available": True, "tested": False}
            return
        text = (await page.evaluate("() => document.body ? document.body.innerText : ''"))[:30000]
        no_results = bool(re.search(r"לא\s+נמצאו\s+תוצאות|אין\s+תוצאות|no\s+results|nothing\s+found|0\s+results", text, re.I))
        found_term = term.lower() in text.lower()
        st.page_url = page.url
        st.screenshot_id = await self._shot(page, "search", "desktop")
        works = page.url != url_before and found_term and not no_results
        self.out.facts["search"] = {"available": True, "tested": True, "term": term, "works": works, "no_results": no_results}
        st.status = "passed" if works else "failed"
        st.detail = f"חיפוש '{term}' החזיר תוצאות" if works else f"חיפוש '{term}' (שם של מוצר קיים) לא החזיר תוצאות רלוונטיות"

    async def _mobile(self, ctx: BrowserContext, product_url: str | None):
        await self._report("mobile", "בודק את האתר בטלפון (iPhone)…")
        st = self._step("mobile", "חוויית מובייל")
        page = await ctx.new_page()
        ok, err, ms = await self._goto(page, self.out.facts["final_url"])
        st.page_url, st.duration_ms = page.url, ms
        st.screenshot_id = await self._shot(page, "home", "mobile")
        if not ok:
            st.status, st.detail = "failed", err
            return
        data = await page.evaluate(PAGE_FACTS_JS)
        data.pop("links", None)
        data.pop("text", None)
        mob = {**data, "load_ms": ms}
        if product_url:
            ok, _, pms = await self._goto(page, product_url)
            if ok:
                atc = await self._find_atc(page)
                box = await atc.bounding_box() if atc else None
                vh = page.viewport_size["height"]
                mob["product_load_ms"] = pms
                mob["atc_above_fold"] = bool(box and box["y"] < vh)
                mob["atc_position_px"] = int(box["y"]) if box else None
                mob["product_screenshot"] = await self._shot(page, "product", "mobile")
        self.out.facts["mobile"] = mob
        problems = []
        if data["horizontal_overflow"]:
            problems.append("גלילה הצידה")
        if data["overlay"]:
            problems.append("חלון קופץ מכסה את המסך")
        st.status = "warning" if problems else "passed"
        st.detail = (f"נטען תוך {ms / 1000:.1f} שנ'" + (" · בעיות: " + ", ".join(problems) if problems else ""))


async def collect(start_url: str, shot_dir: Path, **kw) -> Collected:
    return await Collector(start_url, shot_dir, **kw).run()
