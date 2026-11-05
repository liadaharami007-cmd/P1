// @ts-check
// P1 AI — מעטפת האפליקציה: התחברות, ניווט, שפה, מצב מערכת.
import { lang, setLang, t } from "./i18n.js";
import { $, $$, api, esc, icon, openLightbox, setCategories } from "./ui.js";
import { authView } from "./views/auth.js";
import { dashboardView } from "./views/dashboard.js";
import { auditsView } from "./views/audits.js";
import { auditView } from "./views/audit.js";
import { tasksView } from "./views/tasks.js";
import { assistantView } from "./views/assistant.js";
import { integrationsView } from "./views/integrations.js";
import { accountView } from "./views/account.js";
import { adminView } from "./views/admin.js";
import { fixStudioView } from "./views/fixstudio.js";
import { sitesView } from "./views/sites.js";
import { demoView } from "./views/demo.js";

/** @typedef {{ status: any, me: any, account: any, cleanup: (() => void) | null }} AppState */
/** @type {AppState} */
export const app = { status: null, me: null, account: null, cleanup: null };

const NAV = [
  { path: "/", key: "overview", icon: "overview", group: "workspace" },
  { path: "/sites", key: "sites", icon: "globe", group: "workspace" },
  { path: "/audits", key: "audits", icon: "audit", group: "workspace" },
  { path: "/fix", key: "fix", icon: "sparkle", group: "workspace", desktopOnly: true },
  { path: "/tasks", key: "tasks", icon: "tasks", group: "workspace" },
  { path: "/assistant", key: "assistant", icon: "chat", group: "workspace" },
  { path: "/demo", key: "demo", icon: "play", group: "settings", desktopOnly: true },
  { path: "/integrations", key: "integrations", icon: "plug", group: "settings", desktopOnly: true },
  { path: "/account", key: "account", icon: "account", group: "settings" },
];

function route() {
  const hash = location.hash.replace(/^#/, "").split("?")[0] || "/";
  const m = hash.match(/^\/audits\/([a-f0-9]+)$/);
  if (m) return { view: auditView, params: /** @type {any} */ ({ id: m[1] }), nav: "/audits" };
  const fx = hash.match(/^\/fix(?:\/([a-f0-9]+))?$/);
  if (fx) return { view: fixStudioView, params: /** @type {any} */ ({ id: fx[1] || null }), nav: "/fix" };
  /** @type {Record<string, Function>} */
  const table = { "/": dashboardView, "/audits": auditsView, "/tasks": tasksView, "/assistant": assistantView,
    "/integrations": integrationsView, "/account": accountView, "/admin": adminView, "/sites": sitesView, "/demo": demoView };
  return { view: table[hash] || dashboardView, params: /** @type {any} */ ({}), nav: table[hash] ? hash : "/" };
}

function shell() {
  const u = app.me.user;
  $("#root").innerHTML = `<div class="shell">
    <aside class="sidebar" aria-label="Main">
      <a class="logo" href="#/"><span class="logo-mark">P1</span><span class="logo-text">P1 AI<small>${esc(app.me.account.name)}</small></span></a>
      <nav class="nav" id="nav"></nav>
      <div class="side-foot">
        <div class="usage-mini" id="usage-mini"></div>
        <div class="user-row"><span class="avatar">${esc((u.name || u.email)[0].toUpperCase())}</span>
          <span class="truncate" style="flex:1" title="${esc(u.email)}">${esc(u.name || u.email)}</span>
          <button class="icon-btn" id="lang-btn" title="${t("common.language")}" aria-label="${t("common.language")}">${icon("globe")}</button>
          <button class="icon-btn" id="logout-btn" title="${t("common.logout")}" aria-label="${t("common.logout")}">${icon("logout")}</button></div>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        <a class="logo logo-mobile" href="#/"><span class="logo-mark">P1</span></a>
        <h1 class="page-title truncate" id="page-title"></h1>
        <div class="topbar-actions" id="topbar-actions"></div>
        <div class="notif-wrap"><button class="icon-btn" id="notif-btn" aria-label="${t("notif.title")}" aria-haspopup="true">${icon("bell")}<span class="notif-dot" id="notif-dot" hidden></span></button>
          <div class="notif-panel" id="notif-panel" hidden></div></div>
      </header>
      <main id="view" class="view" tabindex="-1"></main>
    </div>
  </div>
  <nav class="bottom-nav" id="bottom-nav" aria-label="Main"></nav>`;
  $("#lang-btn").onclick = () => switchLang();
  $("#notif-btn").onclick = (/** @type {Event} */ e) => { e.stopPropagation(); toggleNotifications(); };
  $("#logout-btn").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); boot(); };
}

/** @param {string} active */
function renderNav(active) {
  const item = (/** @type {any} */ n, /** @type {boolean} */ short) =>
    `<a href="#${n.path}" class="${n.path === active ? "active" : ""}" ${n.path === active ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${t((short ? "nav.short." : "nav.") + n.key)}</span></a>`;
  const admin = app.me.user.is_platform_admin ? item({ path: "/admin", key: "admin", icon: "admin" }, false) : "";
  const group = (/** @type {string} */ g) => NAV.filter((n) => n.group === g).map((n) => item(n, false)).join("");
  $("#nav").innerHTML = `<div class="nav-label">${t("nav.group.workspace")}</div>${group("workspace")}<div class="nav-label">${t("nav.group.settings")}</div>${group("settings")}${admin}`;
  $("#bottom-nav").innerHTML = NAV.filter((n) => !n.desktopOnly).map((n) => item(n, true)).join("");
}

