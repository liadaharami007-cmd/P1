// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

const ICONS = { claude: "✳️", shopify: "🛍️", woocommerce: "🧩", ga4: "📈", pagespeed: "⚡", billing: "💳" };

/** @param {HTMLElement} view */
export async function integrationsView(view) {
  setTitle(t("int.title"));
  const list = await api("/api/integrations");
  view.innerHTML = `<p class="muted" style="margin-bottom:14px">${t("int.sub")}</p>
    <div class="grid g2">${list.map((/** @type {any} */ i) => `<div class="card integration">
      <div class="integration-icon">${/** @type {any} */ (ICONS)[i.id] || "🔌"}</div>
      <div style="flex:1;min-width:0"><div class="row"><h3 style="font-size:14.5px">${esc(i.name)}</h3><span class="badge st-${i.status}">${t("int." + i.status)}</span></div>
        <dl class="kv"><dt>${t("int.powers")}</dt><dd>${esc(i.powers)}</dd><dt>${t("int.requires")}</dt><dd>${esc(i.requires)}</dd></dl></div></div>`).join("")}</div>`;
}
