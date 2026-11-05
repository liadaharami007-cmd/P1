import { setTitle } from "../app.js";
import { api, FINDING_STATUS, hostOf, toast } from "../ui.js";
import { findingCard } from "./audit.js";

const ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export async function tasksView(view) {
  setTitle("משימות תיקון");
  const all = await api("/api/tasks");
  if (!all.length) {
    view.innerHTML = `<div class="card empty"><h3>אין משימות עדיין</h3><p>אחרי בדיקת אתר, כל בעיה שנמצאה תופיע כאן כמשימה.</p><a class="btn btn-primary" href="#/audits">להתחלת בדיקה</a></div>`;
    return;
  }
  const multi = new Set(all.map((f) => f.site_id)).size > 1;
  const groups = ["in_progress", "open", "done", "dismissed"];
  let active = "open";
  const draw = () => {
    const list = all.filter((f) => f.status === active).sort((a, b) => ORDER[a.severity] - ORDER[b.severity]);
    view.innerHTML = `<p class="muted" style="margin-top:0">הבעיות מהבדיקה האחרונה של כל אתר. עדכנו סטטוס תוך כדי עבודה, ואחרי תיקון — הריצו בדיקה חוזרת כדי לוודא שזה באמת עבד.</p>
      <div class="tabs">${groups.map((g) => `<button data-g="${g}" class="${g === active ? "active" : ""}">${FINDING_STATUS[g]}<span class="count">${all.filter((f) => f.status === g).length}</span></button>`).join("")}</div>
      ${list.length ? list.map((f) => findingCard(f, multi ? `<span class="badge badge-outline ltr">${hostOf(f.site_url)}</span>` : "")).join("") : `<div class="card empty">אין משימות בסטטוס הזה.</div>`}`;
    view.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => { active = b.dataset.g; draw(); }));
    view.querySelectorAll("[data-status-for]").forEach((sel) => sel.addEventListener("change", async () => {
      try {
        await api(`/api/findings/${sel.dataset.statusFor}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) });
        all.find((f) => f.id === sel.dataset.statusFor).status = sel.value;
        toast(`הועבר ל"${FINDING_STATUS[sel.value]}"`); draw();
      } catch (e) { toast(e.message); }
    }));
  };
  draw();
}
