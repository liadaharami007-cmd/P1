import { setTitle } from "../app.js";
import {
  api, auditForm, bindAuditForm, bindTrend, categoryBars, esc, fmtDate, gradeLabel, hostOf, icon, IMPACT,
  PERSONAS, scoreRing, sevBadge, srcBadge, trendChart, VERDICT, CATEGORIES,
} from "../ui.js";

export async function dashboardView(view, _params, app) {
  const siteId = new URLSearchParams(location.hash.split("?")[1] || "").get("site");
  const d = await api("/api/dashboard" + (siteId ? `?site_id=${siteId}` : ""));
  const browser = app.status.capabilities.browser_audit;

  if (!d.site) {
    setTitle("ברוכים הבאים ל-P1 AI");
    view.innerHTML = `
      <section class="hero">
        <h2>גלו מה עוצר לקוחות מלקנות בחנות שלכם</h2>
        <p>הכניסו את כתובת החנות. P1 נכנס אליה בדפדפן אמיתי — במחשב ובטלפון — מחפש מוצר, מוסיף לסל, מגיע לקופה, ומתעד כל מכשול בצילומי מסך.</p>
        ${auditForm(browser)}
        <div class="hero-points">
          <div class="hero-point"><strong>בדיקה אמיתית</strong>דפדפן Chromium אמיתי עובר את מסע הרכישה המלא.</div>
          <div class="hero-point"><strong>5 לקוחות מדומים</strong>חשדן, מחפש מחיר, מתלבט, ממהר וחוקר — מה הפריע לכל אחד.</div>
          <div class="hero-point"><strong>תוכנית תיקון</strong>כל בעיה עם חומרה, השפעה משוערת וצעדי תיקון ברורים.</div>
        </div>
      </section>`;
    bindAuditForm(view);
    return;
  }

  const L = d.latest;
  setTitle(d.site.name || hostOf(d.site.url),
    `<a class="btn btn-primary btn-sm" href="#/audits">${icon("plus")}<span class="btn-label">בדיקה חדשה</span></a>`);
  const siteSwitch = d.sites.length > 1 ? `<select class="input" id="site-switch" aria-label="בחירת אתר" style="max-width:280px">
      ${d.sites.map((s) => `<option value="${s.id}" ${s.id === d.site.id ? "selected" : ""}>${esc(s.name || hostOf(s.url))}</option>`).join("")}</select>` : "";
  const running = d.running.length ? `<a class="notice notice-info" href="#/audits/${d.running[0].id}" style="text-decoration:none">
      <span class="spinner"></span><span><strong>בדיקה רצה עכשיו</strong> — לחצו לצפייה בהתקדמות</span></a>` : "";
  const open = Object.values(d.severity_counts).reduce((a, b) => a + b, 0);

  view.innerHTML = `
    <div class="stack">
      <div class="row">${siteSwitch}<span class="muted small ltr">${esc(d.site.url)}</span><span class="spacer"></span>
        ${L ? `<span class="legend">${srcBadge("measured")} נתונים מהבדיקה האחרונה · ${fmtDate(L.finished_at)}</span>` : ""}</div>
      ${running}
      ${!L ? `<div class="card empty"><h3>עדיין אין בדיקה שהסתיימה לאתר הזה</h3><p>${d.recent_audits[0]?.status === "failed" ? "הבדיקה האחרונה נכשלה: " + esc(d.recent_audits[0].error || "") : "ממתינים לתוצאות."}</p>
         <a class="btn" href="#/audits">לבדיקות</a></div>` : `
      <div class="grid grid-main">
        <div class="card">
          <div class="card-head"><div><h2>ציון בריאות האתר</h2><div class="card-sub">מחושב רק מבדיקות שבוצעו בפועל</div></div>
            <a class="btn btn-sm" href="#/audits/${L.id}">לדוח המלא</a></div>
          <div class="row" style="gap:32px;align-items:center;flex-wrap:wrap">
            <div class="score-block" style="text-align:center">${scoreRing(L.score)}<div style="margin-top:8px">${gradeLabel(L.score)}</div></div>
            <div style="flex:1;min-width:240px">${categoryBars(L.category_scores)}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><div><h2>בעיות פתוחות</h2><div class="card-sub">מהבדיקה האחרונה</div></div><a class="btn btn-sm btn-ghost" href="#/tasks">למשימות</a></div>
          <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
            ${["critical", "high", "medium", "low"].map((s) => `<div class="kpi"><div class="kpi-num">${d.severity_counts[s]}</div><div class="kpi-label">${sevBadge(s)}</div></div>`).join("")}
          </div>
          <div class="row small muted" style="margin-top:14px">✓ תוקנו: <strong>${d.status_counts.done}</strong> · בטיפול: <strong>${d.status_counts.in_progress}</strong> · פתוחות: <strong>${open}</strong></div>
        </div>
      </div>

      <div class="grid grid-main">
        <div class="card">
          <div class="card-head"><div><h2>הבעיות שהכי פוגעות במכירות</h2><div class="card-sub">מסודר לפי חומרה והשפעה משוערת</div></div></div>
          ${d.top_findings.length ? `<div class="list">${d.top_findings.map((f) => `
            <a class="list-item" href="#/audits/${L.id}?f=${f.id}">
              <div class="list-main"><div class="list-title">${esc(f.title)}</div>
                <div class="finding-meta">${sevBadge(f.severity)}<span class="badge badge-outline">${CATEGORIES[f.category]}</span><span class="small muted">${IMPACT[f.impact]}</span></div></div>
            </a>`).join("")}</div>` : `<div class="empty"><h3>אין בעיות פתוחות 🎉</h3></div>`}
        </div>
        <div class="card">
          <div class="card-head"><div><h2>מגמת ציון</h2><div class="card-sub">לאורך בדיקות שהסתיימו</div></div></div>
          ${d.trend.length >= 2 ? trendChart(d.trend)
            : `<div class="empty small" style="padding:24px 8px">נדרשות לפחות 2 בדיקות כדי להציג מגמה.<br>הריצו בדיקה נוספת אחרי שתתקנו משהו — ותראו כאן אם הציון השתפר.</div>`}
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h2>לקוחות מדומים</h2><div class="card-sub">איך 5 סוגי לקוחות היו מגיבים לאתר</div></div>${srcBadge("simulation")}</div>
        <div class="personas">${d.personas.map((p) => `
          <div class="persona"><div class="persona-head"><div class="persona-avatar">${PERSONAS[p.persona].emoji}</div>
            <h4>${PERSONAS[p.persona].name}</h4><span class="spacer"></span><span class="badge ${VERDICT[p.verdict].cls}">${VERDICT[p.verdict].ico} ${VERDICT[p.verdict].label}</span></div>
            <div class="small muted">${p.blockers.length ? esc(p.blockers[0]) : "לא נתקל במכשולים"}</div></div>`).join("")}</div>
      </div>`}

      <div class="card">
        <div class="card-head"><h2>בדיקות אחרונות</h2><a class="btn btn-sm btn-ghost" href="#/audits">הכול</a></div>
        <div class="list">${d.recent_audits.map(auditRow).join("")}</div>
      </div>
    </div>`;
  if (L) bindTrend(view, d.trend);
  view.querySelector("#site-switch")?.addEventListener("change", (e) => (location.hash = `#/?site=${e.target.value}`));
}

export function auditRow(a) {
  const st = { done: "", running: "רצה…", queued: "בתור…", failed: "נכשלה" }[a.status];
  return `<a class="list-item" href="#/audits/${a.id}">
    <div class="mini-score" style="color:${a.score == null ? "var(--muted)" : "inherit"}">${a.status === "done" ? (a.score ?? "—") : a.status === "failed" ? "✕" : '<span class="spinner"></span>'}</div>
    <div class="list-main"><div class="list-title">${esc(a.site_name || hostOf(a.site_url))}</div>
      <div class="small muted">${fmtDate(a.created_at)}${a.status === "done" ? ` · ${a.finding_count} ממצאים` : ` · ${st}`}${a.status === "failed" && a.error ? " — " + esc(a.error) : ""}</div></div>
    ${a.status === "done" ? gradeLabel(a.score) : ""}</a>`;
}
