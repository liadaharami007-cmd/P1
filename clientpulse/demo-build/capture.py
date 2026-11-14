import json, os, sys, tempfile
os.environ["P1_RUN_WORKER"] = "0"; os.environ["P1_AI_ENGINE"] = "rules"
sys.path.insert(0, "/home/user/P1")
from fastapi.testclient import TestClient
from app.db import Database
from app.main import create_app
OUT = sys.argv[1]
c = TestClient(create_app(db=Database(tempfile.mkdtemp() + "/s.db")))
assert c.post("/api/auth/register", json={"email": "niv@demo-agency.co", "password": "correct-horse-battery", "name": "ניב", "account_name": "משרד הפרסום — דמו"}).status_code == 201
c.post("/api/pulse/demo")
P = lambda u, b=None: c.post(u, json=b or {}).json()
tasks = [t for t in c.get("/api/pulse/tasks").json()["tasks"]]
reds = [t for t in tasks if t["severity"] == "red" and (t["alert_key"] or "").endswith(":cpl")] or [t for t in tasks if t["severity"] == "red"]
# יום עבודה: אחד טופל ואומת, אחד ממתין לאישור, שניים בטיפול
t0 = reds[0]["id"]
for a in ("start", "submit", "approve", "simulate_fix"): P(f"/api/pulse/tasks/{t0}/{a}")
P("/api/pulse/lab/advance", {"days": 4})
tasks = c.get("/api/pulse/tasks").json()["tasks"]
open_reds = [t for t in tasks if t["status"] == "new" and t["severity"] == "red"]
if open_reds:
    t1 = open_reds[0]["id"]; P(f"/api/pulse/tasks/{t1}/start"); P(f"/api/pulse/tasks/{t1}/submit")
for t in open_reds[1:3]: P(f"/api/pulse/tasks/{t['id']}/start"); P(f"/api/pulse/tasks/{t['id']}/log_time", {"extra": 25})
P("/api/pulse/lab/scenario", {"scenario": "zero_leads"})
for cl in [x for x in c.get("/api/pulse/clients").json()["clients"] if x["status"] == "red"][:4]:
    P(f"/api/pulse/clients/{cl['id']}/update-draft")
data = {}
G = lambda u: data.__setitem__(u, c.get(u).json())
for u in ["/api/pulse/state", "/api/pulse/overview", "/api/pulse/alerts", "/api/pulse/clients", "/api/pulse/tasks", "/api/pulse/notifications",
          "/api/pulse/automations", "/api/pulse/impact", "/api/pulse/team", "/api/pulse/profit", "/api/pulse/opportunities", "/api/pulse/lab",
          "/api/pulse/integrations", "/api/pulse/ask/suggestions", "/api/pulse/brief", "/api/pulse/ads", "/api/pulse/my", "/api/pulse/trend",
          "/api/pulse/settings/thresholds", "/api/pulse/knowledge", "/api/pulse/decisions", "/api/pulse/commitments"]:
    G(u)
data["/api/pulse/state"]["unread"] = 0
for m in data["/api/pulse/state"]["team"]:
    G(f"/api/pulse/my?member={m['id']}")
for cl in data["/api/pulse/clients"]["clients"]:
    if cl["source"] == "demo":
        G(f"/api/pulse/ads?client={cl['id']}")
    for d in (30, 90):
        G(f"/api/pulse/clients/{cl['id']}?days={d}")
asks = {}
qs = list(data["/api/pulse/ask/suggestions"]["suggestions"])
for cl in data["/api/pulse/clients"]["clients"]:
    if cl["alerts"]:
        qs += [f"למה {cl['name']} במצב הזה?", f"תכין לי סיכום לפגישה עם {cl['name']}"]
for q in qs:
    a = c.post("/api/pulse/ask", json={"q": q}).json()
    asks[q] = a
    qs += [f for f in a.get("follow", []) if f not in asks and f not in qs]
data["__ask__"] = asks
json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
print(len(data), "keys", os.path.getsize(OUT) // 1024, "KB", "asks", len(asks))
