// @ts-check
// Live Mission Control — מצב חי של בדיקה דרך SSE. כל מה שמוצג מגיע ממסד הנתונים (פעולות שבוצעו בפועל).
import { setTitle } from "../app.js";
import { lang, t } from "../i18n.js";
import { $, $$, api, esc, fmtDuration, hostOf, icon, openModal, toast } from "../ui.js";

export const AGENT_META = {
  trust: { emoji: "🛡️", he: "סוכן אמון", en: "Trust Agent" },
  fast_buyer: { emoji: "⚡", he: "קונה מהיר", en: "Fast Buyer" },
  price: { emoji: "🏷️", he: "רגיש למחיר", en: "Price-Sensitive" },
  confused: { emoji: "🤔", he: "קונה מבולבל", en: "Confused Buyer" },
  mobile_ad: { emoji: "📱", he: "הגיע מפרסומת בטלפון", en: "Mobile Ad Visitor" },
};
export const agentName = (/** @type {string} */ k) => (/** @type {any} */ (AGENT_META)[k] || {})[lang] || k;
const PHASES = ["home", "trust", "links", "product", "add_to_cart", "cart", "checkout", "search", "mobile"];
const FEED_ICO = { navigate: "↗", loaded: "•", click: "◉", type: "⌨", select: "☰", screenshot: "▣", scroll: "↓", step_passed: "✓",
  step_failed: "✕", step_warning: "!", step_skipped: "–", error: "!", ai: "✦", info: "i", device: "▯" };

/**
 * @param {HTMLElement} view @param {string} id @param {() => void} onDone
 * @returns {() => void} cleanup
 */
