// P1 AI — נקודת הכניסה: ניווט בין עמודים (hash router) ומצב המערכת
import { $, $$, api, icon, openLightbox, setCategories } from "./ui.js";
import { dashboardView } from "./views/dashboard.js";
import { auditsView } from "./views/audits.js";
import { auditView } from "./views/audit.js";
import { tasksView } from "./views/tasks.js";
import { assistantView } from "./views/assistant.js";
import { integrationsView } from "./views/integrations.js";

const NAV = [
  { path: "/", label: "לוח בקרה", short: "בית", icon: "dashboard" },
  { path: "/audits", label: "בדיקות אתר", short: "בדיקות", icon: "audit" },
  { path: "/tasks", label: "משימות תיקון", short: "משימות", icon: "tasks" },
  { path: "/assistant", label: "עוזר AI", short: "עוזר", icon: "chat" },
  { path: "/integrations", label: "חיבורים", short: "חיבורים", icon: "plug" },
];

export const app = { status: null, cleanup: null };

function route() {
  const hash = location.hash.replace(/^#/, "").split("?")[0] || "/";
  const m = hash.match(/^\/audits\/([a-f0-9]+)$/);
  if (m) return { view: auditView, params: { id: m[1] }, nav: "/audits" };
  const table = { "/": dashboardView, "/audits": auditsView, "/tasks": tasksView, "/assistant": assistantView, "/integrations": integrationsView };
  return { view: table[hash] || dashboardView, params: {}, nav: table[hash] ? hash : "/" };
}

function renderNav(active) {
  const item = (n, short) => `<a href="#${n.path}" class="${n.path === active ? "active" : ""}" ${n.path === active ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${short ? n.short : n.label}</span></a>`;
  $("#nav").innerHTML = NAV.map((n) => item(n)).join("");
  $("#bottom-nav").innerHTML = NAV.map((n) => item(n, true)).join("");
}

function renderSystemStatus() {
  const c = app.status.capabilities;
  const row = (label, cap) => `<div class="sys-row"><span class="sys-dot ${cap.ready ? "on" : "off"}"></span>${label}${cap.ready ? "" : " — לא מחובר"}</div>`;
  $("#system-status").innerHTML = `<h4>מצב המערכת</h4>${row("בדיקות בדפדפן", c.browser_audit)}${row("סימולציית לקוחות", c.customer_simulation)}${row("Claude AI", c.chat)}${row("נתוני חנות", c.store_data)}`;
}

async function render() {
  if (app.cleanup) { app.cleanup(); app.cleanup = null; }
  const r = route();
  renderNav(r.nav);
  const view = $("#view");
  $("#topbar-actions").innerHTML = "";
  try {
    const cleanup = await r.view(view, r.params, app);
    if (typeof cleanup === "function") app.cleanup = cleanup;
  } catch (e) {
    view.innerHTML = `<div class="notice notice-error">שגיאה בטעינת העמוד: ${e.message}</div>`;
  }
  view.focus({ preventScroll: true });
}

export function setTitle(title, actions = "") {
  $("#page-title").textContent = title;
  document.title = `${title} · P1 AI`;
  $("#topbar-actions").innerHTML = actions;
}

// הגדלת צילומי מסך — לכל כפתור עם data-shot בכל העמודים
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-shot]");
  if (b) { e.preventDefault(); openLightbox(`/api/screenshots/${b.dataset.shot}`, b.dataset.caption); }
  if (e.target.closest("[data-close]") || e.target.id === "lightbox") $("#lightbox").close();
});

window.addEventListener("hashchange", render);
(async () => {
  try {
    app.status = await api("/api/status");
    setCategories(app.status.categories);
    renderSystemStatus();
  } catch (e) {
    $("#view").innerHTML = `<div class="notice notice-error">השרת לא זמין: ${e.message}</div>`;
    return;
  }
  render();
})();
