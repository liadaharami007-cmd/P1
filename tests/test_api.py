from types import SimpleNamespace

from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock

from app.agent import Agent
from app.db import Database
from tests.conftest import register


class FakeMessages:
    """מדמה את Claude בבדיקות בלבד: בפעם הראשונה מבקש לחקור אתר, בשנייה עונה בטקסט."""

    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        last = kwargs["messages"][-1]
        if isinstance(last["content"], str):
            return SimpleNamespace(stop_reason="tool_use", content=[
                BetaTextBlock(type="text", text="בודק את האתר."),
                BetaToolUseBlock(type="tool_use", id="tu_1", name="analyze_website", input={"url": "shop.test"}),
            ])
        return SimpleNamespace(stop_reason="end_turn", content=[BetaTextBlock(type="text", text="הבעיה העיקרית: אין כפתור הזמנה.")])


async def fake_analyzer(url):
    return {"requested_url": url, "ok": True, "final_url": "https://shop.test/", "score": 55,
            "facts": {}, "issues": [{"id": "no_cta", "severity": "high"}]}


def _agent(db):
    fake = FakeMessages()
    return Agent(db, client=SimpleNamespace(beta=SimpleNamespace(messages=fake)), analyzer=fake_analyzer), fake


def test_requires_login(make_client):
    c = make_client()
    for path in ("/api/status", "/api/audits", "/api/dashboard", "/api/conversations", "/api/tasks"):
        assert c.get(path).status_code == 401, path
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/").status_code == 200


def test_chat_without_key_is_disabled(make_client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    c = make_client()
    register(c, "a@shop.co.il")
    assert c.get("/api/status").json()["capabilities"]["chat"] == {"ready": False, "missing": "ANTHROPIC_API_KEY"}
    conv = c.post("/api/conversations").json()
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"text": "שלום"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert c.get(f"/api/conversations/{conv['id']}").json()["items"] == []  # לא נשמר חצי


def test_chat_with_tool_persistence_and_isolation(tmp_path, make_client):
    db = Database(tmp_path / "c.db")
    agent, fake = _agent(db)
    a = make_client(db=db, agent=agent)
    register(a, "owner@a.co.il")
    conv = a.post("/api/conversations").json()
    data = a.post(f"/api/conversations/{conv['id']}/messages", json={"text": "תבדוק את shop.test"}).json()
    types = [i["type"] for i in data["items"]]
    assert types == ["user", "assistant", "tool_use", "tool_result", "assistant"]
    assert fake.calls[1]["messages"][-1]["content"][0]["tool_use_id"] == "tu_1"
    rep_id = data["items"][3]["report_id"]
    assert a.get(f"/api/research/{rep_id}").json()["score"] == 55
    # חשבון אחר לא רואה את השיחה ואת הדוח
    b = make_client(db=db, agent=agent)
    register(b, "other@b.co.il")
    assert b.get(f"/api/conversations/{conv['id']}").status_code == 404
    assert b.get(f"/api/research/{rep_id}").status_code == 404
    assert b.get("/api/conversations").json() == []
