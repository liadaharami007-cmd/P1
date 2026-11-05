"""הפעלת דפדפן אמיתי (Chromium דרך Playwright) עם הגנות אבטחה."""
from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Playwright, Route

from .. import config

DESKTOP = {"viewport": {"width": 1366, "height": 900}, "locale": "he-IL"}
USER_AGENT_SUFFIX = " P1-AI-Auditor/0.2"


class HostGuard:
    """חוסם בקשות מהדפדפן לכתובות פנימיות (הגנת SSRF). שומר תוצאות במטמון לכל דומיין."""

    def __init__(self, allow_private: bool = False):
        self.allow_private = allow_private
        self._cache: dict[str, bool] = {}
        self.blocked: list[str] = []

    async def is_allowed(self, url: str) -> bool:
        if self.allow_private:
            return True
        parsed = urlparse(url)
        if parsed.scheme in ("data", "blob", "about"):
            return True
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if host in self._cache:
            return self._cache[host]
        allowed = await self._check(host)
        self._cache[host] = allowed
        if not allowed:
            self.blocked.append(host)
        return allowed

    @staticmethod
    async def _check(host: str) -> bool:
        if not host or host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            pass
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None)
        except OSError:
            return True  # DNS פתור רק דרך proxy — הבקשה תיכשל ממילא אם הדומיין לא קיים
        return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)

    async def route(self, route: Route) -> None:
        if await self.is_allowed(route.request.url):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")


async def launch(pw: Playwright) -> Browser:
    kwargs = {}
    path = config.chromium_path()
    if path:
        kwargs["executable_path"] = path
    return await pw.chromium.launch(**kwargs)


async def new_context(browser: Browser, guard: HostGuard, device: dict | None = None) -> BrowserContext:
    opts = dict(device or DESKTOP)
    opts.setdefault("locale", "he-IL")
    ctx = await browser.new_context(**opts)
    await ctx.route("**/*", guard.route)
    ctx.set_default_timeout(15000)
    ctx.set_default_navigation_timeout(45000)
    return ctx
