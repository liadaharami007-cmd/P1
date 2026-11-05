import { setTitle } from "../app.js";
import {
  api, categoryBars, CATEGORIES, esc, evidenceThumb, fmtDate, FINDING_STATUS, gradeLabel, hostOf, icon, IMPACT,
  PERSONAS, scoreRing, sevBadge, srcBadge, stepBadge, STEP_STATUS, toast, VERDICT,
} from "../ui.js";

const PROGRESS_KEYS = [
  ["home", "טעינת עמוד הבית"], ["product", "חיפוש עמוד מוצר"], ["add_to_cart", "הוספה לסל"], ["cart", "בדיקת העגלה"],
  ["checkout", "כניסה לקופה"], ["search", "בדיקת חיפוש"], ["mobile", "בדיקה בטלפון"], ["analyze", "ניתוח וסימולציית לקוחות"],
];

export async function auditView(view, { id }) {
  let timer = null, alive = true;
  const load = async () => {
    const a = await api(`/api/audits/${id}`);
    if (!alive) return;
    if (a.status === "queued" || a.status === "running") {
      renderProgress(view, a);
      timer = setTimeout(load, 1500);
    } else if (a.status === "failed") renderFailed(view, a);
    else renderReport(view, a);
  };
  await load();
  return () => { alive = false; clearTimeout(timer); };
}

function renderProgress(view, a) {
  setTitle(`בודק את ${hostOf(a.start_url)}…`);
  const seen = new Set((a.progress || []).map((p) => p.key));
  const current = a.progress?.length ? a.progress[a.progress.length - 1].key : null;
  view.innerHTML = `<div class="card" style="max-width:720px">
    <div class="card-head"><div><h2>${a.status === "queued" ? "הבדיקה ממתינה בתור" : "דפדפן אמיתי גולש עכשיו באתר"}</h2>
      <div class="card-sub ltr">${esc(a.start_url)}</div></div></div>
    <div class="pulse-bar"></div>
    <div class="progress-steps">${PROGRESS_KEYS.map(([k, label]) => {
      const done = seen.has(k) && k !== current;
      const now = k === current;
      return `<div class="progress-step" style="${!seen.has(k) ? "color:var(--muted)" : ""}">
        ${done ? '<span class="check-ico">✓</span>' : now ? '<span class="spinner"></span>' : '<span class="check-ico" style="background:var(--surface-3)"></span>'}
        ${label}${now ? ` — <span class="muted">${esc(a.progress[a.progress.length - 1].message)}</span>` : ""}</div>`;
    }).join("")}</div>
    <p class="small muted" style="margin-top:18px">הבדיקה לא ממלאת פרטים אישיים ולא מבצעת הזמנה. אפשר לעזוב את העמוד — היא ממשיכה לרוץ ברקע.</p></div>`;
}

function renderFailed(view, a) {
  setTitle(`הבדיקה נכשלה`);
  view.innerHTML = `<div class="card" style="max-width:720px"><div class="notice notice-error"><div>
    <strong>הבדיקה של <span class="ltr">${esc(a.start_url)}</span> לא הושלמה</strong><br>${esc(a.error || "שגיאה לא ידועה")}</div></div>
    <div class="row" style="margin-top:16px"><a class="btn" href="#/audits">חזרה לבדיקות</a>
    <button class="btn btn-ghost" id="del">${icon("trash")} מחיקה</button></div></div>`;
  view.querySelector("#del").onclick = () => del(a.id);
}

async function del(id) {
  if (!confirm("למחוק את הבדיקה וכל צילומי המסך שלה?")) return;
  await api(`/api/audits/${id}`, { method: "DELETE" });
  location.hash = "#/audits";
}

