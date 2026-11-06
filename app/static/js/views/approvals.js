// @ts-check
// מרכז אישורים: כל פעולה מוצגת עם "מה יקרה" + סיכון, ומתבצעת רק אחרי אישור אנושי.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { $, api, esc, fmtDate, icon, openModal, toast } from "../ui.js";

/** @param {string} s */
export const actStatus = (s) => `<span class="badge act-st act-${s}">${t("act.st." + s)}</span>`;

/** כרטיס פעולה מלא (משמש גם במודאל וגם ברשימה). @param {any} a */
export function actionCard(a) {
  const r = a.result || {};
  const verify = a.kind === "verify_fix" && a.status === "done" ? `<div class="grid g-2" style="margin-top:10px">
      <div class="kpi"><div class="kpi-label">✓ ${t("act.verified")}</div>${(r.verified_fixed || []).map((/** @type {any} */ x) => `<div class="small">${esc(x.title)}</div>`).join("") || "—"}</div>
      <div class="kpi"><div class="kpi-label">• ${t("act.still")}</div>${(r.still_present || []).map((/** @type {any} */ x) => `<div class="small">${esc(x.title)}</div>`).join("") || "—"}</div></div>` : "";
  return `<article class="card action-card" data-action="${a.id}">
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div style="min-width:0;flex:1"><h3 class="action-title">${esc(a.title)}</h3><p class="small muted" style="margin-top:4px">${esc(a.summary)}</p></div>
      ${actStatus(a.status)}</div>
    <div class="action-meta small"><span>${t("act.risk")}: <strong>${t("act.risk." + a.risk)}</strong></span>
      <span class="badge src-rules">${t("act.source." + (a.source === "ai" ? "ai" : "rules"))}</span>
      <span class="faint">${fmtDate(a.created_at)}</span></div>
    ${a.status === "proposed" ? `<div class="action-changes"><div class="small" style="font-weight:600;margin-bottom:6px">${t("act.changes")}</div>
      <ul>${a.changes.map((/** @type {string} */ c) => `<li>${esc(c)}</li>`).join("")}</ul></div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn btn-ghost btn-sm" data-reject="${a.id}">${t("act.reject")}</button>
      <button class="btn btn-primary btn-sm" data-approve="${a.id}">${icon("play")}${t("act.approve")}</button></div>` : ""}
    ${a.status === "failed" ? `<div class="notice notice-error" style="margin-top:10px"><span class="ico">!</span><span>${esc(a.error || "")}</span></div>` : ""}
    ${r.score != null ? `<div class="small" style="margin-top:8px">${t("act.scoreNow")}: <strong class="num">${r.score}</strong></div>` : ""}
    ${verify}
    <div class="row" style="margin-top:10px">
      ${a.kind === "fix_package" && a.status === "done" ? `<a class="btn btn-sm" href="/api/actions/${a.id}/package.html">${icon("download")}${t("act.download")}</a>
        <button class="btn btn-sm btn-ghost" data-applied="${a.payload.finding_id}">${icon("check")}${t("act.markApplied")}</button>` : ""}
      ${r.audit_id ? `<a class="btn btn-sm btn-ghost" href="#/audits/${r.audit_id}">${t("act.toAudit")}</a>` : ""}</div>
  </article>`;
}

/** חיבור כפתורי אישור/דחייה בתוך root. @param {HTMLElement} root @param {() => void} onChange */
export function bindActionButtons(root, onChange) {
  root.addEventListener("click", async (e) => {
    const el = /** @type {HTMLElement} */ (e.target);
    const ap = /** @type {HTMLButtonElement|null} */ (el.closest("[data-approve]"));
    const rj = /** @type {HTMLButtonElement|null} */ (el.closest("[data-reject]"));
    const applied = /** @type {HTMLButtonElement|null} */ (el.closest("[data-applied]"));
    if (applied) {
      applied.disabled = true;
      try {
        await api(`/api/findings/${applied.dataset.applied}/fix`, { method: "PATCH", body: JSON.stringify({ status: "applied" }) });
        toast(t("act.appliedToast"));
        onChange();
      } catch (err) { toast(/** @type {Error} */ (err).message, "error"); applied.disabled = false; }
      return;
    }
    if (!ap && !rj) return;
    const btn = /** @type {HTMLButtonElement} */ (ap || rj);
    btn.disabled = true;
    try {
      const a = await api(`/api/actions/${ap ? ap.dataset.approve : rj?.dataset.reject}/${ap ? "approve" : "reject"}`, { method: "POST" });
      toast(a.status === "failed" ? a.error : ap ? t("act.approved") : t("act.rejected"), a.status === "failed" ? "error" : "success");
      window.dispatchEvent(new CustomEvent("p1:usage"));
      onChange();
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); btn.disabled = false; }
  });
}

/** פתיחת מודאל אישור לפעולה. @param {any} a @param {() => void} onChange */
export function openActionModal(a, onChange) {
  openModal(`<h3>${t("act.title")}</h3>${actionCard(a)}`);
  const body = $("#modal-body");
  if (!body.dataset.bound) {
    body.dataset.bound = "1";
    bindActionButtons(body, () => { $("#modal").close(); window.dispatchEvent(new CustomEvent("p1:actions")); });
  }
  const handler = () => { onChange(); window.removeEventListener("p1:actions", handler); };
  window.addEventListener("p1:actions", handler);
}

/** @param {HTMLElement} view */
export async function approvalsView(view) {
  setTitle(t("act.title"));
  let filter = "open";
  let timer = 0;
  view.innerHTML = `<div></div>`;
  const root = /** @type {HTMLElement} */ (view.firstElementChild);
  const load = async () => {
    const { items } = await api("/api/actions");
    const shown = filter === "open" ? items.filter((/** @type {any} */ a) => ["proposed", "executing"].includes(a.status)) : items;
    root.innerHTML = `<div class="stack">
      <div class="row" style="justify-content:space-between"><p class="muted" style="max-width:640px">${t("act.sub")}</p>
        <div class="seg" role="tablist"><button data-f="open" class="${filter === "open" ? "on" : ""}">${t("act.filter.open")}</button>
        <button data-f="all" class="${filter === "all" ? "on" : ""}">${t("act.filter.all")}</button></div></div>
      ${shown.length ? `<div class="stack">${shown.map(actionCard).join("")}</div>` : `<div class="card empty">${t("act.none")}</div>`}</div>`;
    root.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => { filter = /** @type {HTMLElement} */ (b).dataset.f || "open"; load(); }));
    clearTimeout(timer);
    if (items.some((/** @type {any} */ a) => a.status === "executing")) timer = window.setTimeout(load, 4000);
  };
  bindActionButtons(root, load);
  await load();
  return () => clearTimeout(timer);
}
