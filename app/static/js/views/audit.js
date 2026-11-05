// @ts-check
// בדיקה בודדת: מצב חי (יומן פעולות + צילום אחרון) ← דוח מלא.
import { refreshUsage, setTitle } from "../app.js";
import { lang, t } from "../i18n.js";
import {
  $, $$, animateRings, api, categoryBars, CATEGORIES, compareBars, delta, esc, evidenceThumb, fmtDate, fmtDuration,
  gradeLabel, hostOf, icon, openModal, scoreRing, sevBadge, srcBadge, STEP_ICON, stepBadge, toast,
} from "../ui.js";

const PHASES = ["home", "trust", "links", "product", "add_to_cart", "cart", "checkout", "search", "mobile"];
const FEED_ICO = { navigate: "↗", loaded: "•", click: "◉", type: "⌨", select: "☰", screenshot: "▣", step_passed: "✓",
  step_failed: "✕", step_warning: "!", step_skipped: "–", error: "!", ai: "✦", info: "i", device: "▯" };
const PERSONA_EMOJI = { price_seeker: "🏷️", wary_newcomer: "🧐", in_a_hurry: "⚡", unclear_benefits: "🤔", mobile_ad_visitor: "📱" };
const RULE_PERSONA = { skeptic: ["🧐", "Skeptic", "הלקוח החשדן"], bargain: ["🏷️", "Bargain hunter", "מחפש המחיר"],
  hesitant: ["🤔", "Hesitant", "המתלבט"], rushed: ["⚡", "In a hurry", "הממהר"], researcher: ["🔬", "Researcher", "החוקר"] };
const VERDICT_CLS = { likely_buy: "st-passed", hesitant: "st-warning", likely_leave: "st-failed" };

/** @param {HTMLElement} view @param {{id: string}} params @param {any} app */
export async function auditView(view, { id }, app) {
  /** @type {any} */ let timer = null; /** @type {any} */ let clock = null; let alive = true;
  let lastEvent = 0; let mode = "";

  const live = async () => {
    const ev = await api(`/api/audits/${id}/events?after=${lastEvent}`);
    if (!alive) return;
    if (ev.status === "done" || ev.status === "failed") { await report(); return; }
    if (mode !== "live") { mode = "live"; renderLive(view, ev); clearInterval(clock); clock = setInterval(() => tick(view, ev), 1000); }
    appendEvents(view, ev.events);
    if (ev.events.length) lastEvent = ev.events[ev.events.length - 1].id;
    updateLive(view, ev);
    timer = setTimeout(live, 1200);
  };

  const report = async () => {
    clearInterval(clock);
    const a = await api(`/api/audits/${id}`);
    if (!alive) return;
    if (a.status === "failed") { mode = "failed"; renderFailed(view, a); return; }
    const keepTab = /** @type {HTMLElement|null} */ (view.querySelector(".tabs button.active"))?.dataset.tab;
    mode = "report";
    renderReport(view, a, app, keepTab);
    if (a.ai_status === "running" || a.ai_status === "pending") timer = setTimeout(report, 3000);
    else refreshUsage();
  };

  await live();
  return () => { alive = false; clearTimeout(timer); clearInterval(clock); };
}

