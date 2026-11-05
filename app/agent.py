"""הסוכן — מחבר את Claude לכלים של P1.

זרימה (agent loop):
1. שולחים ל-Claude את כל השיחה + רשימת הכלים.
2. אם Claude מבקש להפעיל כלי (למשל לחקור אתר) — אנחנו מריצים אותו באמת
   ומחזירים לו את התוצאה.
3. חוזרים על זה עד ש-Claude מסיים לענות.
כל שלב נשמר במסד הנתונים כדי שהשיחה תישמר.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import anthropic

from . import config
from .db import Database
from .research.analyzer import analyze_url

SYSTEM_PROMPT = """אתה P1 AI — עוזר AI לבעלי עסקים. אתה מדבר עברית פשוטה וברורה (אלא אם המשתמש כותב בשפה אחרת).

התפקיד שלך: לעזור לעסקים למכור יותר — לנתח אתרים, לזהות בעיות שפוגעות במכירות ובשיווק, ולתת המלצות מעשיות לפי סדר עדיפות.

כלים זמינים לך כרגע:
- analyze_website: חוקר אתר אמיתי (מוריד את העמוד, בודק מהירות, SEO, מובייל, דרכי יצירת קשר, כפתורי פעולה, כלי מדידה, קישורים שבורים ועוד).

כללים:
- כשמשתמש מזכיר אתר או מבקש בדיקה של אתר — הפעל את analyze_website במקום לנחש.
- התבסס רק על מה שהכלי מצא בפועל. אם הכלי נכשל — אמור זאת בכנות והסבר למה.
- הבדיקה האוטומטית רואה את ה-HTML של העמוד הראשי בלבד. אם תוכן נטען ב-JavaScript, ציין שייתכן שחלק מהממצאים לא מדויקים.
- אין לך עדיין יכולת לשלוח מיילים, לפרסם ברשתות, לגשת לחשבונות פרסום או להפעיל אוטומציות. אם מבקשים זאת — אמור בבירור שזה עוד לא מחובר.
- בסיכום ניתוח אתר: התחל במה הכי פוגע במכירות, ותן לכל בעיה פעולה מעשית אחת.
"""

TOOLS = [
    {
        "name": "analyze_website",
        "description": (
            "Fetches a real public website and analyzes its home page for problems that hurt sales and "
            "marketing: response time, HTTPS, SEO tags, mobile viewport, contact methods, calls to action, "
            "analytics/pixels, broken internal links, robots.txt and sitemap. Returns facts, issues with "
            "severity, and a 0-100 score. Use whenever the user asks about a specific site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The website address, e.g. example.co.il or https://example.com/page"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


class AgentError(Exception):
    """שגיאה שמוצגת למשתמש בעברית."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


def _block_to_dict(block: Any) -> dict:
    return block.model_dump(mode="json", exclude_none=True)


