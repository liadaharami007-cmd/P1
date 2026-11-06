// @ts-check
// שיחה עם P1 CEO: שאלה אחת בכל פעם, רק מה שחסר → תוכנית שבה כל צעד מסומן (עובד / חלקי / לא זמין) → אישור פעולות.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";
import { openActionModal } from "./approvals.js";

const DEPT = { web: "🌐", marketing: "📣", sales: "🤝", finance: "📊", research: "🔭", ops: "⚙️" };

/** @param {any} s */
function stepRow(s, i) {
  const st = `<span class="cap-dot cap-${s.status}"></span><span class="tiny cap-label">${t("cap." + s.status)}</span>`;
  const act = s.action ? (s.action.status === "proposed"
      ? `<button class="btn btn-sm btn-primary" data-act="${s.action.id}">${icon("check")}${t("ceo.approve")}</button>`
      : s.action.audit_id ? `<a class="btn btn-sm" href="#/audits/${s.action.audit_id}">${t("act.st." + s.action.status)} · ${t("act.toAudit")}</a>`
      : `<span class="badge act-st act-${s.action.status}">${t("act.st." + s.action.status)}</span>`)
    : s.link && s.status !== "unavailable" ? `<a class="btn btn-sm btn-ghost" href="${s.link}">${t("cmd.open")}</a>` : "";
  return `<li class="plan-step st-${s.status}"><span class="plan-n">${i + 1}</span>
    <div style="flex:1;min-width:0"><div class="row" style="gap:8px"><span>${/** @type {any} */ (DEPT)[s.department] || "•"}</span><strong class="small">${esc(s.title)}</strong></div>
      ${s.why ? `<div class="tiny muted">${esc(s.why)}</div>` : ""}${s.note ? `<div class="tiny faint">${esc(s.note)}</div>` : ""}
      <div class="row" style="gap:6px;margin-top:4px">${st}${s.needs_approval ? `<span class="chip">${t("ceo.needsApproval")}</span>` : ""}${s.minutes ? `<span class="chip">${t("cmd.minutes", { n: s.minutes })}</span>` : ""}</div></div>
    <div>${act}</div></li>`;
}

/** @param {any} m */
function planHtml(m) {
  const r = m.plan.readiness;
  return `<div class="bubble ceo"><div class="bubble-who">P1 CEO</div>
    <p>${t("ceo.planIntro")}</p>
    ${r ? `<div class="readiness"><div class="row" style="justify-content:space-between"><strong>${t("ceo.readiness")}</strong><span class="num"><strong>${r.score}%</strong></span></div>
      <div class="meter" style="margin:6px 0"><div style="width:${r.score}%"></div></div>
      <ul class="check-list">${r.checks.map((/** @type {any} */ c) => `<li class="${c.ok ? "ok" : "no"}">${c.ok ? "✓" : "○"} ${esc(c.label)}</li>`).join("")}</ul>
      <p class="tiny faint">${esc(r.note)}</p></div>` : ""}
    <ol class="plan-steps">${m.plan.steps.map(stepRow).join("")}</ol>
    <p class="tiny faint">${t("ceo.engineRules")}</p>
    <div class="row" style="margin-top:10px">${m.plan.suggest_demo ? `<a class="btn btn-sm btn-primary" href="#/agency">${t("ceo.toAgency")}</a>` : ""}
      <a class="btn btn-sm" href="#/">${t("ceo.toCommand")}</a><a class="btn btn-sm btn-ghost" href="#/start">${t("ceo.newMission")}</a></div></div>`;
}

