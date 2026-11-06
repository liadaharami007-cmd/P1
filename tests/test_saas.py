import sqlite3

from app.db import Database
from app.saas import auth
from tests.conftest import register


def test_password_hashing():
    h = auth.hash_password("correct-horse-battery")
    assert h.startswith("scrypt$") and "correct" not in h
    assert auth.verify_password("correct-horse-battery", h)
    assert not auth.verify_password("wrong-password!!", h)


def test_register_login_logout_and_admin_bootstrap(make_client):
    c = make_client()
    assert c.get("/api/auth/config").json() == {"signup_allowed": True, "has_users": False, "email_configured": False}
    register(c, "Founder@P1.ai", name="מייסד", business_name="P1")
    me = c.get("/api/auth/me").json()
    assert me["user"]["email"] == "founder@p1.ai" and me["user"]["is_platform_admin"] == 1 and me["role"] == "owner"
    assert "password_hash" not in me["user"]
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"email": "founder@p1.ai", "password": "nope-nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "founder@p1.ai", "password": "correct-horse-battery"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    # משתמש שני — לא מנהל פלטפורמה
    c2 = make_client(db=c.app.state.db)
    register(c2, "second@shop.co.il")
    assert c2.get("/api/auth/me").json()["user"]["is_platform_admin"] == 0
    assert c2.get("/api/admin/overview").status_code == 403
    ov = c.get("/api/admin/overview").json()
    assert ov["totals"]["accounts"] == 2 and ov["totals"]["users"] == 2


def test_validation_and_duplicates(make_client):
    c = make_client()
    assert c.post("/api/auth/register", json={"email": "bad", "password": "correct-horse-battery"}).status_code == 400
    assert c.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 400
    register(c, "a@b.co")
    assert c.post("/api/auth/register", json={"email": "A@B.co", "password": "correct-horse-battery"}).status_code == 409


def test_login_rate_limit(make_client):
    c = make_client()
    auth.login_limiter.hits.clear()
    codes = [c.post("/api/auth/login", json={"email": "x@y.co", "password": "whatever-123"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429
    auth.login_limiter.hits.clear()


def test_csrf_origin_check(make_client):
    c = make_client()
    r = c.post("/api/auth/login", json={"email": "x@y.co", "password": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_security_headers(make_client):
    r = make_client().get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_quota_and_plan_change(make_client):
    admin = make_client()
    register(admin, "admin@p1.ai")
    user = make_client(db=admin.app.state.db)
    register(user, "shop@owner.co.il")
    ok = user.post("/api/audits", json={"url": "https://8.8.8.8/", "confirm_permission": True})
    assert ok.status_code == 202
    # מסלול חינמי: אתר אחד בלבד
    r = user.post("/api/audits", json={"url": "https://1.1.1.1/", "confirm_permission": True})
    assert r.status_code == 402 and "אתרים" in r.json()["detail"]
    acc_id = user.get("/api/auth/me").json()["account"]["id"]
    assert admin.patch(f"/api/admin/accounts/{acc_id}", json={"plan": "pro"}).status_code == 200
    # עדיין בדיקה אחת רצה/בתור — מגבלת מקביליות של pro היא 2
    r = user.post("/api/audits", json={"url": "https://1.1.1.1/", "confirm_permission": True})
    assert r.status_code == 202
    usage = user.get("/api/account").json()["usage"]
    assert usage["sites"] == 2 and usage["audits"] == 2


def test_audit_isolation_between_accounts(make_client):
    a = make_client()
    register(a, "a@a.co")
    audit = a.post("/api/audits", json={"url": "https://8.8.8.8/", "confirm_permission": True}).json()
    b = make_client(db=a.app.state.db)
    register(b, "b@b.co")
    assert a.get(f"/api/audits/{audit['id']}").status_code == 200
    assert b.get(f"/api/audits/{audit['id']}").status_code == 404
    assert b.get(f"/api/audits/{audit['id']}/events").status_code == 404
    assert b.delete(f"/api/audits/{audit['id']}").status_code == 404
    assert b.get("/api/audits").json() == []


def test_migration_from_v1_schema(tmp_path):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE sites (id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, name TEXT, created_at TEXT NOT NULL);
        CREATE TABLE audits (id TEXT PRIMARY KEY, site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
          start_url TEXT NOT NULL, status TEXT NOT NULL, progress_json TEXT NOT NULL DEFAULT '[]', score INTEGER,
          category_scores_json TEXT, facts_json TEXT, error TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT);
        CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE research_reports (id TEXT PRIMARY KEY, url TEXT NOT NULL, final_url TEXT, conversation_id TEXT,
          report_json TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT INTO sites VALUES ('s1', 'https://old.co.il', 'Old', '2026-01-01');
        INSERT INTO audits (id, site_id, start_url, status, created_at) VALUES ('a1', 's1', 'https://old.co.il', 'done', '2026-01-01');
    """)
    c.commit()
    c.close()
    db = Database(path)
    user, acc = db.create_user_with_account("o@o.co", "x", None, "Old")
    assert db.adopt_orphan_data(acc["id"]) >= 2
    assert db.get_audit("a1", acc["id"])["site_url"] == "https://old.co.il"
    from app.db import SCHEMA_VERSION
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_bootstrap_email_guards_first_admin(make_client, monkeypatch):
    monkeypatch.setenv("P1_BOOTSTRAP_EMAIL", "owner@p1.co")
    from app.saas import auth
    monkeypatch.setattr(auth, "ALLOW_SIGNUP", False)
    c = make_client()
    r = c.post("/api/auth/register", json={"email": "attacker@x.co", "password": "correct-horse-battery"})
    assert r.status_code == 403
    assert c.post("/api/auth/register", json={"email": "owner@p1.co", "password": "correct-horse-battery"}).status_code == 201
    assert c.get("/api/auth/me").json()["user"]["is_platform_admin"]
    d = make_client(db=c.app.state.db)
    assert d.post("/api/auth/register", json={"email": "late@x.co", "password": "correct-horse-battery"}).status_code == 403