async function refreshNotifications() {
  try {
    const n = await api("/api/notifications");
    $("#notif-dot").hidden = !n.unread;
    return n;
  } catch { return { items: [], unread: 0 }; }
}

async function toggleNotifications() {
  const panel = $("#notif-panel");
  if (!panel.hidden) { panel.hidden = true; return; }
  const n = await refreshNotifications();
  const ICON = { new_issues: "✕", fixed_issues: "✓", score_change: "↕", first_audit: "★", monitor_skipped: "!", audit_failed: "!" };
  panel.innerHTML = `<div class="row" style="justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border)"><strong>${t("notif.title")}</strong>
    ${n.unread ? `<button class="btn btn-ghost btn-sm" id="notif-read">${t("notif.markRead")}</button>` : ""}</div>
    <div class="notif-list">${n.items.length ? n.items.map((/** @type {any} */ x) => `<a class="notif-item ${x.read_at ? "" : "unread"}" href="${x.audit_id ? `#/audits/${x.audit_id}` : "#/sites"}">
      <span class="notif-ico k-${x.kind}">${/** @type {any} */ (ICON)[x.kind] || "•"}</span><span><strong>${esc(x.title)}</strong><br><span class="small muted">${esc(x.body)}</span>
      <br><span class="tiny faint">${new Date(x.created_at).toLocaleString()}</span></span></a>`).join("") : `<div class="empty small">${t("notif.none")}</div>`}</div>`;
  panel.hidden = false;
  const btn = $("#notif-read");
  if (btn) btn.onclick = async () => { await api("/api/notifications/read", { method: "POST" }); panel.hidden = true; refreshNotifications(); };
}
document.addEventListener("click", (e) => {
  const p = document.getElementById("notif-panel");
  if (p && !p.hidden && !/** @type {HTMLElement} */ (e.target).closest(".notif-wrap")) p.hidden = true;
});

export async function refreshUsage() {
  try {
    app.account = await api("/api/account");
    const u = app.account.usage, p = app.account.plan;
    const pct = Math.min(100, Math.round((u.audits / p.audits_per_month) * 100));
    $("#usage-mini").innerHTML = `<div class="row" style="justify-content:space-between"><span class="muted">${p.name} · ${t("acc.audits")}</span>
      <span class="num"><strong>${u.audits}</strong>/${p.audits_per_month}</span></div>
      <div class="meter ${pct >= 100 ? "full" : pct >= 80 ? "warn" : ""}"><div style="width:${pct}%"></div></div>`;
  } catch { /* לא קריטי */ }
}

async function render() {
  if (!app.me) return;
  if (app.cleanup) { app.cleanup(); app.cleanup = null; }
  const r = route();
  renderNav(r.nav);
  const view = $("#view");
  view.style.animation = "none"; void view.offsetWidth; view.style.animation = "";
  $("#topbar-actions").innerHTML = "";
  view.innerHTML = `<div class="stack"><div class="skeleton" style="height:120px"></div><div class="skeleton" style="height:260px"></div></div>`;
  try {
    const cleanup = await r.view(view, r.params, app);
    if (typeof cleanup === "function") app.cleanup = cleanup;
  } catch (e) {
    view.innerHTML = `<div class="notice notice-error"><span class="ico">!</span><span>${esc(/** @type {Error} */ (e).message)}</span></div>`;
  }
  view.focus({ preventScroll: true });
}

/** @param {string} title @param {string} [actions] */
export function setTitle(title, actions = "") {
  $("#page-title").textContent = title;
  document.title = `${title} · P1 AI`;
  $("#topbar-actions").innerHTML = actions;
}

async function switchLang() {
  const next = lang === "he" ? "en" : "he";
  setLang(next);
  if (app.me) { try { await api("/api/me", { method: "PATCH", body: JSON.stringify({ locale: next }) }); } catch { /* */ } }
  boot();
}

// הגדלת צילומי מסך + סגירת חלונות
document.addEventListener("click", (e) => {
  const target = /** @type {HTMLElement} */ (e.target);
  const b = /** @type {HTMLElement|null} */ (target.closest("[data-shot]"));
  if (b) { e.preventDefault(); openLightbox(`/api/screenshots/${b.dataset.shot}`, b.dataset.caption); }
  if (target.closest("[data-close]") || target.id === "lightbox") $("#lightbox").close();
  if (target.closest("[data-close-modal]") || target.id === "modal") $("#modal").close();
});
window.addEventListener("hashchange", render);
window.addEventListener("p1:unauthorized", () => { app.me = null; boot(); });
window.addEventListener("p1:usage", () => refreshUsage());

export async function boot() {
  if (app.cleanup) { app.cleanup(); app.cleanup = null; }
  try {
    app.me = await api("/api/auth/me");
  } catch {
    app.me = null;
    await authView($("#root"), { onDone: boot, switchLang });
    return;
  }
  if (app.me.user.locale && app.me.user.locale !== lang && !sessionStorage.getItem("p1.langSynced")) {
    sessionStorage.setItem("p1.langSynced", "1");
    setLang(app.me.user.locale);
  }
  app.status = await api("/api/status");
  setCategories(app.status.categories, app.status.categories_en);
  shell();
  refreshUsage();
  refreshNotifications();
  render();
}

boot();
