// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

const ICONS = { claude: "✳️", shopify: "🛍️", woocommerce: "🧩", ga4: "📈", pagespeed: "⚡", billing: "💳" };
const ENGINE_ICON = { anthropic: "✳️", ollama: "🦙", rules: "⚙️" };
const STATUS = {
  connected: ["st-passed", "int.connected"],
  not_connected: ["st-warning", "int.not_connected"],
  planned: ["st-skipped", "int.planned"],
};

/** @param {HTMLElement} view */
export async function integrationsView(view) {
  setTitle(t("int.title"));
  const [list, eng] = await Promise.all([api("/api/integrations"), api("/api/engines")]);
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="card-head"><div><h2>${t("eng.title")}</h2><div class="card-sub">${t("eng.sub")}</div></div></div>
      <div class="grid g3">${eng.engines.map((/** @type {any} */ e) => `<div class="engine ${e.id === eng.active ? "active" : ""}">
        <div class="row" style="justify-content:space-between"><span class="row"><span style="font-size:20px">${/** @type {any} */ (ENGINE_ICON)[e.id]}</span><strong>${esc(e.name)}</strong></span>
          ${e.id === eng.active ? `<span class="badge st-running"><span class="live-dot" style="background:var(--brand)"></span> ${t("eng.active")}</span>` : ""}</div>
        <div class="row" style="margin-top:10px"><span class="badge ${e.available ? "st-passed" : "st-skipped"}">${e.available ? t("eng.available") : t("eng.unavailable")}</span>
          <span class="badge outline">${e.cost === "free" ? t("eng.free") : t("eng.paid")}</span></div>
        <p class="small muted" style="margin-top:8px">${esc(e.detail)}</p></div>`).join("")}</div></div>
    <p class="muted">${t("int.sub")}</p>
    <div class="grid g2">${list.map((/** @type {any} */ i) => { const st = /** @type {any} */ (STATUS)[i.status]; return `<div class="card integration">
      <div class="integration-icon">${/** @type {any} */ (ICONS)[i.id] || "🔌"}</div>
      <div style="flex:1;min-width:0"><div class="row"><h3 style="font-size:14.5px">${esc(i.name)}</h3><span class="badge ${st[0]}">${t(st[1])}</span></div>
        <dl class="kv"><dt>${t("int.powers")}</dt><dd>${esc(i.powers)}</dd><dt>${t("int.requires")}</dt><dd>${esc(i.requires)}</dd></dl></div></div>`; }).join("")}</div></div>`;
}
