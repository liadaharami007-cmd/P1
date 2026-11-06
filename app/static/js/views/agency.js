// @ts-check
// Agency Mode: כל הלקוחות של הסוכנות במסך אחד — מי דורש טיפול, דוחות מוכנים, אישורים, זמן שנחסך.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, fmtDate, hostOf, icon, openModal, toast, $ } from "../ui.js";

/** @param {number|null} s */
const scoreCls = (s) => s == null ? "" : s >= 80 ? "good" : s >= 60 ? "mid" : "bad";

/** @param {any} c */
function row(c) {
  const L = c.latest;
  return `<article class="client-row ${c.needs_attention ? "attn" : ""}">
    <div class="client-score ${scoreCls(L ? L.score : null)}">${L && L.score != null ? L.score : "—"}</div>
    <div class="client-main">
      <div class="row" style="gap:8px"><strong>${esc(c.name)}</strong>${c.is_demo ? `<span class="badge demo-badge">${t("ag.demo")}</span>` : ""}
        ${c.industry ? `<span class="tiny faint">${esc(c.industry)}</span>` : ""}</div>
      <div class="tiny faint ltr" style="text-align:start">${esc(hostOf(c.url))}${c.is_demo ? esc(new URL(c.url).pathname) : ""}</div>
      ${c.reasons.length ? `<div class="client-reasons">${c.reasons.map((/** @type {string} */ r) => `<span class="chip warn">${esc(r)}</span>`).join("")}</div>` : `<div class="client-reasons"><span class="chip ok">✓ ${t("ag.ok")}</span></div>`}
      ${c.top_issues.length ? `<div class="tiny muted" style="margin-top:4px">${c.top_issues.map(esc).join(" · ")}</div>` : ""}
    </div>
    <div class="client-stats">
      <div><span class="num">${c.open_issues}</span><small>${t("ag.open")}</small></div>
      <div><span class="num">${c.score_delta == null ? "—" : (c.score_delta > 0 ? "+" : "") + c.score_delta}</span><small>${t("ag.delta")}</small></div>
      <div><span class="num">${L ? fmtDate(L.finished_at).split(",")[0] : "—"}</span><small>${t("ag.last")}</small></div>
    </div>
    <div class="client-actions">
      ${c.running ? `<span class="chip"><span class="live-dot"></span> ${t("ag.running")}</span>`
        : `<button class="btn btn-sm" data-audit="${c.id}">${icon("refresh")}${t("ag.audit")}</button>`}
      ${L ? `<a class="btn btn-sm btn-ghost" href="#/audits/${L.id}">${t("ag.report")}</a><a class="btn btn-sm btn-ghost" href="/api/audits/${L.id}/report.pdf">PDF</a>` : ""}
    </div>
  </article>`;
}

/** @param {HTMLElement} view */
export async function agencyView(view) {
  view.innerHTML = `<div></div>`;
  const root = /** @type {HTMLElement} */ (view.firstElementChild);
  let timer = 0;
  const load = async () => {
    const d = await api("/api/agency");
    const T = d.totals;
    setTitle(t("ag.title"), `<button class="btn btn-sm btn-primary" id="add-client">${icon("plus")}<span class="btn-label">${t("ag.add")}</span></button>`);
    const hrs = (/** @type {number} */ m) => Math.round(m / 6) / 10;
    root.innerHTML = `<div class="stack">
      ${T.demo_clients ? `<div class="notice notice-sim"><span class="ico">i</span><span>${t("ag.demoNote")}</span>
        <button class="btn btn-sm btn-ghost" id="rm-demo" style="margin-inline-start:auto">${t("ag.removeDemo")}</button></div>` : ""}
      <div class="kpis ag-kpis">
        <div class="kpi"><div class="kpi-num">${T.clients}</div><div class="kpi-label">${t("ag.clients")}</div></div>
        <div class="kpi attn"><div class="kpi-num">${T.need_attention}</div><div class="kpi-label">${t("ag.attention")}</div></div>
        <div class="kpi"><div class="kpi-num">${T.reports_ready}</div><div class="kpi-label">${t("ag.reports")}</div></div>
        <div class="kpi"><div class="kpi-num">${T.pending_actions}</div><div class="kpi-label">${t("ag.pending")}</div></div>
        <div class="kpi"><div class="kpi-num">${T.audits_done}</div><div class="kpi-label">${t("ag.audits")}</div></div>
        <div class="kpi"><div class="kpi-num">${t("cmd.hours", { n: hrs(T.manual_minutes_estimate) })}</div><div class="kpi-label">${t("ag.saved")}</div></div>
      </div>
      <p class="tiny faint">${esc(T.estimate_note)} ${t("ag.machine", { n: T.machine_minutes })}</p>
      ${d.clients.length ? `<div class="client-list">${d.clients.map(row).join("")}</div>`
        : `<div class="card empty"><h3>${t("ag.emptyTitle")}</h3><p class="muted">${t("ag.emptyText")}</p>
            <div class="row" style="justify-content:center;margin-top:12px"><button class="btn btn-primary" id="seed">${t("ag.seed")}</button>
            <button class="btn" id="add-client-2">${t("ag.add")}</button></div></div>`}
    </div>`;
    clearTimeout(timer);
    if (T.running) timer = window.setTimeout(load, 6000);
  };
  const addForm = () => {
    openModal(`<h3>${t("ag.add")}</h3><form id="client-form" class="stack" novalidate>
      <div class="field"><label for="c-name">${t("ag.name")}</label><input class="input" id="c-name" name="name" required></div>
      <div class="field"><label for="c-url">${t("ag.url")}</label><input class="input ltr" id="c-url" name="url" type="url" placeholder="https://" required></div>
      <div class="field"><label for="c-ind">${t("ag.industry")}</label><input class="input" id="c-ind" name="industry"></div>
      <label class="row small"><input type="checkbox" name="confirm_permission" value="1"> ${t("ag.permission")}</label>
      <button class="btn btn-primary" type="submit">${t("ag.save")}</button></form>`);
    const f = /** @type {HTMLFormElement} */ ($("#client-form"));
    f.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      try {
        await api("/api/agency/clients", { method: "POST", body: JSON.stringify({ name: fd.get("name"), url: fd.get("url"), industry: fd.get("industry"), confirm_permission: !!fd.get("confirm_permission") }) });
        $("#modal").close(); toast(t("ag.added")); load();
      } catch (err) { toast(/** @type {Error} */ (err).message, "error"); }
    };
  };
  const onClick = async (/** @type {Event} */ e) => {
    const el = /** @type {HTMLElement} */ (e.target);
    const b = /** @type {HTMLButtonElement|null} */ (el.closest("button"));
    if (!b) return;
    try {
      if (b.id === "add-client" || b.id === "add-client-2") return addForm();
      if (b.id === "seed") { b.disabled = true; await api("/api/agency/demo", { method: "POST" }); toast(t("ag.seeded")); return load(); }
      if (b.id === "rm-demo") { await api("/api/agency/demo", { method: "DELETE" }); return load(); }
      if (b.dataset.audit) { b.disabled = true; await api(`/api/agency/clients/${b.dataset.audit}/audit`, { method: "POST" }); toast(t("ag.queued")); window.dispatchEvent(new CustomEvent("p1:usage")); return load(); }
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); b.disabled = false; }
  };
  root.addEventListener("click", onClick);
  document.getElementById("topbar-actions")?.addEventListener("click", onClick);
  await load();
  return () => { clearTimeout(timer); document.getElementById("topbar-actions")?.removeEventListener("click", onClick); };
}
