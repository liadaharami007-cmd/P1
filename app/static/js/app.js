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

/** @typedef {{ status: any, me: any, account: any, cleanup: (() => void) | null }} AppState */
/** @type {AppState} */
export const app = { status: null, me: null, account: null, cleanup: null };

const NAV = [
  { path: "/", key: "overview", icon: "overview" },
  { path: "/audits", key: "audits", icon: "audit" },
  { path: "/tasks", key: "tasks", icon: "tasks" },
  { path: "/assistant", key: "assistant", icon: "chat" },
  { path: "/integrations", key: "integrations", icon: "plug", desktopOnly: true },
  { path: "/account", key: "account", icon: "account" },
];

function route() {
  const hash = location.hash.replace(/^#/, "").split("?")[0] || "/";
  const m = hash.match(/^\/audits\/([a-f0-9]+)$/);
  if (m) return { view: auditView, params: /** @type {any} */ ({ id: m[1] }), nav: "/audits" };
  /** @type {Record<string, Function>} */
  const table = { "/": dashboardView, "/audits": auditsView, "/tasks": tasksView, "/assistant": assistantView,
    "/integrations": integrationsView, "/account": accountView, "/admin": adminView };
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
      </header>
      <main id="view" class="view" tabindex="-1"></main>
    </div>
  </div>
  <nav class="bottom-nav" id="bottom-nav" aria-label="Main"></nav>`;
  $("#lang-btn").onclick = () => switchLang();
  $("#logout-btn").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); boot(); };
}

/** @param {string} active */
function renderNav(active) {
  const item = (/** @type {any} */ n, /** @type {boolean} */ short) =>
    `<a href="#${n.path}" class="${n.path === active ? "active" : ""}" ${n.path === active ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${t((short ? "nav.short." : "nav.") + n.key)}</span></a>`;
  const admin = app.me.user.is_platform_admin ? `<div class="nav-label">P1</div>${item({ path: "/admin", key: "admin", icon: "admin" }, false)}` : "";
  $("#nav").innerHTML = NAV.map((n) => item(n, false)).join("") + admin;
  $("#bottom-nav").innerHTML = NAV.filter((n) => !n.desktopOnly).map((n) => item(n, true)).join("");
}

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
  render();
}

boot();