// ---------------------------------------------------------------- מצב חי
/** @param {HTMLElement} view @param {any} ev */
function renderLive(view, ev) {
  setTitle(hostOf(ev.start_url));
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="row" style="justify-content:space-between">
      <div><div class="row"><span class="live-dot"></span><h2 style="font-size:16px">${ev.status === "queued" ? t("live.queued") : t("live.title")}</h2></div>
        <div class="small muted ltr" style="margin-top:4px">${esc(ev.start_url)}</div></div>
      <div class="row" style="gap:20px"><div><div class="tiny muted">${t("live.elapsed")}</div><div class="kpi-num num" id="elapsed">0:00</div></div></div></div>
      <div class="phases" id="phases" style="margin-top:16px">${PHASES.map((p) => `<span class="phase" data-p="${p}">${t("phase." + p)}</span>`).join("")}
        <span class="phase" data-p="ai">✦ ${t("live.ai")}</span></div></div>
    <div class="live-grid">
      <div class="card"><div class="card-head"><h3>${t("live.activity")}</h3><span class="tiny muted" id="ev-count"></span></div>
        <div class="feed" id="feed"></div></div>
      <div class="card"><div class="card-head"><h3>${t("live.latestShot")}</h3><span class="badge outline tiny" id="shot-label"></span></div>
        <div class="live-shot" id="live-shot"><span class="muted small">${t("live.noShot")}</span></div>
        <div class="small muted truncate ltr" style="margin-top:10px" id="cur-url"></div>
        <p class="tiny muted" style="margin-top:10px">${t("live.safe")}</p></div>
    </div></div>`;
}

/** @param {HTMLElement} view @param {any} ev */
function tick(view, ev) {
  const el = view.querySelector("#elapsed");
  if (el && ev.started_at) el.textContent = fmtDuration(Date.now() - new Date(ev.started_at).getTime());
}

/** @param {HTMLElement} view @param {any[]} events */
function appendEvents(view, events) {
  const feed = /** @type {HTMLElement|null} */ (view.querySelector("#feed"));
  if (!feed || !events.length) return;
  const start = feed.dataset.t0 ? +feed.dataset.t0 : new Date(events[0].at).getTime();
  feed.dataset.t0 = String(start);
  feed.insertAdjacentHTML("beforeend", events.map((e) => feedItem(e, start)).join(""));
  feed.scrollTop = feed.scrollHeight;
  const shot = [...events].reverse().find((e) => e.kind === "screenshot" && e.screenshot_id) || [...events].reverse().find((e) => e.screenshot_id);
  if (shot) {
    /** @type {HTMLElement} */ (view.querySelector("#live-shot")).innerHTML = `<button class="tl-shot" style="width:100%;height:100%" data-shot="${shot.screenshot_id}" data-caption="${esc(shot.message)}"><img src="/api/screenshots/${shot.screenshot_id}" alt="${esc(shot.message)}"></button>`;
    /** @type {HTMLElement} */ (view.querySelector("#shot-label")).textContent = shot.message.replace(/^[^:]+:\s*/, "");
  }
  const url = [...events].reverse().find((e) => e.page_url);
  if (url) /** @type {HTMLElement} */ (view.querySelector("#cur-url")).textContent = url.page_url;
  const phases = /** @type {HTMLElement} */ (view.querySelector("#phases"));
  for (const e of events) {
    if (e.kind.startsWith("step_") && e.ref) phases.querySelector(`[data-p="${e.ref}"]`)?.setAttribute("class", `phase ${e.kind.slice(5)}`);
    if (e.kind === "ai") phases.querySelector('[data-p="ai"]')?.setAttribute("class", "phase active");
  }
  /** @type {HTMLElement} */ (view.querySelector("#ev-count")).textContent = String(feed.children.length);
}

/** @param {any} e @param {number} t0 */
function feedItem(e, t0) {
  const sec = Math.max(0, Math.round((new Date(e.at).getTime() - t0) / 1000));
  return `<div class="feed-item"><span class="feed-time">+${fmtDuration(sec * 1000)}</span>
    <span class="feed-ico k-${e.kind}">${/** @type {any} */ (FEED_ICO)[e.kind] || "•"}</span>
    <span>${esc(e.message)}${e.page_url && e.kind === "navigate" ? `<span class="feed-url ltr">${esc(e.page_url)}</span>` : ""}</span></div>`;
}

/** @param {HTMLElement} view @param {any} ev */
function updateLive(view, ev) {
  const cur = ev.progress?.length ? ev.progress[ev.progress.length - 1].key : null;
  $$(".phase", view).forEach((p) => {
    if (p.dataset.p === cur && !/passed|failed|warning/.test(p.className)) p.classList.add("active");
    else if (p.dataset.p !== cur) p.classList.remove("active");
  });
}

function renderFailed(/** @type {HTMLElement} */ view, /** @type {any} */ a) {
  setTitle(hostOf(a.start_url));
  view.innerHTML = `<div class="card" style="max-width:720px"><div class="notice notice-error"><span class="ico">!</span><div>
    <strong>${t("report.failed")}</strong><div class="ltr small">${esc(a.start_url)}</div><div>${esc(a.error || "")}</div></div></div>
    <div class="row" style="margin-top:16px"><a class="btn" href="#/audits">${t("report.back")}</a>
    <button class="btn btn-ghost btn-danger" id="del">${icon("trash")} ${t("common.delete")}</button></div></div>`;
  /** @type {HTMLElement} */ (view.querySelector("#del")).onclick = () => del(a.id);
}

/** @param {string} id */
async function del(id) {
  if (!confirm(t("report.confirmDelete"))) return;
  try { await api(`/api/audits/${id}`, { method: "DELETE" }); toast(t("common.delete") + " ✓"); location.hash = "#/audits"; }
  catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
}

// ---------------------------------------------------------------- דוח
/** @param {HTMLElement} view @param {any} a @param {any} app @param {string} [keepTab] */
function renderReport(view, a, app, keepTab) {
  const aiReady = app.status.capabilities.ai_analysis.ready;
  const canRunAi = aiReady && ["not_configured", "failed", "partial", "quota_exceeded"].includes(a.ai_status);
  setTitle(a.site_name || hostOf(a.site_url), `
    <a class="btn btn-sm" href="/api/audits/${a.id}/report.pdf" id="pdf">${icon("download")}<span class="btn-label">${t("report.pdf")}</span></a>
    ${canRunAi ? `<button class="btn btn-sm" id="run-ai">${icon("sparkle")}<span class="btn-label">${t("report.runAi")}</span></button>` : ""}
    <button class="btn btn-sm" id="rerun">${icon("refresh")}<span class="btn-label">${t("report.rerun")}</span></button>
    <button class="icon-btn" id="del" aria-label="${t("common.delete")}">${icon("trash")}</button>`);
  const measured = a.findings.filter((/** @type {any} */ f) => f.source === "measured");
  const aiF = a.findings.filter((/** @type {any} */ f) => f.source === "ai");
  const passed = a.steps.filter((/** @type {any} */ s) => s.status === "passed").length;
  const tested = a.steps.filter((/** @type {any} */ s) => s.status !== "skipped").length;
  const lcp = a.facts?.home?.timing?.lcp || a.facts?.home?.load_ms;
  const focus = new URLSearchParams(location.hash.split("?")[1] || "").get("f");
  const tab = keepTab || (focus ? "findings" : "overview");
  const tabs = [["overview", t("report.tab.overview"), ""], ["findings", t("report.tab.findings"), measured.length + aiF.length],
    ["journey", t("report.tab.journey"), `${passed}/${tested}`], ["customers", t("report.tab.customers"), ""],
    ["evidence", t("report.tab.evidence"), a.screenshots.length], ["data", t("report.tab.data"), ""]];

  view.innerHTML = `<div class="stack">
    <div class="grid g-main">
      <div class="card"><div class="card-head"><div><h2>${t("dash.health")}</h2><div class="card-sub">${t("dash.healthSub")}</div></div>
        <button class="btn btn-sm btn-ghost" id="meth">${icon("info")} ${t("report.methodology")}</button></div>
        <div class="row" style="gap:28px;align-items:center"><div class="score-block">${scoreRing(a.score)}${gradeLabel(a.score)}
          ${a.comparison ? `<span class="small muted">${delta(a.comparison.score_delta)} ${t("dash.compare")}</span>` : ""}</div>
          <div style="flex:1;min-width:240px">${categoryBars(a.category_scores)}</div></div></div>
      <div class="card"><div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
        <div class="kpi"><div class="kpi-num">${measured.length}</div><div class="kpi-label">${srcBadge("measured")}</div></div>
        <div class="kpi"><div class="kpi-num">${aiF.length || "—"}</div><div class="kpi-label">${srcBadge("ai")}</div></div>
        <div class="kpi"><div class="kpi-num">${passed}/${tested}</div><div class="kpi-label">${t("report.steps")}</div></div>
        <div class="kpi"><div class="kpi-num">${lcp ? (lcp < 1000 ? lcp + "ms" : (lcp / 1000).toFixed(1) + t("common.seconds")) : "—"}</div><div class="kpi-label">${t("report.lcp")}</div></div></div>
        <p class="tiny muted" style="margin-top:12px">${t("report.checkedAt")} ${fmtDate(a.finished_at)} · <a class="ltr" href="${esc(a.start_url)}" target="_blank" rel="noopener noreferrer">${esc(a.start_url)}</a>
          ${a.ai.cost_usd ? ` · ${t("report.aiCost")}: $${a.ai.cost_usd.toFixed(3)}` : ""}</p></div>
    </div>
    ${aiNotice(a)}
    <div class="legend"><span>${t("find.refs")}:</span>${srcBadge("measured")}${srcBadge("simulation")}${srcBadge("ai", !aiReady)}${srcBadge("store_data", true)}</div>
    <div><div class="tabs" role="tablist">${tabs.map(([k, label, n]) => `<button role="tab" data-tab="${k}" class="${k === tab ? "active" : ""}">${label}${n !== "" ? `<span class="count">${n}</span>` : ""}</button>`).join("")}</div>
      <div data-panel="overview" ${tab === "overview" ? "" : "hidden"}>${overviewTab(a)}</div>
      <div data-panel="findings" ${tab === "findings" ? "" : "hidden"}>${findingsTab(a, measured, aiF)}</div>
      <div data-panel="journey" ${tab === "journey" ? "" : "hidden"}>${journeyTab(a)}</div>
      <div data-panel="customers" ${tab === "customers" ? "" : "hidden"}>${customersTab(a)}</div>
      <div data-panel="evidence" ${tab === "evidence" ? "" : "hidden"}>${evidenceTab(a)}</div>
      <div data-panel="data" ${tab === "data" ? "" : "hidden"}>${dataTab(a)}</div></div>
  </div>`;
  animateRings(view);

  $$("[data-tab]", view).forEach((b) => b.addEventListener("click", () => {
    $$("[data-tab]", view).forEach((x) => x.classList.toggle("active", x === b));
    $$("[data-panel]", view).forEach((p) => (p.hidden = p.dataset.panel !== b.dataset.tab));
    if (b.dataset.tab === "journey") loadLog(view, a.id);
  }));
  if (tab === "journey") loadLog(view, a.id);
  const applyFilter = () => {
    const cat = $("#f-cat", view)?.value, sev = $("#f-sev", view)?.value, st = $("#f-st", view)?.value;
    let n = 0;
    $$(".finding[data-src=measured]", view).forEach((el) => {
      const show = (!cat || el.dataset.cat === cat) && (!sev || el.dataset.sev === sev) && (!st || el.dataset.st === st);
      el.hidden = !show; n += show ? 1 : 0;
    });
    const c = $("#f-count", view); if (c) c.textContent = t("find.shown", { n });
  };
  $$(".filters select", view).forEach((s) => s.addEventListener("change", applyFilter));
  bindStatusSelects(view);
  $("#meth", view).onclick = () => methodology();
  $("#del").onclick = () => del(a.id);
  $("#pdf").onclick = () => toast(t("report.pdfPreparing"), "info");
  $("#rerun").onclick = async () => {
    if (!confirm(t("report.confirmRerun"))) return;
    try { const n = await api("/api/audits", { method: "POST", body: JSON.stringify({ url: a.start_url, confirm_permission: true }) }); location.hash = `#/audits/${n.id}`; }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };
  const runAi = $("#run-ai");
  if (runAi) runAi.onclick = async () => {
    runAi.disabled = true;
    try { await api(`/api/audits/${a.id}/analyze`, { method: "POST" }); toast(t("ai.running"), "info"); location.reload(); }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); runAi.disabled = false; }
  };
  if (focus) { const el = view.querySelector(`[data-fid="${focus}"]`); if (el) { /** @type {any} */ (el).open = true; el.scrollIntoView({ block: "center" }); } }
}

