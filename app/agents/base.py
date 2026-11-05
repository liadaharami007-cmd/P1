"""תשתית לסוכני הלקוח: יומן פעולות, צילומי מסך, התאוששות משגיאות, עצירה, ומנוע החלטות.

מנוע ההחלטות (Brain):
- RuleBrain — מסלול קבוע מבוסס כללים לכל סוכן (מה שפועל היום). לא נקרא "AI".
- בעתיד: ModelBrain שמחליט על הצעד הבא בעזרת מודל שפה (Claude / Ollama) — הממשק כבר מוגדר.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from playwright.async_api import Error as PWError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PWTimeout

from ..audit.collector import MAIN_TEXT_JS, ATC_TEXT_RE, CART_TEXT_RE, CATEGORY_URL_RE, CHECKOUT_TEXT_RE, PRODUCT_URL_RE, PRODUCT_QS_RE

MAX_ACTIONS = 30
AGENT_TIMEOUT_S = 75


class Brain(Protocol):
    """ממשק למנוע החלטות של סוכן."""
    engine: str

    def describe(self) -> str: ...


class RuleBrain:
    engine = "rules"

    def describe(self) -> str:
        return "מסלול מבוסס כללים (ללא מודל שפה)"


class Stopped(Exception):
    """הבדיקה נעצרה ע"י המשתמש."""


@dataclass
class AgentResult:
    observations: list[dict] = field(default_factory=list)   # {"type": ok|issue|info, "text": str}
    metrics: dict = field(default_factory=dict)
    verdict: str | None = None

    def ok(self, text: str):
        self.observations.append({"type": "ok", "text": text})

    def issue(self, text: str):
        self.observations.append({"type": "issue", "text": text})

    def info(self, text: str):
        self.observations.append({"type": "info", "text": text})

    def decide_verdict(self, hard_issue: bool = False) -> str:
        n = sum(1 for o in self.observations if o["type"] == "issue")
        self.verdict = "likely_leave" if hard_issue or n >= 3 else ("hesitant" if n else "likely_buy")
        return self.verdict


EventFn = Callable[[str, str, str | None, str | None], Awaitable[None]]
ShotFn = Callable[[str, str, str | None, str], str]


