// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

/** @param {number} used @param {number} limit @param {string} label */
function meter(used, limit, label) {
  const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
  return `<div><div class="row small" style="justify-content:space-between"><span class="muted">${label}</span><span class="num"><strong>${used}</strong> / ${limit}</span></div>
    <div class="meter ${pct >= 100 ? "full" : pct >= 80 ? "warn" : ""}" style="margin-top:6px"><div style="width:${pct}%"></div></div></div>`;
}

/** @param {HTMLElement} view */
export async function accountView(view) {
  setTitle(t("acc.title"));
  const d = await api("/api/account");
  const u = d.usage, p = d.plan;
  view.innerHTML = `<div class="stack">
    <div class="grid g-main">
      <div class="card"><div class="card-head"><div><h2>${t("acc.usage")}</h2><div class="card-sub">${esc(d.account.name)} · ${esc(p.name)}</div></div></div>
        <div class="stack">${meter(u.audits, p.audits_per_month, t("acc.audits"))}${meter(u.sites, p.sites, t("acc.sites"))}${meter(u.ai_analyses, p.ai_analyses_per_month, t("acc.ai"))}</div></div>
      <div class="card"><h2 style="font-size:14.5px;margin-bottom:12px">${t("acc.cost")}</h2>
        <div class="kpi-num">$${u.ai_cost_usd.toFixed(3)}</div>
        <p class="small muted" style="margin-top:6px">${t("acc.tokens")}: ${u.ai_input_tokens.toLocaleString()} in · ${u.ai_output_tokens.toLocaleString()} out</p></div>
    </div>
    <div class="card"><div class="card-head"><h2>${t("acc.plans")}</h2></div>
      <div class="notice" style="margin-bottom:14px"><span class="ico">i</span><span>${t("acc.billingOff")}</span></div>
      <div class="grid g3">${Object.entries(d.plans).map(([k, pl]) => { const x = /** @type {any} */ (pl); return `<div class="plan-card ${k === d.account.plan ? "current" : ""}">
        <div class="row" style="justify-content:space-between"><h3 style="font-size:15px">${esc(x.name)}</h3>${k === d.account.plan ? `<span class="badge st-running">${t("acc.current")}</span>` : ""}</div>
        <ul><li>${x.sites} ${t("acc.sites")}</li><li>${x.audits_per_month} ${t("acc.audits")} ${t("acc.perMonth")}</li><li>${x.ai_analyses_per_month} ${t("acc.ai")} ${t("acc.perMonth")}</li>
        <li>${x.concurrent_audits} ${t("acc.concurrent")}</li><li>${x.members} ${t("acc.members")}</li></ul></div>`; }).join("")}</div></div>
  </div>`;
}