function renderReport(view, a) {
  const host = a.site_name || hostOf(a.site_url);
  setTitle(host, `<button class="btn btn-sm" id="rerun">${icon("refresh")}<span class="btn-label">בדיקה חוזרת</span></button>
    <button class="btn btn-sm btn-ghost" id="del" aria-label="מחיקת הבדיקה">${icon("trash")}</button>`);
  const f = a.findings, facts = a.facts || {};
  const counts = { all: f.length };
  const passed = a.steps.filter((s) => s.status === "passed").length;
  const tested = a.steps.filter((s) => s.status !== "skipped").length;
  const focus = new URLSearchParams(location.hash.split("?")[1] || "").get("f");

  view.innerHTML = `<div class="stack">
    <div class="grid grid-main">
      <div class="card"><div class="row" style="gap:28px;align-items:center">
        <div class="score-block" style="text-align:center">${scoreRing(a.score, 140)}<div style="margin-top:8px">${gradeLabel(a.score)}</div></div>
        <div style="flex:1;min-width:240px">${categoryBars(a.category_scores)}</div></div></div>
      <div class="card"><h3 style="font-size:16px;margin-bottom:10px">סיכום הבדיקה</h3>
        <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="kpi"><div class="kpi-num">${f.length}</div><div class="kpi-label">ממצאים</div></div>
          <div class="kpi"><div class="kpi-num">${passed}/${tested}</div><div class="kpi-label">שלבים שעברו</div></div>
          <div class="kpi"><div class="kpi-num">${fmtMs(facts.home?.timing?.lcp || facts.home?.load_ms)}</div><div class="kpi-label">הופעת תוכן (מחשב)</div></div>
          <div class="kpi"><div class="kpi-num">${a.screenshots.length}</div><div class="kpi-label">צילומי מסך</div></div>
        </div>
        <p class="small muted" style="margin:12px 0 0">נבדק ב-${fmtDate(a.finished_at)} · <a class="ltr" href="${esc(a.start_url)}" target="_blank" rel="noopener">${esc(a.start_url)}</a></p></div>
    </div>
    <div class="legend"><span>מקור כל מידע מסומן:</span>${srcBadge("measured")}${srcBadge("simulation")}
      <span class="badge src-store_data" style="opacity:.55">${"נתוני חנות"} — לא מחובר</span><span class="badge src-ai" style="opacity:.55">השערת AI — לא מחובר</span></div>
    <div>
      <div class="tabs" role="tablist">
        <button class="active" data-tab="findings">ממצאים ותיקונים<span class="count">${f.length}</span></button>
        <button data-tab="journey">מסע רכישה<span class="count">${passed}/${tested}</span></button>
        <button data-tab="personas">לקוחות מדומים</button>
        <button data-tab="shots">צילומי מסך<span class="count">${a.screenshots.length}</span></button>
        <button data-tab="data">נתונים גולמיים</button>
      </div>
      <div id="tab-findings">${findingsTab(a)}</div>
      <div id="tab-journey" hidden>${journeyTab(a)}</div>
      <div id="tab-personas" hidden>${personasTab(a)}</div>
      <div id="tab-shots" hidden>${shotsTab(a)}</div>
      <div id="tab-data" hidden>${dataTab(a)}</div>
    </div></div>`;

  view.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    view.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("active", x === b));
    ["findings", "journey", "personas", "shots", "data"].forEach((t) => (view.querySelector(`#tab-${t}`).hidden = t !== b.dataset.tab));
  }));
  // סינון ממצאים
  const applyFilter = () => {
    const cat = view.querySelector("#f-cat").value, sev = view.querySelector("#f-sev").value, st = view.querySelector("#f-st").value;
    let n = 0;
    view.querySelectorAll(".finding").forEach((el) => {
      const show = (!cat || el.dataset.cat === cat) && (!sev || el.dataset.sev === sev) && (!st || el.dataset.st === st);
      el.hidden = !show; n += show;
    });
    view.querySelector("#f-count").textContent = `${n} מוצגים`;
  };
  view.querySelectorAll(".filters select").forEach((s) => s.addEventListener("change", applyFilter));
  // שינוי סטטוס משימה
  view.querySelectorAll("[data-status-for]").forEach((sel) => sel.addEventListener("change", async () => {
    const card = sel.closest(".finding");
    try {
      await api(`/api/findings/${sel.dataset.statusFor}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) });
      card.dataset.st = sel.value; card.classList.toggle("done", sel.value === "done");
      toast(`הסטטוס עודכן: ${FINDING_STATUS[sel.value]}`);
    } catch (e) { toast(e.message); }
  }));
  view.querySelector("#del")?.addEventListener("click", () => del(a.id));
  document.querySelector("#rerun")?.addEventListener("click", async () => {
    if (!confirm("להריץ בדיקה חוזרת? הדפדפן ייכנס שוב לאתר, יוסיף מוצר לסל ויגיע לקופה — בלי למלא פרטים ובלי הזמנה.")) return;
    const n = await api("/api/audits", { method: "POST", body: JSON.stringify({ url: a.start_url, confirm_permission: true }) });
    location.hash = `#/audits/${n.id}`;
  });
  if (focus) {
    const el = view.querySelector(`[data-fid="${focus}"]`);
    if (el) { el.open = true; el.scrollIntoView({ block: "center" }); }
  }
}

function fmtMs(ms) {
  if (!ms) return "—";
  return ms < 1000 ? `${ms}<small style="font-size:14px"> ms</small>` : `${(ms / 1000).toFixed(1)}<small style="font-size:14px"> שנ'</small>`;
}

function findingsTab(a) {
  if (!a.findings.length) return `<div class="card empty"><h3>לא נמצאו בעיות בבדיקות האוטומטיות</h3><p>זה לא אומר שאין מה לשפר — רק שהבדיקות הנוכחיות לא מצאו.</p></div>`;
  const cats = [...new Set(a.findings.map((f) => f.category))];
  return `<div class="row filters" style="margin-bottom:14px">
      <select class="input" id="f-cat" style="width:auto" aria-label="סינון לפי קטגוריה"><option value="">כל הקטגוריות</option>${cats.map((c) => `<option value="${c}">${CATEGORIES[c]}</option>`).join("")}</select>
      <select class="input" id="f-sev" style="width:auto" aria-label="סינון לפי חומרה"><option value="">כל רמות החומרה</option>${["critical", "high", "medium", "low"].map((s) => `<option value="${s}">${({ critical: "קריטי", high: "חמור", medium: "בינוני", low: "נמוך" })[s]}</option>`).join("")}</select>
      <select class="input" id="f-st" style="width:auto" aria-label="סינון לפי סטטוס"><option value="">כל הסטטוסים</option>${Object.entries(FINDING_STATUS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      <span class="muted small" id="f-count">${a.findings.length} מוצגים</span></div>
    ${a.findings.map((f) => findingCard(f)).join("")}`;
}

export function findingCard(f, extraMeta = "") {
  const shot = f.evidence?.screenshot_id;
  return `<details class="finding ${f.status === "done" ? "done" : ""}" data-fid="${f.id}" data-cat="${f.category}" data-sev="${f.severity}" data-st="${f.status}">
    <summary>${icon("chevron", "chev")}<div style="flex:1;min-width:0"><div class="finding-title">${esc(f.title)}</div>
      <div class="finding-meta">${sevBadge(f.severity)}${srcBadge(f.source)}<span class="badge badge-outline">${CATEGORIES[f.category]}</span>${extraMeta}</div></div></summary>
    <div class="finding-body"><div>
      <h5>מה מצאנו</h5><p>${esc(f.detail)}</p>
      <h5>למה זה פוגע במכירות</h5><p>${esc(f.why_it_matters)}</p>
      <h5>הערכת השפעה</h5><p>${IMPACT[f.impact]} <span class="small muted">(הערכה מקצועית, לא מדידה)</span></p>
      <h5>איך מתקנים</h5><ol>${f.fix_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <div class="row" style="margin-top:14px"><label class="small muted" for="st-${f.id}">סטטוס:</label>
        <select class="input" id="st-${f.id}" data-status-for="${f.id}" style="width:auto">${Object.entries(FINDING_STATUS).map(([k, v]) => `<option value="${k}" ${k === f.status ? "selected" : ""}>${v}</option>`).join("")}</select></div>
    </div><div>${shot ? `<h5>ראיה — "לפני"</h5>${evidenceThumb(shot, "צילום מסך מהבדיקה")}
      <p class="small muted" style="margin-top:6px">"אחרי": תקנו והריצו בדיקה חוזרת — הממצא ייעלם אם התיקון עבד.</p>` : ""}
      ${f.evidence?.page_url ? `<p class="small" style="margin-top:8px;overflow-wrap:anywhere"><a class="ltr" href="${esc(f.evidence.page_url)}" target="_blank" rel="noopener">${esc(f.evidence.page_url)}</a></p>` : ""}</div>
    </div></details>`;
}

function journeyTab(a) {
  return `<div class="card"><div class="card-head"><div><h3>מסע הרכישה כפי שהדפדפן עבר אותו</h3>
    <div class="card-sub">כל שלב בוצע בפועל. המסע נעצר בכניסה לקופה — לא הוזנו פרטים ולא בוצעה הזמנה.</div></div>${srcBadge("measured")}</div>
    <div class="timeline">${a.steps.map((s) => `<div class="tl-step">
      <div class="tl-icon st-${s.status}">${STEP_STATUS[s.status].ico}</div>
      <div><div class="row"><span class="tl-title">${esc(s.title)}</span>${stepBadge(s.status)}${s.duration_ms ? `<span class="small muted">${(s.duration_ms / 1000).toFixed(1)} שנ'</span>` : ""}</div>
        <div class="tl-detail">${esc(s.detail)}</div>
        ${s.page_url ? `<div class="small" style="overflow-wrap:anywhere"><a class="ltr" href="${esc(s.page_url)}" target="_blank" rel="noopener">${esc(s.page_url)}</a></div>` : ""}</div>
      ${s.screenshot_id ? `<button class="tl-shot" data-shot="${s.screenshot_id}" data-caption="${esc(s.title)}"><img src="/api/screenshots/${s.screenshot_id}" alt="צילום מסך: ${esc(s.title)}" loading="lazy"></button>` : "<span></span>"}
    </div>`).join("")}</div></div>`;
}

function personasTab(a) {
  if (!a.personas.length) return `<div class="card empty">אין תוצאות סימולציה.</div>`;
  return `<div class="notice notice-sim" style="margin-bottom:16px"><span style="font-size:20px">🧪</span><div>
    <strong>זו סימולציה, לא לקוחות אמיתיים.</strong> כל לקוח מדומה הוא רשימת ציפיות קבועה שנבדקה מול מה שהדפדפן מצא בפועל באתר.
    לכן כל הערה כאן מבוססת על עובדה שנמדדה. בהמשך, עם Claude, הלקוחות המדומים יוכלו גם "להסתכל" על צילומי המסך ולהגיב כמו אדם.</div></div>
    <div class="personas">${a.personas.map((p) => {
      const meta = PERSONAS[p.persona], v = VERDICT[p.verdict];
      return `<div class="persona"><div class="persona-head"><div class="persona-avatar">${meta.emoji}</div><h4>${meta.name}</h4>
        <span class="spacer"></span><span class="badge ${v.cls}">${v.ico} ${v.label}</span></div>
        <p class="persona-goal">${meta.goal}</p>
        <ul>${p.blockers.map((b) => `<li><span class="q">✕</span><span>"${esc(b)}"</span></li>`).join("")}
        ${p.positives.map((b) => `<li style="color:var(--good-text)"><span class="q">✓</span><span>${esc(b)}</span></li>`).join("")}
        ${!p.blockers.length && !p.positives.length ? "<li class='muted'>אין הערות</li>" : ""}</ul></div>`;
    }).join("")}</div>`;
}

function shotsTab(a) {
  const LABELS = { home: "עמוד הבית", product: "עמוד מוצר", "after-add-to-cart": "אחרי הוספה לסל", cart: "עגלה", checkout: "קופה", search: "תוצאות חיפוש" };
  const group = (dev) => a.screenshots.filter((s) => s.device === dev);
  const block = (dev, title) => group(dev).length ? `<h3 style="font-size:15px;margin:4px 0 12px">${title}</h3><div class="gallery">${group(dev).map((s) =>
    evidenceThumb(s.id, `${LABELS[s.label] || s.label} · ${dev === "mobile" ? "טלפון" : "מחשב"}`, dev === "mobile")).join("")}</div>` : "";
  return `<div class="card stack">${block("desktop", "מחשב")}${block("mobile", "טלפון (iPhone 13)")}</div>`;
}

function dataTab(a) {
  const f = a.facts || {}, h = f.home || {}, m = f.mobile || {}, p = f.product, ck = f.checkout || {};
  const yes = (b) => (b ? "כן" : "לא");
  const rows = [
    ["זמן תגובת שרת (TTFB)", h.timing ? `${h.timing.ttfb}ms` : "—"],
    ["הופעת התוכן הגדול (LCP) — מחשב", h.timing ? `${h.timing.lcp}ms` : "—"],
    ["תזוזת תוכן (CLS)", h.timing?.cls ?? "—"],
    ["זמן טעינה — טלפון", m.load_ms ? `${m.load_ms}ms` : "—"],
    ["משאבים שנטענו", h.resources ?? "—"],
    ["משקל שנמדד", h.transfer_kb != null ? `${h.transfer_kb}KB` : "—"],
    ["HTTPS", yes(f.https)],
    ["גלילה הצידה בטלפון", yes(m.horizontal_overflow)],
    ["כפתור קנייה במסך הראשון (טלפון)", m.atc_above_fold == null ? "לא נבדק" : yes(m.atc_above_fold)],
    ["עמוד מוצר", p ? p.url : "לא נמצא"],
    ["מחיר מוצג", p ? yes(p.price_visible) : "—"],
    ["תמונות מוצר גדולות", p ? p.large_images : "—"],
    ["ביקורות", p ? yes(p.mentions_reviews) : "—"],
    ["שדות בקופה", ck.fields ?? "—"],
    ["חובת הרשמה", ck.reached ? yes(ck.login_required) : "—"],
    ["אמצעי תשלום שזוהו", ck.payment_methods?.join(", ") || "—"],
    ["כלי מדידה", h.html?.tracking_tools?.join(", ") || "לא זוהו"],
    ["פלטפורמה", h.html?.platform?.join(", ") || "לא זוהתה"],
    ["שגיאות JavaScript", (f.js_errors || []).length],
    ["משאבים שלא נטענו (רשת)", (f.unreachable_resources || []).length],
  ];
  return `<div class="card"><div class="card-head"><h3>כל מה שנמדד</h3>${srcBadge("measured")}</div>
    <table class="data"><tbody>${rows.map(([k, v]) => `<tr><td class="muted">${k}</td><td style="overflow-wrap:anywhere">${esc(v)}</td></tr>`).join("")}</tbody></table>
    ${(f.unreachable_resources || []).length ? `<p class="small muted" style="margin-top:12px">משאבים שלא נטענו עשויים לנבוע מחסימת רשת בסביבת הבדיקה ולא מבעיה באתר, ולכן אינם נחשבים בציון.</p>` : ""}</div>`;
}
