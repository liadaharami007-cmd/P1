import os

os.environ.setdefault("P1_RUN_WORKER", "0")  # בבדיקות מריצים בדיקות ישירות, בלי worker ברקע

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app


def register(client: TestClient, email: str, password: str = "correct-horse-battery", **kw):
    r = client.post("/api/auth/register", json={"email": email, "password": password, **kw})
    assert r.status_code == 201, r.text
    return r


@pytest.fixture
def make_client(tmp_path):
    def _make(db: Database | None = None, **kw) -> TestClient:
        return TestClient(create_app(db=db or Database(tmp_path / "t.db"), **kw))
    return _make


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.saas import auth
    auth.login_limiter.hits.clear()
    auth.signup_limiter.hits.clear()
    yield
