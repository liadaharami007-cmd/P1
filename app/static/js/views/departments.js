// @ts-check
// 6 המחלקות של P1 תחת P1 CEO — כל יכולת עם סטטוס אמיתי: עובד ונבדק / חלקי / לא זמין.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

const ICON = { web: "🌐", marketing: "📣", sales: "🤝", finance: "📊", research: "🔭", ops: "⚙️" };
const ST = { works: "cap-works", partial: "cap-partial", unavailable: "cap-unavailable" };

/** @param {HTMLElement} view */
export async function departmentsView(view) {
  setTitle(t("dep.title"));
  const { departments } = await api("/api/departments");
  const all = departments.flatMap((/** @type {any} */ d) => d.capabilities);
  const n = (/** @type {string} */ s) => all.filter((/** @type {any} */ c) => c.status === s).length;
  view.innerHTML = `<div class="stack">
    <p class="muted" style="max-width:720px">${t("dep.sub")}</p>
    <div class="row cap-legend"><span class="cap-dot cap-works"></span>${t("cap.works")} (${n("works")})
      <span class="cap-dot cap-partial"></span>${t("cap.partial")} (${n("partial")}) <span class="cap-dot cap-unavailable"></span>${t("cap.unavailable")} (${n("unavailable")})</div>
    <div class="dep-grid">${departments.map((/** @type {any} */ d) => `<section class="card dep">
      <div class="dep-head"><span class="dep-ico">${/** @type {any} */ (ICON)[d.id]}</span><h2>${esc(d.name)}</h2></div>
      <ul class="cap-list">${d.capabilities.map((/** @type {any} */ c) => `<li class="${/** @type {any} */ (ST)[c.status]}">
        <span class="cap-dot ${/** @type {any} */ (ST)[c.status]}" title="${t("cap." + c.status)}"></span>
        <span style="flex:1;min-width:0">${c.link && c.status !== "unavailable" ? `<a href="${c.link}">${esc(c.name)}</a>` : esc(c.name)}
          ${c.note ? `<span class="tiny faint" style="display:block">${esc(c.note)}</span>` : ""}</span>
        <span class="tiny cap-label">${t("cap." + c.status)}</span></li>`).join("")}</ul></section>`).join("")}</div></div>`;
}
