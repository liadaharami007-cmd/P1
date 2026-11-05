// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, auditForm, bindAuditForm } from "../ui.js";
import { auditRow } from "./dashboard.js";

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function auditsView(view, _p, app) {
  setTitle(t("audits.title"));
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="card-head"><div><h2>${t("audits.new")}</h2><div class="card-sub">${t("audits.newSub")}</div></div></div>
      ${auditForm(app.status.capabilities.browser_audit)}</div>
    <div class="card"><div class="card-head"><h2>${t("audits.history")}</h2><span class="muted small" id="audit-count"></span></div>
      <div id="audit-list"><div class="skeleton" style="height:120px"></div></div></div></div>`;
  bindAuditForm(view);
  /** @type {any} */ let timer = null; let alive = true;
  const refresh = async () => {
    const audits = await api("/api/audits");
    if (!alive) return;
    /** @type {HTMLElement} */ (view.querySelector("#audit-count")).textContent = t("audits.count", { n: audits.length });
    /** @type {HTMLElement} */ (view.querySelector("#audit-list")).innerHTML = audits.length
      ? `<div class="list">${audits.map(auditRow).join("")}</div>` : `<div class="empty">${t("audits.none")}</div>`;
    if (audits.some((/** @type {any} */ a) => a.status === "running" || a.status === "queued" || a.ai_status === "running")) timer = setTimeout(refresh, 3000);
  };
  await refresh();
  return () => { alive = false; clearTimeout(timer); };
}