export function missionControl(view, id, onDone) {
  /** @type {any} */ let state = null;
  /** @type {any[]} */ const events = [];
  const seen = new Set();
  let filter = "all";
  /** @type {EventSource|null} */ let es = null;
  /** @type {any} */ let clock = null;
  let ended = false;

  view.innerHTML = `<div class="mc">
    <div class="card mc-head"><div class="row" style="justify-content:space-between;gap:16px">
      <div style="min-width:0"><div class="row"><span class="badge st-running" id="mc-live"><span class="live-dot"></span> ${t("mc.connecting")}</span>
        <h2 class="truncate" id="mc-url" style="font-size:16px"></h2></div>
        <div class="tiny muted" id="mc-status" style="margin-top:4px"></div></div>
      <div class="row" style="gap:22px"><div><div class="tiny muted">${t("live.elapsed")}</div><div class="kpi-num num" id="mc-time">0:00</div></div>
        <div><div class="tiny muted">${t("mc.actions")}</div><div class="kpi-num num" id="mc-actions">0</div></div>
        <button class="btn btn-sm btn-danger" id="mc-stop">${icon("stop")} ${t("mc.stop")}</button></div></div>
      <div class="mc-progress" style="margin-top:14px"><div id="mc-bar"></div></div></div>
    <div class="mc-grid">
      <div class="stack">
        <div class="card"><div class="card-head"><div><h3>${t("mc.core")}</h3><div class="card-sub">${t("mc.coreSub")}</div></div><span class="badge outline" id="core-state"></span></div>
          <div class="phases" id="mc-phases">${PHASES.map((p) => `<span class="phase" data-p="${p}">${t("phase." + p)}</span>`).join("")}<span class="phase" data-p="agents">${t("mc.agents")}</span><span class="phase" data-p="ai">✦ ${t("live.ai")}</span></div>
          <div class="mc-core-shot" id="core-shot"><span class="muted small">${t("live.noShot")}</span></div>
          <div class="tiny muted truncate ltr" id="core-url" style="margin-top:8px"></div></div>
        <div><div class="row" style="margin:4px 0 10px"><h3 style="font-size:14.5px">${t("mc.agents")}</h3><span class="tiny muted">${t("mc.agentsSub")}</span></div>
          <div class="agent-grid" id="agent-grid"></div></div>
      </div>
      <div class="stack">
        <div class="card"><div class="card-head"><h3>${t("mc.feed")}</h3><span class="tiny muted" id="feed-count"></span></div>
          <div class="seg" id="feed-filter" style="margin-bottom:10px"><button class="on" data-f="all">${t("mc.all")}</button><button data-f="core">${t("mc.core")}</button>
            ${Object.keys(AGENT_META).map((k) => `<button data-f="${k}">${/** @type {any} */ (AGENT_META)[k].emoji}</button>`).join("")}</div>
          <div class="feed" id="mc-feed" style="max-height:440px"></div></div>
        <div class="card"><div class="card-head"><h3>${t("mc.errors")}</h3><span class="badge outline" id="err-count">0</span></div>
          <div id="mc-errors" class="stack-sm small"><span class="muted">${t("mc.noErrors")}</span></div></div>
      </div>
    </div></div>`;
  setTitle(t("mc.title"));

  const t0 = () => (state?.started_at ? new Date(state.started_at).getTime() : Date.now());
  clock = setInterval(() => {
    const el = view.querySelector("#mc-time");
    if (!el) { clearInterval(clock); return; }  // המסך הוחלף (למשל לדוח) — עוצרים את השעון
    if (!state?.started_at) return;
    const end = state.finished_at && !(state.agents || []).some((/** @type {any} */ a) => a.status === "running") && state.ai_status !== "running" ? new Date(state.finished_at).getTime() : Date.now();
    el.textContent = fmtDuration(end - t0());
  }, 1000);

  $$("#feed-filter button", view).forEach((b) => b.addEventListener("click", () => {
    filter = b.dataset.f; $$("#feed-filter button", view).forEach((x) => x.classList.toggle("on", x === b)); drawFeed(true);
  }));
  $("#mc-stop", view).onclick = async () => {
    try { await api(`/api/audits/${id}/stop`, { method: "POST" }); toast(t("mc.stopped"), "info"); }
    catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
  };

  const matches = (/** @type {any} */ e) => filter === "all" || (filter === "core" ? !e.agent : e.agent === filter);
  const feedItem = (/** @type {any} */ e) => {
    const sec = Math.max(0, Math.round((new Date(e.at).getTime() - t0()) / 1000));
    const who = e.agent ? `<span class="agent-chip" title="${esc(agentName(e.agent))}">${/** @type {any} */ (AGENT_META)[e.agent]?.emoji || ""}</span>` : "";
    return `<div class="feed-item"><span class="feed-time">+${fmtDuration(sec * 1000)}</span><span class="feed-ico k-${e.kind}">${/** @type {any} */ (FEED_ICO)[e.kind] || "•"}</span>
      <span>${who}${esc(e.message)}${e.page_url && e.kind === "navigate" ? `<span class="feed-url ltr">${esc(e.page_url)}</span>` : ""}</span></div>`;
  };
  const drawFeed = (/** @type {boolean} */ full, /** @type {any[]} */ fresh = []) => {
    const box = $("#mc-feed", view);
    if (full) box.innerHTML = events.filter(matches).slice(-300).map(feedItem).join("");
    else box.insertAdjacentHTML("beforeend", fresh.filter(matches).map(feedItem).join(""));
    box.scrollTop = box.scrollHeight;
    $("#feed-count", view).textContent = String(events.length);
  };

  const drawAgents = () => {
    const grid = $("#agent-grid", view);
    const runs = state.agents || [];
    grid.innerHTML = Object.keys(AGENT_META).map((k) => {
      const r = runs.find((/** @type {any} */ x) => x.agent === k) || { status: state.status === "running" ? "queued" : "skipped", actions: 0 };
      const m = /** @type {any} */ (AGENT_META)[k];
      return `<button class="agent-card s-${r.status}" data-agent="${k}">
        <div class="row" style="justify-content:space-between"><span class="row" style="gap:8px"><span class="agent-emoji">${m.emoji}</span><strong>${m[lang]}</strong></span>
          <span class="badge st-${r.status === "done" ? "passed" : r.status === "running" ? "running" : r.status === "failed" ? "failed" : r.status === "interrupted" ? "warning" : "skipped"}">${r.status === "running" ? '<span class="live-dot"></span>' : ""} ${t("agent.status." + r.status)}</span></div>
        <div class="agent-shot">${r.last_screenshot_id ? `<img src="/api/screenshots/${r.last_screenshot_id}" alt="" loading="lazy">` : `<span class="tiny faint">${m.emoji}</span>`}</div>
        <div class="tiny muted truncate">${t("mc.lastAction")}: <span class="text-2">${esc(r.last_action || "—")}</span></div>
        <div class="tiny faint truncate ltr">${esc(r.current_url || "")}</div>
        <div class="row tiny" style="justify-content:space-between;margin-top:6px"><span class="muted">${t("mc.actions")}: <strong class="num">${r.actions || 0}</strong></span>
          <span class="badge outline tiny">${t("agent.engine.rules")}</span></div></button>`;
    }).join("");
    $$(".agent-card", grid).forEach((c) => c.addEventListener("click", () => openAgentPath(c.dataset.agent)));
  };

  const openAgentPath = (/** @type {string} */ key) => {
    const list = events.filter((e) => e.agent === key);
    const shots = list.filter((e) => e.screenshot_id && e.kind === "screenshot");
    openModal(`<h3>${/** @type {any} */ (AGENT_META)[key].emoji} ${esc(agentName(key))} · ${t("mc.openPath")}</h3>
      ${shots.length ? `<div class="gallery" style="grid-template-columns:repeat(auto-fill,minmax(120px,1fr));margin-bottom:12px">${shots.map((s) =>
        `<button class="evidence" data-shot="${s.screenshot_id}" data-caption="${esc(s.message)}"><img src="/api/screenshots/${s.screenshot_id}" alt=""><span>${esc(s.message.replace(/^[^:]+:\s*/, ""))}</span></button>`).join("")}</div>` : ""}
      <div class="feed" style="max-height:50vh">${list.map(feedItem).join("") || `<span class="muted small">—</span>`}</div>`);
  };

  const apply = (/** @type {any} */ msg) => {
    if (!view.querySelector("#mc-feed")) return;  // המסך כבר לא מוצג
    state = msg;
    const fresh = msg.events.filter((/** @type {any} */ e) => !seen.has(e.id));
    fresh.forEach((/** @type {any} */ e) => { seen.add(e.id); events.push(e); });
    $("#mc-url", view).textContent = hostOf(msg.start_url);
    $("#mc-live", view).innerHTML = msg.status === "running" || msg.ai_status === "running" || (msg.agents || []).some((/** @type {any} */ a) => a.status === "running")
      ? `<span class="live-dot"></span> ${t("mc.live")}` : t("astatus." + (msg.status === "stopped" ? "failed" : msg.status));
    $("#mc-status", view).textContent = msg.status === "queued" ? t("live.queued") : msg.status === "stopped" ? t("mc.stopped") : (msg.progress?.slice(-1)[0]?.message || "");
    $("#mc-actions", view).textContent = String(events.filter((e) => ["navigate", "click", "type", "select", "scroll"].includes(e.kind)).length);
    // שלבים
    const cur = msg.progress?.length ? msg.progress[msg.progress.length - 1].key : null;
    for (const e of fresh) if (e.kind.startsWith("step_") && e.ref && !e.agent) $(`[data-p="${e.ref}"]`, view)?.setAttribute("class", `phase ${e.kind.slice(5)}`);
    $$("#mc-phases .phase", view).forEach((p) => { if (!/passed|failed|warning|skipped/.test(p.className)) p.classList.toggle("active", p.dataset.p === cur); });
    if ((msg.agents || []).length && (msg.agents || []).every((/** @type {any} */ a) => !["running", "queued"].includes(a.status))) $(`[data-p="agents"]`, view).className = "phase passed";
    if (msg.ai_status === "running") $(`[data-p="ai"]`, view).className = "phase active";
    if (["done", "not_configured", "failed", "partial", "quota_exceeded"].includes(msg.ai_status)) $(`[data-p="ai"]`, view).className = `phase ${msg.ai_status === "done" ? "passed" : "skipped"}`;
    // צילום ליבה אחרון
    const coreShot = [...events].reverse().find((e) => !e.agent && e.kind === "screenshot" && e.screenshot_id);
    if (coreShot) {
      const box = $("#core-shot", view);
      if (box.dataset.sid !== String(coreShot.screenshot_id)) { box.dataset.sid = coreShot.screenshot_id;
        box.innerHTML = `<button class="tl-shot" style="width:100%;height:100%" data-shot="${coreShot.screenshot_id}" data-caption="${esc(coreShot.message)}"><img src="/api/screenshots/${coreShot.screenshot_id}" alt=""></button>`; }
      $("#core-url", view).textContent = coreShot.page_url || "";
    }
    $("#core-state", view).textContent = t("astatus." + (msg.status === "stopped" ? "failed" : msg.status));
    // התקדמות: שלבי ליבה + סוכנים + AI
    const doneCore = $$("#mc-phases .phase", view).filter((p) => /passed|failed|warning|skipped/.test(p.className)).length;
    const pct = Math.round((doneCore / (PHASES.length + 2)) * 100);
    $("#mc-bar", view).style.width = `${msg.status === "done" && msg.ai_status !== "running" && msg.ai_status !== "pending" ? 100 : Math.max(4, pct)}%`;
    // שגיאות
    const errs = events.filter((e) => e.kind === "error" || e.kind === "step_failed" || e.kind === "step_warning");
    $("#err-count", view).textContent = String(errs.length);
    if (errs.length) $("#mc-errors", view).innerHTML = errs.slice(-12).reverse().map((e) => `<div class="row row-nw" style="align-items:flex-start;gap:8px">
      <span class="feed-ico k-${e.kind}">${/** @type {any} */ (FEED_ICO)[e.kind]}</span><span>${e.agent ? `<span class="agent-chip">${/** @type {any} */ (AGENT_META)[e.agent]?.emoji}</span>` : ""}${esc(e.message)}</span></div>`).join("");
    drawAgents();
    drawFeed(false, fresh);
    $("#mc-stop", view).hidden = !(msg.status === "running" || msg.status === "queued" || (msg.agents || []).some((/** @type {any} */ a) => a.status === "running"));
  };

  const connect = () => {
    es = new EventSource(`/api/audits/${id}/stream`);
    es.onmessage = (ev) => apply(JSON.parse(ev.data));
    es.addEventListener("end", () => { ended = true; es?.close(); clearInterval(clock); setTimeout(onDone, 600); });
    es.onerror = () => { if (ended) return; $("#mc-live", view).textContent = t("mc.connecting"); };
  };
  connect();
  return () => { es?.close(); clearInterval(clock); };
}
