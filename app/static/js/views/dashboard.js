// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import {
  animateRings, api, auditForm, bindAuditForm, categoryBars, CATEGORIES, compareBars, delta, esc, fmtDate, gradeLabel,
  hostOf, icon, lineChart, scoreRing, sevBadge, srcBadge,
} from "../ui.js";

const PERSONA_EMOJI = { price_seeker: "🏷️", wary_newcomer: "🧐", in_a_hurry: "⚡", unclear_benefits: "🤔", mobile_ad_visitor: "📱",
  skeptic: "🧐", bargain: "🏷️", hesitant: "🤔", rushed: "⚡", researcher: "🔬" };
const VERDICT_CLS = { likely_buy: "st-passed", hesitant: "st-warning", likely_leave: "st-failed" };

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function dashboardView(view, _p, app) {
  const siteId = new URLSearchParams(location.hash.split("?")[1] || "").get("site");
  const d = await api("/api/dashboard" + (siteId ? `?site_id=${encodeURIComponent(siteId)}` : ""));
  const browser = app.status.capabilities.browser_audit;

  if (!d.site) {
    setTitle(t("nav.overview"));
    view.innerHTML = `<section class="hero"><h2>${t("dash.heroTitle")}</h2><p class="lead">${t("dash.heroText")}</p>
      ${auditForm(browser, true)}
      <div class="hero-points"><div class="hero-point"><strong>${t("dash.point1")}</strong>${t("dash.point1t")}</div>
      <div class="hero-point"><strong>${t("dash.point2")}</strong>${t("dash.point2t")}</div>
      <div class="hero-point"><strong>${t("dash.point3")}</strong>${t("dash.point3t")}</div></div></section>`;
    bindAuditForm(view);
    return;
  }

  const L = d.latest;
  setTitle(d.site.name || hostOf(d.site.url), `<a class="btn btn-primary btn-sm" href="#/audits">${icon("plus")}<span class="btn-label">${t("common.newAudit")}</span></a>`);
  const siteSwitch = d.sites.length > 1 ? `<select class="input" id="site-switch" aria-label="site">
      ${d.sites.map((/** @type {any} */ s) => `<option value="${s.id}" ${s.id === d.site.id ? "selected" : ""}>${esc(s.name || hostOf(s.url))}</option>`).join("")}</select>` : "";
  const running = d.running.length ? `<a class="notice notice-info" href="#/audits/${d.running[0].id}" style="text-decoration:none">
      <span class="live-dot" style="margin-top:6px"></span><span><strong>${t("dash.running")}</strong></span></a>` : "";
  const open = Object.values(d.severity_counts).reduce((/** @type {number} */ a, /** @type {number} */ b) => a + b, 0);
  const cmp = d.comparison;
  const personas = d.ai_personas.length && d.ai_personas.some((/** @type {any} */ p) => p.verdict)
    ? d.ai_personas.filter((/** @type {any} */ p) => p.verdict).map((/** @type {any} */ p) => ({ ...p, src: "ai" }))
    : d.rule_personas.map((/** @type {any} */ p) => ({ key: p.persona, name: t("cust.rulesTitle"), verdict: p.verdict, src: "simulation", first: p.blockers[0] }));
  const auditsPct = Math.min(100, Math.round(d.usage.audits / d.plan.audits_per_month * 100));

  view.innerHTML = `<div class="stack">
    <div class="row">${siteSwitch}<span class="muted small ltr">${esc(d.site.url)}</span><span class="spacer"></span>
      ${L ? `<span class="legend">${srcBadge("measured")} ${fmtDate(L.finished_at)}</span>` : ""}</div>
    ${running}
    ${!L ? `<div class="card empty"><h3>${t("dash.noDone")}</h3><p>${d.recent_audits[0]?.status === "failed" ? t("dash.lastFailed") + " " + esc(d.recent_audits[0].error || "") : ""}</p></div>` : `
    <div class="grid g-main">
      <div class="card"><div class="card-head"><div><h2>${t("dash.health")}</h2><div class="card-sub">${t("dash.healthSub")}</div></div>
        <a class="btn btn-sm" href="#/audits/${L.id}">${t("dash.fullReport")}</a></div>
        <div class="row" style="gap:28px;align-items:center">
          <div class="score-block">${scoreRing(L.score)}${gradeLabel(L.score)}${cmp ? `<span class="small muted">${delta(cmp.score_delta)} ${t("dash.compare")}</span>` : ""}</div>
          <div style="flex:1;min-width:240px">${categoryBars(L.category_scores)}</div></div></div>
      <div class="card"><div class="card-head"><div><h2>${t("dash.open")}</h2><div class="card-sub">${t("dash.fromLatest")}</div></div>
        <a class="btn btn-sm btn-ghost" href="#/tasks">${t("dash.toTasks")}</a></div>
        <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          ${["critical", "high", "medium", "low"].map((s) => `<div class="kpi"><div class="kpi-num">${d.severity_counts[s]}</div><div class="kpi-label">${sevBadge(/** @type {any} */ (s))}</div></div>`).join("")}</div>
        <div class="row small muted" style="margin-top:12px">✓ ${t("dash.fixed")}: <strong>${d.status_counts.done}</strong> · ${t("dash.inProgress")}: <strong>${d.status_counts.in_progress}</strong> · ${t("fstatus.open")}: <strong>${open}</strong></div>
        <div class="divider"></div>
        <div class="row small" style="justify-content:space-between"><span class="muted">${t("dash.usage")} · ${esc(d.plan.name)}</span><span class="num">${d.usage.audits}/${d.plan.audits_per_month}</span></div>
        <div class="meter ${auditsPct >= 100 ? "full" : auditsPct >= 80 ? "warn" : ""}" style="margin-top:6px"><div style="width:${auditsPct}%"></div></div></div>
    </div>

    <div class="grid g-main">
      <div class="card"><div class="card-head"><div><h2>${t("dash.trend")}</h2></div>
        ${d.trend.length >= 2 ? `<div class="seg" id="trend-seg" role="tablist"><button class="on" data-k="overall">${t("dash.overall")}</button>
          ${Object.entries(CATEGORIES).map(([k, v]) => `<button data-k="${k}">${esc(v)}</button>`).join("")}</div>` : ""}</div>
        <div id="trend">${d.trend.length >= 2 ? "" : `<div class="empty small">${t("dash.trendNeed")}</div>`}</div>
        ${cmp ? `<div class="divider"></div><div class="card-head" style="margin-bottom:8px"><div><h3>${t("cmp.title")}</h3><div class="card-sub">${t("cmp.sub")}</div></div>
          <span class="small">✓ ${cmp.fixed.length} ${t("cmp.fixed")} · ✕ ${cmp.new.length} ${t("cmp.new")}</span></div>${compareBars(cmp)}` : ""}</div>
      <div class="card"><div class="card-head"><div><h2>${t("dash.aiSummary")}</h2></div>${srcBadge("ai")}</div>
        ${d.ai_summary ? `<p style="white-space:pre-line">${esc(d.ai_summary)}</p>` :
          `<div class="notice"><span class="ico">i</span><span>${L.ai_status === "running" ? t("ai.running") : t("ai." + (L.ai_status === "quota_exceeded" ? "quota_exceeded" : "not_configured"))}</span></div>`}</div>
    </div>

    <div class="grid g-main">
      <div class="card"><div class="card-head"><div><h2>${t("dash.top")}</h2><div class="card-sub">${t("dash.topSub")}</div></div></div>
        ${d.top_findings.length ? `<div class="list">${d.top_findings.map((/** @type {any} */ f) => `
          <a class="list-item" href="#/audits/${L.id}?f=${f.id}"><div class="list-main"><div class="list-title">${esc(f.title)}</div>
            <div class="finding-meta">${sevBadge(f.severity)}<span class="badge outline">${esc(CATEGORIES[f.category] || f.category)}</span><span class="tiny muted">${t("impact." + f.impact)}</span></div></div></a>`).join("")}</div>`
          : `<div class="empty"><h3>${t("dash.noOpen")}</h3></div>`}</div>
      <div class="card"><div class="card-head"><div><h2>${t("dash.customers")}</h2></div>${srcBadge(personas[0]?.src === "ai" ? "ai" : "simulation")}</div>
        <div class="list">${personas.map((/** @type {any} */ p) => `<div class="list-item"><span class="persona-avatar">${/** @type {any} */ (PERSONA_EMOJI)[p.key] || "👤"}</span>
          <div class="list-main"><div class="list-title">${esc(p.src === "ai" ? p.name : (p.first || p.key))}</div></div>
          <span class="badge ${/** @type {any} */ (VERDICT_CLS)[p.verdict]}">${t("verdict." + p.verdict)}</span></div>`).join("")}</div></div>
    </div>`}

    <div class="card"><div class="card-head"><h2>${t("dash.recent")}</h2><a class="btn btn-sm btn-ghost" href="#/audits">${t("common.all")}</a></div>
      <div class="list">${d.recent_audits.map(auditRow).join("")}</div></div>
  </div>`;

  animateRings(view);
  view.querySelector("#site-switch")?.addEventListener("change", (e) => (location.hash = `#/?site=${/** @type {HTMLSelectElement} */ (e.target).value}`));
  const trendEl = /** @type {HTMLElement|null} */ (view.querySelector("#trend"));
  if (trendEl && d.trend.length >= 2) {
    const draw = (/** @type {string} */ k) => lineChart(trendEl, d.trend.map((/** @type {any} */ p) => ({ id: p.id, at: p.at,
      score: k === "overall" ? p.score : (p.categories || {})[k] ?? null })), k === "overall" ? t("dash.overall") : CATEGORIES[k]);
    draw("overall");
    view.querySelectorAll("#trend-seg button").forEach((b) => b.addEventListener("click", () => {
      view.querySelectorAll("#trend-seg button").forEach((x) => x.classList.toggle("on", x === b));
      draw(/** @type {HTMLElement} */ (b).dataset.k || "overall");
    }));
  }
}

/** @param {any} a */
export function auditRow(a) {
  const busy = a.status === "running" || a.status === "queued";
  return `<a class="list-item" href="#/audits/${a.id}">
    <div class="mini-score">${a.status === "done" ? (a.score ?? "—") : a.status === "failed" ? "✕" : '<span class="spinner"></span>'}</div>
    <div class="list-main"><div class="list-title">${esc(a.site_name || hostOf(a.site_url))}</div>
      <div class="tiny muted">${fmtDate(a.created_at)} · ${a.status === "done" ? t("audits.findings", { n: a.finding_count }) : t("astatus." + a.status)}${a.status === "failed" && a.error ? " — " + esc(a.error) : ""}</div></div>
    ${busy ? `<span class="badge st-running"><span class="live-dot"></span> ${t("astatus." + a.status)}</span>` : a.status === "done" ? gradeLabel(a.score) : `<span class="badge st-failed">${t("astatus.failed")}</span>`}</a>`;
}
