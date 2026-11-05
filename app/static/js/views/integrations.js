import { setTitle } from "../app.js";
import { api, esc } from "../ui.js";

const ICONS = { claude: "✳️", shopify: "🛍️", woocommerce: "🧩", ga4: "📈", pagespeed: "⚡", support: "💬" };
const STATUS = {
  connected: ["st-passed", "✓ מחובר"],
  not_connected: ["st-warning", "לא מחובר — חסר מפתח"],
  planned: ["st-skipped", "בתכנון — טרם נבנה"],
};

export async function integrationsView(view) {
  setTitle("חיבורים");
  const list = await api("/api/integrations");
  view.innerHTML = `<p class="muted" style="margin-top:0">כאן רואים בדיוק מה מחובר ומה לא. שום חיבור לא מוצג כפעיל אם הוא לא באמת פעיל.</p>
    <div class="grid grid-2">${list.map((i) => `<div class="card integration">
      <div class="integration-icon">${ICONS[i.id] || "🔌"}</div>
      <div style="flex:1;min-width:0"><div class="row"><h3 style="font-size:16px">${esc(i.name)}</h3><span class="badge ${STATUS[i.status][0]}">${STATUS[i.status][1]}</span></div>
        <dl><dt>מה זה יאפשר</dt><dd>${esc(i.powers)}</dd><dt>מה צריך</dt><dd>${esc(i.requires)}</dd></dl></div></div>`).join("")}</div>`;
}
