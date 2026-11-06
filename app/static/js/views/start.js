// @ts-check
// מסך פתיחה: "מה תרצה להשיג היום?" — 6 מסלולים + שיחה חופשית. משם P1 CEO מובילה.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";
import { AGENT } from "../agents-meta.js";

/** אריח אייקון בצבע הסוכן. @param {string} key */
export const tile = (key) => { const a = AGENT[key] || AGENT.consult; return `<span class="tile" style="--hue:${a.hue}">${icon(a.icon)}</span>`; };

const PATHS = [
  ["stuck", "start.p.stuck", "start.p.stuckT"], ["site_sales", "start.p.site", "start.p.siteT"], ["ads", "start.p.ads", "start.p.adsT"],
  ["customers", "start.p.customers", "start.p.customersT"], ["start", "start.p.start", "start.p.startT"], ["no_time", "start.p.notime", "start.p.notimeT"],
];
const HOW = [["browser", "start.how1", "start.how1T"], ["users", "start.how2", "start.how2T"], ["check", "start.how3", "start.how3T"], ["trend", "start.how4", "start.how4T"]];

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function startView(view, _p, app) {
  setTitle(t("start.title"));
  const ms = await api("/api/missions");
  const name = app.me.user.name ? app.me.user.name.split(" ")[0] : "";
  view.innerHTML = `<div class="start">
    <section class="start-hero aurora">
      <div class="start-mark" aria-hidden="true">P1</div>
      <div class="eyebrow-light">${t("start.eyebrow")}</div>
      <h2>${name ? esc(name) + ", " : ""}${t("start.q")}</h2>
      <p class="lead">${t("start.sub")}</p>
    </section>
    <div class="path-grid problems">${PATHS.map(([id, ti, tx]) => `<a class="path-card" href="#/ceo?intent=${id}">
      ${tile(id)}<strong>${t(ti)}</strong><span class="small muted">${t(tx)}</span><span class="path-go">${icon("chevron")}</span></a>`).join("")}</div>
    <section class="free-box">      <form id="free" class="start-free" novalidate><label class="free-label" for="free-text">${t("start.freeLabel")}</label>
        <textarea class="input" id="free-text" name="text" rows="2" placeholder="${t("start.placeholder")}" aria-label="${t("start.q")}"></textarea>
        <div class="start-btns"><button class="btn btn-primary" type="submit">${icon("sparkle")}${t("start.go")}</button>
        <button class="btn" type="button" id="autopilot">${icon("play")}${t("start.autopilot")}</button></div>
      </form>
      <div class="start-examples" hidden>${["start.ex1", "start.ex2", "start.ex3", "start.ex4"].map((k) => `<button class="chip-btn" data-ex="${esc(t(k))}">${t(k)}</button>`).join("")}</div>
</section>
    <a class="agency-strip" href="#/ceo?intent=agency">${tile("agency")}<span><strong>${t("start.p.agency")}</strong><span class="small muted">${t("start.p.agencyT")}</span></span>${icon("chevron")}</a>
    <section class="how-solve"><h2 class="section-title">${t("start.howTitle")}</h2>
      <ol class="how-steps">${HOW.map(([ic, ti, tx], n) => `<li><span class="how-n">${n + 1}</span><span class="tile" style="--hue:var(--brand)">${icon(ic)}</span><div><strong>${t(ti)}</strong><p class="small muted">${t(tx)}</p></div></li>`).join("")}</ol></section>
    <section class="gets card"><h2 class="section-title" style="margin-top:0">${t("start.getsTitle")}</h2><p class="small muted">${t("start.getsSub")}</p>
      <div class="gets-grid">${[["browser", 1], ["megaphone", 2], ["handshake", 3], ["bolt", 4], ["check", 5], ["trend", 6]].map(([ic, n]) =>
        `<div class="get"><span class="tile">${icon(String(ic))}</span><div><strong>${t(`start.get${n}`)}</strong><p class="small muted">${t(`start.get${n}T`)}</p></div></div>`).join("")}</div>
      <a class="btn btn-primary" id="gets-go" href="#/run" style="margin-top:14px">${icon("play")}${t("start.getsCta")}</a></section>
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