/** @param {any} a */
function aiNotice(a) {
  const s = a.ai.status;
  if (s === "running" || s === "pending") return `<div class="notice notice-ai"><span class="spinner"></span><span>${t("ai.running")}</span></div>`;
  if (s === "not_configured") return `<div class="notice"><span class="ico">i</span><span>${t("ai.not_configured")}</span></div>`;
  if (s === "quota_exceeded") return `<div class="notice notice-warn"><span class="ico">!</span><span>${t("ai.quota_exceeded")}</span></div>`;
  if (s === "failed") return `<div class="notice notice-error"><span class="ico">!</span><span>${t("ai.failed")} ${esc(a.ai.analysis_error || "")}</span></div>`;
  if (s === "partial") return `<div class="notice notice-warn"><span class="ico">!</span><span>${t("ai.partial")}</span></div>`;
  return "";
}

function methodology() {
  api("/api/methodology").then((m) => openModal(`<h3>${t("meth.title")}</h3>
    <p class="small" style="margin-bottom:10px">${t("meth.p1")}</p>
    <div class="row" style="margin-bottom:12px">${["critical", "high", "medium", "low"].map((s) => `${sevBadge(/** @type {any} */ (s))} <span class="num small">−${m.penalty[s]}</span>`).join(" ")}</div>
    <table class="data"><tr><th></th><th>${t("meth.weight")}</th></tr>${Object.entries(CATEGORIES).map(([k, v]) => `<tr><td>${esc(v)}</td><td class="num">${m.weights[k]}%</td></tr>`).join("")}</table>
    <p class="small" style="margin-top:12px">${t("meth.p2")}</p><p class="small" style="margin-top:8px">${t("meth.p3", { cap: m.critical_cap })}</p>
    <p class="small" style="margin-top:8px">${t("meth.p4")}</p><p class="tiny muted" style="margin-top:10px">v${esc(m.version)}</p>`));
}

