// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, hostOf, toast } from "../ui.js";
import { findingCard } from "./audit.js";

const ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

/** @param {HTMLElement} view */
export async function tasksView(view) {
  setTitle(t("tasks.title"));
  const all = (await api("/api/tasks")).filter((/** @type {any} */ f) => f.source === "measured" || f.source === "ai");
  if (!all.length) {
    view.innerHTML = `<div class="card empty"><h3>${t("tasks.none")}</h3><p>${t("tasks.noneSub")}</p><a class="btn btn-primary" style="margin-top:12px" href="#/audits">${t("common.newAudit")}</a></div>`;
    return;
  }
  const multi = new Set(all.map((/** @type {any} */ f) => f.site_id)).size > 1;
  const groups = ["open", "in_progress", "done", "dismissed"];
  let active = "open";
  const draw = () => {
    const list = all.filter((/** @type {any} */ f) => f.status === active)
      .sort((/** @type {any} */ a, /** @type {any} */ b) => (a.source === b.source ? 0 : a.source === "measured" ? -1 : 1) || /** @type {any} */ (ORDER)[a.severity] - /** @type {any} */ (ORDER)[b.severity]);
    view.innerHTML = `<p class="muted" style="margin-bottom:14px">${t("tasks.sub")}</p>
      <div class="tabs">${groups.map((g) => `<button data-g="${g}" class="${g === active ? "active" : ""}">${t("fstatus." + g)}<span class="count">${all.filter((/** @type {any} */ f) => f.status === g).length}</span></button>`).join("")}</div>
      ${list.length ? list.map((/** @type {any} */ f) => findingCard(f, multi ? `<span class="badge outline ltr">${hostOf(f.site_url)}</span>` : "")).join("") : `<div class="card empty">${t("tasks.empty")}</div>`}`;
    view.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => { active = /** @type {HTMLElement} */ (b).dataset.g || "open"; draw(); }));
    view.querySelectorAll("[data-status-for]").forEach((el) => el.addEventListener("change", async () => {
      const sel = /** @type {HTMLSelectElement} */ (el);
      try {
        await api(`/api/findings/${sel.dataset.statusFor}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) });
        all.find((/** @type {any} */ f) => f.id === sel.dataset.statusFor).status = sel.value;
        toast(t("tasks.moved", { s: t("fstatus." + sel.value) })); draw();
      } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
    }));
  };
  draw();
}
