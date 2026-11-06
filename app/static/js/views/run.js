// @ts-check
// Autopilot: בקשה אחת → סוכנים ברצף. רואים כל סוכן, מה הוא קיבל מהקודמים ומה הוא הפיק — בזמן אמת.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";

const ICON = { audit: "🔍", research: "🔭", strategy: "🧭", ads: "📣", content: "🗓️", video: "🎬", landing_page: "🌐", leads: "🤝", tasks: "✅" };
const LINK = { ai_output: (/** @type {string} */ id) => "#/studio", page: (/** @type {string} */ id) => `#/pages?id=${id}`, audit: (/** @type {string} */ id) => `#/audits/${id}`,
  action: () => "#/approvals", leads: () => "#/leads", plan: () => "#/" };

/** @param {HTMLElement} view */
export async function runView(view) {
  const id = new URLSearchParams(location.hash.split("?")[1] || "").get("id");
  setTitle("Autopilot");
  let timer = 0;
  if (!id) {
    const d = await api("/api/autopilot");
    view.innerHTML = `<div class="stack" style="max-width:820px;margin:0 auto">
      <form class="card stack" id="ap" novalidate><h2 style="font-size:17px">${t("ap.title")}</h2><p class="small muted">${t("ap.sub")}</p>
        <textarea class="input" name="request" rows="3">${esc(t("ap.example"))}</textarea>
        <div class="row" style="justify-content:space-between"><span class="tiny faint">${d.ai ? t("ap.aiOn") : t("ap.aiOff")}</span>
          <button class="btn btn-primary">${icon("play")}${t("ap.go")}</button></div></form>
      ${d.items.length ? `<div class="list">${d.items.map((/** @type {any} */ r) => `<a class="list-item" href="#/run?id=${r.id}"><span class="small truncate" style="flex:1">${esc(r.request)}</span>
        <span class="badge">${t("ap.st." + r.status)}</span></a>`).join("")}</div>` : ""}</div>`;
    const f = /** @type {HTMLFormElement} */ (view.querySelector("#ap"));
    f.onsubmit = async (e) => { e.preventDefault(); const b = /** @type {HTMLButtonElement} */ (f.querySelector("button")); b.disabled = true; b.innerHTML = `<span class="spinner"></span>${t("ap.planning")}`;
      try { const r = await api("/api/autopilot", { method: "POST", body: JSON.stringify({ request: new FormData(f).get("request") }) }); location.hash = `#/run?id=${r.id}`; }
      catch (err) { toast(/** @type {Error} */ (err).message, "error"); b.disabled = false; b.textContent = t("ap.go"); } };
    return;
  }
  const draw = async () => {
    const r = await api(`/api/autopilot/${id}`);
    const done = r.plan.steps.filter((/** @type {any} */ s) => ["done", "awaiting_approval"].includes(s.status)).length;
    view.innerHTML = `<div class="stack" style="max-width:820px;margin:0 auto">
      <div class="bubble me" dir="auto" style="align-self:flex-end">${esc(r.request)}</div>
      <div class="bubble ceo"><div class="bubble-who">P1 CEO</div><p>${r.planner === "pending" ? `<span class="spinner"></span> ${t("ap.planning")}` : esc(r.plan.reply || t("ap.planned"))}</p>
        <p class="tiny faint">${t("ap.planner")} ${r.planner === "ai" ? t("src.ai") : t("act.source.rules")} · ${done}/${r.plan.steps.length}</p>
        <div class="meter" style="margin-top:6px"><div style="width:${Math.round(done / Math.max(1, r.plan.steps.length) * 100)}%"></div></div></div>
      <ol class="plan-steps">${r.plan.steps.map((/** @type {any} */ s, /** @type {number} */ i) => `<li class="plan-step ap-${s.status}"><span class="plan-n">${/** @type {any} */ (ICON)[s.agent] || i + 1}</span>
        <div style="flex:1;min-width:0"><div class="row" style="justify-content:space-between"><strong class="small">${t("ap.agent." + s.agent)}</strong>
          <span class="badge ap-badge-${s.status}">${s.status === "running" ? `<span class="live-dot"></span> ` : ""}${t("ap.s." + s.status)}</span></div>
          <div class="tiny muted">${esc(s.goal)}</div>
          ${s.summary ? `<div class="small" style="margin-top:6px;white-space:pre-line">${esc(s.summary.slice(0, 600))}</div>` : ""}
          ${s.error ? `<div class="notice notice-error" style="margin-top:6px"><span class="ico">!</span><span class="small">${esc(s.error)}</span></div>` : ""}
          ${s.ref && /** @type {any} */ (LINK)[s.ref.type] ? `<a class="btn btn-sm" style="margin-top:6px" href="${/** @type {any} */ (LINK)[s.ref.type](s.ref.id)}">${s.ref.needs_approval ? t("ceo.approve") : t("cmd.open")}</a>` : ""}</div></li>`).join("")}</ol>
      ${r.status !== "running" ? `<div class="row"><a class="btn btn-sm" href="#/">${t("ceo.toCommand")}</a><a class="btn btn-sm btn-ghost" href="#/run">${t("ap.new")}</a></div>` : ""}</div>`;
    clearTimeout(timer);
    if (r.status === "running") timer = window.setTimeout(draw, 3000);
  };
  await draw();
  return () => clearTimeout(timer);
}
