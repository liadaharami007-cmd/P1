"""P1 CEO: זיהוי כוונה, שאלות רק על מה שחסר, תוכנית מיכולות אמיתיות בלבד, פעולה שנוצרת לאישור, 'מה עושים היום', הפרדה."""
from app.business import missions
from app.intelligence import engines

from .conftest import register


def test_classify_hebrew_and_english():
    assert missions.classify("יש לי משרד פרסום עם 15 לקוחות")["intent"] == "agency"
    assert missions.classify("מה עושים היום?")["intent"] == "today"
    assert missions.classify("אני רוצה לפתוח עסק של עוגות")["intent"] == "start"
    assert missions.classify("אני לא מצליח למכור באתר שלי")["intent"] == "website"
    assert missions.classify("I need campaigns and videos")["intent"] == "marketing"
    assert missions.classify("שלום")["intent"] == "consult"


def test_readiness_is_rules_and_honest():
    r = missions.readiness({"offer": "עוגות מעוצבות לאירועים קטנים", "audience": "הורים שמארגנים ימי הולדת"}, {})
    assert r["engine"] == "rules" and 0 < r["score"] < 100 and "לא תחזית" in r["note"]


def test_mission_flows(make_client, monkeypatch):
    monkeypatch.setattr(engines, "status", lambda: {"active": "rules", "preferred": "auto", "engines": []})
    c = make_client()
    register(c, "ceo@p1.co")
    q = c.post("/api/ceo/intent", json={"text": "אני רוצה לשפר את האתר"}).json()
    assert q["intent"] == "website" and q["ai"] is False and any(x["id"] == "permission" for x in q["questions"])
    assert c.post("/api/missions", json={"intent": "website", "answers": {}}).status_code == 400  # חסרה תשובה
    m = c.post("/api/missions", json={"intent": "website", "answers": {
        "business_name": "פרחי בלום", "business_type": "ecommerce", "website": "https://8.8.8.8", "permission": "yes", "site_goal": "sales"}}).json()
    first = m["plan"]["steps"][0]
    assert first["action"]["status"] == "proposed" and first["needs_approval"] and first["status"] == "works"
    assert c.get("/api/business/profile").json()["data"]["business_name"] == "פרחי בלום"
    # שאלות שכבר נענו לא נשאלות שוב
    q2 = c.post("/api/ceo/intent", json={"intent": "grow"}).json()["questions"]
    assert "business_name" not in {x["id"] for x in q2} and "goals" in {x["id"] for x in q2}
    # בלי אישור הרשאה — אין פעולת בדיקה
    m2 = c.post("/api/missions", json={"intent": "grow", "answers": {"goals": ["more_sales"], "offer": "פרחים", "website": "https://1.1.1.1"}}).json()
    assert not any(s.get("action") for s in m2["plan"]["steps"])
    assert any(s["status"] == "unavailable" and "Google Analytics" in (s["note"] or "") for s in m2["plan"]["steps"])
    st = c.post("/api/missions", json={"intent": "start", "answers": {"offer": "עוגות מעוצבות לאירועים קטנים", "audience": "הורים"}}).json()
    assert st["plan"]["readiness"]["engine"] == "rules"
    cons = c.post("/api/missions", json={"intent": "consult", "answers": {"question": "איך מתמחרים?"}}).json()
    assert cons["plan"]["steps"][0]["status"] == "unavailable"  # בלי מנוע מודל — לא מעמידים פנים
    ag = c.post("/api/missions", json={"intent": "agency", "answers": {"business_name": "סוכנות X", "clients_count": 15}}).json()
    assert ag["plan"]["suggest_demo"] and any(s["link"] == "#/agency" for s in ag["plan"]["steps"])
    assert len(c.get("/api/missions").json()["items"]) == 5
    today = c.get("/api/ceo/today").json()
    assert today["items"] and all({"cost_note", "agents", "outcome", "needs_approval"} <= set(i) for i in today["items"])
    o = make_client(db=c.app.state.db)
    register(o, "other@p1.co")
    assert o.get(f"/api/missions/{m['id']}").status_code == 404 and o.get("/api/missions").json()["items"] == []