/** @param {HTMLElement} view */
export async function ceoView(view) {
  setTitle("P1 CEO");
  const qs = new URLSearchParams(location.hash.split("?")[1] || "");
  view.innerHTML = `<div class="chat-wrap"><div class="chat" id="chat" aria-live="polite"></div><div id="composer" class="composer"></div></div>`;
  const chat = /** @type {HTMLElement} */ (view.querySelector("#chat"));
  const composer = /** @type {HTMLElement} */ (view.querySelector("#composer"));
  const say = (/** @type {string} */ html, who = "ceo") => { chat.insertAdjacentHTML("beforeend", who === "ceo"
    ? `<div class="bubble ceo"><div class="bubble-who">P1 CEO</div>${html}</div>` : `<div class="bubble me" dir="auto">${html}</div>`); chat.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "end" }); };
  const bindPlan = (/** @type {any} */ m) => chat.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    try { openActionModal(await api(`/api/actions/${/** @type {HTMLElement} */ (b).dataset.act}`), async () => {
      const fresh = await api(`/api/missions/${m.id}`); chat.lastElementChild?.remove(); chat.insertAdjacentHTML("beforeend", planHtml(fresh)); bindPlan(fresh); }); }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); } }));

  const missionId = qs.get("mission");
  if (missionId) {
    const m = await api(`/api/missions/${missionId}`);
    say(`<p>${t("ceo.missionOf")} <strong>${esc(m.title)}</strong></p>`);
    chat.insertAdjacentHTML("beforeend", planHtml(m)); bindPlan(m); composer.innerHTML = ""; return;
  }
  const intent = qs.get("intent") || "consult";
  if (intent === "today") return todayFlow();
  const freeText = sessionStorage.getItem("p1.ceoText");
  sessionStorage.removeItem("p1.ceoText");
  const r = await api("/api/ceo/intent", { method: "POST", body: JSON.stringify({ intent }) });
  if (freeText) say(esc(freeText), "me");
  say(`<p>${t("ceo.understood")} <strong>${esc(r.label)}</strong>.</p>${r.questions.length ? `<p class="small muted">${t("ceo.fewQuestions", { n: r.questions.length })}</p>` : ""}`);
  /** @type {Record<string, any>} */
  const answers = {};
  let i = 0;
  const ask = () => {
    if (i >= r.questions.length) return finish();
    const q = r.questions[i];
    say(`<p>${esc(q.q)}</p>${q.hint ? `<p class="tiny faint">${esc(q.hint)}</p>` : ""}`);
    const opt = (/** @type {any} */ o, /** @type {string} */ type) => `<label class="chip-check"><input type="${type}" name="a" value="${esc(o[0])}"><span>${esc(o[1])}</span></label>`;
    const input = q.kind === "choice" ? `<div class="chips-select">${q.options.map((/** @type {any} */ o) => opt(o, "radio")).join("")}</div>`
      : q.kind === "multi" ? `<div class="chips-select">${q.options.map((/** @type {any} */ o) => opt(o, "checkbox")).join("")}</div>`
      : q.kind === "yesno" ? `<div class="chips-select">${opt(["yes", t("common.yes")], "radio")}${opt(["no", t("common.no")], "radio")}</div>`
      : q.kind === "textarea" ? `<textarea class="input" name="a" rows="3"></textarea>`
      : `<input class="input ${q.kind === "url" ? "ltr" : ""}" name="a" ${q.kind === "number" ? 'type="number" min="0" inputmode="decimal"' : q.kind === "url" ? 'type="url" placeholder="https://"' : ""} value="${esc(q.default || "")}">`;
    composer.innerHTML = `<form class="composer-form" novalidate>${input}<div class="row" style="justify-content:flex-end;gap:8px">
      ${q.required ? "" : `<button class="btn btn-ghost btn-sm" type="button" data-skip>${t("ceo.skip")}</button>`}
      <button class="btn btn-primary btn-sm" type="submit">${t("ceo.next")} ${icon("chevron")}</button></div></form>`;
    const f = /** @type {HTMLFormElement} */ (composer.querySelector("form"));
    /** @type {HTMLElement|null} */ (f.querySelector("input:not([type=radio]):not([type=checkbox]), textarea"))?.focus();
    const next = (/** @type {any} */ val, /** @type {string} */ shown) => { if (val !== undefined) answers[q.id] = val; say(esc(shown || t("ceo.skipped")), "me"); i += 1; ask(); };
    /** @type {HTMLElement|null} */ (f.querySelector("[data-skip]"))?.addEventListener("click", () => next(undefined, ""));
    f.onsubmit = (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const vals = fd.getAll("a").map(String).filter((v) => v.trim());
      if (!vals.length) { if (q.required) { toast(t("ceo.required"), "error"); return; } return next(undefined, ""); }
      const labels = q.options.length ? vals.map((v) => (q.options.find((/** @type {any} */ o) => o[0] === v) || [v, v])[1]) : q.kind === "yesno" ? vals.map((v) => t(v === "yes" ? "common.yes" : "common.no")) : vals;
      next(q.kind === "multi" ? vals : vals[0], labels.join(", "));
    };
  };
  const finish = async () => {
    composer.innerHTML = `<div class="row small muted"><span class="spinner"></span>${t("ceo.building")}</div>`;
    try {
      const m = await api("/api/missions", { method: "POST", body: JSON.stringify({ intent, answers }) });
      history.replaceState(null, "", `#/ceo?mission=${m.id}`);
      chat.insertAdjacentHTML("beforeend", planHtml(m)); bindPlan(m);
      chat.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "end" });
      composer.innerHTML = "";
    } catch (e) { composer.innerHTML = `<div class="notice notice-error"><span class="ico">!</span><span>${esc(/** @type {Error} */ (e).message)}</span></div>`; }
  };
  ask();

  async function todayFlow() {
    say(esc(t("start.ex1")), "me");
    const d = await api("/api/ceo/today");
    say(`<p>${t("ceo.todayIntro")}</p><ol class="plan-steps">${d.items.map((/** @type {any} */ it, /** @type {number} */ n) => `<li class="plan-step"><span class="plan-n">${n + 1}</span>
      <div style="flex:1;min-width:0"><strong class="small">${esc(it.title)}</strong><div class="tiny muted">${t("ceo.why")} ${esc(it.why)}</div>
      <div class="tiny muted">${t("ceo.outcome")} ${esc(it.outcome)} · ${t("ceo.time")} ${t("cmd.minutes", { n: it.minutes })} · ${t("ceo.cost")} ${esc(it.cost_note)}</div>
      <div class="tiny faint">${t("ceo.agents")} ${it.agents.map(esc).join(", ")} · ${it.needs_approval ? t("ceo.needsApproval") : t("ceo.noApproval")}</div></div>
      <div>${it.kind === "link" ? `<a class="btn btn-sm" href="${it.link}">${t("cmd.open")}</a>` : `<a class="btn btn-sm btn-primary" href="#/">${t("cmd.prepare")}</a>`}</div></li>`).join("")}</ol>
      <p class="tiny faint">${esc(d.method)}</p>`);
    composer.innerHTML = "";
  }
}
