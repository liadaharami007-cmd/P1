// @ts-check
// P1 Value Center: מה P1 עשה בפועל (נמדד) · מה זה שווה (אומדן עם הנחות שלך) · נתוני הדגמה בנפרד.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc } from "../ui.js";

/** @param {HTMLElement} view */
export async function valueView(view) {
  setTitle(t("val.title"));
  const d = await api("/api/business/value");
  const M = d.measured, D = d.demo, A = d.assumptions;
  const kpi = (/** @type {any} */ v, /** @type {string} */ k) => `<div class="kpi"><div class="kpi-num">${v}</div><div class="kpi-label">${t(k)}</div></div>`;
  view.innerHTML = `<div class="stack">
    <p class="muted" style="max-width:760px">${t("val.sub")}</p>
    <section class="card"><div class="card-head"><div><h2>${t("val.measured")}</h2><div class="card-sub">${t("val.measuredSub")}</div></div><span class="badge src-measured">${t("src.measured")}</span></div>
      <div class="kpis val-kpis">${kpi(M.audits, "val.audits")}${kpi(M.issues_found, "val.found")}${kpi(M.issues_verified_fixed, "val.verified")}
        ${kpi(M.actions_done, "val.actions")}${kpi(M.browser_steps, "val.steps")}${kpi(M.machine_minutes + " " + t("val.min"), "val.machine")}
        ${kpi("$" + Number(M.ai_cost_usd_month).toFixed(2), "val.aiCost")}${kpi(M.actions_waiting, "val.waiting")}</div></section>
    <section class="card"><div class="card-head"><div><h2>${t("val.roi")}</h2><div class="card-sub">${t("val.roiSub")}</div></div><span class="badge">${t("val.estimate")}</span></div>
      <form class="roi-app" id="roi" novalidate>
        <label>${t("val.in.hourly")}<input class="input" type="number" min="0" name="hourly" value="${A.hourly_value || 120}"></label>
        <label>${t("val.in.people")}<input class="input" type="number" min="1" name="people" value="1"></label>
        <label>${t("val.in.tasks")}<input class="input" type="number" min="0" name="tasks" value="${Math.max(M.audits, 4)}"></label>
        <label>${t("val.in.minutes")}<input class="input" type="number" min="0" name="minutes" value="${A.manual_minutes_per_audit}"></label>
        <label>${t("val.in.price")}<input class="input" type="number" min="0" name="price" value="0"></label>
      </form>
      <div class="roi-result" aria-live="polite"><div><span id="r-hours" class="num"></span><small>${t("val.r.hours")}</small></div>
        <div><span id="r-money" class="num"></span><small>${t("val.r.money")}</small></div><div><span id="r-net" class="num"></span><small>${t("val.r.net")}</small></div></div>
      <p class="tiny faint" id="r-formula"></p></section>
    <section class="card"><div class="card-head"><div><h2>${t("val.business")}</h2></div><span class="badge">${t("cmd.noData")}</span></div>
      <p class="small muted">${esc(d.business_metrics.note)}</p><a class="btn btn-sm" href="#/integrations" style="margin-top:8px">${t("nav.integrations")}</a></section>
    ${D.audits ? `<section class="card demo-card"><div class="card-head"><div><h2>${t("val.demo")}</h2><div class="card-sub">${t("val.demoSub")}</div></div><span class="badge demo-badge">${t("ag.demo")}</span></div>
      <div class="kpis val-kpis">${kpi(D.audits, "val.audits")}${kpi(D.issues_found, "val.found")}${kpi(D.machine_minutes + " " + t("val.min"), "val.machine")}</div></section>` : ""}
    <section class="card"><div class="card-head"><h2>${t("val.next")}</h2><a class="btn btn-sm btn-ghost" href="#/">${t("nav.command")}</a></div>
      <ol class="wk-lines">${d.next.map((/** @type {any} */ x) => `<li>${esc(x.title)}</li>`).join("") || `<li>${t("cmd.empty")}</li>`}</ol></section>
  </div>`;
  const f = /** @type {HTMLFormElement} */ (view.querySelector("#roi"));
  const nf = new Intl.NumberFormat(document.documentElement.lang === "he" ? "he-IL" : "en-US", { maximumFractionDigits: 1 });
  const calc = () => {
    const fd = new FormData(f); const n = (/** @type {string} */ k) => Math.max(0, Number(fd.get(k)) || 0);
    const hours = n("tasks") * n("minutes") / 60 * Math.max(1, n("people"));
    const money = hours * n("hourly");
    /** @type {HTMLElement} */ (view.querySelector("#r-hours")).textContent = nf.format(hours);
    /** @type {HTMLElement} */ (view.querySelector("#r-money")).textContent = "₪" + nf.format(Math.round(money));
    /** @type {HTMLElement} */ (view.querySelector("#r-net")).textContent = "₪" + nf.format(Math.round(money - n("price")));
    /** @type {HTMLElement} */ (view.querySelector("#r-formula")).textContent = t("val.formula", { tasks: n("tasks"), minutes: n("minutes"), people: Math.max(1, n("people")), hourly: n("hourly"), price: n("price") });
  };
  f.addEventListener("input", calc); calc();
}
