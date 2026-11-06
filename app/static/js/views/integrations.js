// @ts-check
// מרכז חיבורים: מה מחובר, מה בנוי וחסרים לו מפתחות, ומה עוד לא נבנה — ומה כל חיבור פותח.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

const ENGINE_ICON = { anthropic: "✳️", ollama: "🦙", rules: "⚙️" };
const ST = { connected: ["st-passed", "int.st.connected"], not_configured: ["st-warning", "int.st.not_configured"], not_built: ["st-skipped", "int.st.not_built"] };

/** @param {HTMLElement} view */
export async function integrationsView(view) {
  setTitle(t("int.title"));
  const [list, eng] = await Promise.all([api("/api/integrations"), api("/api/engines")]);
  const card = (/** @type {any} */ i) => { const st = /** @type {any} */ (ST)[i.status]; return `<div class="card integration int-${i.status}">
    <div style="flex:1;min-width:0"><div class="row" style="justify-content:space-between"><h3 style="font-size:14.5px">${esc(i.name)}</h3><span class="badge ${st[0]}">${t(st[1])}</span></div>
      <p class="small" style="margin-top:6px">${esc(i.unlocks)}</p>
      ${i.status === "not_configured" && i.missing.length ? `<p class="tiny" style="margin-top:6px"><strong>${t("int.missing")}</strong> <span class="ltr">${i.missing.map(esc).join(" · ")}</span></p>` : ""}
      <p class="tiny muted" style="margin-top:6px">${t("int.how")} ${esc(i.how)}${i.cost && i.cost !== "—" ? ` · ${esc(i.cost)}` : ""}</p></div></div>`; };
  const group = (/** @type {string} */ st) => list.filter((/** @type {any} */ i) => i.status === st);
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="card-head"><div><h2>${t("eng.title")}</h2><div class="card-sub">${t("eng.sub")}</div></div></div>
      <div class="grid g3">${eng.engines.map((/** @type {any} */ e) => `<div class="engine ${e.id === eng.active ? "active" : ""}">
        <div class="row" style="justify-content:space-between"><span class="row"><span style="font-size:20px">${/** @type {any} */ (ENGINE_ICON)[e.id]}</span><strong>${esc(e.name)}</strong></span>
          ${e.id === eng.active ? `<span class="badge st-running">${t("eng.active")}</span>` : ""}</div>
        <div class="row" style="margin-top:10px"><span class="badge ${e.available ? "st-passed" : "st-skipped"}">${e.available ? t("eng.available") : t("eng.unavailable")}</span>
          <span class="badge outline">${e.cost === "free" ? t("eng.free") : t("eng.paid")}</span></div>
        <p class="small muted" style="margin-top:8px">${esc(e.detail)}</p></div>`).join("")}</div></div>
    <p class="muted">${t("int.honest")}</p>
    ${["connected", "not_configured", "not_built"].map((s) => group(s).length ? `<section><h2 class="section-title">${t(/** @type {any} */ (ST)[s][1])} (${group(s).length})</h2>
      <div class="grid g2">${group(s).map(card).join("")}</div></section>` : "").join("")}</div>`;
}
