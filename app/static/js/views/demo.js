// @ts-check
// Demo Experience — סיור מודרך על חנות דמו של P1. הבדיקה עצמה אמיתית; החנות מסומנת כדמו.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, icon, toast } from "../ui.js";

/** @param {HTMLElement} view */
export async function demoView(view) {
  setTitle(t("demo.title"));
  const audits = await api("/api/audits");
  const demoAudit = audits.find((/** @type {any} */ a) => a.is_demo && a.status === "done");
  const running = audits.find((/** @type {any} */ a) => a.is_demo && (a.status === "running" || a.status === "queued"));
  const A = demoAudit ? demoAudit.id : null;
  /** @type {[string, string|null, boolean][]} */
  const steps = [
    ["demo.step1", "#/", true],
    ["demo.step2", "#/sites", true],
    ["demo.step3", running ? `#/audits/${running.id}` : null, !!demoAudit],
    ["demo.step4", running ? `#/audits/${running.id}` : A ? `#/audits/${A}` : null, !!demoAudit],
    ["demo.step5", A ? `#/audits/${A}` : null, !!demoAudit],
    ["demo.step6", A ? `#/fix/${A}` : null, false],
    ["demo.step7", A ? `#/fix/${A}` : null, false],
    ["demo.step8", A ? `#/fix/${A}` : null, false],
    ["demo.step9", A ? `/api/audits/${A}/report.pdf` : null, false],
  ];
  view.innerHTML = `<div class="stack">
    <section class="hero"><span class="badge" style="background:rgba(255,255,255,.14);color:#fff">${t("demo.badge")}</span>
      <h2 style="margin-top:10px">${t("demo.title")}</h2><p class="lead">${t("demo.sub")}</p>
      <div class="row"><button class="btn btn-primary btn-lg" id="demo-start">${icon("play")} ${t("demo.start")}</button>
        <a class="btn btn-lg" href="/demo-store/" target="_blank" rel="noopener">${t("demo.openStore")}</a></div>
      <p class="small" style="color:#c9c8ea;margin-top:14px">${t("demo.storeNote")}</p></section>
    <div class="card"><div class="demo-steps">${steps.map(([k, href, done], i) => `<div class="demo-step ${done ? "done" : ""}">
      <span class="demo-num">${done ? "✓" : i + 1}</span><span class="demo-label">${t(k)}</span>
      ${href ? `<a class="btn btn-sm" href="${href}">${t("demo.go")}</a>` : `<span class="tiny muted">—</span>`}</div>`).join("")}</div></div></div>`;
  /** @type {HTMLButtonElement} */ (view.querySelector("#demo-start")).onclick = async () => {
    try { const a = await api("/api/demo/start", { method: "POST" }); location.hash = `#/audits/${a.id}`; }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
}