class Agent:
    def __init__(self, db: Database, client: Any | None = None,
                 analyzer: Callable[[str], Awaitable[dict]] | None = None):
        self.db = db
        self._client = client
        self.analyzer = analyzer or analyze_url

    @property
    def ready(self) -> bool:
        return self._client is not None or config.anthropic_configured()

    @property
    def client(self):
        if self._client is None:
            if not config.anthropic_configured():
                raise AgentError(
                    "חסר מפתח API של Anthropic. הוסיפו ANTHROPIC_API_KEY לקובץ .env והפעילו מחדש את השרת.",
                    status=503,
                )
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def _run_tool(self, name: str, tool_input: dict, conv_id: str) -> tuple[str, bool]:
        if name != "analyze_website":
            return f"Unknown tool: {name}", True
        url = tool_input.get("url") if isinstance(tool_input, dict) else None
        if not isinstance(url, str) or not url.strip():
            return "Missing 'url' parameter", True
        report = await self.analyzer(url)
        report_id = self.db.save_report(report, conversation_id=conv_id)
        payload = {"report_id": report_id, **report}
        return json.dumps(payload, ensure_ascii=False), not report.get("ok", False)

    async def _call_claude(self, messages: list[dict]):
        try:
            return await self.client.beta.messages.create(
                model=config.MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            raise AgentError("מפתח ה-API של Anthropic לא תקין. בדקו את ANTHROPIC_API_KEY.", 401)
        except anthropic.PermissionDeniedError:
            raise AgentError("למפתח ה-API אין הרשאה למודל הזה.", 403)
        except anthropic.RateLimitError:
            raise AgentError("חרגנו ממגבלת הבקשות של Anthropic. נסו שוב בעוד דקה.", 429)
        except anthropic.BadRequestError as e:
            raise AgentError(f"בקשה לא תקינה ל-Claude: {e.message}", 400)
        except anthropic.APIStatusError as e:
            raise AgentError(f"שגיאה מצד Anthropic ({e.status_code}). נסו שוב.", 502)
        except anthropic.APIConnectionError:
            raise AgentError("אין חיבור לשרתי Anthropic. בדקו חיבור לאינטרנט.", 502)

    async def send(self, conv_id: str, user_text: str) -> str | None:
        """שולח הודעת משתמש, מריץ את הלולאה ושומר הכול.

        מחזיר הודעת הערה למשתמש (או None), וזורק AgentError על כשל.
        """
        history = self.db.get_messages(conv_id)
        is_first = not history
        pending: list[dict] = [{"role": "user", "content": user_text}]

        def flush():
            for m in pending:
                self.db.add_message(conv_id, m["role"], m["content"])
            history.extend(pending)
            pending.clear()

        notice: str | None = None
        for _ in range(config.MAX_AGENT_STEPS):
            response = await self._call_claude(history + pending)
            content = [_block_to_dict(b) for b in response.content]
            pending.append({"role": "assistant", "content": content})

            if response.stop_reason == "refusal":
                flush()
                notice = "Claude סירב להשיב לבקשה הזו מטעמי בטיחות."
                break
            if response.stop_reason == "max_tokens":
                flush()
                notice = "התשובה נקטעה כי הייתה ארוכה מדי."
                break
            if response.stop_reason == "pause_turn":
                flush()
                continue
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                flush()
                break

            results = []
            for tu in tool_uses:
                text, is_error = await self._run_tool(tu.name, tu.input, conv_id)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text, "is_error": is_error})
            pending.append({"role": "user", "content": results})
            flush()
        else:
            notice = f"הסוכן עצר אחרי {config.MAX_AGENT_STEPS} צעדים. אפשר לכתוב 'המשך'."

        if is_first:
            title = user_text.strip().replace("\n", " ")
            self.db.rename_conversation(conv_id, title[:50] + ("…" if len(title) > 50 else ""))
        return notice


def to_display(messages: list[dict]) -> list[dict]:
    """ממיר את ההיסטוריה הגולמית לפריטים פשוטים להצגה בממשק."""
    items: list[dict] = []
    for m in messages:
        content = m["content"]
        if m["role"] == "user":
            if isinstance(content, str):
                items.append({"type": "user", "text": content})
                continue
            for block in content:
                if block.get("type") == "tool_result":
                    try:
                        data = json.loads(block.get("content") or "{}")
                    except (TypeError, json.JSONDecodeError):
                        data = {}
                    items.append({
                        "type": "tool_result",
                        "ok": not block.get("is_error"),
                        "report_id": data.get("report_id"),
                        "url": data.get("final_url") or data.get("requested_url"),
                        "score": data.get("score"),
                        "error": data.get("error") if block.get("is_error") else None,
                    })
                elif block.get("type") == "text":
                    items.append({"type": "user", "text": block.get("text", "")})
        else:
            for block in content:
                t = block.get("type")
                if t == "text" and block.get("text"):
                    items.append({"type": "assistant", "text": block["text"]})
                elif t == "tool_use":
                    items.append({"type": "tool_use", "name": block.get("name"), "input": block.get("input")})
    return items
