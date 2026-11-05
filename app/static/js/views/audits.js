import { setTitle } from "../app.js";
import { api, auditForm, bindAuditForm } from "../ui.js";
import { auditRow } from "./dashboard.js";

export async function auditsView(view, _p, app) {
  setTitle("בדיקות אתר");
  view.innerHTML = `<div class="stack">
    <div class="card"><div class="card-head"><div><h2>בדיקה חדשה</h2>
      <div class="card-sub">דפדפן אמיתי ייכנס לחנות במחשב ובטלפון ויעבור את מסע הרכישה. לוקח בדרך כלל 30–90 שניות.</div></div></div>
      ${auditForm(app.status.capabilities.browser_audit)}</div>
    <div class="card"><div class="card-head"><h2>היסטוריית בדיקות</h2><span class="muted small" id="audit-count"></span></div>
      <div id="audit-list"><div class="skeleton" style="height:120px"></div></div></div>
  </div>`;
  bindAuditForm(view);

  let timer = null, alive = true;
  const refresh = async () => {
    const audits = await api("/api/audits");
    if (!alive) return;
    view.querySelector("#audit-count").textContent = `${audits.length} בדיקות`;
    view.querySelector("#audit-list").innerHTML = audits.length
      ? `<div class="list">${audits.map(auditRow).join("")}</div>` : `<div class="empty">עוד לא בוצעו בדיקות.</div>`;
    // רענון אוטומטי של הרשימה כל עוד יש בדיקה שרצה
    if (audits.some((a) => a.status === "running" || a.status === "queued")) timer = setTimeout(refresh, 3000);
  };
  await refresh();
  return () => { alive = false; clearTimeout(timer); };
}
