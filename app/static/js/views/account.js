// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, toast } from "../ui.js";

/** @param {number} used @param {number} limit @param {string} label */
function meter(used, limit, label) {
  const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
  return `<div><div class="row small" style="justify-content:space-between"><span class="muted">${label}</span><span class="num"><strong>${used}</strong> / ${limit}</span></div>
    <div class="meter ${pct >= 100 ? "full" : pct >= 80 ? "warn" : ""}" style="margin-top:6px"><div style="width:${pct}%"></div></div></div>`;
}

/** @param {HTMLElement} view */
export async function accountView(view) {
  setTitle(t("acc.title"));
  const [d, b] = await Promise.all([api("/api/account"), api("/api/billing")]);
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
      ${b.configured ? `<div class="notice notice-info" style="margin-bottom:14px"><span class="ico">i</span><span>${t("bill.on", { p: b.provider })}${b.sandbox ? " · " + t("bill.sandbox") : ""}
          · ${t("bill.status")}: <strong>${esc(b.subscription_status)}</strong></span>${b.has_customer ? `<button class="btn btn-sm" id="portal" style="margin-inline-start:auto">${t("bill.portal")}</button>` : ""}</div>`
        : `<div class="notice notice-warn" style="margin-bottom:14px"><span class="ico">!</span><span>${t("bill.off")}<br><span class="tiny ltr">${b.missing.map(esc).join(" · ")}</span></span></div>`}
      <div class="grid g3">${Object.entries(d.plans).map(([k, pl]) => { const x = /** @type {any} */ (pl); return `<div class="plan-card ${k === d.account.plan ? "current" : ""}">
        <div class="row" style="justify-content:space-between"><h3 style="font-size:15px">${esc(x.name)}</h3>${k === d.account.plan ? `<span class="badge st-running">${t("acc.current")}</span>` : ""}</div>
        <ul><li>${x.sites} ${t("acc.sites")}</li><li>${x.audits_per_month} ${t("acc.audits")} ${t("acc.perMonth")}</li><li>${x.ai_analyses_per_month} ${t("acc.ai")} ${t("acc.perMonth")}</li>
        <li>${x.concurrent_audits} ${t("acc.concurrent")}</li><li>${x.members} ${t("acc.members")}</li></ul>
        ${k !== "free" && k !== d.account.plan ? `<div class="row" style="margin-top:10px"><button class="btn btn-sm btn-primary" data-checkout="${k}" data-interval="monthly" ${b.configured ? "" : "disabled"}>${t("bill.monthly")}</button>
          <button class="btn btn-sm" data-checkout="${k}" data-interval="yearly" ${b.configured ? "" : "disabled"}>${t("bill.yearly")}</button></div>` : ""}</div>`; }).join("")}</div></div>
  </div>`;
  view.querySelectorAll("[data-checkout]").forEach((el) => el.addEventListener("click", async () => {
    const btn = /** @type {HTMLButtonElement} */ (el);
    btn.disabled = true;
    try {
      const r = await api("/api/billing/checkout", { method: "POST", body: JSON.stringify({ plan: btn.dataset.checkout, interval: btn.dataset.interval }) });
      location.href = r.url;
    } catch (e) { toast(/** @type {Error} */ (e).message, "error"); btn.disabled = false; }
  }));
  const portal = /** @type {HTMLButtonElement|null} */ (view.querySelector("#portal"));
  if (portal) portal.onclick = async () => {
    try { location.href = (await api("/api/billing/portal", { method: "POST" })).url; } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
}
