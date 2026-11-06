// @ts-check
// Growth Timeline: מה זוהה, מה הוצע, מה בוצע ומה נמדד.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, fmtDate } from "../ui.js";

const DOT = { audit_done: "measured", audit_failed: "failed", action_done: "done", action_failed: "failed", action_proposed: "proposed",
  action_approved: "proposed", action_rejected: "muted", profile_created: "brand", profile_updated: "brand" };

/** @param {HTMLElement} view */
export async function timelineView(view) {
  setTitle(t("tl.title"));
  const { items } = await api("/api/business/timeline");
  view.innerHTML = `<div class="stack"><p class="muted">${t("tl.sub")}</p>
    ${items.length ? `<ol class="timeline">${items.map((/** @type {any} */ x) => `<li class="tl-item">
      <span class="tl-dot tl-${/** @type {any} */ (DOT)[x.kind] || "muted"}" aria-hidden="true"></span>
      <div class="tl-body"><div class="row" style="justify-content:space-between"><strong class="small">${esc(x.title)}</strong>
        <span class="tiny faint">${fmtDate(x.at)}</span></div>
        ${x.detail ? `<div class="small muted">${esc(x.detail)}</div>` : ""}
        ${x.ref_type === "audit" ? `<a class="tiny" href="#/audits/${x.ref_id}">${t("act.toAudit")}</a>` : x.ref_type === "action" ? `<a class="tiny" href="#/approvals">${t("nav.approvals")}</a>` : ""}</div>
    </li>`).join("")}</ol>` : `<div class="card empty">${t("tl.none")}</div>`}</div>`;
}
