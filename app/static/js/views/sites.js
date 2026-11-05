// @ts-check
// אתרים מורשים + Smart Monitor + דוח התקדמות
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { $, $$, api, esc, fmtDate, gradeLabel, hostOf, icon, lineChart, toast } from "../ui.js";

const NOTIF_ICON = { new_issues: "✕", fixed_issues: "✓", score_change: "↕", first_audit: "★" };

/** @param {HTMLElement} view */
export async function sitesView(view) {
  setTitle(t("sites.title"));
  const d = await api("/api/sites");
  const sel = new URLSearchParams(location.hash.split("?")[1] || "").get("site") || d.sites[0]?.id;
  const freqs = ["daily", "weekly", "monthly"];
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="card-head"><div><h2>${t("sites.add")}</h2><div class="card-sub">${t("sites.addSub")}</div></div></div>
      <form id="add-site" class="audit-form"><div class="row"><input class="input" name="url" placeholder="${t("form.urlPlaceholder")}" required aria-label="URL">
        <button class="btn btn-primary" type="submit">${icon("plus")} ${t("sites.addBtn")}</button></div>
        <label class="check" style="margin-top:10px"><input type="checkbox" name="confirm" required><span>${t("form.permission")}</span></label>
        <p class="form-error" hidden></p></form></div>
    ${d.sites.length ? `<div class="grid g-main"><div class="card"><div class="list">${d.sites.map((/** @type {any} */ s) => `
      <a class="list-item ${s.id === sel ? "selected" : ""}" href="#/sites?site=${s.id}"><div class="mini-score">${s.last_score ?? "—"}</div>
        <div class="list-main"><div class="list-title">${esc(s.name || hostOf(s.url))} ${s.is_demo ? `<span class="badge st-warning">${t("demo.badge")}</span>` : ""}</div>
          <div class="tiny muted ltr">${esc(s.url)}</div>
          <div class="tiny muted">${s.audits} ${t("sites.audits")} · ${t("sites.monitor")}: ${s.monitor_enabled ? t("sites.freq." + s.monitor_frequency) : t("sites.freq.off")}
          ${s.authorized_at ? ` · ✓ ${t("sites.authorized")}` : ""}</div></div>${s.last_score != null ? gradeLabel(s.last_score) : ""}</a>`).join("")}</div></div>
      <div id="site-panel" class="stack"><div class="skeleton" style="height:300px"></div></div></div>`
      : `<div class="card empty"><h3>${t("sites.none")}</h3></div>`}</div>`;

  /** @type {any} */ const form = $("#add-site", view);
  form.onsubmit = async (/** @type {Event} */ e) => {
    e.preventDefault();
    const err = $(".form-error", form); err.hidden = true;
    try {
      const s = await api("/api/sites", { method: "POST", body: JSON.stringify({ url: form.url.value, confirm_permission: form.confirm.checked }) });
      location.hash = `#/sites?site=${s.id}`;
    } catch (ex) { err.textContent = /** @type {Error} */ (ex).message; err.hidden = false; }
  };
  if (!sel) return;
  const p = await api(`/api/sites/${sel}/progress`);
  const m = p.monitor, allowed = d.plan.monitor;
  $("#site-panel", view).innerHTML = `
    <div class="card"><div class="card-head"><div><h3>${t("sites.monitor")}</h3><div class="card-sub">${t("sites.monitorNote")}</div></div></div>
      <div class="seg" id="mon-seg"><button data-f="off" class="${!m || !m.enabled ? "on" : ""}">${t("sites.freq.off")}</button>
        ${freqs.map((f) => `<button data-f="${f}" class="${m?.enabled && m.frequency === f ? "on" : ""}" ${allowed.includes(f) ? "" : "disabled title='Plan'"}>${t("sites.freq." + f)}</button>`).join("")}</div>
      ${m?.enabled ? `<p class="small muted" style="margin-top:10px">${t("sites.next")}: <strong>${fmtDate(m.next_run_at)}</strong></p>` : ""}
      <div class="row" style="margin-top:12px"><button class="btn btn-sm" id="run-now">${icon("play")} ${t("sites.runNow")}</button></div></div>
    <div class="card"><div class="card-head"><div><h3>${t("sites.progress")}</h3><div class="card-sub">${t("sites.firstLast")}</div></div></div>
      <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
        <div class="kpi"><div class="kpi-num">${p.summary.first_score ?? "—"} → ${p.summary.last_score ?? "—"}</div><div class="kpi-label">${t("dash.overall")}</div></div>
        <div class="kpi"><div class="kpi-num" style="color:var(--good-text)">${p.summary.fixed}</div><div class="kpi-label">${t("cmp.fixed")}</div></div>
        <div class="kpi"><div class="kpi-num" style="color:var(--critical-text)">${p.summary.new}</div><div class="kpi-label">${t("cmp.new")}</div></div></div>
      <div id="site-trend" style="margin-top:14px">${p.history.length >= 2 ? "" : `<p class="small muted">${t("dash.trendNeed")}</p>`}</div></div>
    <div class="card"><div class="card-head"><h3>${t("sites.changes")}</h3></div>
      <div class="list">${p.changes.length ? p.changes.map((/** @type {any} */ n) => `<a class="list-item" href="${n.audit_id ? `#/audits/${n.audit_id}` : "#/sites"}">
        <span class="notif-ico k-${n.kind}">${/** @type {any} */ (NOTIF_ICON)[n.kind] || "•"}</span>
        <div class="list-main"><div class="list-title">${esc(n.title)}</div><div class="tiny muted">${esc(n.body)} · ${fmtDate(n.created_at)}</div></div></a>`).join("")
        : `<p class="small muted">—</p>`}</div></div>`;
  if (p.history.length >= 2) lineChart(/** @type {HTMLElement} */ ($("#site-trend", view)), p.history, t("dash.overall"));
  $$("#mon-seg button", view).forEach((b) => b.addEventListener("click", async () => {
    const f = b.dataset.f;
    try {
      await api(`/api/sites/${sel}/monitor`, { method: "PUT", body: JSON.stringify({ frequency: f === "off" ? (m?.frequency || allowed[allowed.length - 1]) : f, enabled: f !== "off" }) });
      toast(t("sites.saved")); sitesView(view);
    } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  }));
  $("#run-now", view).onclick = async () => {
    try { const a = await api("/api/audits", { method: "POST", body: JSON.stringify({ url: p.site.url, confirm_permission: true }) }); location.hash = `#/audits/${a.id}`; }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
}
