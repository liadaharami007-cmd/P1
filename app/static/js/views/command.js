// @ts-check
// Business Command Center — המסך הראשי: 3 הפעולות הבאות, בריאות העסק, הוכחת ערך, דוח שבועי.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, fmtDate, hostOf, icon, scoreRing, animateRings, toast } from "../ui.js";
import { actionCard, bindActionButtons, openActionModal } from "./approvals.js";

const AREA_ICON = { website: "globe", brain: "account", trust: "admin", conversion: "sparkle", checkout: "tasks", ux_mobile: "globe", technical: "plug" };

/** @param {any} it */
function planCard(it, i) {
  const st = it.open_action;
  const btn = st ? `<button class="btn btn-sm" data-open-action="${st.id}">${st.status === "executing" ? `<span class="live-dot"></span>${t("cmd.running")}` : t("cmd.waiting")}</button>`
    : it.kind === "link" ? `<a class="btn btn-sm btn-primary" href="${it.link}">${t("cmd.open")}</a>`
    : `<button class="btn btn-sm btn-primary" data-prepare="${esc(it.key)}">${icon("wand")}${t("cmd.prepare")}</button>`;
  return `<article class="next-card">
    <div class="next-num">${i + 1}</div>
    <div class="next-body"><div class="next-head"><span class="next-ico">${icon(/** @type {any} */ (AREA_ICON)[it.area] || "sparkle")}</span>
      <h3>${esc(it.title)}</h3></div>
      <p class="small muted">${esc(it.why)}</p>
      ${it.evidence ? `<p class="tiny faint" style="margin-top:4px">${esc(it.evidence)}</p>` : ""}
      <div class="next-foot"><span class="chip">${t("cmd.impact")}: ${t("lvl." + it.impact)}</span><span class="chip">${t("cmd.effort")}: ${t("lvl." + it.effort)}</span>
        <span class="chip">${t("cmd.minutes", { n: it.minutes })}</span><span class="spacer"></span>${btn}</div></div>
  </article>`;
}

/** @param {any} d */
function healthCard(d) {
  return `<div class="card"><div class="card-head"><div><h2>${t("cmd.health")}</h2><div class="card-sub">${t("cmd.healthSub")}</div></div></div>
    <div class="health-grid">${d.health.domains.map((/** @type {any} */ x) => `<div class="health-item ${x.status}">
      <div class="row" style="justify-content:space-between"><strong class="small">${t("dom." + x.id)}</strong>
      ${x.status === "measured" ? `<span class="badge src-measured">${t("cmd.measured")}</span>` : `<span class="badge">${t("cmd.noData")}</span>`}</div>
      ${x.score != null ? `<div class="health-score num">${x.score}<small>/100</small></div>`
        : x.trend != null ? `<div class="health-score num">${x.trend > 0 ? "+" : ""}${x.trend}</div>`
        : `<div class="tiny faint" style="margin-top:6px">${t("cmd.missing")} ${esc(x.missing || "")}</div>`}
      ${x.basis ? `<div class="tiny faint">${esc(x.basis)}</div>` : ""}</div>`).join("")}</div>
    ${d.health.overall == null ? `<div class="notice" style="margin-top:12px"><span class="ico">i</span><span class="small">${esc(d.health.overall_reason)}</span></div>` : ""}</div>`;
}

