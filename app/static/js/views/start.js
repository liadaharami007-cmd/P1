// @ts-check
// מסך פתיחה: "מה תרצה להשיג היום?" — 6 מסלולים + שיחה חופשית. משם P1 CEO מובילה.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";

const PATHS = [
  ["start", "🚀", "start.p.start", "start.p.startT"], ["grow", "📈", "start.p.grow", "start.p.growT"],
  ["website", "🌐", "start.p.website", "start.p.websiteT"], ["marketing", "📣", "start.p.marketing", "start.p.marketingT"],
  ["manage", "🧭", "start.p.manage", "start.p.manageT"], ["consult", "💬", "start.p.consult", "start.p.consultT"],
];

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function startView(view, _p, app) {
  setTitle(t("start.title"));
  const ms = await api("/api/missions");
  const name = app.me.user.name ? app.me.user.name.split(" ")[0] : "";
  view.innerHTML = `<div class="start">
    <section class="start-hero">
      <div class="start-mark" aria-hidden="true">P1</div>
      <h2>${name ? esc(name) + ", " : ""}${t("start.q")}</h2>
      <p class="lead">${t("start.sub")}</p>
      <form id="free" class="start-free" novalidate>
        <textarea class="input" name="text" rows="2" placeholder="${t("start.placeholder")}" aria-label="${t("start.q")}"></textarea>
        <div class="start-btns"><button class="btn btn-primary" type="submit">${icon("sparkle")}${t("start.go")}</button>
        <button class="btn" type="button" id="autopilot">${icon("play")}${t("start.autopilot")}</button></div>
      </form>
      <div class="start-examples">${["start.ex1", "start.ex2", "start.ex3", "start.ex4"].map((k) => `<button class="chip-btn" data-ex="${esc(t(k))}">${t(k)}</button>`).join("")}</div>
    </section>
    <div class="path-grid">${PATHS.map(([id, emo, ti, tx]) => `<a class="path-card" href="#/ceo?intent=${id}">
      <span class="path-emo">${emo}</span><strong>${t(ti)}</strong><span class="small muted">${t(tx)}</span></a>`).join("")}
      <a class="path-card path-agency" href="#/ceo?intent=agency"><span class="path-emo">🏢</span><strong>${t("start.p.agency")}</strong><span class="small muted">${t("start.p.agencyT")}</span></a>
    </div>
    ${ms.items.length ? `<section class="card"><div class="card-head"><h2>${t("start.missions")}</h2><a class="btn btn-sm btn-ghost" href="#/">${t("nav.command")}</a></div>
      <div class="list">${ms.items.slice(0, 5).map((/** @type {any} */ m) => `<a class="list-item" href="#/ceo?mission=${m.id}"><strong class="small">${esc(m.title)}</strong>
        <span class="tiny faint" style="margin-inline-start:auto">${new Date(m.created_at).toLocaleDateString()}</span></a>`).join("")}</div></section>` : ""}
  </div>`;
  const form = /** @type {HTMLFormElement} */ (view.querySelector("#free"));
  const go = async (/** @type {string} */ text) => {
    try {
      const r = await api("/api/ceo/intent", { method: "POST", body: JSON.stringify({ text }) });
      sessionStorage.setItem("p1.ceoText", text);
      location.hash = `#/ceo?intent=${r.intent}`;
    } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
  /** @type {HTMLElement} */ (view.querySelector("#autopilot")).onclick = async () => {
    const v = String(new FormData(form).get("text") || "").trim() || t("ap.example");
    try { const r = await api("/api/autopilot", { method: "POST", body: JSON.stringify({ request: v }) }); location.hash = `#/run?id=${r.id}`; }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
  form.onsubmit = (e) => { e.preventDefault(); const v = String(new FormData(form).get("text") || "").trim(); if (v) go(v); };
  view.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => go(/** @type {HTMLElement} */ (b).dataset.ex || "")));
}
