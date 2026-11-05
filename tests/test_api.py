from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock
from fastapi.testclient import TestClient

from app.agent import Agent
from app.db import Database
from app.main import create_app


class FakeMessages:
    """מדמה את Claude: בפעם הראשונה מבקש לחקור אתר, בשנייה עונה בטקסט."""

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


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "t.db")
    fake = FakeMessages()
    agent = Agent(db, client=SimpleNamespace(beta=SimpleNamespace(messages=fake)), analyzer=fake_analyzer)
    return TestClient(create_app(db=db, agent=agent)), fake, db


def test_status_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = TestClient(create_app(db=Database(tmp_path / "s.db")))
    s = client.get("/api/status").json()
    assert s["capabilities"]["chat"] == {"ready": False, "missing": "ANTHROPIC_API_KEY"}
    conv = client.post("/api/conversations").json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "שלום"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert client.get(f"/api/conversations/{conv['id']}").json()["items"] == []  # לא נשמר חצי


def test_chat_with_tool_and_persistence(setup):
    client, fake, db = setup
    conv = client.post("/api/conversations").json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "תבדוק את shop.test"})
    assert r.status_code == 200
    data = r.json()
    types = [i["type"] for i in data["items"]]
    assert types == ["user", "assistant", "tool_use", "tool_result", "assistant"]
    assert data["items"][3]["score"] == 55 and data["items"][3]["report_id"]
    assert data["title"].startswith("תבדוק את")
    # הקריאה השנייה ל-Claude כוללת את תוצאת הכלי
    second = fake.calls[1]["messages"]
    assert second[-1]["content"][0]["type"] == "tool_result"
    assert second[-1]["content"][0]["tool_use_id"] == "tu_1"
    # הדוח נשמר ונגיש
    rep = client.get(f"/api/research/{data['items'][3]['report_id']}").json()
    assert rep["score"] == 55
    # השיחה נשמרת ונטענת מחדש
    again = client.get(f"/api/conversations/{conv['id']}").json()
    assert [i["type"] for i in again["items"]] == types
    assert len(db.get_messages(conv["id"])) == 4


def test_conversation_crud(setup):
    client, _, _ = setup
    c = client.post("/api/conversations").json()
    assert any(x["id"] == c["id"] for x in client.get("/api/conversations").json())
    assert client.delete(f"/api/conversations/{c['id']}").status_code == 204
    assert client.get(f"/api/conversations/{c['id']}").status_code == 404


def test_research_endpoint_rejects_internal(setup):
    client, _, _ = setup
    r = client.post("/api/research", json={"url": "http://127.0.0.1:22"}).json()
    assert r["ok"] is False and r["id"]
    assert client.get("/api/research").json()[0]["ok"] is False


def test_index_served(setup):
    client, _, _ = setup
    r = client.get("/")
    assert r.status_code == 200 and "P1" in r.text
