// @ts-check
// סטודיו הסוכנים: שיווק (אסטרטגיה, מודעות, לוח תוכן, תסריט וידאו), שירות לקוחות (מבוסס מידע העסק), ייעוץ עם P1 CEO.
// מנוע מודל אמיתי בלבד; בלי מנוע — מוצג "לא מחובר" ולא תשובה מוכנה.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";

const TABS = [
  ["marketing", [["marketing_strategy", "st.k.strategy", false], ["ad_copy", "st.k.ads", true], ["content_calendar", "st.k.calendar", false], ["video_script", "st.k.video", true]]],
  ["support", [["support_answer", "st.k.support", true]]],
  ["consult", [["consult", "st.k.consult", true]]],
];

/** הצגת פלט מובנה בצורה קריאה (כל שדה = כותרת + ערך). @param {any} o */
function render(o) {
  const val = (/** @type {any} */ v) => Array.isArray(v) ? (v.length ? `<ul class="out-list">${v.map((x) => `<li>${typeof x === "object" ? Object.entries(x).map(([k, y]) => `<span class="tiny faint">${esc(k)}:</span> ${esc(y)}`).join("<br>") : esc(x)}</li>`).join("")}</ul>` : "—")
    : typeof v === "boolean" ? (v ? "✓" : "✕") : `<p style="white-space:pre-line">${esc(v)}</p>`;
  return Object.entries(o).map(([k, v]) => `<div class="out-field ${k === "missing_info" ? "out-missing" : ""}"><div class="out-key">${t("st.f." + k) !== "st.f." + k ? t("st.f." + k) : esc(k)}</div>${val(v)}</div>`).join("");
}

/** @param {HTMLElement} view */
export async function studioView(view) {
  const tab = new URLSearchParams(location.hash.split("?")[1] || "").get("tab") || "marketing";
  setTitle(t("st.title"));
  const h = await api("/api/studio/history");
  const kinds = /** @type {any[]} */ ((TABS.find((x) => x[0] === tab) || TABS[0])[1]);
  view.innerHTML = `<div class="stack">
    <div class="seg" role="tablist">${TABS.map(([id]) => `<a class="seg-a ${id === tab ? "on" : ""}" href="#/studio?tab=${id}">${t("st.tab." + id)}</a>`).join("")}</div>
    ${h.ai ? "" : `<div class="notice notice-warn"><span class="ico">!</span><span>${t("st.noAi")} <a href="#/integrations">${t("nav.integrations")}</a></span></div>`}
    <p class="muted small">${t("st.sub." + tab)}</p>
    <form class="card stack" id="st-form" novalidate>
      <div class="chips-select">${kinds.map(([k, label], i) => `<label class="chip-check"><input type="radio" name="kind" value="${k}" ${i === 0 ? "checked" : ""}><span>${t(label)}</span></label>`).join("")}</div>
      <textarea class="input" name="input" rows="3" placeholder="${t("st.ph." + tab)}"></textarea>
      <div class="row" style="justify-content:space-between"><span class="tiny faint">${t("st.grounded")}</span>
        <button class="btn btn-primary" type="submit" ${h.ai ? "" : "disabled"}>${icon("sparkle")}${t("st.run")}</button></div>
    </form>
    <div id="st-out"></div>
    ${h.items.length ? `<section><h2 class="section-title">${t("st.history")}</h2><div class="stack">${h.items.filter((/** @type {any} */ x) => kinds.some((/** @type {any} */ k) => k[0] === x.kind)).slice(0, 8).map((/** @type {any} */ x) =>
      `<details class="card out-card"><summary><strong class="small">${t(kinds.find((/** @type {any} */ k) => k[0] === x.kind)?.[1] || "")}</strong> · <span class="small muted">${esc((x.input || "").slice(0, 80))}</span>
        <span class="tiny faint" style="float:inline-end">${esc(x.model)} · ${new Date(x.created_at).toLocaleString()}</span></summary>${render(x.output)}</details>`).join("")}</div></section>` : ""}
  </div>`;
  const f = /** @type {HTMLFormElement} */ (view.querySelector("#st-form"));
  f.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(f), btn = /** @type {HTMLButtonElement} */ (f.querySelector("button[type=submit]"));
    const out = /** @type {HTMLElement} */ (view.querySelector("#st-out"));
    btn.disabled = true;
    out.innerHTML = `<div class="card row muted"><span class="spinner"></span>${t("st.working")}</div>`;
    try {
      const r = await api("/api/studio/run", { method: "POST", body: JSON.stringify({ kind: fd.get("kind"), input: fd.get("input") || "" }) });
      out.innerHTML = `<article class="card out-card"><div class="row" style="justify-content:space-between"><span class="badge src-ai">${t("src.ai")} · ${esc(r.model)}</span>
        <span class="tiny faint">${t("st.basedOn")} ${r.grounded_on.profile_fields.length} ${t("st.fields")} · ${r.grounded_on.site_pages.length} ${t("st.pages")}</span></div>${render(r.output)}
        <p class="tiny faint" style="margin-top:8px">${t("st.draft")}</p></article>`;
    } catch (err) { out.innerHTML = ""; toast(/** @type {Error} */ (err).message, "error"); }
    btn.disabled = false;
  };
}