/** @param {any} p */
function proofCard(p) {
  const hrs = Math.round(p.time_saved_estimate.minutes / 6) / 10;
  return `<div class="card"><div class="card-head"><div><h2>${t("cmd.proof")}</h2><div class="card-sub">${t("cmd.proofSub")}</div></div></div>
    <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
      <div class="kpi"><div class="kpi-num">${p.audits_done}</div><div class="kpi-label">${t("cmd.audits")}</div></div>
      <div class="kpi"><div class="kpi-num">${p.browser_steps}</div><div class="kpi-label">${t("cmd.steps")}</div></div>
      <div class="kpi"><div class="kpi-num">${p.issues_fixed_verified.length}</div><div class="kpi-label">${t("cmd.fixedVerified")}</div></div>
      <div class="kpi"><div class="kpi-num">${t("cmd.hours", { n: hrs })}</div><div class="kpi-label">${t("cmd.timeSaved")}</div></div></div>
    <p class="tiny faint" style="margin-top:10px">${esc(p.time_saved_estimate.assumption)} · ${esc(p.revenue_note)}</p></div>`;
}

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function commandView(view, _p, app) {
  view.innerHTML = `<div></div>`;
  const root = /** @type {HTMLElement} */ (view.firstElementChild);
  let timer = 0;
  const load = async () => {
    const [d, wk] = await Promise.all([api("/api/business/overview"), api("/api/business/weekly")]);
    const name = d.profile.business_name || app.me.account.name;
    setTitle(t("nav.command"), `<a class="btn btn-sm" href="#/approvals">${t("nav.approvals")}${d.pending_actions.length ? ` <span class="count-pill">${d.pending_actions.length}</span>` : ""}</a>`);
    const L = d.latest;
    root.innerHTML = `<div class="stack">
      <section class="cmd-hero">
        <div style="flex:1;min-width:0"><div class="eyebrow">${esc(name)}${d.site ? ` · <span class="ltr">${esc(hostOf(d.site.url))}</span>` : ""}</div>
          <h2>${t("cmd.hello", { name: app.me.user.name ? ", " + esc(app.me.user.name.split(" ")[0]) : "" })}</h2>
          <p class="lead">${t("cmd.sub")}</p>
          ${!d.completeness.ready ? `<a class="btn btn-primary" href="#/business" style="margin-top:14px">${t("cmd.profileBtn")} · ${d.completeness.percent}%</a>` : ""}</div>
        ${L ? `<a class="cmd-score" href="#/audits/${L.id}" aria-label="score">${scoreRing(L.score, 112)}<span class="tiny">${t("dom.website")} · ${fmtDate(L.finished_at)}</span></a>` : ""}
      </section>

      <section class="card"><div class="card-head"><div><h2>${t("cmd.top3")}</h2><div class="card-sub">${t("cmd.top3Sub")}</div></div>
        <span class="badge">${t("act.source.rules")}</span></div>
        ${d.plan.top3.length ? `<div class="next-list">${d.plan.top3.map(planCard).join("")}</div>` : `<div class="empty small">${t("cmd.empty")}</div>`}
        ${d.plan.items.length > 3 ? `<details class="more-plan"><summary class="small">${t("cmd.allPlan")} (${d.plan.items.length})</summary>
          <div class="next-list" style="margin-top:10px">${d.plan.items.slice(3).map((/** @type {any} */ x, /** @type {number} */ i) => planCard(x, i + 3)).join("")}</div>
          <p class="tiny faint">${esc(d.plan.method)}</p></details>` : ""}
      </section>

      ${d.pending_actions.length ? `<section><h2 class="section-title">${t("cmd.pending")}</h2><div class="stack">${d.pending_actions.slice(0, 3).map(actionCard).join("")}</div></section>` : ""}

      <div class="grid g-main">${healthCard(d)}${proofCard(d.proof)}</div>

      <div class="grid g-main">
        <div class="card"><div class="card-head"><div><h2>${t("wk.title")}</h2><div class="card-sub">${t("wk.period")} · ${t("wk.audits")}: ${wk.audits_in_period}</div></div>
          <a class="btn btn-sm btn-ghost" href="#/timeline">${t("nav.timeline")}</a></div>
          <ul class="wk-lines">${wk.summary.map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
        <div class="card" id="brief"><div class="card-head"><div><h2>${t("cmd.brief")}</h2></div><span class="badge src-ai">${d.engines}</span></div>
          ${d.engines === "rules" ? `<div class="notice"><span class="ico">i</span><span class="small">${t("cmd.briefNone")}</span></div>`
            : `<button class="btn btn-sm" id="brief-btn">${icon("sparkle")}${t("cmd.briefBtn")}</button><div id="brief-out"></div>`}</div>
      </div></div>`;
    animateRings(root);
    const bb = /** @type {HTMLButtonElement|null} */ (root.querySelector("#brief-btn"));
    if (bb) bb.onclick = async () => {
      bb.disabled = true;
      try {
        const r = await api("/api/business/brief", { method: "POST" });
        const out = /** @type {HTMLElement} */ (root.querySelector("#brief-out"));
        out.innerHTML = r.ai_status !== "done" ? `<p class="small muted">${esc(r.missing)}</p>` : `<p style="margin-top:10px">${esc(r.summary)}</p>
          ${r.insufficient_data.length ? `<p class="small muted">${t("cmd.insufficient")} ${r.insufficient_data.map(esc).join(" · ")}</p>` : ""}
          <ul class="wk-lines">${r.advice.map((/** @type {any} */ a) => `<li><strong>${esc(a.title)}</strong> — ${esc(a.why)} <span class="tiny faint">${t("cmd.basedOn")} ${esc(a.based_on)}</span></li>`).join("")}</ul>`;
      } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
      bb.disabled = false;
    };
    clearTimeout(timer);
    if (d.pending_actions.some((/** @type {any} */ a) => a.status === "executing")) timer = window.setTimeout(load, 5000);
  };
  root.addEventListener("click", async (e) => {
    const el = /** @type {HTMLElement} */ (e.target);
    const prep = /** @type {HTMLButtonElement|null} */ (el.closest("[data-prepare]"));
    const open = /** @type {HTMLElement|null} */ (el.closest("[data-open-action]"));
    try {
      if (prep) { prep.disabled = true; openActionModal(await api("/api/actions", { method: "POST", body: JSON.stringify({ key: prep.dataset.prepare }) }), load); load(); }
      if (open) openActionModal(await api(`/api/actions/${open.dataset.openAction}`), load);
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); if (prep) prep.disabled = false; }
  });
  bindActionButtons(root, load);
  await load();
  return () => clearTimeout(timer);
}
