// @ts-check
// פרופיל העסק (Business Brain / Onboarding): 4 קבוצות קצרות, רק מה שבעל העסק כותב.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, toast } from "../ui.js";

const GROUPS = [
  ["biz.step1", ["business_name", "business_type", "industry", "website"]],
  ["biz.step2", ["offer", "audience", "usps", "competitors", "price_range"]],
  ["biz.step3", ["goals", "channels"]],
  ["biz.step4", ["monthly_ad_budget", "avg_order_value", "monthly_leads_or_orders", "hours_on_site_per_month", "hourly_value", "notes"]],
];
const TEXTAREA = new Set(["offer", "audience", "usps", "competitors", "notes"]);
const NUM = new Set(["monthly_ad_budget", "avg_order_value", "monthly_leads_or_orders", "hours_on_site_per_month", "hourly_value"]);
const REQUIRED = new Set(["business_name", "business_type", "industry", "website", "offer", "audience", "goals"]);

/** @param {HTMLElement} view */
export async function businessView(view) {
  setTitle(t("nav.business"));
  const p = await api("/api/business/profile");
  const d = p.data;
  /** @param {string} k */
  const field = (k) => {
    const label = `${t("biz.f." + k)}${REQUIRED.has(k) ? ` <span class="req">*</span>` : ""}`;
    if (k === "business_type") return `<div class="field"><label for="f-${k}">${label}</label><select class="input" id="f-${k}" name="${k}">
      <option value=""></option>${p.options.business_type.map((/** @type {string} */ o) => `<option value="${o}" ${d[k] === o ? "selected" : ""}>${t("bt." + o)}</option>`).join("")}</select></div>`;
    if (k === "goals" || k === "channels") return `<fieldset class="field"><legend>${label}</legend><div class="chips-select">
      ${p.options[k].map((/** @type {string} */ o) => `<label class="chip-check"><input type="checkbox" name="${k}" value="${o}" ${(d[k] || []).includes(o) ? "checked" : ""}>
      <span>${t((k === "goals" ? "goal." : "ch.") + o)}</span></label>`).join("")}</div></fieldset>`;
    if (TEXTAREA.has(k)) return `<div class="field"><label for="f-${k}">${label}</label><textarea class="input" rows="3" id="f-${k}" name="${k}">${esc(d[k] || "")}</textarea></div>`;
    return `<div class="field"><label for="f-${k}">${label}</label><input class="input ${k === "website" ? "ltr" : ""}" id="f-${k}" name="${k}"
      ${NUM.has(k) ? 'inputmode="decimal" type="number" min="0" step="any"' : k === "website" ? 'type="url" placeholder="https://"' : ""} value="${esc(d[k] ?? "")}"></div>`;
  };
  view.innerHTML = `<form class="stack" id="biz-form" novalidate>
    <div class="card"><div class="row" style="justify-content:space-between"><p class="muted" style="max-width:620px">${t("biz.sub")}</p>
      <div style="min-width:200px"><div class="row small" style="justify-content:space-between"><span>${t("biz.complete")}</span><strong class="num" id="pct">${p.completeness.percent}%</strong></div>
      <div class="meter" style="margin-top:6px"><div id="pct-bar" style="width:${p.completeness.percent}%"></div></div></div></div></div>
    ${GROUPS.map(([title, keys], i) => `<section class="card"><div class="card-head"><h2><span class="step-num">${i + 1}</span>${t(/** @type {string} */ (title))}</h2></div>
      <div class="form-grid">${/** @type {string[]} */ (keys).map(field).join("")}</div></section>`).join("")}
    <div class="sticky-save"><button class="btn btn-primary btn-lg" type="submit">${t("biz.save")}</button></div></form>`;
  const form = /** @type {HTMLFormElement} */ (view.querySelector("#biz-form"));
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    /** @type {Record<string, any>} */
    const data = {};
    for (const [, keys] of GROUPS) for (const k of /** @type {string[]} */ (keys)) {
      if (k === "goals" || k === "channels") data[k] = fd.getAll(k);
      else { const v = String(fd.get(k) ?? "").trim(); if (v) data[k] = v; }
    }
    const btn = /** @type {HTMLButtonElement} */ (form.querySelector("button[type=submit]"));
    btn.disabled = true;
    try {
      const r = await api("/api/business/profile", { method: "PUT", body: JSON.stringify({ data }) });
      /** @type {HTMLElement} */ (view.querySelector("#pct")).textContent = r.completeness.percent + "%";
      /** @type {HTMLElement} */ (view.querySelector("#pct-bar")).style.width = r.completeness.percent + "%";
      toast(t("biz.saved"));
      if (r.completeness.ready) location.hash = "#/";
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); }
    btn.disabled = false;
  };
}