class AgentContext:
    """מה שכל סוכן מקבל: דף דפדפן, יומן, צילומים, בדיקת עצירה ומגבלת פעולות."""

    def __init__(self, key: str, page: Page, device: str, shot_dir: Path, log: EventFn, save_shot: ShotFn,
                 should_stop: Callable[[], bool], on_state: Callable[[dict], None]):
        self.key, self.page, self.device, self.shot_dir = key, page, device, shot_dir
        self._log, self._save_shot, self._should_stop, self._on_state = log, save_shot, should_stop, on_state
        self.actions = 0
        self.popups_closed = 0
        self.t0 = time.perf_counter()
        self.shots = 0

    async def log(self, kind: str, msg: str, url: str | None = None, shot: str | None = None):
        await self._log(kind, msg, url or self.page.url, shot)
        self._on_state({"current_url": url or self.page.url, "last_action": msg, "actions": self.actions,
                        **({"last_screenshot_id": shot} if shot else {})})

    def check(self):
        if self._should_stop():
            raise Stopped()
        if self.actions >= MAX_ACTIONS:
            raise RuntimeError("הגיע למגבלת הפעולות לסוכן")

    async def shot(self, label: str) -> str | None:
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        path = self.shot_dir / f"{self.key}-{self.shots:02d}-{label}.jpg"
        self.shots += 1
        try:
            await self.page.screenshot(path=str(path), type="jpeg", quality=65, timeout=12000)
        except PWError:
            return None
        sid = self._save_shot(f"agent:{self.key}:{label}", self.device, self.page.url, str(path))
        await self.log("screenshot", f"צילום מסך: {label}", shot=sid)
        return sid

    async def settle(self, ms: int = 3500):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=ms)
        except PWTimeout:
            pass

    async def dismiss_popups(self) -> bool:
        """לקוח אמיתי סוגר חלון קופץ לפני שהוא ממשיך. מחפש כפתור סגירה בתוך חלון שמכסה את המסך."""
        try:
            found = await self.page.evaluate(r"""() => {
              const vw = innerWidth, vh = innerHeight;
              for (const el of document.querySelectorAll('body *')) {
                const s = getComputedStyle(el); if (s.position !== 'fixed' || s.display === 'none') continue;
                const r = el.getBoundingClientRect();
                if ((Math.min(r.right, vw) - Math.max(r.left, 0)) * (Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh) < 0.45) continue;
                const btn = [...el.querySelectorAll('button, a, [role=button], [aria-label]')].find((b) =>
                  /סגור|סגירה|close|×|✕|לא\s+תודה|no\s+thanks|dismiss/i.test((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')));
                if (btn) { btn.setAttribute('data-p1-close', '1'); return true; }
                return 'no-button';
              }
              return false; }""")
        except PWError:
            return False
        if found is True:
            self.actions += 1
            await self.log("click", "סוגר חלון קופץ שמכסה את המסך")
            try:
                await self.page.locator("[data-p1-close]").first.click(timeout=4000)
                await self.page.wait_for_timeout(400)
                return True
            except PWError:
                pass
        if found:  # יש חלון אבל אין כפתור סגירה — מנסים Escape
            await self.page.keyboard.press("Escape")
            await self.log("info", "יש חלון קופץ בלי כפתור סגירה ברור — ניסיתי Escape")
        return bool(found)

    async def goto(self, url: str, why: str) -> bool:
        """ניווט עם ניסיון חוזר אחד (התאוששות משגיאות רשת חולפות)."""
        self.check()
        for attempt in (1, 2):
            self.actions += 1
            await self.log("navigate", f"{why}", url)
            try:
                resp = await self.page.goto(url, wait_until="load", timeout=40000)
                await self.settle()
                if resp is not None and resp.status >= 400:
                    await self.log("error", f"השרת החזיר {resp.status}", url)
                    return False
                if await self.dismiss_popups():
                    self.popups_closed += 1
                return True
            except PWError as e:
                await self.log("error", f"ניסיון {attempt} נכשל: {str(e).splitlines()[0][:120]}", url)
                if attempt == 2:
                    return False
                await asyncio.sleep(1.5)
        return False

    async def click(self, locator: Any, label: str, wait_nav: bool = True) -> bool:
        """לחיצה אמיתית על אלמנט + המתנה לתגובת העמוד. לא זורק — מחזיר הצלחה."""
        self.check()
        self.actions += 1
        await self.log("click", f"לוחץ על \"{label[:50]}\"")
        try:
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.click(timeout=8000)
        except PWError as e:
            await self.log("error", f"הלחיצה נכשלה: {str(e).splitlines()[0][:120]}")
            return False
        if wait_nav:
            await self.page.wait_for_timeout(1200)
            await self.settle(3000)
        return True

    async def main_text(self) -> str:
        """טקסט התוכן בלבד — בלי כותרת, תפריט ופוטר."""
        try:
            return re.sub(r"\s+", " ", await self.page.evaluate(MAIN_TEXT_JS))
        except PWError:
            return ""

    async def text(self) -> str:
        try:
            return re.sub(r"\s+", " ", await self.page.evaluate("() => document.body ? document.body.innerText : ''"))
        except PWError:
            return ""

    # ---------------------------------------------------------------- מאתרים משותפים
    async def link_matching(self, rx: re.Pattern, same_site: bool = True):
        host = re.sub(r"^www\.", "", (self.page.url.split("/")[2] if "://" in self.page.url else ""))
        for a in await self.page.locator("a[href]").all():
            try:
                if not await a.is_visible():
                    continue
                txt = ((await a.inner_text()) or (await a.get_attribute("aria-label")) or "").strip()
                href = await a.get_attribute("href") or ""
                if rx.search(txt) or rx.search(href):
                    full = await a.evaluate("a => a.href")
                    if same_site and host and host not in full:
                        continue
                    return a, txt or href
            except PWError:
                continue
        return None, None

    async def product_link(self):
        for a in await self.page.locator("a[href]").all():
            try:
                href = await a.evaluate("a => a.href")
                path = href.split("://", 1)[-1]
                path = path[path.find("/"):] if "/" in path else "/"
                if (PRODUCT_URL_RE.search(path) or PRODUCT_QS_RE.search(path)) and await a.is_visible():
                    return a, ((await a.inner_text()) or href).strip()[:60]
            except PWError:
                continue
        return None, None

    async def category_link(self):
        for a in await self.page.locator("a[href]").all():
            try:
                href = await a.evaluate("a => a.href")
                if CATEGORY_URL_RE.search(href) and await a.is_visible():
                    return a, ((await a.inner_text()) or href).strip()[:60]
            except PWError:
                continue
        return None, None

    async def atc(self):
        for sel in ("button[name=add]", "button.single_add_to_cart_button", "form[action*='/cart/add'] [type=submit]"):
            loc = self.page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                return loc
        for role in ("button", "link"):
            loc = self.page.get_by_role(role, name=ATC_TEXT_RE).first
            if await loc.count() and await loc.is_visible():
                return loc
        return None

    async def select_required_options(self):
        for sel in await self.page.locator("form select:visible").all():
            try:
                if not await sel.input_value():
                    for o in (await sel.locator("option").all())[1:]:
                        v = await o.get_attribute("value")
                        label = ((await o.text_content()) or "").strip()
                        if (v or label) and not await o.is_disabled():
                            await (sel.select_option(v) if v else sel.select_option(label=label))
                            self.actions += 1
                            await self.log("select", f"בוחר אפשרות: {((await o.text_content()) or v).strip()[:30]}")
                            break
            except PWError:
                pass

    async def checkout_button(self):
        for role in ("button", "link"):
            loc = self.page.get_by_role(role, name=CHECKOUT_TEXT_RE).first
            if await loc.count() and await loc.is_visible():
                return loc
        return None

    async def cart_link(self):
        a, label = await self.link_matching(re.compile(r"/cart\b|/basket|/סל", re.I))
        if a:
            return a, label
        return await self.link_matching(CART_TEXT_RE)
