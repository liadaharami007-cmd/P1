// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, fmtDate, toast } from "../ui.js";

/** @param {HTMLElement} view */
export async function adminView(view) {
  setTitle(t("admin.title"));
  const d = await api("/api/admin/overview");
  const k = d.totals;
  view.innerHTML = `<div class="stack">
    <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
      <div class="kpi"><div class="kpi-num">${k.accounts}</div><div class="kpi-label">${t("admin.accounts")}</div></div>
      <div class="kpi"><div class="kpi-num">${k.users}</div><div class="kpi-label">${t("admin.users")}</div></div>
      <div class="kpi"><div class="kpi-num">${k.audits_month}</div><div class="kpi-label">${t("admin.auditsMonth")}</div></div>
      <div class="kpi"><div class="kpi-num">${k.failed_audits_month}</div><div class="kpi-label">${t("admin.failed")}</div></div>
      <div class="kpi"><div class="kpi-num">$${k.ai_cost_month.toFixed(3)}</div><div class="kpi-label">${t("admin.aiCost")}</div></div>
      <div class="kpi"><div class="kpi-num">${k.queued}</div><div class="kpi-label">${t("admin.queue")}</div></div></div>
    <div class="card"><div class="card-head"><h2>${t("admin.accounts")}</h2></div><div class="table-wrap"><table class="data">
      <tr><th>${t("admin.accounts")}</th><th>${t("admin.owner")}</th><th>Plan</th><th>${t("acc.sites")}</th><th>${t("admin.auditsMonth")}</th><th>${t("admin.aiCost")}</th><th></th></tr>
      ${d.accounts.map((/** @type {any} */ a) => `<tr><td><strong>${esc(a.name)}</strong><div class="tiny muted">${fmtDate(a.created_at)}</div></td>
        <td class="ltr small">${esc(a.owner_email || "")}</td>
        <td><select class="input" data-plan-for="${a.id}">${Object.entries(d.plans).map(([pk, pv]) => `<option value="${pk}" ${pk === a.plan ? "selected" : ""}>${esc(/** @type {any} */ (pv).name)}</option>`).join("")}</select></td>
        <td class="num">${a.sites}</td><td class="num">${a.audits_month}</td><td class="num">$${a.ai_cost_month.toFixed(3)}</td><td class="tiny muted">${a.members} 👤</td></tr>`).join("")}
    </table></div></div></div>`;
  view.querySelectorAll("[data-plan-for]").forEach((el) => el.addEventListener("change", async () => {
    const sel = /** @type {HTMLSelectElement} */ (el);
    try { await api(`/api/admin/accounts/${sel.dataset.planFor}`, { method: "PATCH", body: JSON.stringify({ plan: sel.value }) }); toast(t("admin.planChanged")); }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  }));
}