/** @param {HTMLElement} view */
function bindStatusSelects(view) {
  $$("[data-status-for]", view).forEach((sel) => sel.addEventListener("change", async () => {
    const card = sel.closest(".finding");
    try {
      await api(`/api/findings/${sel.dataset.statusFor}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) });
      card.dataset.st = sel.value; card.classList.toggle("done", sel.value === "done");
      toast(t("tasks.moved", { s: t("fstatus." + sel.value) }));
    } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  }));
}

/** @param {any} a */
function overviewTab(a) {
  const an = a.ai.analysis;
  const plan = an?.action_plan?.length ? an.action_plan : a.action_plan_rules;
  const c = a.comparison;
  return `<div class="stack">
    ${an ? `<div class="grid g-main"><div class="card"><div class="card-head"><h3>${t("ai.summary")}</h3>${srcBadge("ai")}</div>
        <p style="white-space:pre-line">${esc(an.executive_summary)}</p><div class="divider"></div>
        <h5 class="small muted" style="margin-bottom:4px">${t("ai.readiness")}</h5><p>${esc(an.conversion_readiness)}</p></div>
      <div class="card"><div class="card-head"><h3>${t("ai.strengths")}</h3>${srcBadge("ai")}</div>
        <ul style="margin:0;padding-inline-start:18px">${(an.top_strengths || []).map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ul></div></div>` : ""}
    <div class="card"><div class="card-head"><div><h3>${t("ai.plan")}</h3><div class="card-sub">${an ? t("ai.planAi") : t("ai.planRules")}</div></div>${an ? srcBadge("ai") : srcBadge("measured")}</div>
      <div class="list">${plan.map((/** @type {any} */ p) => `<div class="list-item" style="align-items:flex-start"><div class="mini-score">${p.priority}</div>
        <div class="list-main"><div style="font-weight:600">${esc(p.title)}</div><div class="small muted" style="margin-top:2px">${esc(p.why_first || "")}</div>
        ${p.first_step ? `<div class="small" style="margin-top:4px">→ ${esc(p.first_step)}</div>` : ""}
        ${p.expected_effect ? `<div class="small" style="margin-top:4px">→ ${esc(p.expected_effect)}</div>` : ""}</div>
        ${p.effort ? `<span class="badge outline">${t("ai.effort")}: ${esc(p.effort)}</span>` : ""}</div>`).join("") || `<div class="empty">${t("find.none")}</div>`}</div></div>
    ${an?.copy_suggestions?.length ? `<div class="card"><div class="card-head"><h3>${t("ai.copy")}</h3>${srcBadge("ai")}</div><div class="stack-sm">
      ${an.copy_suggestions.map((/** @type {any} */ s) => `<div class="box"><span class="badge outline">${esc(s.area)}</span>
        ${s.current_text ? `<p class="small muted" style="margin-top:8px">${t("ai.current")}: “${esc(s.current_text)}”</p>` : ""}
        <p style="margin-top:6px"><strong>${t("ai.suggested")}:</strong> “${esc(s.suggested_text)}”</p><p class="small muted" style="margin-top:4px">${esc(s.rationale)}</p></div>`).join("")}</div></div>` : ""}
    <div class="card"><div class="card-head"><div><h3>${t("cmp.title")}</h3><div class="card-sub">${t("cmp.sub")}</div></div>${c ? srcBadge("measured") : ""}</div>
      ${c ? `<div class="row" style="margin-bottom:14px;gap:22px"><div><div class="tiny muted">${t("cmp.before")}</div><div class="kpi-num">${c.before.score ?? "—"}</div></div>
          <div><div class="tiny muted">${t("cmp.after")}</div><div class="kpi-num">${c.after.score ?? "—"} ${delta(c.score_delta)}</div></div>
          <span class="spacer"></span><span class="small">✓ ${c.fixed.length} ${t("cmp.fixed")} · ✕ ${c.new.length} ${t("cmp.new")} · ${c.persisting.length} ${t("cmp.persisting")}</span></div>
        ${compareBars(c)}
        ${c.fixed.length ? `<div class="divider"></div>${c.fixed.map((/** @type {any} */ f) => `<div class="small" style="color:var(--good-text)">✓ ${esc(f.title)}</div>`).join("")}` : ""}
        ${c.new.length ? `<div style="margin-top:6px">${c.new.map((/** @type {any} */ f) => `<div class="small" style="color:var(--critical-text)">✕ ${esc(f.title)}</div>`).join("")}</div>` : ""}
        ${an?.comparison_notes ? `<div class="box" style="margin-top:12px"><div class="row" style="margin-bottom:4px"><strong class="small">${t("ai.comparison")}</strong>${srcBadge("ai")}</div><p class="small">${esc(an.comparison_notes)}</p></div>` : ""}`
        : `<p class="muted small">${t("cmp.none")}</p>`}</div>
  </div>`;
}

/** @param {any} a @param {any[]} measured @param {any[]} aiF */
function findingsTab(a, measured, aiF) {
  const cats = [...new Set(measured.map((f) => f.category))];
  const note = lang === "en" ? `<div class="notice" style="margin-bottom:12px"><span class="ico">i</span><span>${t("lang.contentNote")}</span></div>` : "";
  return `${note}<div class="row filters" style="margin-bottom:12px">
      <select class="input" id="f-cat" aria-label="section"><option value="">${t("find.allCats")}</option>${cats.map((c) => `<option value="${c}">${esc(CATEGORIES[c] || c)}</option>`).join("")}</select>
      <select class="input" id="f-sev" aria-label="severity"><option value="">${t("find.allSev")}</option>${["critical", "high", "medium", "low"].map((s) => `<option value="${s}">${t("sev." + s)}</option>`).join("")}</select>
      <select class="input" id="f-st" aria-label="status"><option value="">${t("find.allStatus")}</option>${["open", "in_progress", "done", "dismissed"].map((k) => `<option value="${k}">${t("fstatus." + k)}</option>`).join("")}</select>
      <span class="muted small" id="f-count">${t("find.shown", { n: measured.length })}</span></div>
    ${measured.map((f) => findingCard(f)).join("") || `<div class="card empty">${t("find.none")}</div>`}
    ${aiF.length ? `<div class="row" style="margin:26px 0 10px"><h3 style="font-size:15px">${t("report.aiFindings")}</h3>${srcBadge("ai")}</div>
      <div class="notice notice-ai" style="margin-bottom:10px"><span class="ico">✦</span><span>${t("ai.hypothesesNote")}</span></div>
      ${aiF.map((f) => findingCard(f)).join("")}` : ""}`;
}

/** @param {any} f @param {string} [extraMeta] */
export function findingCard(f, extraMeta = "") {
  const shot = f.evidence?.screenshot_id;
  const isAi = f.source === "ai";
  return `<details class="finding ${f.status === "done" ? "done" : ""}" data-fid="${f.id}" data-src="${f.source}" data-cat="${f.category}" data-sev="${f.severity}" data-st="${f.status}">
    <summary>${icon("chevron", "chev")}<div style="flex:1;min-width:0"><div class="finding-title">${esc(f.title)}</div>
      <div class="finding-meta">${sevBadge(f.severity)}${srcBadge(f.source)}<span class="badge outline">${esc(CATEGORIES[f.category] || f.category)}</span>
        ${isAi ? `<span class="tiny muted">${t("conf." + f.evidence.confidence)}</span>` : `<span class="tiny muted">${t("impact." + f.impact)}</span>`}${extraMeta}</div></div></summary>
    <div class="finding-body"><div>
      <h5>${t("find.what")}</h5><p>${esc(f.detail)}</p>
      <h5>${t("find.why")}</h5><p>${esc(f.why_it_matters)}</p>
      <h5>${t("find.impact")}</h5><p>${t("impact." + f.impact)} <span class="tiny muted">${t("find.impactNote")}</span></p>
      <h5>${t("find.fix")}</h5><ol>${f.fix_steps.map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ol>
      ${isAi && f.evidence.refs?.length ? `<h5>${t("find.refs")}</h5><div class="row">${f.evidence.refs.map((/** @type {string} */ r) => `<span class="badge outline ltr">${esc(r)}</span>`).join("")}</div>` : ""}
      <div class="row" style="margin-top:14px"><label class="small muted" for="st-${f.id}">${t("find.status")}:</label>
        <select class="input" id="st-${f.id}" data-status-for="${f.id}">${["open", "in_progress", "done", "dismissed"].map((k) => `<option value="${k}" ${k === f.status ? "selected" : ""}>${t("fstatus." + k)}</option>`).join("")}</select></div>
    </div><div>${shot ? `<h5>${t("find.evidence")}</h5>${evidenceThumb(shot, f.title)}<p class="tiny muted" style="margin-top:6px">${t("find.afterNote")}</p>` : ""}
      ${f.evidence?.page_url ? `<p class="tiny" style="margin-top:8px;overflow-wrap:anywhere"><a class="ltr" href="${esc(f.evidence.page_url)}" target="_blank" rel="noopener noreferrer">${esc(f.evidence.page_url)}</a></p>` : ""}</div>
    </div></details>`;
}

/** @param {any} a */
function journeyTab(a) {
  return `<div class="grid g-main"><div class="card"><div class="card-head"><div><h3>${t("journey.title")}</h3><div class="card-sub">${t("journey.sub")}</div></div>${srcBadge("measured")}</div>
    <div class="timeline">${a.steps.map((/** @type {any} */ s) => `<div class="tl-step"><div class="tl-icon st-${s.status}">${/** @type {any} */ (STEP_ICON)[s.status]}</div>
      <div><div class="row"><span class="tl-title">${esc(s.title)}</span>${stepBadge(s.status)}${s.duration_ms ? `<span class="tiny muted num">${(s.duration_ms / 1000).toFixed(1)}${t("common.seconds")}</span>` : ""}</div>
        <div class="tl-detail">${esc(s.detail)}</div>${s.page_url ? `<div class="tiny feed-url ltr">${esc(s.page_url)}</div>` : ""}</div>
      ${s.screenshot_id ? `<button class="tl-shot" data-shot="${s.screenshot_id}" data-caption="${esc(s.title)}"><img src="/api/screenshots/${s.screenshot_id}" alt="${esc(s.title)}" loading="lazy"></button>` : "<span></span>"}</div>`).join("")}</div></div>
    <div class="card"><div class="card-head"><h3>${t("journey.log")}</h3><span class="tiny muted" id="log-count"></span></div><div class="feed" id="log"><div class="skeleton" style="height:200px"></div></div></div></div>`;
}

/** @param {HTMLElement} view @param {string} id */
async function loadLog(view, id) {
  const box = /** @type {HTMLElement|null} */ (view.querySelector("#log"));
  if (!box || box.dataset.loaded) return;
  box.dataset.loaded = "1";
  const ev = await api(`/api/audits/${id}/events`);
  const t0 = ev.events.length ? new Date(ev.events[0].at).getTime() : 0;
  box.innerHTML = ev.events.map((/** @type {any} */ e) => feedItem(e, t0)).join("");
  /** @type {HTMLElement} */ (view.querySelector("#log-count")).textContent = String(ev.events.length);
}

/** @param {any} a */
function customersTab(a) {
  const ai = a.ai.personas.filter((/** @type {any} */ p) => p.result);
  const list = (/** @type {string} */ title, /** @type {string[]} */ items, /** @type {string} */ q) => items?.length
    ? `<h5>${title}</h5><ul>${items.map((x) => `<li><span class="q">${q}</span><span>${esc(x)}</span></li>`).join("")}</ul>` : "";
  return `<div class="stack">
    <div><div class="row" style="margin-bottom:10px"><h3 style="font-size:15px">${t("cust.aiTitle")}</h3>${srcBadge("simulation")}${srcBadge("ai")}</div>
      <div class="notice notice-sim" style="margin-bottom:12px"><span class="ico">🧪</span><span>${t("cust.aiNote")}</span></div>
      ${ai.length ? `<div class="personas">${ai.map((/** @type {any} */ p) => { const r = p.result; return `<div class="persona">
        <div class="persona-head"><span class="persona-avatar">${/** @type {any} */ (PERSONA_EMOJI)[p.key] || "👤"}</span><h4>${esc(p.name)}</h4><span class="spacer"></span>
          <span class="badge ${/** @type {any} */ (VERDICT_CLS)[r.verdict]}">${t("verdict." + r.verdict)}</span></div>
        <p>${esc(r.verdict_reason)}</p>
        <h5>${t("cust.understood")}</h5><p style="margin-top:0">${esc(r.understood)}</p>
        ${list(t("cust.attention"), r.caught_attention, "★")}${list(t("cust.confusing"), r.confusing, "?")}${list(t("cust.distrust"), r.distrust, "✕")}
        ${list(t("cust.issues"), r.purchase_issues, "✕")}${list(t("cust.improve"), r.improvements, "→")}</div>`; }).join("")}</div>`
        : `<div class="notice"><span class="ico">i</span><span>${a.ai.status === "running" ? t("ai.running") : t("cust.noAi")}</span></div>`}</div>
    <div><div class="row" style="margin-bottom:10px"><h3 style="font-size:15px">${t("cust.rulesTitle")}</h3>${srcBadge("simulation")}</div>
      <p class="small muted" style="margin-bottom:10px">${t("cust.rulesNote")}</p>
      <div class="personas">${a.personas.map((/** @type {any} */ p) => { const m = /** @type {any} */ (RULE_PERSONA)[p.persona] || ["👤", p.persona, p.persona]; return `<div class="persona">
        <div class="persona-head"><span class="persona-avatar">${m[0]}</span><h4>${lang === "en" ? m[1] : m[2]}</h4><span class="spacer"></span>
          <span class="badge ${/** @type {any} */ (VERDICT_CLS)[p.verdict]}">${t("verdict." + p.verdict)}</span></div>
        <ul style="margin-top:8px">${p.blockers.map((/** @type {string} */ b) => `<li><span class="q">✕</span><span>${esc(b)}</span></li>`).join("")}
        ${p.positives.map((/** @type {string} */ b) => `<li style="color:var(--good-text)"><span class="q">✓</span><span>${esc(b)}</span></li>`).join("")}</ul></div>`; }).join("")}</div></div>
  </div>`;
}

/** @param {any} a */
function evidenceTab(a) {
  const LABELS = { home: "phase.home", product: "phase.product", "after-add-to-cart": "phase.add_to_cart", cart: "phase.cart", checkout: "phase.checkout", search: "phase.search" };
  const group = (/** @type {string} */ dev) => a.screenshots.filter((/** @type {any} */ s) => s.device === dev);
  const block = (/** @type {string} */ dev) => group(dev).length ? `<div><h3 style="font-size:14px;margin-bottom:10px">${t("evidence." + dev)}</h3><div class="gallery">${group(dev).map((/** @type {any} */ s) =>
    evidenceThumb(s.id, `${t(/** @type {any} */ (LABELS)[s.label] || s.label)} · ${t("evidence." + dev)}`, dev === "mobile")).join("")}</div></div>` : "";
  return `<div class="card stack">${block("desktop")}${block("mobile")}</div>`;
}

/** @param {any} a */
function dataTab(a) {
  const f = a.facts || {}, h = f.home || {}, m = f.mobile || {}, p = f.product, ck = f.checkout || {}, links = f.links || {};
  const yes = (/** @type {any} */ b) => (b ? t("common.yes") : t("common.no"));
  const rows = [
    ["TTFB", h.timing ? `${h.timing.ttfb}ms` : "—"], ["LCP (desktop)", h.timing ? `${h.timing.lcp}ms` : "—"], ["CLS", h.timing?.cls ?? "—"],
    ["Mobile load", m.load_ms ? `${m.load_ms}ms` : "—"], ["Resources", h.resources ?? "—"], ["Transfer", h.transfer_kb != null ? `${h.transfer_kb}KB` : "—"],
    ["HTTPS", yes(f.https)], ["Mobile horizontal scroll", yes(m.horizontal_overflow)],
    ["Add-to-cart above the fold (mobile)", m.atc_above_fold == null ? t("common.notTested") : yes(m.atc_above_fold)],
    ["Product page", p ? p.url : t("common.notTested")], ["Price visible", p ? yes(p.price_visible) : "—"], ["Product images", p ? p.large_images : "—"],
    ["Reviews", p ? yes(p.mentions_reviews) : "—"], ["Checkout fields", ck.fields ?? "—"], ["Login required", ck.reached ? yes(ck.login_required) : "—"],
    ["Payment methods", ck.payment_methods?.join(", ") || "—"], ["Links checked / broken", links.checked != null ? `${links.checked} / ${links.broken.length}` : "—"],
    ["Analytics", h.html?.tracking_tools?.join(", ") || "—"], ["Platform", h.html?.platform?.join(", ") || "—"],
    ["JavaScript errors", (f.js_errors || []).length], ["Pages visited", f.navigations ?? "—"],
    ["Unreachable resources (network)", (f.unreachable_resources || []).length],
  ];
  return `<div class="card"><div class="card-head"><h3>${t("report.tab.data")}</h3>${srcBadge("measured")}</div><div class="table-wrap">
    <table class="data"><tbody>${rows.map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td class="ltr" style="overflow-wrap:anywhere">${esc(v)}</td></tr>`).join("")}</tbody></table></div></div>`;
}
