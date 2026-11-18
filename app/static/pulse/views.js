// ClientPulse OS — מסכים. כל מסך עונה על שאלה עסקית אחת; כל כפתור קורא ל-API אמיתי.
import { MORE, api, chart, chg, closeModal, demoTag, esc, go, ic, memberName, modal, money, N, pctf, pill, refreshMe, render, SL, st, toast, dayLabel } from './app.js';

const $ = (s, el = document) => el.querySelector(s);
const STATUS = { new: 'חדש', in_progress: 'בטיפול', awaiting_approval: 'ממתין לאישור', done: 'בוצע', awaiting_verification: 'ממתין לבדיקה חוזרת', closed: 'נסגר' };
const FLOW = ['new', 'in_progress', 'awaiting_approval', 'awaiting_verification', 'closed'];
const ACTION = { check: 'בדיקה ותיקון', campaign_change: 'שינוי בקמפיין', budget_change: 'שינוי תקציב', client_message: 'הודעה ללקוח' };
const SENS = new Set(['campaign_change', 'budget_change', 'client_message']);
const HANDLING = { open: 'פתוחה', in_progress: 'בטיפול', resolved: 'נפתרה', cleared: 'חזרה לתקין', dismissed: 'סומנה כשווא' };
const kpi = (label, n, sub, dot, route) => `<${route ? `button data-act="go" data-arg="${route}"` : 'div'} class="kpi"><div class="l">${dot ? `<i class="dot d-${dot}"></i>` : ''}${label}</div><div class="n">${N(n)}</div>${sub ? `<div class="s">${sub}</div>` : ''}</${route ? 'button' : 'div'}>`;
const empty = (t) => `<div class="empty">${t}</div>`;
const healthRing = (h) => `<div class="ring" style="--v:${h ?? 0};--c:var(--${h == null ? 'line2' : h >= 75 ? 'g' : h >= 45 ? 'y' : 'r'})" title="ציון בריאות"><b>${N(h ?? '—')}</b></div>`;
const memberOpts = (sel) => (st.me.team || []).map((m) => `<option value="${esc(m.id)}" ${m.id === sel ? 'selected' : ''}>${esc(m.name)} · ${esc(m.role || '')}</option>`).join('');

export const V = { actions: {} };
const A = V.actions;

// ================================================================ ברוכים הבאים (אין לקוחות)
V.welcome = async (view) => {
  view.innerHTML = `<div class="hello"><div><h2>ברוכים הבאים ל-ClientPulse OS</h2><div class="meta">מערכת ההפעלה של משרד הפרסום: רמזור לקוחות, טיפול, אוטומציות והוכחת ערך — במקום אחד.</div></div></div>
  <div class="grid g2">
    <div class="card pad"><div class="h2">${ic('flask')} התנסות מלאה עם נתוני דמו</div>
      <p class="tx2">50 לקוחות מדומים עם 90 ימי היסטוריה ותרחישים אמיתיים: זינוק בעלות לליד, קמפיין שהפסיק להביא לידים, שחיקה הדרגתית, לקוחות שהשתפרו. הבדיקה, האוטומציות והמשימות רצות באמת — רק הנתונים מדומים, ומסומנים "דמו" בכל מקום.</p>
      <button class="btn acc" data-act="startDemo">${ic('play', 15)} הפעל סביבת דמו</button></div>
    <div class="card pad"><div class="h2">${ic('users')} התחלה עם לקוח אמיתי</div>
      <p class="tx2">הוסיפו לקוח, ייבאו ייצוא יומי מ-Meta Ads Manager או Google Ads (CSV), והמנוע ינתח אותו מיד. חיבור API ישיר דורש הרשאות — ראו חיבורים.</p>
      <button class="btn sec" data-act="addClient">הוספת לקוח</button> <a class="btn sec" href="#/integrations">חיבורים</a></div>
  </div>`;
};
A.startDemo = async (b) => {
  b.disabled = true; b.textContent = 'בונה 50 לקוחות ומריץ בדיקה…';
  try { const r = await api('/api/pulse/demo', { method: 'POST' }); toast(`סביבת הדמו מוכנה: ${r.check.n} לקוחות נותחו, ${r.check.new} חריגות זוהו`); st.clients = null; await refreshMe(); go('home'); }
  catch { b.disabled = false; b.textContent = 'הפעל סביבת דמו'; }
};

// ================================================================ מרכז פיקוד
// ================================================================ מסך הבית: לקוח אחד בכל פעם (מיקוד). הטבלה המלאה ב"כל הרשימה".
V.focus = async (view) => {
  st.skip = st.skip || [];
  const [b, ab] = await Promise.all([api('/api/pulse/brief'), api('/api/pulse/alerts')]);
  const c = b.counts, w = b.week || {}, hour = new Date().getHours(), greet = hour < 12 ? 'בוקר טוב' : hour < 18 ? 'צהריים טובים' : 'ערב טוב';
  const seen = new Set(), queue = [];
  ab.cards.filter((x) => !x.task_id || x.task_status === 'new').sort((x, y) => (x.severity === y.severity ? 0 : x.severity === 'red' ? -1 : 1) || (y.potential_leads || 0) - (x.potential_leads || 0))
    .forEach((x) => { if (!seen.has(x.client_id)) { seen.add(x.client_id); queue.push(x); } });
  const q = queue.filter((x) => !st.skip.includes(x.key)).concat(queue.filter((x) => st.skip.includes(x.key)));
  const f = q[0], nxt = q.slice(1, 4);
  view.innerHTML = `<div class="calm focus">
  <div class="calm-head"><h2>${greet}, ${esc(st.me.user.name)}</h2>
    <div class="counts">${[['red', 'דחוף'], ['yellow', 'במעקב'], ['green', 'תקין']].map(([k, t]) => `<a href="#/queue?s=${k}"><i class="dot d-${k}"></i>${N(c[k])} ${t}</a>`).join('')}</div></div>
  <a class="back" href="#/home?v=plan">‹ חזרה לתוכנית</a>
  <div class="prog"><span><b>${N(w.handled_today || 0)}</b> טיפלת היום</span><span><b>${N(queue.length)}</b> נשארו</span>${b.potential ? `<span>~<b>${N(b.potential.leads_week)}</b> לידים בשבוע אפשר להחזיר</span>` : ''}</div>
  ${f ? `<div class="card fcard"><div class="row" style="gap:10px"><i class="dot d-${f.severity}" style="width:12px;height:12px"></i><span class="note">${f.severity === 'red' ? 'דחוף' : 'במעקב'} · הכי חשוב עכשיו</span></div>
    <h1>${esc(f.client)}</h1>
    <div class="fl"><span class="hk">מה קרה</span><p>${esc(f.what)}</p></div>
    <div class="fl"><span class="hk">מה לעשות</span><p><b>${esc(f.next)}</b></p></div>
    ${f.potential_leads ? `<div class="fl"><span class="hk">כמה זה שווה</span><p>כ-${N(f.potential_leads)} לידים בשבוע <span class="note">(הערכה מהנתונים של הלקוח)</span></p></div>` : ''}
    <div class="fbtn"><button class="btn pri big" data-act="handle" data-arg="${esc(f.key)}|done">טיפלתי ✓</button><button class="btn sec" data-act="handle" data-arg="${esc(f.key)}|start">אני על זה</button>
      <button class="btn sec" data-act="skip" data-arg="${esc(f.key)}">דלג</button><a class="btn sec" href="#/client/${f.client_id}">פרטים מלאים</a></div></div>`
  : `<div class="card fcard done"><h1>הכול מטופל ✓</h1><p class="tx2">לכל לקוח שדורש תשומת לב יש כבר טיפול. המערכת תבדוק בעצמה אם המספרים חוזרים ליעד.</p></div>`}
  ${nxt.length ? `<div class="nextq"><span class="note">הבאים בתור:</span>${nxt.map((x) => `<a href="#/client/${x.client_id}"><i class="dot d-${x.severity}"></i>${esc(x.client)}</a>`).join('')}<a class="note" href="#/queue">כל הרשימה ←</a></div>` : '<a class="note" href="#/queue">כל הרשימה ←</a>'}
  <footer class="proof">השבוע במשרד: ${N(w.detected || 0)} בעיות זוהו · ${N(w.handled || 0)} טופלו · ${N(w.improved || 0)} השתפרו ואומתו בנתונים · נבדקו ${N(b.clients)} חשבונות ב-${N(b.scan_ms)} מ"ש</footer>
  </div>`;
};
// ================================================================ מסך הבית: רמזור קלאסי — שלוש שורות, כל צבע מתקבץ לפי סוג הבעיה
const LIGHT = {
  red: { t: 'דחוף', sub: 'צריכים טיפול עכשיו' },
  yellow: { t: 'במעקב', sub: 'חריגה או מגמה — לבדוק לפני שזה מחמיר' },
  green: { t: 'תקין', sub: 'אפשר לחכות — הזדמנויות להציע ולשפר' },
};
const GROUP = { cpl: 'עלות לליד זינקה', no_leads: 'אין לידים', spend_up: 'הוצאה עלתה בלי לידים', ctr: 'ירידה בהקלקות', cvr: 'ירידה בהמרה',
  trend: 'הידרדרות הדרגתית', goal: 'מעל היעד', data: 'נתונים לא מתעדכנים', no_sales: 'לידים בלי מכירות', commitment: 'התחייבות באיחור',
  contact: 'אין קשר עם הלקוח', satisfaction: 'שביעות רצון נמוכה', budget_headroom: 'תקציב לא מנוצל — אפשר להציע הגדלה',
  scale: 'מתחת ליעד — אפשר לגדול', lead_handling: 'הרבה לידים, מעט מכירות', pricing: 'רווחיות נמוכה', site_check: 'כדאי לבדוק את האתר',
  keep: 'יציבים — לשמור', data_missing: 'חסרים נתונים' };
// ================================================================ פתיחה רגועה: שלום, ושני כפתורים
const kfmt = (x) => (x >= 1000 ? `כ-₪${Math.round(x / 1000).toLocaleString()} אלף` : `₪${Math.round(x)}`);
// ================================================================ מסך הבית — עיצוב מוצר: מד רמזור, מגמות, משימות היום, רשימת לקוחות
const AVC = ['#0E7C86', '#5B5BD6', '#C2410C', '#0F766E', '#7C3AED', '#B45309', '#2563EB', '#BE185D'];
const avatar = (name, i) => `<span class="av2" style="background:${AVC[i % AVC.length]}">${esc((name || '?').trim()[0])}</span>`;
const spark = (vals, color) => {
  const v = (vals || []).filter((x) => x != null); if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v), r_ = hi - lo || 1, W = 84, H = 26;
  const pts = v.map((x, i) => `${(i * W / (v.length - 1)).toFixed(1)},${(H - 3 - (x - lo) / r_ * (H - 6)).toFixed(1)}`).join(' ');
  return `<svg class="spk" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
};
const gauge = (c) => {
  const tot = c.red + c.yellow + c.green || 1, R = 64, C = 2 * Math.PI * R; let off = 0;
  const seg = (n, col) => { const len = n / tot * C; const s_ = `<circle r="${R}" cx="80" cy="80" fill="none" stroke="${col}" stroke-width="16" stroke-dasharray="${Math.max(0, len - 3)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 80 80)"/>`; off += len; return s_; };
  return `<svg class="gauge" viewBox="0 0 160 160" role="img" aria-label="מצב המשרד"><circle r="${R}" cx="80" cy="80" fill="none" stroke="var(--line)" stroke-width="16"/>${seg(c.red, 'var(--r)')}${seg(c.yellow, 'var(--y)')}${seg(c.green, 'var(--g)')}</svg>`;
};
// מסך הבית: רמזור בשלושה ריבועים (דחוף · במעקב · תקין). לכל לקוח — מה אפשר לשפר ואיך, לא "טיפלתי".
const IMPROVE = { cpl: 'להוריד את העלות לליד', no_leads: 'להחזיר את זרימת הלידים', spend_up: 'לכוון את התקציב ללידים', ctr: 'לרענן את המודעות',
  cvr: 'לשפר את ההמרה בדף', trend: 'לעצור את הירידה ולחזור לקצב', goal: 'לחזור ליעד', data: 'לחבר מחדש את הנתונים', no_sales: 'להפוך לידים למכירות',
  commitment: 'לסגור את מה שהובטח ללקוח', contact: 'לחדש קשר עם הלקוח', satisfaction: 'לחזק את הקשר עם הלקוח' };
const better = (x) => {
  if (x.st === 'green') return { head: x.status === 'nodata' ? 'להשלים נתונים' : x.suggest?.action ? 'הזדמנות לגדול' : 'לשמור על הקיים', how: x.status === 'nodata' ? 'לחבר את מקור הנתונים כדי לדעת איך הוא עומד' : x.suggest?.action || 'יציב — אין צורך לגעת' };
  const c = x.card; if (!c) return { head: 'לבדוק', how: '' };
  return { head: IMPROVE[c.key.split(':')[1]] || c.title, how: x.st === 'red' ? c.next : c.check?.[0] || c.next };
};
// מסך הבית — תדריך המנהל הראשי. למעלה: מצב הסוכנות במשפט + שלושת הדברים החשובים היום (מהמנהל הראשי, agents.py).
// מתחת: רשימה שקטה לפי רמזור, ולצידה תיק התובנות של הלקוח שנבחר — כל ששת התפקידים בתמונה אחת.
const dm = (d) => `${Number(d.slice(8, 10))}.${Number(d.slice(5, 7))}`;
const STL = { red: 'דורש התערבות', yellow: 'במעקב', green: 'תקין', nodata: 'חסרים נתונים' };
const actBtn = (cid, key, title, owner, cls = 'hm-pri') => `<button class="${cls}" data-act="agentAct" data-arg="${esc(cid)}|${esc(key || '')}|${esc(title || '')}">פתח משימה ל${esc(owner || 'קמפיינר')}</button>`;
const taskTag = (st_, owner) => `<span class="hm-tag">${st_ === 'awaiting_approval' ? 'ממתין לאישור מנהל' : st_ === 'new' ? 'נפתחה משימה' : 'בטיפול'}${owner ? ` · ${esc(owner)}` : ''}</span>`;
export const insightHTML = (i, opts = {}) => {
  const M = i.monitor, L = i.leads, C = i.campaigns, G = i.strategy, E = i.execution, mem = i.memory;
  return `
    ${opts.head === false ? '' : `<div class="hm-dh"><div><h2><a href="#/client/${i.client.id}">${esc(i.client.name)}</a></h2><p><i class="dot d-${M.status}"></i>${STL[M.status]} · ${esc(i.client.industry || '')} · ${esc(M.owner)}</p></div>
      ${M.status === 'green' && !G.opportunities.length ? '' : E.task_id ? taskTag(E.task_status, M.owner) : actBtn(i.client.id, E.key, E.key ? '' : (G.opportunities[0]?.action || ''), M.owner)}</div>`}
    <div class="hm-sum">${esc(i.chief)}</div>
    ${M.status !== 'green' && M.when ? `<div class="hm-sec"><h3>מה קרה</h3><dl class="hm-dl">
      <div><dt>הממצא</dt><dd>${esc(M.what)}</dd></div><div><dt>מאז</dt><dd>${esc(M.when)}${M.days_open ? ` · ${N(M.days_open)} ימים` : ''}</dd></div>
      <div><dt>סיבה אפשרית</dt><dd>${esc(M.cause)}</dd></div><div><dt>נתונים</dt><dd>${M.evidence.map(esc).join('<br>')}</dd></div>
      <div><dt>אחראי</dt><dd>${esc(M.owner)}</dd></div><div><dt>בדיקה חוזרת</dt><dd>${esc(M.recheck || '—')}</dd></div></dl></div>` : ''}
    <div class="hm-ch"><div class="hm-chl"><span><i style="background:var(--acc)"></i>לידים ביום</span><span><i class="ds"></i>הרמה הרגילה של הלקוח</span></div><div id="hmChart"></div></div>
    <div class="hm-sec"><h3>לידים</h3><p class="hm-lead">${esc(L.state)}</p>
      ${L.kind !== 'stable' ? `<p class="hm-why"><b>${L.kind === 'opportunity' ? 'ההזדמנות' : 'למה זה קורה'}:</b> ${esc(L.cause)}</p>` : ''}
      ${L.data.length ? `<div class="hm-chips">${L.data.map((x) => `<span>${esc(x)}</span>`).join('')}</div>` : ''}</div>
    ${M.todo.length ? `<div class="hm-sec"><h3>מה עושים</h3>${L.kind !== 'stable' ? `<p class="hm-why">${esc(L.improve)}</p>` : ''}<ol>${M.todo.map((s_) => `<li>${esc(s_)}</li>`).join('')}</ol>
      <p class="hm-meas"><b>איך נדע שהצליח:</b> ${esc(L.kind !== 'stable' ? L.measure : 'החריגה נסגרת בבדיקה החוזרת')}</p>${G.adapt ? `<p class="hm-mem">${esc(G.adapt)}</p>` : ''}</div>` : ''}
    ${G.opportunities.length ? `<div class="hm-sec"><h3>איך לשדרג</h3>${G.opportunities.map((o) => `<p>${esc(o.title)}<small>${esc(o.action)}${o.potential ? ' · ' + esc(o.potential) : ''}</small></p>`).join('')}</div>` : ''}
    <div class="hm-sec"><h3>קמפיינים</h3>${C.connected ? `<p>${N(C.good)} מתוך ${N(C.count)} מודעות עובדות טוב${C.best ? ` · המובילה: ${esc(C.best)}` : ''}${C.top_fix ? `<small>לשפר: ${esc(C.top_fix.name)} — ${esc(C.top_fix.issue)}. ${esc(C.top_fix.do)}</small>` : ''}</p>` : `<p class="hm-why">${esc(C.missing)}</p>`}
      ${C.budget.monthly ? `<div class="hm-bud"><span>ניצול תקציב (קצב חודשי)</span><div><i style="width:${Math.min(100, C.budget.use)}%" class="${C.budget.use > 110 ? 'over' : ''}"></i></div><b>${N(C.budget.use)}%</b><small>${money(C.budget.pace)} מתוך ${money(C.budget.monthly)}</small></div>` : ''}
      ${C.connected ? `<a class="hm-link2" href="#/ads?client=${i.client.id}">ניתוח מודעות מלא ←</a>` : ''}</div>
    ${mem.history.length || mem.commitments.length ? `<div class="hm-sec"><h3>מה כבר קרה אצל הלקוח</h3><ul class="hm-hist">${mem.history.map((h) => `<li><span>${esc(h.day)}</span>${esc(h.text)} — <em class="${h.ok ? 'ok' : 'no'}">${esc(h.result)}</em></li>`).join('')}${mem.commitments.map((x) => `<li><span>${esc(x.due)}</span>התחייבות פתוחה: ${esc(x.text)}</li>`).join('')}</ul></div>` : ''}
    <div class="hm-sec"><h3>עוד אפשר</h3><div class="hm-ai">
      <button data-act="updDraft" data-arg="${i.client.id}">${ic('spark', 14)}<span>לנסח עדכון ללקוח<small>טיוטה בלבד — לא נשלח</small></span></button>
      <a href="#/ask?q=${encodeURIComponent('למה ' + i.client.name + ' במצב הזה?')}">${ic('chat', 14)}<span>לשאול את העוזר<small>תשובה מתוך הנתונים</small></span></a></div></div>`;
};
export const insightChart = async (cid) => {
  const d = await api(`/api/pulse/clients/${encodeURIComponent(cid)}?days=30`);
  const ser = d.series || [], base = d.result?.base?.dailyLeads;
  const el = $('#hmChart'); if (!el) return;
  chart(el, { labels: ser.map((x) => dm(x.date)), h: 150, fmt: (v) => Math.round(v).toLocaleString(),
    series: [{ name: 'לידים', color: 'var(--acc)', w: 2.2, vals: ser.map((x) => x.leads) }, ...(base ? [{ name: 'רמה רגילה', color: 'var(--g)', w: 1.4, dash: true, vals: ser.map(() => Math.round(base * 10) / 10) }] : [])] });
};
// ================================================================ הלוח הראשי בשיטת Monday: קבוצה לכל קמפיינר, שורה לכל לקוח
const ST3 = { red: 'לטיפול', yellow: 'לבדיקה', green: 'תקין', nodata: 'לבדיקה' };
const LT = (s_) => (s_ === 'nodata' ? 'yellow' : s_);
const ago = (n) => (n == null ? 'אין תיעוד' : n === 0 ? 'היום' : n === 1 ? 'אתמול' : `לפני ${n} ימים`);
const openSet = () => { try { return new Set(JSON.parse(localStorage.getItem('cp.closed') || '[]')); } catch { return new Set(); } };
const BD = { closed: openSet(), openG: new Set((() => { try { return JSON.parse(localStorage.getItem('cp.open') || '[]'); } catch { return []; } })()), exp: null, deep: null };
const bdLink = (p, o) => `#/home?${new URLSearchParams(Object.fromEntries(Object.entries({ q: p.q, f: p.f, m: p.m, s: p.s, ...o }).filter(([, v]) => v))).toString()}`;
const sortRows = (rs, s) => {
  const r = [...rs];
  if (s === 'leads') r.sort((a, b) => (a.leads_norm ? a.leads / a.leads_norm : 9) - (b.leads_norm ? b.leads / b.leads_norm : 9));
  else if (s === 'check') r.sort((a, b) => (b.check.ago ?? 99) - (a.check.ago ?? 99));
  else if (s === 'name') r.sort((a, b) => a.name.localeCompare(b.name, 'he'));
  else if (s === 'cpl') r.sort((a, b) => ((b.cpl_norm && b.cpl ? b.cpl / b.cpl_norm : 0) - (a.cpl_norm && a.cpl ? a.cpl / a.cpl_norm : 0)));
  else if (s === 'contact') r.sort((a, b) => (b.contact.ago ?? 99) - (a.contact.ago ?? 99));
  return r;
};
const cplCell = (x) => (x.cpl == null ? '<span class="cpm">אין לידים</span>' : `${money(x.cpl)}${x.cpl_norm ? `<small class="${x.cpl > x.cpl_norm * 1.2 ? 'bad' : 'cpm'}">רגיל ${money(x.cpl_norm)}</small>` : ''}`);
const leadsCell = (x) => `${N(x.leads)}${x.leads_norm != null ? `<small class="${x.leads < x.leads_norm * 0.7 ? 'bad' : 'cpm'}">מתוך ~${N(x.leads_norm)}</small>` : ''}`;
const MCOL = ['#579BFC', '#A25DDC', '#FF7575', '#00A9A5', '#FDAB3D', '#9CD326', '#CAB641', '#784BD1'];
const bRow = (x, gc, gid) => {
  const on = BD.exp === x.id && BD.expG === gid;
  const m = (st._bd?.groups || []).find((g) => g.id === x.owner);
  return `<div class="mr ${on ? 'open' : ''}" style="--gc:${gc}" data-act="bdRow" data-arg="${x.id}|${gid}" role="button" tabindex="0" aria-expanded="${on}">
    <span class="m-name" title="${esc(x.name)}"><b>${esc(x.name)}</b></span>
    <span class="m-own">${m ? `<i class="m-av" style="background:${MCOL[(st._bd.groups.indexOf(m)) % MCOL.length]}">${esc(m.name[0])}</i>` : ''}</span>
    <span class="m-st"><em class="st-${LT(x.status)}">${ST3[x.status]}</em></span>
    <span class="m-tx" title="${esc(x.why)}">${esc(x.why)}</span>
    <span class="m-n ${x.leads_norm != null && x.leads < x.leads_norm * 0.7 ? 'bad' : ''}">${N(x.leads)}${x.leads_norm != null ? `<i>/${N(x.leads_norm)}</i>` : ''}</span>
    <span class="m-n ${x.cpl && x.cpl_norm && x.cpl > x.cpl_norm * 1.2 ? 'bad' : ''}">${x.cpl == null ? '—' : money(x.cpl)}</span>
    <span class="m-n ${x.check.late ? 'bad' : ''}">${ago(x.check.ago)}</span>
    <span class="m-n ${x.contact.late ? 'bad' : ''}">${ago(x.contact.ago)}</span>
    <span class="m-tx m-rec" title="${esc(x.rec)}">${esc(x.rec)}</span>
    <span class="m-go"><button class="m-help ${x.status === 'red' ? 'hot' : ''}" data-act="bdDeep" data-arg="${x.id}|${gid}">איך לעזור ←</button></span>
  </div>`;
};
const bdExp = (x) => `<div class="hp" id="bd-${x.id}"><div class="sk" style="height:140px"></div></div>`;
const deepHTML = (i, x) => {
  const L = i.leads, M = i.monitor, C = i.campaigns, cap = i.capabilities || [], tf = C.top_fix, E = i.execution;
  const steps = M.todo.length ? M.todo : [];
  const capOn = (id) => cap.find((c) => c.id === id)?.status === 'available';
  const stable = L.kind === 'stable' && M.status === 'green';
  const what = stable ? (i.strategy.opportunities[0]?.action || 'הלקוח יציב — אין צורך בפעולה. לבדוק שוב לפי התדירות.') : L.kind === 'stable' ? (i.strategy.recommendation || M.what) : L.improve;
  const taskBtn = E.task_id ? `<a class="hp-b" href="#/tasks?hl=${E.task_id}">משימה פתוחה · ${esc(STATUS[E.task_status] || '')}</a>`
    : (M.status !== 'green' || i.strategy.opportunities.length) ? `<button class="hp-b pri" data-act="agentAct" data-arg="${i.client.id}|${esc(E.key || '')}|${E.key ? '' : esc(i.strategy.opportunities[0]?.action || L.improve)}">פתח משימה עם הצעדים</button>` : '';
  const P = i.profile || {};
  const about = P.about ? `<div class="hp-who">
    <div class="hp-k">על הלקוח${P.demo ? ' <span class="cpm">(פרופיל דמו)</span>' : ''}</div>
    <p class="hp-about">${esc(P.about)}</p>
    <dl class="hp-dl">${P.goal ? `<div><dt>מה הוא רוצה</dt><dd>${esc(P.goal)}</dd></div>` : ''}${P.audience ? `<div><dt>הקהל שלו</dt><dd>${esc(P.audience)}</dd></div>` : ''}
      ${P.likes?.length ? `<div><dt>מה חשוב לו</dt><dd>${P.likes.map(esc).join('<br>')}</dd></div>` : ''}${P.avoid ? `<div><dt>להימנע</dt><dd>${esc(P.avoid)}</dd></div>` : ''}</dl>
    ${P.help?.length ? `<p class="hp-tip">💡 ${P.help.map(esc).join(' · ')}</p>` : ''}</div>`
    : `<div class="hp-who"><div class="hp-k">על הלקוח</div><p class="cpm">עוד לא הוזן פרופיל ללקוח הזה${P.contact ? ` · איש קשר: ${esc(P.contact)}` : ''}. אפשר להוסיף הערה בתיק הלקוח.</p></div>`;
  return `${about}
  <div class="hp-short">
    <div class="hp-k">איך לעזור לו — בקצרה</div>
    <p class="hp-what"><b>${esc(L.headline)}.</b> ${esc(what)}</p>
    ${steps.length ? `<ol class="hp-steps">${steps.map((t) => `<li>${esc(t)}</li>`).join('')}</ol>` : ''}
    <p class="hp-meas">✓ איך נדע שהצליח: ${esc(stable ? 'הרמה נשמרת בבדיקה הבאה' : L.kind === 'stable' ? 'החריגה נסגרת בבדיקה החוזרת' : L.measure)}${M.recheck && !stable ? ` · המערכת תבדוק שוב ב-${esc(M.recheck)}` : ''}</p>
    ${i.strategy.adapt ? `<p class="hp-mem">${esc(i.strategy.adapt)}</p>` : ''}
    <div class="hp-acts">${taskBtn}
      <button class="hp-b" data-act="bdTouch" data-arg="${i.client.id}|check">✓ בדקתי את הקמפיין</button>
      <button class="hp-b" data-act="bdTouch" data-arg="${i.client.id}|call">☎ דיברתי עם הלקוח</button>
      <a class="hp-b" href="#/client/${i.client.id}">תיק לקוח</a></div>
  </div>
  <div class="hp-ai">
    <div class="hp-k">ה-AI יכול לעזור</div>
    <div class="hp-ai-l">
      <button class="hp-ai-i" data-act="agentAct" data-arg="${i.client.id}|${esc(E.key || '')}|${E.key ? '' : esc(what)}" ${E.task_id ? 'disabled' : ''}><b>להכין משימה לקמפיינר</b><small>${E.task_id ? 'כבר נפתחה' : 'עם הצעדים, אחראי ותאריך בדיקה'}</small></button>
      <button class="hp-ai-i" data-act="updDraft" data-arg="${i.client.id}"><b>לנסח עדכון ללקוח</b><small>טיוטה להעתקה — לא נשלח</small></button>
      ${tf ? (capOn('copy') ? `<button class="hp-ai-i" data-act="adRewrite" data-arg="${esc(tf.id)}"><b>לכתוב קופי חלופי</b><small>ל${esc(tf.name)}</small></button>`
        : `<div class="hp-ai-i off"><b>לכתוב קופי חלופי</b><small>לא מחובר · צריך מפתח Gemini בשרת</small></div>`) : ''}
      <div class="hp-ai-i off"><b>לשנות תקציב / לעצור מודעה</b><small>לא מחובר · צריך Meta Ads · תמיד באישור מנהל</small></div>
    </div>
  </div>
  <details class="hp-more"><summary>בהרחבה — נתונים, סיבה, מודעות</summary>
    <div class="dp">
      <div><h4>מצב נוכחי</h4><p>${esc(L.state)}</p>${M.what && M.status !== 'green' ? `<p class="cpm">${esc(M.what)}</p>` : ''}</div>
      <div><h4>${L.kind === 'opportunity' ? 'ההזדמנות' : 'למה זה קורה'}</h4><p>${esc(L.cause)}</p></div>
      <div><h4>נתונים תומכים</h4>${(L.data.length ? L.data : M.evidence).map((d) => `<p class="cpm">${esc(d)}</p>`).join('') || '<p class="cpm">—</p>'}</div>
      ${tf ? `<div class="wide"><h4>המודעה החלשה: ${esc(tf.name)}</h4><p>${esc(tf.issue)} — ${esc(tf.why)}</p>
        <table class="dt"><tr><td>קופי</td><td>${esc(tf.do)}</td></tr><tr><td>קריאייטיב חלופי</td><td>${esc(tf.alt_creative)}</td></tr><tr><td>קהל חלופי</td><td>${esc(tf.alt_audience)}</td></tr></table></div>` : C.connected === false ? `<div class="wide"><h4>מודעות</h4><p class="cpm">${esc(C.missing)}</p></div>` : ''}
      ${C.budget.monthly ? `<div><h4>ניצול תקציב</h4><p>${N(C.budget.use)}% <span class="cpm">· קצב ${money(C.budget.pace)} מתוך ${money(C.budget.monthly)}</span></p></div>` : ''}
      <div><h4>אחראי ומעקב</h4><p>${esc(M.owner)}${x ? ` · בדיקת קמפיין ${esc(ago(x.check.ago))} · קשר ${esc(ago(x.contact.ago))}` : ''}</p></div>
    </div></details>`;
};
const openSide = (view, bd) => {
  const sx = BD.exp && bd.groups.flatMap((g) => g.rows).find((r) => r.id === BD.exp);
  if (!sx) return;
  const m = bd.groups.find((g) => g.id === sx.owner);
  view.insertAdjacentHTML('beforeend', `<aside class="sd" role="dialog" aria-label="${esc(sx.name)}">
    <header class="sd-h"><div><h2><a href="#/client/${sx.id}">${esc(sx.name)}</a></h2>
      <p><em class="sdt st-${LT(sx.status)}">${ST3[sx.status]}</em>${m ? `<span>${esc(m.name)}</span>` : ''}<span>${esc(sx.why)}</span></p></div>
      <button class="sd-x" data-act="sdClose" aria-label="סגירה">✕</button></header>
    <div class="sd-b">${bdExp(sx)}</div></aside>`);
  loadDeep(sx.id);
};
V.home = async (view, p = {}) => {
  if (p.v === 'big' || p.v === 'today') return V.today(view);
  if (p.v === 'plan') return V.plan(view, p);
  if (p.v === 'focus') return V.focus(view);
  const bd = await api('/api/pulse/board');
  st._bd = bd;
  const hour = new Date().getHours(), greet = hour < 12 ? 'בוקר טוב' : hour < 18 ? 'צהריים טובים' : 'ערב טוב';
  const q = (p.q || '').trim(), f = p.f || '', s_ = p.s || '';
  const match = (x) => (!q || x.name.includes(q)) && (!f || LT(x.status) === f);
  const C_ = bd.counts;
  const groups = bd.groups.filter((g) => !p.m || g.id === p.m).map((g) => ({ ...g, rows: sortRows(g.rows.filter(match), s_) }));
  const sh = (k, t) => `<span class="sortable ${s_ === k ? 'on' : ''}" data-act="bdSortH" data-arg="${k}" role="button" tabindex="0" title="מיון">${t}${s_ === k ? ' ▾' : ''}</span>`;
  const hdr = `<div class="mr mh">${sh('name', 'לקוח')}<span>קמפיינר</span>${sh('', 'סטטוס')}<span>למה</span>${sh('leads', 'לידים')}${sh('cpl', 'עלות לליד')}${sh('check', 'בדיקת קמפיין')}${sh('contact', 'קשר עם הלקוח')}<span>המלצה</span><span></span></div>`;
  const bat = (rs) => { const n = rs.length || 1; return `<div class="mbat">${['red', 'yellow', 'green'].map((k) => { const c = rs.filter((x) => LT(x.status) === k).length; return c ? `<i class="st-${k}" style="flex:${c}" title="${ST3[k]}: ${c}"></i>` : ''; }).join('')}</div>`; };
  const grp = (id, name, color, rs, extra, open) => `<section class="mg" style="--gc:${color}">
    <div class="mg-h" data-act="bdGroup" data-arg="${id}" role="button" tabindex="0" aria-expanded="${open}"><span class="car">${open ? '▾' : '◂'}</span><b>${esc(name)}</b><span class="mg-c">${N(rs.length)} לקוחות</span>${extra || ''}
      ${open ? '' : `<span class="mg-sum"><em class="r">${N(rs.filter((x) => x.status === 'red').length)}</em><em class="y">${N(rs.filter((x) => LT(x.status) === 'yellow').length)}</em><em class="g">${N(rs.filter((x) => x.status === 'green').length)}</em>${bat(rs)}</span>`}</div>
    ${open ? `<div class="mt">${hdr}${rs.map((x) => bRow(x, color, id)).join('') || '<div class="mr-empty">אין לקוחות שמתאימים לסינון</div>'}<div class="mr mf"><span></span><span></span><span>${bat(rs)}</span><span></span><span class="m-n">${N(rs.reduce((t, x) => t + x.leads, 0))}</span><span></span><span class="m-n">${rs.filter((x) => x.check.late).length} באיחור</span><span class="m-n">${rs.filter((x) => x.contact.late).length} באיחור</span><span></span><span></span></div></div>` : ''}</section>`;
  const urgentRows = bd.urgent.filter(match);
  const sel = (id, label, opts, val) => `<label class="mtool">${label}<select id="${id}">${opts.map(([v, t]) => `<option value="${v}" ${val === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>`;
  view.innerHTML = `<div class="mb2">
  <header class="mb2-h"><h1>${greet}, ${esc(st.me.user.name)}</h1><p>${C_.red ? 'אלה הלקוחות שדורשים את תשומת הלב שלך היום' : 'אין היום לקוחות שדורשים התערבות'}</p></header>
  <section class="kp">
    <a class="kp-i kp-r ${f === 'red' ? 'on' : ''}" href="${bdLink(p, { f: f === 'red' ? '' : 'red' })}"><span>לטיפול</span><b>${N(C_.red)}</b><small>בעיה משמעותית שצריך לטפל בה</small></a>
    <a class="kp-i kp-y ${f === 'yellow' ? 'on' : ''}" href="${bdLink(p, { f: f === 'yellow' ? '' : 'yellow' })}"><span>לבדיקה</span><b>${N(C_.yellow + C_.nodata)}</b><small>לבדוק ולעקוב</small></a>
    <a class="kp-i kp-g ${f === 'green' ? 'on' : ''}" href="${bdLink(p, { f: f === 'green' ? '' : 'green' })}"><span>תקינים</span><b>${N(C_.green)}</b><small>אפשר להציע שיפור</small></a>
    <a class="kp-i" href="#/tasks"><span>משימות להיום</span><b>${N(bd.tasks_today)}</b><small>${bd.approvals ? `${N(bd.approvals)} ממתינות לאישורך` : 'פתוחות ובאיחור'}</small></a>
    <div class="kp-bar">${['red', 'yellow', 'green'].map((k) => { const n = k === 'yellow' ? C_.yellow + C_.nodata : C_[k]; return n ? `<i class="st-${k}" style="flex:${n}"></i>` : ''; }).join('')}</div>
    ${bd.urgent[0] ? `<button class="kp-go" data-act="bdJump" data-arg="${bd.urgent[0].id}">התחל טיפול מהדחוף ביותר ←</button>` : ''}
  </section>
  <div class="mtools">
    <form id="bdQ" class="mtool"><span aria-hidden="true">⌕</span><input name="q" value="${esc(q)}" placeholder="חיפוש" aria-label="חיפוש לקוח"></form>
    ${sel('bdM', 'קמפיינר', [['', 'כולם'], ...bd.groups.map((g) => [g.id, g.name])], p.m || '')}
    ${sel('bdF', 'סטטוס', [['', 'הכול'], ['red', `לטיפול (${C_.red})`], ['yellow', `לבדיקה (${C_.yellow + C_.nodata})`], ['green', `תקין (${C_.green})`]], f)}
    ${sel('bdS', 'מיון', [['', 'דחוף קודם'], ['leads', 'ירידה בלידים'], ['check', 'לא נבדק הכי הרבה'], ['cpl', 'עלות לליד חריגה'], ['contact', 'בלי קשר הכי הרבה'], ['name', 'שם']], s_)}
    ${q || f || p.m || s_ ? '<a class="mtool" href="#/home">ניקוי</a>' : ''}</div>
  ${!p.m && urgentRows.length ? grp('__urgent', 'דורשים תשומת לב היום', '#676879', urgentRows, '', !BD.closed.has('__urgent')) : ''}
  ${groups.map((g, gi) => grp(g.id, g.name, MCOL[bd.groups.indexOf(bd.groups.find((y) => y.id === g.id)) % MCOL.length], g.rows,
    `<span class="mg-x">${g.late_checks ? `${N(g.late_checks)} בדיקות באיחור · ` : ''}${N(g.open_tasks)} משימות</span>${g.id ? `<button class="mg-ho" data-act="handover" data-arg="${g.id}">מסירה</button>` : ''}`,
    BD.openG.has(g.id) || !!(q || f || p.m))).join('')}
  </div>`;
  $('#bdF').addEventListener('change', (e) => { location.hash = bdLink(p, { f: e.target.value }); });
  $('#bdQ').addEventListener('submit', (e) => { e.preventDefault(); location.hash = bdLink(p, { q: new FormData(e.target).get('q') || '' }); });
  $('#bdM').addEventListener('change', (e) => { location.hash = bdLink(p, { m: e.target.value }); });
  $('#bdS').addEventListener('change', (e) => { location.hash = bdLink(p, { s: e.target.value }); });
  openSide(view, bd);
};
const loadDeep = async (cid) => {
  const el = document.getElementById('bd-' + cid); if (!el) return;
  const i = await api(`/api/pulse/clients/${encodeURIComponent(cid)}/insight`);
  el.innerHTML = deepHTML(i, (st._bd?.groups || []).flatMap((g) => g.rows).find((r) => r.id === cid));
};
A.bdRow = (el, arg, ev) => { const ln = ev && ev.target.closest('a[href]'); if (ln) { location.hash = ln.getAttribute('href'); return; } const [cid, gid] = arg.split('|'); const same = BD.exp === cid && BD.expG === gid; BD.exp = same ? null : cid; BD.expG = gid; if (same) BD.deep = null; render(); };
A.bdSortH = (b, k) => { const p_ = new URLSearchParams(location.hash.split('?')[1] || ''); if (k) p_.set('s', k); else p_.delete('s'); location.hash = '#/home?' + p_.toString(); };
A.sdClose = () => { BD.exp = null; render(); };
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && BD.exp && document.querySelector('.sd')) { BD.exp = null; render(); } });
A.bdDeep = (b, arg) => { const [cid, gid] = arg.split('|'); const same = BD.exp === cid && (!gid || BD.expG === gid); BD.exp = same ? null : cid; if (gid) BD.expG = gid; render(); };
A.bdGroup = (b, gid) => { const S_ = gid === '__urgent' ? BD.closed : BD.openG; S_.has(gid) ? S_.delete(gid) : S_.add(gid); try { localStorage.setItem('cp.closed', JSON.stringify([...BD.closed])); localStorage.setItem('cp.open', JSON.stringify([...BD.openG])); } catch { /* */ } render(); };
A.bdJump = (b, cid) => { BD.exp = cid; BD.expG = '__urgent'; render(); };
A.bdTouch = async (b, arg) => { const [cid, kind] = arg.split('|'); b.disabled = true; const r = await api(`/api/pulse/clients/${cid}/touch`, { method: 'POST', body: { kind } }); toast(r.msg); render(); };

// ================================================================ תיק לקוח — ארבעה אזורים בלבד
V.client = async (view, p) => {
  const [i, d] = await Promise.all([api(`/api/pulse/clients/${encodeURIComponent(p.id)}/insight`), api(`/api/pulse/clients/${encodeURIComponent(p.id)}?days=30`)]);
  const bd = st._bd || await api('/api/pulse/board');
  const x = bd.groups.flatMap((g) => g.rows).find((r) => r.id === p.id) || {};
  const c = d.client, M = i.monitor, L = i.leads, C = i.campaigns, r = d.result;
  const sec = (k, t, body) => `<section class="cf"><h2>${t}</h2>${body}</section>`;
  const kv = (rows_) => `<table class="dt kv">${rows_.filter(Boolean).map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join('')}</table>`;
  const contacts = d.contacts.map((y) => `${esc(y.name)} <span class="cpm">${esc(y.role || '')} · <bdi>${esc(y.phone || '')}</bdi></span>`).join('<br>') || '<span class="cpm">לא הוזן</span>';
  const evs = d.events.filter((e) => ['check', 'note', 'task', 'verified', 'verify_failed'].includes(e.type)).slice(0, 8);
  view.innerHTML = `<a class="back" href="#/home">${ic('back', 14)} הלוח</a>
  <div class="cf-h"><h1>${esc(c.name)}</h1><em class="sp-${M.status}">${ST3[M.status]}</em><span class="cpm">${esc(c.industry || '')} · ${esc(M.owner)}</span>${c.is_demo ? demoTag() : ''}</div>
  <div class="cf-g">
  ${sec('a', 'פרטי הלקוח ומצבו', `<p class="cf-sum">${esc(i.chief)}</p>${kv([['סטטוס', `${ST3[M.status]} — ${esc(M.title)}`], M.when && ['מאז', esc(M.when)], M.status !== 'green' && ['סיבה', esc(M.cause)],
    ['אחראי', esc(M.owner)], M.recheck && ['בדיקה חוזרת', esc(M.recheck)], ['אנשי קשר', contacts], c.goals?.targetCpl && ['יעד עלות לליד', money(c.goals.targetCpl)], c.goals?.monthlyBudget && ['תקציב חודשי', money(c.goals.monthlyBudget)]])}`)}
  ${sec('b', 'קמפיינים ומעקב קמפיינר', `${kv([['הוצאה 7 ימים', money(r.rec.spend)], ['עלות לליד', r.rec.cpl ? `${money(r.rec.cpl)} <span class="cpm">(רגיל ${money(r.base.cpl)})</span>` : 'אין לידים'],
    C.budget.monthly && ['ניצול תקציב', `${N(C.budget.use)}% <span class="cpm">קצב ${money(C.budget.pace)} מתוך ${money(C.budget.monthly)}</span>`],
    C.connected ? ['מודעות', `${N(C.good)} מתוך ${N(C.count)} עובדות טוב${C.top_fix ? ` · לשפר: ${esc(C.top_fix.name)} (${esc(C.top_fix.issue)})` : ''} <a href="#/ads?client=${c.id}">ניתוח מודעות</a>`] : ['מודעות', `<span class="cpm">${esc(C.missing)}</span>`],
    ['בדיקת קמפיין אחרונה', `<span class="${x.check?.late ? 'bad' : ''}">${ago(x.check?.ago)}</span> <span class="cpm">· נדרש כל ${N(x.check?.every)} ימים · ${N(x.check?.n)} בדיקות מתועדות</span>`],
    ['קשר אחרון עם הלקוח', `<span class="${x.contact?.late ? 'bad' : ''}">${ago(x.contact?.ago)}</span> <span class="cpm">· נדרש כל ${N(x.contact?.every)} ימים</span>`]])}
    <div class="bx-acts"><button data-act="cfTouch" data-arg="${c.id}|check">✓ בדקתי את הקמפיין</button><button data-act="cfTouch" data-arg="${c.id}|call">☎ תיעדתי שיחה</button><button data-act="cfTouch" data-arg="${c.id}|meeting">תיעדתי פגישה</button></div>
    ${evs.length ? `<table class="dt log">${evs.map((e) => `<tr><td>${esc(dayLabel ? dayLabel(e.day) : e.day)}</td><td>${esc(e.text)}</td><td class="cpm">${esc(e.user || '')}</td></tr>`).join('')}</table>` : ''}`)}
  ${sec('c', 'לידים ואיכות', `<p>${esc(L.state)}</p>${L.kind !== 'stable' ? `<p class="cpm">${esc(L.cause)}</p>` : ''}
    ${kv([['לידים 7 ימים', `${N(r.rec.leads)} <span class="cpm">(רגיל ~${N(Math.round(r.base.dailyLeads * 7))})</span>`], ['המרה מקליק לליד', r.rec.cvr != null ? `${(r.rec.cvr * 100).toFixed(1)}% <span class="cpm">(רגיל ${r.base.cvr ? (r.base.cvr * 100).toFixed(1) + '%' : '—'})</span>` : '—'],
      r.sales28 && ['מכירות 28 ימים', `${N(r.sales28.sales)} מתוך ${N(r.sales28.leads)} לידים`], !r.sales28 && ['איכות לידים', '<span class="cpm">אין נתוני מכירות מהלקוח — אפשר להזין ב-CSV</span>']])}
    <div id="hmChart" class="cf-ch"></div>`)}
  ${sec('d', 'המלצות ופעולות', `<p><b>${esc(L.headline)}</b> — ${esc(L.kind === 'stable' ? (i.strategy.recommendation || L.improve) : L.improve)}</p>
    ${M.todo.length ? `<ol>${M.todo.map((t) => `<li>${esc(t)}</li>`).join('')}</ol>` : ''}<p class="cpm">איך נדע שהצליח: ${esc(L.kind === 'stable' ? 'הרמה נשמרת' : L.measure)}</p>
    ${i.strategy.adapt ? `<p class="mem">${esc(i.strategy.adapt)}</p>` : ''}
    <div class="bx-acts">${i.execution.task_id ? `<a href="#/tasks?hl=${i.execution.task_id}">משימה פתוחה · ${esc(STATUS[i.execution.task_status] || '')}</a>` : M.status !== 'green' || i.strategy.opportunities.length ? `<button data-act="agentAct" data-arg="${c.id}|${esc(i.execution.key || '')}|${i.execution.key ? '' : esc(i.strategy.opportunities[0]?.action || L.improve)}">פתח משימה לקמפיינר</button>` : ''}
      <button data-act="updDraft" data-arg="${c.id}">נסח עדכון ללקוח</button><button data-act="bdDeepC" data-arg="${c.id}">בדיקה מעמיקה</button></div>
    <div id="bd-${c.id}"></div>
    ${i.memory.history.length ? `<table class="dt log">${i.memory.history.map((h) => `<tr><td>${esc(h.day)}</td><td>${esc(h.text)}</td><td class="${h.ok ? 'ok' : 'bad'}">${esc(h.result)}</td></tr>`).join('')}</table>` : ''}`)}
  </div><p class="cpm" style="margin-top:18px"><a href="#/client360/${c.id}">היסטוריה ופרטים מלאים</a> · <a href="/api/pulse/reports/client/${c.id}.html?days=30" target="_blank" rel="noopener">דוח ללקוח</a></p>`;
  insightChart(c.id);
};
A.cfTouch = async (b, arg) => { const [cid, kind] = arg.split('|'); b.disabled = true; const r = await api(`/api/pulse/clients/${cid}/touch`, { method: 'POST', body: { kind } }); toast(r.msg); st._bd = null; render(); };
A.bdDeepC = async (b, cid) => { const el = document.getElementById('bd-' + cid); if (el.innerHTML) { el.innerHTML = ''; return; } el.innerHTML = '<div class="sk" style="height:100px"></div>'; el.classList.add('bx-deep'); el.innerHTML = deepHTML(await api(`/api/pulse/clients/${encodeURIComponent(cid)}/insight`), (st._bd?.groups || []).flatMap((g) => g.rows).find((r) => r.id === cid)); };
A.agentAct = async (b, arg) => {
  const [client_id, key, title] = arg.split('|');
  b.disabled = true;
  try { const r = await api('/api/pulse/agents/act', { method: 'POST', body: { client_id, key: key || null, title: title || null } }); toast(r.msg); b.outerHTML = '<span class="hm-tag">נפתחה משימה ✓</span>'; }
  catch (e) { b.disabled = false; }
};
V.agents = async (view) => {
  const br = await api('/api/pulse/agents/brief');
  view.innerHTML = `<div class="hm" style="max-width:860px"><header><h1 style="margin:0;font-size:26px;font-weight:600">צוות הסוכנים</h1>
    <p class="hm-sub">שישה תפקידים שעובדים יחד על אותם נתונים. כל ממצא עובר מבקרה, לניתוח, להמלצה, לאישור, לביצוע ולבדיקה חוזרת.</p></header>
    <ol class="ag">${br.agents.map((a, i) => `<li><span class="hm-n">${i + 1}</span><div><b>${esc(a.name)}</b><p>${esc(a.does)}</p><small>עובד על: ${esc(a.uses)}</small></div><em>${N(a.findings)}<small>${a.id === 'execution' ? 'משימות פתוחות' : a.id === 'chief' ? 'דברים להיום' : 'ממצאים'}</small></em></li>`).join('')}</ol>
    <p class="note">מנוע: ${br.engine === 'rules' ? 'כללים וסטטיסטיקה מול ההיסטוריה של כל לקוח — בלי מודל שפה. חיבור Gemini / Claude ישפר ניסוח בלבד; ההחלטות נשארות מבוססות נתונים.' : esc(br.engine)}
    · פעולות רגישות (תקציב, עצירת קמפיין, הודעה ללקוח) ממתינות לאישור מנהל.</p></div>`;
};
A.handover = async (b, frm) => {
  const perf = await api('/api/pulse/team/perf');
  const ab = await api('/api/pulse/alerts');
  const from = perf.find((x) => x.id === frm);
  const mine = ab.cards.filter((c) => ab.board.find((x) => x.id === c.client_id)?.owner === frm);
  const seen = new Set(), top = mine.filter((c) => !seen.has(c.client_id) && seen.add(c.client_id)).slice(0, 8);
  modal(`<div class="mh"><b>מסירה זמנית · ${esc(from.name)}</b><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div>
    <div class="pad"><p class="tx2" style="margin-top:0">מה שמי שמחליף צריך לדעת על ${N(from.clients)} הלקוחות של ${esc(from.name)}:</p>
    ${top.map((c) => `<div class="cgi"><i class="dot d-${c.severity}"></i><b>${esc(c.client)}</b><span class="note">${esc(c.title)} — ${esc(c.next)}</span></div>`).join('') || '<p class="note">אין כרגע חריגות פתוחות.</p>'}
    <div class="row" style="margin-top:14px"><label class="small" for="hoTo">להעביר את כל המשימות הפתוחות אל:</label><select class="inp" id="hoTo">${perf.filter((x) => x.id !== frm).map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select>
    <button class="btn pri" data-act="doHandover" data-arg="${frm}">העבר</button></div><p class="note">הלקוחות נשארים של ${esc(from.name)}; רק הטיפול עובר זמנית. הכול מתועד.</p></div>`);
};
A.doHandover = async (b, frm) => { const r = await api('/api/pulse/team/handover', { method: 'POST', body: { frm, to: document.getElementById('hoTo').value } }); toast(r.msg, r.ok ? '' : 'warn'); closeModal(); render(); };
A.offerGroup = async (btn, gk) => {
  const items = (st._rows || []).filter((x) => x.st === 'green' && st._keyOf(x) === gk && x.suggest?.action);
  btn.disabled = true; btn.textContent = 'מכין…';
  let k = 0;
  for (const x of items) { try { await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: x.id, title: x.suggest.action, source: 'opportunity', due_days: 7 } }); k++; } catch { /* */ } }
  toast(`נוצרו ${k} משימות הצעה`); btn.outerHTML = '<span class="note ok">נוצרו ✓</span>';
};

// ================================================================ מה עושים עכשיו: תוכנית מסודרת לפי סיבה — לא רשימה של 200 אדומים
V.plan = async (view, p = {}) => {
  const ab = await api('/api/pulse/alerts');
  const byClient = {};
  ab.cards.forEach((x) => { if (!byClient[x.client_id]) byClient[x.client_id] = x; });
  const board = Object.fromEntries(ab.board.map((x) => [x.id, x]));
  const g = {};
  Object.values(byClient).forEach((cd) => { const k = cd.key.split(':')[1]; (g[k] = g[k] || []).push({ ...cd, b: board[cd.client_id] || {} }); });
  const steps = Object.entries(g).map(([k, items]) => ({ k, items, red: items.some((x) => x.severity === 'red'),
    waste: items.reduce((t, x) => t + (x.b.excess || 0), 0), pot: items.reduce((t, x) => t + (x.potential_leads || 0), 0),
    open: items.filter((x) => !x.task_id || x.task_status === 'new').length }))
    .sort((a, z) => (z.red - a.red) || (z.waste - a.waste) || (z.pot - a.pot) || (z.items.length - a.items.length));
  const offers = ab.board.filter((x) => (x.status === 'green') && x.suggest?.action);
  const openK = p.s || '', showAll = p.all === '1';
  const why = (st_) => st_.waste > 0 ? `כ-${st_.pot || 0} לידים בשבוע אפשר להחזיר` : st_.pot ? `כ-${st_.pot} לידים בשבוע אפשר להחזיר` : (st_.items[0].evidence || []).slice(-1)[0] || '';
  const step = (st_, i) => {
    const isOpen = openK === st_.k, f = st_.items[0];
    return `<div class="step ${isOpen ? 'open' : ''}"><button class="sth" data-act="go" data-arg="home?v=plan${isOpen ? '' : '&s=' + st_.k}">
      <span class="sn">${i + 1}</span><span class="stt"><b>${esc(GROUP[st_.k] || f.title)} · ${N(st_.items.length)} לקוחות</b><span class="note">${esc(why(st_))}</span></span>
      <span class="sto">${st_.open ? `${N(st_.open)} פתוחים` : '<span class="ok">הכול בטיפול ✓</span>'}</span><span class="chev">${isOpen ? '−' : '+'}</span></button>
      ${isOpen ? `<div class="stb"><div class="stdo"><span class="note">מה עושים:</span> <b>${esc(f.next)}</b></div>
        ${st_.items.map((x) => `<div class="gri"><i class="dot d-${x.severity}"></i><a href="#/client/${x.client_id}">${esc(x.client)}</a><span class="note">${x.b.excess ? kfmt(x.b.excess) + ' התבזבזו' : x.potential_leads ? '~' + x.potential_leads + ' לידים/שבוע' : ''}</span><span class="sp"></span>
          ${!x.task_id || ['new', 'in_progress'].includes(x.task_status) ? `<button class="btn sec sm" data-act="handle" data-arg="${esc(x.key)}|done">טיפלתי</button>` : '<span class="note ok">טופל ✓</span>'}</div>`).join('')}</div>` : ''}</div>`;
  };
  const shown = showAll ? steps : steps.slice(0, 5);
  view.innerHTML = `<div class="mini wide">
    <a class="back" href="#/home">‹ חזרה</a>
    <h2>מה עושים עכשיו</h2><p class="lead">סידרתי את הכול לפי סיבה, ולפי כמה זה עולה לך. מתחילים מלמעלה.</p>
    <div class="plansteps">${shown.map(step).join('') || '<p class="tx2">אין מה לטפל — הכול תקין.</p>'}
    ${offers.length ? `<div class="step"><div class="sth static"><span class="sn ok">+</span><span class="stt"><b>הזדמנויות · ${N(offers.length)} לקוחות תקינים</b><span class="note">אפשר להציע להם הרחבה — זה כסף נוסף למשרד</span></span><button class="btn sec sm" data-act="offerAll">הכן הצעה לכולם</button></div></div>` : ''}</div>
    ${steps.length > 5 && !showAll ? `<a class="quiet" href="#/home?v=plan&all=1">עוד ${N(steps.length - 5)} נושאים קטנים</a>` : ''}
    <a class="quiet" href="#/home?v=focus">או: לטפל לקוח אחד בכל פעם ←</a></div>`;
  st._offers = offers.map((x) => ({ id: x.id, suggest: x.suggest }));
};

// ================================================================ מה קורה היום: תמונת מצב שמוכיחה — במילים פשוטות + גרף
V.today = async (view) => {
  const [o, t, b] = await Promise.all([api('/api/pulse/overview'), api('/api/pulse/trend'), api('/api/pulse/brief')]);
  const c = o.counts, wk = o.week, sc = o.score || {}, w = b.week || {}, n = c.red + c.yellow + c.green + c.nodata;
  const pct = (a, z) => (a != null && z ? Math.round((a / z - 1) * 100) : null);
  const lp = pct(wk.leads, wk.prev_leads), cp = pct(wk.cpl, wk.prev_cpl);
  const lines = [
    lp != null && [lp >= 0 ? 'up' : 'down', `לידים: ${wk.leads.toLocaleString()} השבוע, ${lp >= 0 ? 'עלייה' : 'ירידה'} של ${Math.abs(lp)}% משבוע שעבר.`],
    cp != null && [cp <= 0 ? 'up' : 'down', `עלות לליד: ${money(wk.cpl)}, ${cp <= 0 ? 'זול יותר' : 'יקר יותר'} ב-${Math.abs(cp)}% משבוע שעבר.`],
    
    c.red && ['down', `${c.red} לקוחות צריכים טיפול עכשיו, ${c.yellow} במעקב.`],
    w.handled && ['up', `טופלו השבוע ${w.handled} בעיות${w.improved ? `, ${w.improved} מהן כבר השתפרו בפועל` : ''}.`],
    o.opps && ['up', `יש ${o.opps} הזדמנויות להרחבה אצל לקוחות תקינים.`],
  ].filter(Boolean);
  view.innerHTML = `<div class="mini wide">
    <a class="back" href="#/home">‹ לרמזור</a>
    <h2>מה קורה היום</h2>
    <div class="tod"><div class="score2"><span class="note">ציון המשרד</span><b>${N(sc.score ?? '—')}</b>${sc.prev != null ? `<span class="${sc.score >= sc.prev ? 'ok' : 'bad'}">${sc.score >= sc.prev ? '▲' : '▼'} ${Math.abs(sc.score - sc.prev)} משבוע שעבר</span>` : ''}
      <div class="mini3">${[['red', c.red], ['yellow', c.yellow], ['green', c.green + c.nodata]].map(([k, v]) => `<span><i class="dot d-${k}"></i>${N(v)}</span>`).join('')}</div></div>
      <ul class="says">${lines.map(([k, txt]) => `<li class="s-${k}">${esc(txt)}</li>`).join('')}</ul></div>
    <div class="card pad"><div class="note">לידים בשבוע · כל המשרד · 12 שבועות</div><div id="tdChart"></div></div>
    <div class="card pad why"><b>מה המערכת עשתה בשבילך</b><div class="sv3">
      <div><b>${N(n)}</b><span>חשבונות נבדקו אוטומטית, ב-${N(o.ms)} מ"ש</span></div>
      <div><b>${N(t.since.detected)}</b><span>בעיות נתפסו לפני שהלקוח התקשר</span></div>
      <div><b>~${N(Math.round((o.time?.saved_min || 0) / 6) / 10)} ש'</b><span>בדיקה ידנית נחסכה היום (הערכה)</span></div></div>
      <p class="note">בלי המערכת: לפתוח ${N(n)} חשבונות מודעות, להשוות ידנית לשבועות קודמים, ולגלות בעיה רק כשהלקוח מתקשר.</p></div>
    <a class="btn pri" style="align-self:flex-start" href="#/home?v=plan">למה שצריך לעשות עכשיו ←</a></div>`;
  chart($('#tdChart'), { labels: t.weeks.map((x) => x.label), h: 190, fmt: (v) => Math.round(v).toLocaleString(), series: [{ name: 'לידים', color: 'var(--acc)', w: 2.6, vals: t.weeks.map((x) => x.leads) }] });
};
A.offerAll = async (btn) => {
  const items = st._offers || [];
  btn.disabled = true; btn.textContent = 'מכין…';
  let n = 0;
  for (const x of items) { try { await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: x.id, title: x.suggest.action, source: 'opportunity', due_days: 7 } }); n++; } catch { /* */ } }
  toast(`נוצרו ${n} משימות הצעה — אחת לכל לקוח`); btn.outerHTML = '<span class="note ok">נוצרו ✓</span>';
};
A.bulk = async (btn, arg) => {
  const [k, g] = arg.split('|');
  const { rows, gkey } = st._home || {};
  if (!rows) return;
  const items = rows.filter((x) => x.st === k && gkey(x) === g);
  btn.disabled = true; btn.textContent = 'מבצע…';
  let n = 0;
  for (const x of items) {
    try {
      if (k === 'green') { if (x.suggest?.action) { await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: x.id, title: x.suggest.action, source: 'opportunity', due_days: 7 } }); n++; } }
      else if (x.card && !x.card.task_id) { await api('/api/pulse/alerts/handle', { method: 'POST', body: { key: x.card.key, mode: 'start' } }); n++; }
    } catch { /* ממשיכים לשאר */ }
  }
  toast(k === 'green' ? `נוצרו ${n} משימות הצעה` : `נפתח טיפול ל-${n} לקוחות`);
  await refreshMe(); render();
};

V.big = async (view) => {
  const t = await api('/api/pulse/trend');
  const s = t.since, w = t.weeks;
  view.innerHTML = `<div class="calm focus">
  <div class="calm-head"><h2>התמונה הגדולה</h2><p class="lead">${esc(t.sentence || 'אין עדיין מספיק שבועות של נתונים')}</p></div>
  <div class="stabs"><button data-act="go" data-arg="home">רמזור</button><button class="on">התמונה הגדולה</button></div>
  <div class="card pad"><div class="note">לידים בשבוע · כל המשרד · 12 שבועות</div><div id="bgLeads"></div></div>
  <div class="card pad"><div class="note">עלות לליד · ממוצע המשרד</div><div id="bgCpl"></div></div>
  <div class="card pad"><div class="h2">${ic('trophy')} מה המערכת עשתה${s.first_label ? ` מאז ${N(s.first_label)}` : ''}</div>
    <div class="since"><div><b>${N(s.detected)}</b><span>בעיות זוהו לפני שהלקוח התקשר</span></div><div><b>${N(s.handled)}</b><span>טופלו</span></div><div><b>${N(s.improved)}</b><span>השתפרו ואומתו בנתונים</span></div></div></div>
  ${t.is_demo ? '<p class="note">נתוני דמו</p>' : ''}</div>`;
  const lb = w.map((x) => x.label);
  chart($('#bgLeads'), { labels: lb, h: 180, fmt: (v) => Math.round(v).toLocaleString(), series: [{ name: 'לידים', color: 'var(--acc)', w: 2.6, vals: w.map((x) => x.leads) }] });
  chart($('#bgCpl'), { labels: lb, h: 160, fmt: (v) => money(v), series: [{ name: 'עלות לליד', color: 'var(--tx2)', w: 2.2, vals: w.map((x) => x.cpl) }] });
};
A.handle = async (b, arg) => {
  const [key, mode] = arg.split('|');
  b.disabled = true;
  try { const r = await api('/api/pulse/alerts/handle', { method: 'POST', body: { key, mode } }); toast(r.msg, r.ok ? '' : 'warn'); await refreshMe(); render(); }
  finally { b.disabled = false; }
};
A.skip = (b, key) => { (st.skip = st.skip || []).push(key); render(); };

V.queue = async (view, p = {}) => {
  const [b, o, ab] = await Promise.all([api('/api/pulse/brief'), api('/api/pulse/overview'), api('/api/pulse/alerts')]);
  const c = b.counts, hour = new Date().getHours(), greet = hour < 12 ? 'בוקר טוב' : hour < 18 ? 'צהריים טובים' : 'ערב טוב';
  const byClient = {};
  ab.cards.forEach((x) => { if (!byClient[x.client_id]) byClient[x.client_id] = x; });
  const bucket = (x) => (!x.card ? 'ok' : !x.card.task_id || x.card.task_status === 'new' ? 'todo' : ['awaiting_verification', 'closed'].includes(x.card.task_status) ? 'done' : 'doing');
  const rows = ab.board.map((x) => ({ ...x, card: byClient[x.id] })).map((x) => ({ ...x, b: bucket(x) }));
  const tab = p.s || (c.red ? 'red' : c.yellow ? 'yellow' : 'green'), hf = p.h || 'all', more = p.all === '1';
  const inTab = rows.filter((x) => x.status === tab);
  const attention = rows.filter((x) => x.status === 'red' || x.status === 'yellow');
  const cnt = { todo: attention.filter((x) => x.b === 'todo').length, doing: attention.filter((x) => x.b === 'doing').length, done: attention.filter((x) => x.b === 'done').length };
  const shown = inTab.filter((x) => hf === 'all' || x.b === hf).sort((x, y) => ({ todo: 0, doing: 1, done: 2, ok: 3 }[x.b] - { todo: 0, doing: 1, done: 2, ok: 3 }[y.b]) || (y.card?.potential_leads || 0) - (x.card?.potential_leads || 0));
  const list = more ? shown : shown.slice(0, 10);
  const go_ = (q) => `queue?s=${q.s ?? tab}&h=${q.h ?? hf}`;
  const H = { todo: ['לא טופל', 'tx2'], doing: ['בטיפול', ''], done: ['טופל · ממתין לאימות', 'ok'], ok: ['', ''] };
  const actBtn = (x) => !x.card ? '' : !x.card.task_id ? `<button class="btn pri sm" data-act="createTask" data-arg="${esc(x.card.key)}">פתח טיפול</button>`
    : x.card.task_status === 'new' ? `<button class="btn sec sm" data-act="task" data-arg="${esc(x.card.task_id)}|start">התחלתי</button>`
    : x.card.task_status === 'in_progress' ? `<button class="btn sec sm" data-act="task" data-arg="${esc(x.card.task_id)}|submit">סיימתי</button>` : '';
  const isIssue = tab === 'red' || tab === 'yellow';
  view.innerHTML = `<div class="calm">
  <div class="calm-head"><h2>${greet}, ${esc(st.me.user.name)}</h2>
    <p class="lead">${c.red + c.yellow ? `${N(c.red + c.yellow)} לקוחות צריכים תשומת לב. ${cnt.todo ? `${N(cnt.todo)} עוד לא טופלו.` : 'כולם בטיפול.'}` : 'כל הלקוחות תקינים היום.'}${b.potential ? ` <span class="small">אפשר להחזיר כ-${N(b.potential.leads_week)} לידים בשבוע (הערכה).</span>` : ''}</p></div>
  <div class="hstrip">${[['todo', 'לא טופלו'], ['doing', 'בטיפול'], ['done', 'טופלו']].map(([k, t]) => `<button class="hs ${hf === k ? 'on' : ''}" data-act="go" data-arg="${go_({ h: hf === k ? 'all' : k, s: tab === 'green' || tab === 'nodata' ? 'red' : tab })}"><b>${N(cnt[k])}</b><span>${t}</span></button>`).join('')}</div>
  <div class="stabs">${[['red', 'דחוף'], ['yellow', 'במעקב'], ['green', 'תקין'], ['nodata', 'אין מספיק מידע']].map(([k, t]) => `<button class="${tab === k ? 'on' : ''}" data-act="go" data-arg="${go_({ s: k, h: 'all' })}"><i class="dot d-${k}"></i>${t} <span class="note">${N(c[k])}</span></button>`).join('')}</div>
  <div class="card ttable">${isIssue ? `<div class="tr th"><span>לקוח</span><span>הבעיה</span><span>מה לעשות</span><span>כמה</span><span>טיפול</span><span></span></div>` : `<div class="tr th tr-ok"><span>לקוח</span><span>לידים 7 ימים</span><span>עלות לליד</span><span>מול הממוצע שלו</span></div>`}
    ${list.map((x) => isIssue ? `<div class="tr"><a class="tn" href="#/client/${x.id}">${esc(x.name)}</a><span class="tx2">${esc(x.card ? x.card.title : x.title)}</span><span>${esc(x.card ? x.card.next : '')}</span>
      <span class="tx2">${x.card && x.card.potential_leads ? `~${N(x.card.potential_leads)} לידים/שבוע` : '—'}</span><span class="${H[x.b][1]}">${H[x.b][0]}${x.card && x.card.late ? ' · <b class="bad">באיחור</b>' : ''}</span><span>${actBtn(x)}</span></div>`
      : `<div class="tr tr-ok"><a class="tn" href="#/client/${x.id}">${esc(x.name)}</a><span>${N(x.leads ?? '—')}</span><span>${N(money(x.cpl))}</span><span class="tx2">${x.cpl && x.base_cpl ? N((x.cpl <= x.base_cpl ? '' : '+') + Math.round((x.cpl / x.base_cpl - 1) * 100) + '%') : x.status === 'nodata' ? 'אין מספיק נתונים' : '—'}</span></div>`).join('')
      || `<div class="empty">${hf === 'all' ? 'אין לקוחות בקטגוריה הזו' : 'אין לקוחות בסינון הזה'}</div>`}
    ${shown.length > 10 && !more ? `<button class="tmore" data-act="go" data-arg="${go_({})}&all=1">הצג את כל ${N(shown.length)}</button>` : ''}</div>
  <footer class="proof">נבדקו ${N(b.clients)} חשבונות ב-${N(b.scan_ms)} מ"ש${o.time ? ` · ~${N(Math.round(o.time.saved_min / 6) / 10)} שעות בדיקה ידנית נחסכו היום (הערכה)` : ''}${o.week && o.week.leads ? ` · ${N(o.week.leads.toLocaleString())} לידים השבוע בכל המשרד` : ''}</footer>
  </div>`;
};
A.setSat = async (b, arg) => { const [cid, n] = arg.split('|'); await api(`/api/pulse/clients/${cid}/satisfaction`, { method: 'PUT', body: { score: Number(n) } }); toast('שביעות הרצון עודכנה'); render(); };
A.updDraft = async (b, cid) => { const r = await api(`/api/pulse/clients/${cid}/update-draft`, { method: 'POST' }); toast(r.msg); render(); };
// ================================================================ מצב פגישה עם לקוח — מסך נקי להצגה ללקוח עצמו (בלי נתונים פנימיים)
V.meet = async (view, p) => {
  const d = await api(`/api/pulse/clients/${encodeURIComponent(p.id)}?days=90`);
  const c = d.client, r = d.result, s = d.series;
  const last = s.slice(-30), prev = s.slice(-60, -30);
  const sum = (a, k) => a.reduce((t, x) => t + (x[k] || 0), 0);
  const L = sum(last, 'leads'), Lp = sum(prev, 'leads'), Sp = sum(last, 'spend'), Spp = sum(prev, 'spend');
  const cpl = L ? Sp / L : null, cplp = Lp ? Spp / Lp : null;
  const done = d.tasks.filter((t) => t.verification && t.verification.ok);
  const doing = d.tasks.filter((t) => t.status !== 'closed');
  const next = d.alerts.length ? d.alerts.slice(0, 2).map((a) => a.card.next) : ['להמשיך באותו קו ולבחון הגדלה הדרגתית של התקציב'];
  const k = (l, v, pv, goodDown) => `<div class="mk"><div class="note">${l}</div><b>${N(v)}</b>${pv ? `<div class="note">${pv}</div>` : ''}</div>`;
  const ch = (a, b) => (a != null && b ? `${a >= b ? '+' : ''}${Math.round((a / b - 1) * 100)}% מהחודש הקודם` : '');
  view.innerHTML = `<div class="meet"><a class="back" href="#/client/${c.id}">${ic('back', 14)} חזרה לתיק</a>
    <h1>${esc(c.name)}</h1><p class="lead">סיכום 30 הימים האחרונים</p>
    <div class="mks">${k('לידים', L.toLocaleString(), ch(L, Lp))}${k('עלות לליד', money(cpl), ch(cpl, cplp))}${k('השקעה בפרסום', money(Sp), ch(Sp, Spp))}${c.goals.targetCpl ? k('היעד שסיכמנו', money(c.goals.targetCpl), cpl ? (cpl <= c.goals.targetCpl ? 'עומדים ביעד' : 'מעל היעד — בטיפול') : '') : ''}</div>
    <div class="card pad"><div class="note" style="margin-bottom:6px">עלות לליד לאורך החודש (ממוצע נע 7 ימים)</div><div id="meetChart"></div></div>
    <div class="mcols"><div><h3>מה עשינו</h3><ul>${done.map((t) => `<li>${esc(t.title.split(' · ')[0])} — אומת בנתונים</li>`).join('')}${doing.map((t) => `<li>${esc(t.plan?.[0]?.text || t.title.split(' · ')[0])} (בתהליך)</li>`).join('')}${!done.length && !doing.length ? '<li>שמרנו על הקמפיינים יציבים ועקבנו אחרי הביצועים</li>' : ''}</ul></div>
      <div><h3>מה הלאה</h3><ul>${next.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
    ${c.is_demo ? '<p class="note">נתוני דמו</p>' : ''}</div>`;
  const roll = d.rolling.slice(-30);
  chart($('#meetChart'), { labels: roll.map((x) => x.date.slice(8, 10) + '.' + Number(x.date.slice(5, 7))), target: c.goals.targetCpl, fmt: (v) => money(v), h: 200,
    series: [{ name: 'עלות לליד', color: 'var(--acc)', w: 2.6, vals: roll.map((x) => x.cpl) }] });
};

A.talk = async (b, cid) => {
  const d = st._client;
  const r = await api(`/api/pulse/clients/${cid}/update-draft`, { method: 'POST' });
  const ct = (d.contacts || [])[0];
  const phone = ct?.phone ? ct.phone.replace(/\D/g, '').replace(/^0/, '972') : '';
  const wa = phone ? `https://wa.me/${phone}?text=${encodeURIComponent(r.text)}` : `https://wa.me/?text=${encodeURIComponent(r.text)}`;
  modal(`<div class="mh"><b>דבר עם הלקוח · ${esc(d.client.name)}</b><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div>
    <div class="pad talk">${ct ? `<div class="tk-c"><b>${esc(ct.name)}</b><span class="note">${esc(ct.role || '')}</span><bdi class="tx2">${esc(ct.phone || '')}</bdi></div>` : '<p class="note">אין איש קשר שמור — אפשר להוסיף בתיק הלקוח.</p>'}
    <div class="note" style="margin-top:12px">הודעה מוכנה מהנתונים (אפשר לערוך):</div><textarea class="inp" id="talkT" rows="7">${esc(r.text)}</textarea>
    <div class="row" style="margin-top:12px"><a class="btn pri" id="waBtn" href="${wa}" target="_blank" rel="noopener">פתח בוואטסאפ</a><button class="btn sec" data-act="copyTalk">העתק</button><span class="note">לא נשלח אוטומטית — אתה שולח</span></div></div>`);
  const ta = document.getElementById('talkT');
  ta.oninput = () => { document.getElementById('waBtn').href = `https://wa.me/${phone}?text=${encodeURIComponent(ta.value)}`; };
};
A.copyTalk = async () => { try { await navigator.clipboard.writeText(document.getElementById('talkT').value); toast('הועתק'); } catch { document.getElementById('talkT').select(); toast('סמנו והעתיקו', 'warn'); } };
A.commitDone = async (b, id) => { const r = await api(`/api/pulse/commitments/${id}`, { method: 'PATCH', body: { status: 'done' } }); toast(r.msg); render(); };

// ================================================================ ניתוח מודעות (הבקשה של יובל: מה לשפר בהצעה, בקופי ובקריאייטיב)
const VERD = { red: ['לעצור או לשכתב', '#E2445C'], yellow: ['לשפר', '#FDAB3D'], win: ['מנצחות — להגדיל', '#00C875'], ok: ['תקינות', '#579BFC'] };
const vk = (a) => (a.tone === 'red' ? 'red' : a.verdict.startsWith('מנצחת') ? 'win' : a.tone === 'yellow' ? 'yellow' : 'ok');
V.ads = async (view, p) => {
  const d = await api('/api/pulse/ads' + (p.client ? `?client=${encodeURIComponent(p.client)}` : ''));
  const an = d.analysis, sm = an.summary;
  st._ads = d;
  const hdr = `<div class="mr mh mad"><span>מודעה</span><span>פורמט</span><span>החלטה</span><span>הוצאה</span><span>CTR</span><span>המרה</span><span>עלות לליד</span><span>תדירות</span><span>הבעיה המרכזית</span><span></span></div>`;
  const row = (a, color) => `<div class="mr mad ${BD.ad === a.id ? 'open' : ''}" style="--gc:${color}" data-act="adRow" data-arg="${esc(a.id)}" role="button" tabindex="0">
    <span class="m-name"><b>${esc(a.name.split(' · ')[0])}</b></span><span class="m-n">${esc(a.format)}</span>
    <span class="m-st"><em style="background:${color}">${esc(VERD[vk(a)][0].split(' — ')[0])}</em></span>
    <span class="m-n">${money(a.spend)}</span><span class="m-n">${pctf(a.ctr, 2)}</span><span class="m-n">${pctf(a.cvr, 1)}</span>
    <span class="m-n ${a.tone === 'red' ? 'bad' : ''}">${a.cpl == null ? '—' : money(a.cpl)}</span><span class="m-n ${a.frequency >= 3.5 ? 'bad' : ''}">${N(a.frequency)}</span>
    <span class="m-tx m-rec">${a.recs.length ? esc(a.recs[0].issue) : 'אין בעיה'}</span>
    <span class="m-go"><button class="m-help" data-act="adRow" data-arg="${esc(a.id)}">איך לשפר ←</button></span></div>`;
  const groups = ['red', 'yellow', 'win', 'ok'].map((k) => [k, an.ads.filter((a) => vk(a) === k)]).filter(([, l]) => l.length);
  view.innerHTML = `<div class="mb2">
  <header class="mb2-h"><h1>מודעות</h1><p>${d.client ? `${esc(d.client.name)} · ${sm ? esc(sm.headline) : ''}${sm?.winner ? ` · המובילה: ${esc(sm.winner)}` : ''}` : 'בחר לקוח'}</p></header>
  <div class="mtools">
    <label class="mtool">לקוח<select id="adC">${d.clients.map((c) => `<option value="${c.id}" ${d.client && c.id === d.client.id ? 'selected' : ''}>${esc(c.name)}${c.to_fix ? ` · ${c.to_fix} לשפר` : ''}</option>`).join('')}</select></label>
    ${sm ? `<span class="mtool cpm">${esc(sm.note)}</span>` : ''}
    <span class="mtool cpm">${d.ai ? 'קופי חלופי: ' + esc(d.ai) : 'בדיקה לפי כללים · קופי חלופי לא מחובר (צריך Gemini)'}</span></div>
  ${d.note ? `<p class="cpm">${esc(d.note)}</p>` : ''}
  ${groups.map(([k, l]) => `<section class="mg" style="--gc:${VERD[k][1]}"><div class="mg-h"><b>${VERD[k][0]}</b><span class="mg-c">${N(l.length)} מודעות</span></div>
    <div class="mt">${hdr}${l.map((a) => row(a, VERD[k][1])).join('')}</div></section>`).join('') || (d.note ? '' : '<p class="cpm">אין מודעות להצגה</p>')}</div>`;
  $('#adC').onchange = (e) => { BD.ad = null; go('ads?client=' + e.target.value); };
  const ad = BD.ad && an.ads.find((a) => a.id === BD.ad);
  if (ad) {
    const color = VERD[vk(ad)][1];
    view.insertAdjacentHTML('beforeend', `<aside class="sd" role="dialog" aria-label="${esc(ad.name)}">
      <header class="sd-h"><div><h2>${esc(ad.name)}</h2><p><em class="sdt" style="background:${color}">${esc(ad.verdict)}</em><span>${esc(d.client.name)}</span>${ad.is_demo ? '<span>מודעת דמו</span>' : ''}</p></div>
        <button class="sd-x" data-act="adClose" aria-label="סגירה">✕</button></header>
      <div class="sd-b"><div class="hp">
        <div class="hp-who"><div class="hp-k">המודעה</div><p class="hp-about"><b>${esc(ad.headline)}</b><br>${esc(ad.text)}</p>
          <div class="ad-chk">${Object.entries(ad.checks).map(([k, v]) => `<span class="${v ? 'ok' : 'bad'}">${v ? '✓' : '✗'} ${esc(k)}</span>`).join('')}</div></div>
        <div class="hp-short"><div class="hp-k">איך לשפר — בקצרה</div>
          ${ad.recs.length ? `<ol class="hp-steps">${ad.recs.map((r) => `<li><b>${esc(r.area)}:</b> ${esc(r.do)}</li>`).join('')}</ol>` : '<p class="hp-what">המודעה עובדת טוב. אם היא מנצחת — להגדיל לה תקציב בהדרגה.</p>'}
          <p class="hp-meas">✓ איך נדע שהצליח: עלות לליד יורדת אל מתחת לממוצע של הלקוח (${money(sm.avg.cpl)}) תוך 7 ימים</p>
          <div class="hp-acts"><button class="hp-b pri" data-act="oppTask" data-arg="${esc(d.client.id)}|${esc(ad.name + ': ' + (ad.recs[0]?.do || 'להגדיל תקציב בהדרגה'))}">פתח משימה לקמפיינר</button></div></div>
        <div class="hp-ai"><div class="hp-k">ה-AI יכול לעזור</div><div class="hp-ai-l">
          ${d.ai ? `<button class="hp-ai-i" data-act="adRewrite" data-arg="${esc(ad.id)}"><b>לכתוב 3 גרסאות קופי</b><small>רק מעובדות שבמודעה — בלי להמציא</small></button>` : '<div class="hp-ai-i off"><b>לכתוב 3 גרסאות קופי</b><small>לא מחובר · צריך מפתח Gemini בשרת</small></div>'}
          <div class="hp-ai-i off"><b>לעצור מודעה / להעביר תקציב</b><small>לא מחובר · צריך Meta Ads · תמיד באישור מנהל</small></div></div><div id="rw_${esc(ad.id)}"></div></div>
        <details class="hp-more"><summary>בהרחבה — למה ומה הנתונים</summary><div class="dp">
          ${ad.recs.map((r) => `<div class="wide"><h4>${esc(r.area)} · ${esc(r.issue)}</h4><p>${esc(r.why)}</p></div>`).join('')}
          <div><h4>ביצועים 7 ימים</h4><p>הוצאה ${money(ad.spend)} · ${N(ad.leads)} לידים · ${N(ad.clicks)} הקלקות</p></div>
          <div><h4>מול ממוצע הלקוח</h4><p>CTR ${pctf(ad.ctr, 2)} מול ${pctf(sm.avg.ctr, 2)} · המרה ${pctf(ad.cvr, 1)} מול ${pctf(sm.avg.cvr, 1)}</p></div></div></details>
      </div></div></aside>`);
  }
};
A.adRow = (b, id) => { BD.ad = BD.ad === id ? null : id; render(); };
A.adClose = () => { BD.ad = null; render(); };
A.addClient = () => {
  document.querySelector('.sd')?.remove();
  const g = st._bd?.groups || [];
  document.getElementById('view').insertAdjacentHTML('beforeend', `<aside class="sd" role="dialog" aria-label="לקוח חדש"><header class="sd-h"><div><h2>לקוח חדש</h2><p><span>הנתונים מגיעים מייבוא CSV או מחיבור Meta</span></p></div><button class="sd-x" data-act="sdRemove" aria-label="סגירה">✕</button></header>
    <div class="sd-b"><form id="ncF" class="nc">
      <label>שם הלקוח<input name="name" required minlength="1" maxlength="120"></label>
      <label>תחום<input name="industry" maxlength="80" placeholder="למשל: מרפאת שיניים"></label>
      <label>קמפיינר<select name="owner"><option value="">ללא</option>${g.filter((x) => x.id).map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></label>
      <label>יעד עלות לליד (₪)<input name="target_cpl" type="number" min="0"></label>
      <label>תקציב חודשי (₪)<input name="monthly_budget" type="number" min="0"></label>
      <button class="hp-b pri">הוסף לקוח</button></form></div></aside>`);
  document.getElementById('ncF').addEventListener('submit', async (e) => {
    e.preventDefault(); const f = new FormData(e.target); const body = {};
    for (const [k, v] of f.entries()) if (v !== '') body[k] = ['target_cpl', 'monthly_budget'].includes(k) ? Number(v) : v;
    const r = await api('/api/pulse/clients', { method: 'POST', body }); toast(`${r.name || body.name} נוסף. עכשיו אפשר לייבא נתונים בתיק הלקוח.`); document.querySelector('.sd')?.remove(); render();
  });
};
A.sdRemove = () => document.querySelector('.sd')?.remove();
A.adRewrite = async (b, id) => {
  b.disabled = true; b.textContent = 'כותב…';
  try {
    const r = await api(`/api/pulse/ads/${encodeURIComponent(id)}/rewrite`, { method: 'POST' });
    (document.getElementById('rw_' + id) || {}).innerHTML = `<div class="recs" style="margin-top:10px">${r.variants.map((v) => `<div class="rec"><span class="pill p-imp">גרסה</span><div><b>${esc(v.headline)}</b><div class="small">${esc(v.text)}</div><div class="note">${esc(v.why)}</div></div><button class="btn sec sm" data-act="copy" data-arg="${esc(v.headline + '\n' + v.text)}">העתק</button></div>`).join('')}<p class="note">נכתב ע"י ${esc(r.engine)} מתוך המודעה והבעיות שזוהו. לבדוק לפני שימוש.</p></div>`;
  } catch { /* ההודעה הוצגה */ } finally { b.disabled = false; b.innerHTML = ic('spark', 13) + ' הצע קופי משופר'; }
};

// ================================================================ המשימות שלי — לכל עובד: מה דחוף ומה לעשות
V.my = async (view, p) => {
  const d = await api('/api/pulse/my' + (p.member ? `?member=${encodeURIComponent(p.member)}` : ''));
  const mem = d.team.find((m) => m.id === d.member);
  view.innerHTML = `<div class="row" style="margin-bottom:12px"><select class="inp" id="myM" aria-label="עובד">${d.team.map((m) => `<option value="${m.id}" ${m.id === d.member ? 'selected' : ''}>${esc(m.name)} · ${esc(m.role || '')}</option>`).join('')}</select>
    <span class="note">${N(d.clients)} לקוחות באחריות ${esc(mem?.name || '')} · ${N(d.tasks.length)} משימות פתוחות</span></div>
  ${d.need.length ? `<div class="card pad" style="margin-bottom:14px"><div class="h2"><i class="dot d-red"></i> לקוחות שלך שצריכים טיפול ואין עדיין משימה</div>${d.need.map((x) => `<div class="bi sev-${x.status}"><div class="bt"><b>${esc(x.name)}</b><div class="small tx2">${esc(x.title)}</div></div><button class="btn pri sm" data-act="go" data-arg="client/${x.id}">פתח הסבר</button></div>`).join('')}</div>` : ''}
  ${d.commitments.length ? `<div class="card pad" style="margin-bottom:14px"><div class="h2">${ic('check')} התחייבויות ללקוחות (3 הימים הקרובים ובאיחור)</div>${d.commitments.map((x) => `<div class="bi sev-${x.due_day < d.ref ? 'red' : 'yellow'}"><div class="bt"><b>${esc(x.text)}</b><div class="small tx2">${esc(x.client_name)} · יעד ${N(dayLabel(x.due_day))}${x.due_day < d.ref ? ` · באיחור ${N(d.ref - x.due_day)} ימים` : ''}</div></div><button class="btn sec sm" data-act="commitDone" data-arg="${x.id}">בוצע</button></div>`).join('')}</div>` : ''}
  ${d.ads.length ? `<div class="card pad" style="margin-bottom:14px"><div class="h2">${ic('spark')} מודעות לשפר אצל הלקוחות שלך</div>${d.ads.map((x) => `<div class="bi sev-red"><div class="bt"><b>${esc(x.client)} · ${esc(x.ad)}</b><div class="small tx2">${esc(x.first.issue)}: ${esc(x.first.do)}</div></div><button class="btn sec sm" data-act="go" data-arg="ads?client=${x.client_id}">לניתוח</button></div>`).join('')}</div>` : ''}
  <div class="h2">${ic('check')} המשימות שלי</div><div class="cards">${d.tasks.map((t) => taskCard(t, d.ref, false, t.late)).join('') || `<div class="card">${empty('אין משימות פתוחות')}</div>`}</div>`;
  $('#myM').onchange = (e) => go('my?member=' + e.target.value);
};

// ================================================================ הגדרות וכלים — כל המסכים המשניים במקום אחד
V.settings = async (view) => {
  const th = await api('/api/pulse/settings/thresholds');
  view.innerHTML = `<div class="cards" style="margin-bottom:14px">${MORE.map(([r, t, i]) => `<a class="card pad setl" href="#/${r}">${ic(i)}<b>${esc(t)}</b></a>`).join('')}</div>
  <div class="card pad"><div class="h2">${ic('zap')} ספי הרמזור של הסוכנות<span class="sp"></span><span class="note">ברירת מחדל לכל הלקוחות; אפשר לשנות גם ללקוח בודד בתיק שלו</span></div>
    <form id="thF" class="frm">${Object.entries(th).map(([k, t]) => `<div class="fld"><label for="ath_${k}">${esc(t.label)} <span class="note">ברירת מחדל ${N(t.default)}</span></label><input class="inp" id="ath_${k}" data-th="${k}" type="number" step="any" min="${t.min}" max="${t.max}" value="${t.value ?? ''}" ${st.me.can_approve ? '' : 'disabled'}></div>`).join('')}
    ${st.me.can_approve ? '<button class="btn pri sm">שמירה וחישוב מחדש</button>' : '<p class="note">שינוי ספים מותר לבעלים / מנהל</p>'}</form></div>`;
  const f = $('#thF');
  f.onsubmit = async (e) => { e.preventDefault(); const t = {}; f.querySelectorAll('[data-th]').forEach((i) => { if (i.value !== '') t[i.dataset.th] = Number(i.value); }); await api('/api/pulse/settings/thresholds', { method: 'PUT', body: { thresholds: t } }); toast('נשמר. הרמזור חושב מחדש לפי הספים.'); };
};

// ================================================================ ידע הסוכנות — מה עבד בעבר
V.knowledge = async (view) => {
  const d = await api('/api/pulse/knowledge');
  view.innerHTML = `<p class="tx2">נבנה אוטומטית מטיפולים שאומתו בנתונים, ומלקחים שהצוות מתעד.</p>
  <div class="cards">${d.patterns.map((g) => `<div class="card pad"><b>${esc(g.name)}</b><div class="small tx2">${N(g.fixed)} טופלו ואומתו${g.avg_days != null ? ` · ${N(g.avg_days)} ימים בממוצע` : ''}${g.failed_first ? ` · ${N(g.failed_first)} דרשו יותר מניסיון אחד` : ''}</div>${g.actions.length ? `<ul class="ul">${g.actions.map(([t, n]) => `<li>${esc(t)} <span class="note">(${N(n)})</span></li>`).join('')}</ul>` : ''}</div>`).join('') || `<div class="card">${empty('עוד אין טיפולים שאומתו. כל טיפול שיאומת יופיע כאן כדפוס שעבד.')}</div>`}</div>
  <form class="card pad row" id="lsF" style="margin-top:14px"><input class="inp" id="lsT" placeholder="לקח לצוות, למשל: אצל מרפאות, ייעוץ חינם ממיר טוב יותר מהנחה" style="flex:1" required minlength="3"><button class="btn sec sm">שמירה</button></form>
  ${d.lessons.map((l) => `<div class="fi"><span class="pill p-gray">לקח</span><div>${esc(l.text)}<div class="note">${esc(l.user_name || '')}</div></div></div>`).join('')}`;
  $('#lsF').onsubmit = async (e) => { e.preventDefault(); await api('/api/pulse/knowledge', { method: 'POST', body: { text: $('#lsT').value } }); render(); };
};

function feedItem(e) {
  const col = { alert: 'red', cleared: 'green', verified: 'green', verify_failed: 'yellow', task: 'imp', automation: 'yellow', lab: 'none', note: 'none', check: 'none' }[e.type] || 'none';
  return `<div class="fi ev"><span class="tm">${N(dayLabel(e.day))}</span><i class="dot d-${col}" style="margin-top:7px"></i><div>${e.client_id ? `<a href="#/client/${esc(e.client_id)}">${esc(e.text)}</a>` : esc(e.text)}${e.user ? ` <span class="note">· ${esc(e.user)}</span>` : ''}</div></div>`;
}

// ================================================================ לקוחות
V.clients = async (view, p) => {
  const [d, bd] = await Promise.all([api('/api/pulse/clients'), api('/api/pulse/board')]);
  st.clients = d.clients; st._bd = bd;
  const q = (p.q || '').trim(), m_ = p.m || '', s_ = p.s || '';
  const bi = Object.fromEntries(bd.groups.flatMap((g) => g.rows).map((r) => [r.id, r]));
  const gi = Object.fromEntries(bd.groups.map((g, i) => [g.id, i]));
  let rows = d.clients.filter((c) => (!q || c.name.includes(q) || (c.industry || '').includes(q)) && (!m_ || c.owner === m_));
  if (s_ === 'name') rows.sort((x, y) => x.name.localeCompare(y.name, 'he'));
  else if (s_ === 'leads') rows.sort((x, y) => y.leads - x.leads);
  else if (s_ === 'spend') rows.sort((x, y) => y.spend - x.spend);
  const link = (o) => `#/clients?${new URLSearchParams(Object.fromEntries(Object.entries({ q, m: m_, s: s_, ...o }).filter(([, v]) => v))).toString()}`;
  const hdr = `<div class="mr mh mc"><span>לקוח</span><span>קמפיינר</span><span>סטטוס</span><span>תחום</span><span>לידים 7 ימים</span><span>עלות לליד</span><span>יעד</span><span>הוצאה 7 ימים</span><span>הנושא המרכזי</span><span></span></div>`;
  const row = (c, color, gid) => { const x = bi[c.id] || {}; const own = bd.groups[gi[c.owner]];
    return `<div class="mr mc ${BD.exp === c.id ? 'open' : ''}" style="--gc:${color}" data-act="clRow" data-arg="${c.id}" role="button" tabindex="0">
      <span class="m-name"><b>${esc(c.name)}</b></span>
      <span class="m-own">${own ? `<i class="m-av" style="background:${MCOL[gi[c.owner] % MCOL.length]}">${esc(own.name[0])}</i>` : ''}</span>
      <span class="m-st"><em class="st-${LT(c.status)}">${ST3[c.status]}</em></span>
      <span class="m-tx">${esc(c.industry || '')}</span>
      <span class="m-n">${N(c.leads)}</span>
      <span class="m-n ${c.cpl && c.target && c.cpl > c.target ? 'bad' : ''}">${c.cpl == null ? '—' : money(c.cpl)}</span>
      <span class="m-n">${c.target ? money(c.target) : '—'}</span>
      <span class="m-n">${money(c.spend)}</span>
      <span class="m-tx m-rec">${esc(c.alerts.length ? c.alerts[0].title : c.improved ? 'השתפר' : x.why || 'תקין')}</span>
      <span class="m-go"><button class="m-help" data-act="clRow" data-arg="${c.id}">פרטים ←</button></span></div>`; };
  const grp = (k, name, color) => { const rs = rows.filter((c) => LT(c.status) === k); const open = !BD.closed.has('cl_' + k);
    return `<section class="mg" style="--gc:${color}"><div class="mg-h" data-act="bdGroup" data-arg="cl_${k}" role="button" tabindex="0"><span class="car">${open ? '▾' : '◂'}</span><b>${name}</b><span class="mg-c">${N(rs.length)} לקוחות</span></div>
      ${open ? `<div class="mt">${hdr}${rs.map((c) => row(c, color, k)).join('') || '<div class="mr-empty">אין לקוחות</div>'}</div>` : ''}</section>`; };
  view.innerHTML = `<div class="mb2">
  <header class="mb2-h"><h1>לקוחות</h1><p>${N(d.clients.length)} לקוחות במשרד · לחיצה על לקוח פותחת את הפרטים בצד</p></header>
  <div class="mtools">
    <form id="clQ" class="mtool"><span aria-hidden="true">⌕</span><input name="q" value="${esc(q)}" placeholder="חיפוש לקוח או תחום" aria-label="חיפוש לקוח"></form>
    <label class="mtool">קמפיינר<select id="clM"><option value="">כולם</option>${bd.groups.map((g) => `<option value="${g.id}" ${m_ === g.id ? 'selected' : ''}>${esc(g.name)}</option>`).join('')}</select></label>
    <label class="mtool">מיון<select id="clS">${[['', 'דחוף קודם'], ['leads', 'הכי הרבה לידים'], ['spend', 'הוצאה'], ['name', 'שם']].map(([v, t]) => `<option value="${v}" ${s_ === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <button class="mtool" data-act="addClient">+ לקוח חדש</button>
    ${q || m_ || s_ ? '<a class="mtool" href="#/clients">ניקוי</a>' : ''}</div>
  ${grp('red', 'לטיפול', '#E2445C')}${grp('yellow', 'לבדיקה', '#FDAB3D')}${grp('green', 'תקינים', '#00C875')}</div>`;
  $('#clQ').addEventListener('submit', (e) => { e.preventDefault(); location.hash = link({ q: new FormData(e.target).get('q') || '' }); });
  $('#clM').addEventListener('change', (e) => { location.hash = link({ m: e.target.value }); });
  $('#clS').addEventListener('change', (e) => { location.hash = link({ s: e.target.value }); });
  openSide(view, bd);
};
A.clRow = (b, cid) => { BD.exp = BD.exp === cid ? null : cid; render(); };
V.client360 = async (view, p) => {
  const days = Number(p.days || 30), metric = p.m || 'cpl';
  const d = await api(`/api/pulse/clients/${encodeURIComponent(p.id)}?days=${days}`);
  const c = d.client, r = d.result, h = r.health, top = d.alerts[0];
  const met = (l, a, b, fmt, goodDown) => `<div class="met"><div class="l">${l}</div><div class="v">${N(a == null ? '—' : fmt(a))}</div><div class="c">${chg(a, b, goodDown)} <span class="note">מול ${N(b == null ? '—' : fmt(b))}</span></div></div>`;
  const tab = p.tab || (top ? 'issue' : 'perf');
  const cd = top && top.card;
  const tabBtn = (k, t, n) => `<button class="${tab === k ? 'on' : ''}" data-act="go" data-arg="client360/${c.id}?tab=${k}&days=${days}&m=${metric}">${t}${n ? ` <span class="note">${n}</span>` : ''}</button>`;
  view.innerHTML = `<a class="back" href="#/clients">${ic('back', 14)} כל הלקוחות</a>
  <div class="ch"><div><div class="row" style="gap:10px"><i class="dot d-${r.status}" style="width:12px;height:12px"></i><h2>${esc(c.name)}</h2></div>
    <div class="meta2" style="margin:6px 0 0"><span>${esc(SL[r.status])}</span><span>${esc(c.industry || '')}</span></div></div>
    <div class="sp"></div><div class="row"><button class="btn pri sm" data-act="talk" data-arg="${c.id}">${ic('chat', 14)} דבר עם הלקוח</button>
      <details class="menu"><summary class="btn sec sm">עוד</summary><div class="menu-list"><a href="/api/pulse/reports/client/${c.id}.html?days=30" target="_blank" rel="noopener">דוח ללקוח</a><a href="/api/pulse/reports/client/${c.id}.pdf?days=30">PDF</a>
        <a href="#/meet/${c.id}">מצב פגישה עם הלקוח</a><a href="#/ask?q=${encodeURIComponent('למה ' + c.name + ' במצב הזה?')}">שאל על הלקוח</a>${c.is_demo ? `<a href="#/ads?client=${c.id}">ניתוח המודעות</a>` : ''}<button data-act="editClient" data-arg="${c.id}">הגדרות ויעדים</button></div></details></div></div>
  <div class="k4s cl">${[['לידים 7 ימים', r.rec.leads, r.base.leads / 3, true, (v) => Math.round(v)], ['עלות לליד', r.rec.cpl, r.base.cpl, false, money], ['הוצאה 7 ימים', r.rec.spend, r.base.spend / 3, null, money]].map(([l, v, pv, gu, fm]) => {
    const x = v != null && pv ? Math.round((v / pv - 1) * 100) : null;
    return `<div class="k4"><span class="note">${l}</span><b>${N(v == null ? '—' : fm(v))}</b>${x == null ? '' : `<span class="${gu == null ? 'note' : (x > 0) === gu ? 'ok' : 'bad'}">${x > 0 ? '▲' : '▼'} ${Math.abs(x)}% <span class="note">מהרגיל</span></span>`}</div>`; }).join('')}</div>
  <section class="hm-d cl-ins" id="clIns"><div class="sk" style="height:240px"></div></section>
  <div class="card pad" style="margin-bottom:14px"><div class="note">עלות לליד · 30 יום (ממוצע נע)${r.goals.targetCpl ? ' · קו ירוק = יעד' : ''}</div><div id="cl30"></div></div>
  <details class="moreinfo" ${p.tab ? 'open' : ''}><summary>עוד פרטים</summary>
  <div class="seg tabbar">${top ? tabBtn('issue', 'פרטי הבעיה', d.alerts.length) : ''}${tabBtn('perf', 'ביצועים')}${tabBtn('work', 'טיפול', d.tasks.filter((t) => t.status !== 'closed').length || '')}${tabBtn('about', 'הלקוח')}</div>
  <div class="tabpane">${tab === 'issue' ? d.alerts.map((a, i) => alertCard(a, d, i === 0)).join('')
    : tab === 'perf' ? `  <div class="card pad" style="margin-bottom:14px"><div class="h2">ביצועים<span class="sp"></span>
    <div class="seg">${[['cpl', 'עלות לליד'], ['leads', 'לידים'], ['spend', 'הוצאה'], ['ctr', 'CTR']].map(([k, t]) => `<button class="${metric === k ? 'on' : ''}" data-act="go" data-arg="client360/${c.id}?tab=perf&days=${days}&m=${k}">${t}</button>`).join('')}</div>
    <div class="seg">${[30, 60, 90].map((n) => `<button class="${days === n ? 'on' : ''}" data-act="go" data-arg="client360/${c.id}?tab=perf&days=${n}&m=${metric}">${n} יום</button>`).join('')}</div></div>
    <div class="mets" style="margin-bottom:12px">${met('הוצאה 7 ימים', r.rec.spend, r.base.spend / 3, money)}${met('לידים 7 ימים', r.rec.leads, r.base.leads / 3, (v) => Math.round(v))}${met('עלות לליד', r.rec.cpl, r.base.cpl, money, true)}${met('CTR', r.rec.ctr, r.base.ctr, (v) => pctf(v, 2))}${met('המרה לליד', r.rec.cvr, r.base.cvr, (v) => pctf(v, 1))}${met('CPM', r.rec.cpm, r.base.cpm, money, true)}</div>
    <div id="chartBox"></div><div class="legend" style="margin-top:6px">${metric === 'cpl' ? '<span><i style="background:var(--acc)"></i>ממוצע נע 7 ימים</span><span><i style="background:var(--line2)"></i>יומי</span>' : ''}${r.goals.targetCpl && metric === 'cpl' ? '<span><i style="background:var(--g)"></i>יעד</span>' : ''}<span class="note">"מול" = ממוצע 21 הימים שלפני השבוע האחרון</span></div></div>`
    : tab === 'work' ? `<div class="grid g2"><div class="stack">      <div class="card pad"><div class="h2">${ic('check')} משימות</div>${d.tasks.length ? d.tasks.map((t) => `<button class="act" style="width:100%;margin-bottom:6px" data-act="go" data-arg="task/${t.id}"><div style="text-align:start"><b>${esc(t.title.split(' · ')[0])}</b><div class="small tx2">${esc(STATUS[t.status])} · ${esc(memberName(t.assignee))}</div></div></button>`).join('') : empty('אין משימות')}
        <button class="btn sec sm" data-act="manualTask" data-arg="${c.id}">+ משימה ידנית</button></div>      <div class="card pad"><div class="h2">${ic('check')} התחייבויות ללקוח</div>
        ${d.commitments.map((x) => `<div class="bi sev-${x.status !== 'open' ? 'green' : x.due_day < d.ref ? 'red' : 'yellow'}"><div class="bt"><b style="${x.status !== 'open' ? 'text-decoration:line-through;color:var(--mute)' : ''}">${esc(x.text)}</b><div class="small tx2">${esc(memberName(x.owner))} · יעד ${N(dayLabel(x.due_day))}${x.status === 'open' && x.due_day < d.ref ? ' · באיחור' : x.status === 'done' ? ' · בוצע' : x.status === 'cancelled' ? ' · בוטל' : ''}</div></div>${x.status === 'open' ? `<button class="btn sec sm" data-act="commitDone" data-arg="${x.id}">בוצע</button>` : ''}</div>`).join('') || '<p class="small tx2">אין התחייבויות פתוחות</p>'}
        <form id="cmF" class="row" style="margin-top:8px"><input class="inp" id="cmT" placeholder="מה הבטחנו ללקוח" required minlength="2" style="flex:1;min-width:140px"><select class="inp" id="cmO" aria-label="אחראי">${memberOpts(c.owner)}</select><input class="inp" id="cmD" type="number" min="0" max="180" value="3" style="width:70px" aria-label="תוך ימים"><button class="btn sec sm">הוספה</button></form></div></div><div class="stack">      ${d.decisions.length ? `<div class="card pad"><div class="h2">${ic('check')} החלטות ותוצאות</div>${d.decisions.map((x) => `<div class="fi"><span class="tm">${N(dayLabel(x.day))}</span><div class="small"><b>${x.decision === 'approve' ? 'אושר' : 'נדחה'}</b> ע"י ${esc(x.by_name)}: ${esc(x.title)}${x.rationale ? `<div class="note">${esc(x.rationale)}</div>` : ''}<div class="${x.outcome === 'אומת בנתונים' ? 'ok' : x.outcome ? 'bad' : 'note'}">תוצאה: ${esc(x.outcome || 'ממתין לבדיקה חוזרת')}</div></div></div>`).join('')}</div>` : ''}      ${d.drafts.length ? `<div class="card pad"><div class="h2">${ic('chat')} טיוטות ללקוח</div>${d.drafts.map((x) => `<div class="hyp"><div class="small">${esc(x.text).replace(/\n/g, '<br>')}</div><div class="row" style="margin-top:8px"><span class="note">${esc(x.channel || '')} · ${x.status === 'approved' ? 'אושר ע"י ' + esc(x.approved_by) : 'טיוטה'}</span><span class="sp"></span><button class="btn sec sm" data-act="copy" data-arg="${esc(x.text)}">העתק</button>${x.status !== 'approved' && st.me.can_approve ? `<button class="btn sec sm" data-act="approveDraft" data-arg="${x.id}">אשר</button>` : ''}</div></div>`).join('')}<p class="note">השליחה ידנית — WhatsApp / Email לא מחוברים.</p></div>` : ''}      <div class="card pad"><div class="h2">${ic('report')} ציר זמן חכם</div><div class="tl">${timeline(d).map((e) => `<div class="tli ${e.k}"><div>${esc(e.t)}</div><div class="w">${N(dayLabel(e.day))}${e.who ? ' · ' + esc(e.who) : ''}</div></div>`).join('') || empty('אין עדיין אירועים')}</div></div></div></div>`
    : `<div class="grid g2"><div class="stack">      <div class="card pad"><div class="h2">${ic('users')} אנשי קשר ושביעות רצון</div>
        ${d.contacts.map((x) => `<div class="fi"><div><b>${esc(x.name)}</b> <span class="note">${esc(x.role || '')}</span><div class="small tx2"><bdi>${esc(x.phone || '')}</bdi> ${x.email ? '· <bdi>' + esc(x.email) + '</bdi>' : ''}</div></div></div>`).join('') || '<p class="small tx2">אין אנשי קשר</p>'}
        <form id="ctF" class="row" style="margin-top:8px"><input class="inp" id="ctN" placeholder="שם" required style="flex:1;min-width:100px"><input class="inp" id="ctR" placeholder="תפקיד" style="width:110px"><input class="inp" id="ctP" placeholder="טלפון" style="width:120px" dir="ltr"><button class="btn sec sm">הוספה</button></form>
        <div class="row" style="margin-top:12px"><span class="small">שביעות רצון${c.satisfaction ? ` (כרגע ${N(c.satisfaction)}/5)` : ' (לא תועדה)'}:</span>${[1, 2, 3, 4, 5].map((n) => `<button class="chip ${c.satisfaction === n ? 'on' : ''}" data-act="setSat" data-arg="${c.id}|${n}">${n}</button>`).join('')}</div></div>      <div class="card pad"><div class="h2">${ic('chat')} הערות, שיחות והחלטות</div>
        <form id="noteF"><div class="row"><select class="inp" id="nk"><option value="note">הערה</option><option value="call">שיחה</option><option value="meeting">פגישה</option><option value="decision">החלטה</option></select><input class="inp" id="nt" placeholder="מה סוכם / מה קרה" style="flex:1" required maxlength="4000"><button class="btn sec sm">שמור</button></div></form>
        ${d.notes.map((n) => `<div class="fi"><span class="pill p-gray">${{ note: 'הערה', call: 'שיחה', meeting: 'פגישה', decision: 'החלטה' }[n.kind]}</span><div>${esc(n.text)}<div class="note">${esc(n.user_name || '')}</div></div></div>`).join('')}</div>      <div class="card pad"><div class="h2">${ic('chart')} היסטוריית הרמזור</div>${d.status_history.map((x) => `<div class="fi"><span class="tm">${N(dayLabel(x.day))}</span>${pill(x.status)}<div class="small">${esc(x.reason || '')}</div></div>`).join('') || '<p class="small tx2">אין עדיין שינויים</p>'}</div></div><div class="stack">      ${d.opportunities.length ? `<div class="card pad"><div class="h2"><i class="dot d-imp"></i> הזדמנויות</div>${d.opportunities.map((o) => oppCard(o, c.id)).join('')}</div>` : ''}      <div class="card pad"><div class="h2">${ic('trophy')} ציון בריאות: ${N(h.score ?? 'אין מספיק מידע')}<span class="sp"></span><span class="note">ביטחון ${esc(h.confidence)}</span></div>
        ${h.parts.length ? `<table class="ft">${h.parts.map((x) => `<tr><td>${esc(x.label)}</td><td class="bad">${N(x.points)}</td></tr>`).join('')}</table>` : '<p class="small tx2">אין קנסות — 100.</p>'}<p class="note">${esc(h.formula)}</p></div>      <div class="card pad"><div class="h2">סיכון נטישה<span class="sp"></span>${d.risk.level === 'unknown' ? '<span class="pill p-gray">אין מספיק נתונים</span>' : `<span class="pill p-${d.risk.level === 'high' ? 'red' : d.risk.level === 'medium' ? 'yellow' : 'green'}">${{ high: 'גבוה', medium: 'בינוני', low: 'נמוך' }[d.risk.level]}</span>`}</div><ul class="ul">${d.risk.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>${d.risk.note ? `<p class="note">${esc(d.risk.note)}</p>` : ''}</div>      <div class="card pad"><div class="h2">${ic('coin')} רווחיות לסוכנות</div>${d.profit ? `<div class="kv"><span>הכנסה חודשית</span><b>${N(money(d.profit.fee))}</b><span>עלות עבודה</span><span>${N(money(d.profit.labor))} (${N(d.profit.hours)} ש')</span><span>עלויות נוספות</span><span>${N(money(d.profit.other))}</span><span>רווח גולמי</span><b class="${d.profit.profit < 0 ? 'bad' : 'ok'}">${N(money(d.profit.profit))} · ${N(pctf(d.profit.margin))}</b><span>תקציב פרסום 30 יום</span><span class="muted">${N(money(d.profit.ad_spend_30))} (של הלקוח)</span></div>${d.profit.complete ? '' : '<p class="note">חסרות שעות או עלות שעה — הרווחיות חלקית.</p>'}` : '<p class="small tx2">לא הוזנה הכנסה חודשית. הוסיפו בהגדרות כדי לראות רווחיות.</p>'}</div>      ${!c.is_demo ? `<div class="card pad"><div class="h2">${ic('plug')} ייבוא נתונים (CSV)</div><p class="small tx2">ייצוא יומי מ-Meta Ads Manager / Google Ads. עמודות: date, spend, impressions, clicks, leads · אופציונלי: sales, revenue. כותרות בעברית נתמכות.</p>
        <input type="file" accept=".csv,text/csv" id="csvF" class="inp" style="width:100%"><button class="btn sec sm" style="margin-top:8px" data-act="importCsv" data-arg="${c.id}">ייבוא</button><div id="csvR" class="note"></div></div>` : ''}</div></div>`}</div></details>`;
  api(`/api/pulse/clients/${encodeURIComponent(c.id)}/insight`).then((ins) => { const el = $('#clIns'); if (el) { el.innerHTML = insightHTML(ins, { head: false }); insightChart(c.id); } });
  // גרף
  const s = d.series, roll = d.rolling;
  if ($('#cl30')) chart($('#cl30'), { labels: roll.map((x) => x.date.slice(8, 10) + '.' + Number(x.date.slice(5, 7))), target: r.goals.targetCpl, fmt: (v) => money(v), h: 170, series: [{ name: 'עלות לליד', color: 'var(--acc)', w: 2.4, vals: roll.map((x) => x.cpl) }] });
  if ($('#chartBox')) {
  const labels = s.map((x) => x.date.slice(8, 10) + '.' + Number(x.date.slice(5, 7)));
  if (metric === 'cpl') {
    const rm = Object.fromEntries(roll.map((x) => [x.date, x.cpl]));
    chart($('#chartBox'), { labels, target: r.goals.targetCpl, fmt: (v) => money(v), series: [{ name: 'יומי', color: 'var(--line2)', w: 1.2, vals: s.map((x) => x.cpl) }, { name: 'ממוצע נע 7 ימים', color: 'var(--acc)', w: 2.4, vals: s.map((x) => rm[x.date] ?? null) }] });
  } else {
    const k = metric, fmt = k === 'spend' ? money : k === 'ctr' ? (v) => v.toFixed(2) + '%' : (v) => Math.round(v);
    chart($('#chartBox'), { labels, fmt, series: [{ name: { leads: 'לידים', spend: 'הוצאה', ctr: 'CTR' }[k], color: 'var(--acc)', vals: s.map((x) => x[k]) }] });
  }
  }
  if ($('#ctF')) $('#ctF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/contacts`, { method: 'POST', body: { name: $('#ctN').value, role: $('#ctR').value || null, phone: $('#ctP').value || null } }); render(); };
  if ($('#cmF')) $('#cmF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/commitments`, { method: 'POST', body: { text: $('#cmT').value, owner: $('#cmO').value, due_in: Number($('#cmD').value) } }); toast('ההתחייבות נשמרה ותיכנס לרמזור אם תאחר'); render(); };
  if ($('#noteF')) $('#noteF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/notes`, { method: 'POST', body: { kind: $('#nk').value, text: $('#nt').value } }); toast('נשמר בתיק הלקוח'); render(); };
  st._client = d;
};

function yuvalCard(c, compact) {
  const row = (k, v) => `<div class="yr"><span class="yk">${k}</span><span class="yv">${v}</span></div>`;
  const list = (xs) => (xs.length ? `<ul class="ul">${xs.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '—');
  return `<div class="ycard">
    ${row('מה קרה', esc(c.what))}
    ${row('מתי התחיל', `${N(c.started_label)} · פתוח ${N(c.days_open)} ימים · ${esc(c.period)}`)}
    ${row('מה השתנה', list(c.changed))}
    ${row('חומרה', `<span class="pill p-${c.severity}">${esc(c.severity_label)}</span>`)}
    ${compact ? '' : row('נתונים תומכים', list(c.evidence))}
    ${row('הסברים אפשריים', list(compact ? c.explanations.slice(0, 1) : c.explanations))}
    ${compact ? '' : row('מה לבדוק', list(c.check))}
    ${row('הפעולה הבאה', `<b>${esc(c.next)}</b>`)}
    ${c.potential ? row('פוטנציאל', `<span class="ok">${esc(c.potential)}</span> <span class="note">(הערכה)</span>`) : ''}
    ${row('מי אחראי', esc(c.owner_name) + (c.late ? ' <span class="pill p-red">באיחור</span>' : ''))}
    ${row('האם טופל', esc(c.handled))}
    ${row('האם השתפר', esc(c.improved))}
  </div>`;
}

V.alerts = async (view, p) => {
  const d = await api('/api/pulse/alerts');
  const f = p.f || 'all';
  const cards = d.cards.filter((c) => f === 'all' || (f === 'nohandler' ? !c.task_id : f === 'late' ? c.late : c.severity === f));
  view.innerHTML = `<p class="tx2">כל חריגה פתוחה, בפורמט אחד: מה קרה, מתי, מה השתנה, כמה חמור, על סמך מה, למה זה יכול לקרות, מה לבדוק, מה הצעד הבא, מי אחראי, האם טופל והאם השתפר.</p>
  <div class="chips tabs">${[['all', 'הכול'], ['red', 'אדום'], ['yellow', 'צהוב'], ['nohandler', 'בלי מטפל'], ['late', 'באיחור']].map(([k, t]) => `<button class="chip ${f === k ? 'on' : ''}" data-act="go" data-arg="alerts?f=${k}">${t} ${N(d.cards.filter((c) => k === 'all' || (k === 'nohandler' ? !c.task_id : k === 'late' ? c.late : c.severity === k)).length)}</button>`).join('')}</div>
  <div class="cards" style="grid-template-columns:repeat(auto-fill,minmax(420px,1fr))">${cards.map((c) => `<div class="card pad sev-${c.severity}"><div class="row"><a href="#/client/${c.client_id}"><b>${esc(c.client)}</b></a>${demoTag(c.is_demo)}<span class="sp"></span>${pill(c.severity)}</div>
    <h3 style="margin:8px 0 10px;font-size:16px">${esc(c.title)}</h3>${yuvalCard(c, true)}
    <div class="row" style="margin-top:10px">${c.task_id ? `<button class="btn sec sm" data-act="go" data-arg="task/${c.task_id}">למשימה</button>` : `<button class="btn pri sm" data-act="createTask" data-arg="${esc(c.key)}">צור משימה</button>`}<button class="btn sec sm" data-act="go" data-arg="client/${c.client_id}">כל הפרטים והגרף</button></div></div>`).join('') || `<div class="card">${empty('אין חריגות פתוחות')}</div>`}</div>`;
};

function alertCard(a, d, primary) {
  const inv = a.inv, t = a.task;
  const sev = a.severity;
  return `<div class="card al ${sev === 'red' ? 'red' : ''}" style="margin-bottom:14px">
    <div class="alh">${pill(sev)}<span class="t">${esc(a.title)}</span>${a.handling ? `<span class="pill p-gray">${esc(HANDLING[a.handling] || a.handling)}</span>` : ''}${a.early ? '<span class="pill p-imp">התרעה מוקדמת</span>' : ''}<span class="sp"></span>
      <span class="engine">${ic('spark', 12)} מנוע כללים סטטיסטי · ביטחון ${esc(a.confidence)}</span></div>
    <div class="meta2"><span>${esc(a.period)}</span>${a.first_day ? `<span>התחיל: ${N(dayLabel(a.first_day))}</span>` : ''}<span>משך: ${N(a.durationDays)} ימים</span></div>
    ${yuvalCard(a.card, !primary)}
    <details style="margin-top:10px"><summary>חקירה מלאה: טבלת מדדים, משקל כל השערה ומדד הצלחה</summary>
    <div class="inv">
      <div class="blk"><div class="k"><span class="tag3 t-fact">עובדות</span> מה השתנה ביחס לתקופה קודמת</div><table class="ft"><tr><th>מדד</th><th>לפני</th><th>עכשיו</th><th>שינוי</th></tr>${inv.facts.map((f) => `<tr><td>${esc(f.label)}</td><td>${N(f.before)}</td><td>${N(f.after)}</td><td>${f.change == null ? '' : N((f.change > 0 ? '+' : '') + Math.round(f.change * 100) + '%')}</td></tr>`).join('')}</table></div>
      <div class="blk"><div class="k"><span class="tag3 t-hyp">השערות</span> הסברים אפשריים, לפי משקל בנתונים</div>${inv.hypotheses.map((x) => `<div class="hyp"><div><b>${esc(x.text)}</b></div><div class="small tx2">${esc(x.evidence)}</div><div class="note">${esc(x.support)}</div><div class="bar"><i style="width:${Math.round((x.share || 0) * 100)}%"></i></div></div>`).join('')}</div>
      <div class="blk"><div class="k">מה לבדוק</div><ul class="ul">${inv.checks.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="blk"><div class="k"><span class="tag3 t-rec">המלצה</span> תוכנית פעולה</div><ol class="plan">${inv.plan.map((x) => `<li><span>${esc(x.text)} ${SENS.has(x.actionType) ? `<span class="pill p-yellow">${esc(ACTION[x.actionType])} · דורש אישור</span>` : ''}</span></li>`).join('')}</ol></div>
      <div class="okbox"><b>מדד הצלחה:</b> ${esc(inv.success.text)} · בדיקה חוזרת אוטומטית אחרי ${N(inv.success.days)} ימים</div>
      <div class="unk">לא ידוע (חסר חיבור): ${inv.unknown.map(esc).join(' · ')}</div>
    </div></details>
    <div class="row" style="margin-top:12px">${t ? `<button class="btn pri sm" data-act="go" data-arg="task/${t.id}">למשימה (${esc(STATUS[t.status])} · ${esc(memberName(t.assignee))})</button>` : `<select class="inp sm" id="as_${esc(a.key)}" aria-label="אחראי">${memberOpts(d.client.owner)}</select><button class="btn pri sm" data-act="createTask" data-arg="${esc(a.key)}">צור משימה ושייך</button>`}
      <span class="sp"></span>${a.feedback ? `<span class="note">משוב: ${a.feedback === 'useful' ? 'מועילה' : 'שווא'}</span>` : `<button class="btn sec sm" data-act="fb" data-arg="${esc(a.key)}|useful">מועילה</button><button class="btn sec sm" data-act="fb" data-arg="${esc(a.key)}|false_positive">התראת שווא</button>`}</div>
  </div>`;
}

function timeline(d) {
  const out = [];
  d.alerts.concat(d.past_alerts).forEach((a) => (a.history || []).forEach((h) => out.push({ day: h.day, t: h.a + ' — ' + (a.title || ''), k: /נפתרה|נעלמה|חזרו/.test(h.a) ? 'verified' : 'alert', ts: h.t })));
  d.tasks.forEach((t) => t.history.forEach((h) => out.push({ day: h.day, t: h.a, who: h.who, k: /אומת/.test(h.a) ? 'verified' : /אוטומציה/.test(h.who || '') ? 'automation' : 'task', ts: h.t })));
  d.notes.forEach((n) => out.push({ day: null, t: 'תועד: ' + n.text, who: n.user_name, k: 'task', ts: n.created_at }));
  const seen = new Set();
  return out.filter((e) => { const k = e.t + e.ts; if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a, b) => b.ts - a.ts).slice(0, 40).map((e) => ({ ...e, day: e.day ?? st.me.ref }));
}

function oppCard(o, cid) {
  return `<div class="hyp"><b>${esc(o.title)}</b><div class="small tx2">${esc(o.evidence)}</div><div class="small">הצעה: ${esc(o.action)}</div>${o.potential ? `<div class="note">${esc(o.potential)}</div>` : ''}
    <div class="row" style="margin-top:8px"><button class="btn sec sm" data-act="oppTask" data-arg="${esc(cid)}|${esc(o.action)}">צור משימה</button><button class="btn sec sm" data-act="oppDraft" data-arg="${esc(cid)}|${esc(o.kind)}">הכן טיוטת הצעה</button></div></div>`;
}

A.createTask = async (b, key) => {
  const sel = document.getElementById('as_' + key);
  const t = await api('/api/pulse/tasks', { method: 'POST', body: { alert_key: key, assignee: sel?.value } });
  toast(`נוצרה משימה ל${memberName(t.assignee)}`); go('task/' + t.id);
};
A.fb = async (b, arg) => { const [key, verdict] = arg.split('|'); const r = await api('/api/pulse/alerts/feedback', { method: 'POST', body: { key, verdict } }); toast(r.msg); render(); };
A.editClient = (b, cid) => {
  const d = st._client, c = d.client;
  modal(`<div class="mh"><b>הגדרות ויעדים · ${esc(c.name)}</b><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div>
  <form class="pad" id="ecF">${clientFields(c)}<div class="h2" style="margin-top:12px">ספי התראה ללקוח הזה <span class="note">(ריק = ברירת מחדל)</span></div>
  <div class="frm">${Object.entries(d.thresholds).map(([k, t]) => `<div class="fld"><label for="th_${k}">${esc(t.label)} <span class="note">ברירת מחדל ${N(t.default)}</span></label><input class="inp" id="th_${k}" data-th="${k}" type="number" step="any" min="${t.min}" max="${t.max}" value="${t.value ?? ''}"></div>`).join('')}</div>
  <div class="row" style="margin-top:12px"><button class="btn pri">שמירה</button>${st.me.can_approve ? `<span class="sp"></span><button type="button" class="btn dng sm" data-act="delClient" data-arg="${c.id}">מחיקת לקוח</button>` : ''}</div></form>`);
  const form = $('#ecF');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const body = readClientForm(form);
    Object.keys(body).filter((k) => k.startsWith('th_')).forEach((k) => delete body[k]);
    body.thresholds = {};
    form.querySelectorAll('[data-th]').forEach((i) => { if (i.value !== '') body.thresholds[i.dataset.th] = Number(i.value); });
    await api(`/api/pulse/clients/${cid}`, { method: 'PATCH', body }); closeModal(); toast('נשמר. הניתוח חושב מחדש לפי ההגדרות.'); render();
  };
};
A.delClient = async (b, cid) => { if (!confirm('למחוק את הלקוח וכל הנתונים שלו? אי אפשר לבטל.')) return; await api(`/api/pulse/clients/${cid}`, { method: 'DELETE' }); closeModal(); st.clients = null; await refreshMe(); go('clients'); };
A.importCsv = async (b, cid) => {
  const f = $('#csvF').files[0];
  if (!f) return toast('בחרו קובץ CSV', 'warn');
  const r = await api(`/api/pulse/clients/${cid}/import`, { method: 'POST', body: { csv: await f.text() } });
  $('#csvR').innerHTML = `יובאו ${N(r.imported)} ימים.` + (r.errors.length ? '<br>' + r.errors.map(esc).join('<br>') : '');
  if (r.imported) { toast(`יובאו ${r.imported} ימים. מריץ ניתוח…`); await api('/api/pulse/check', { method: 'POST' }); render(); }
};
A.manualTask = (b, cid) => modal(`<div class="mh"><b>משימה ידנית</b><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div>
  <form class="pad" id="mtF"><div class="fld"><label for="mtT">מה צריך לעשות</label><input class="inp" id="mtT" required minlength="2"></div><div class="frm"><div class="fld"><label for="mtA">אחראי</label><select class="inp" id="mtA">${memberOpts()}</select></div><div class="fld"><label for="mtD">תוך כמה ימים</label><input class="inp" id="mtD" type="number" min="1" max="30" value="3"></div></div><button class="btn pri">יצירה</button></form>`)
  || ($('#mtF').onsubmit = async (e) => { e.preventDefault(); const t = await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: cid, title: $('#mtT').value, assignee: $('#mtA').value, due_days: Number($('#mtD').value) } }); closeModal(); go('task/' + t.id); });
A.oppTask = async (b, arg) => { const [cid, title] = arg.split('|'); await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: cid, title, source: 'opportunity', due_days: 7 } }); toast('נוצרה משימה: ' + title); b.outerHTML = '<span class="note ok">נוצרה משימה ✓</span>'; };
A.oppDraft = async (b, arg) => { const [cid, kind] = arg.split('|'); const r = await api('/api/pulse/opportunities/draft', { method: 'POST', body: { client_id: cid, kind } }); toast(r.msg); go('client/' + cid); };
A.copy = async (b, txt) => { try { await navigator.clipboard.writeText(txt); toast('הועתק'); } catch { toast('ההעתקה נחסמה בדפדפן', 'warn'); } };
A.approveDraft = async (b, id) => { const r = await api(`/api/pulse/drafts/${id}/approve`, { method: 'POST' }); toast(r.msg); render(); };

// ================================================================ משימות ואישורים
V.task = (view, p) => V.tasks(view, { ...p, hl: p.id });
V.tasks = async (view, p) => {
  const d = await api('/api/pulse/tasks');
  const tab = p.tab || (p.hl ? 'all' : 'open');
  const ref = d.ref;
  const late = (t) => t.due_day != null && t.due_day < ref && ['new', 'in_progress', 'awaiting_approval'].includes(t.status);
  const F = { open: (t) => !['closed', 'awaiting_verification'].includes(t.status), mine: (t) => (st.me.team.find((m) => m.id === t.assignee)?.name === st.me.user.name) && t.status !== 'closed',
    approval: (t) => t.status === 'awaiting_approval', verify: (t) => t.status === 'awaiting_verification', late, closed: (t) => t.status === 'closed', all: () => true };
  const list = d.tasks.filter(F[tab] || F.open);
  view.innerHTML = `<div class="card pad" style="margin-bottom:14px"><div class="h2">${ic('team')} עומס לפי עובד<span class="sp"></span><a class="small" href="#/team">צוות</a></div>
    <div class="row">${d.team.filter((m) => m.open || m.clients).map((m) => `<div class="met" style="min-width:150px"><div class="l">${esc(m.name)} · ${esc(m.role || '')}</div><div class="v">${N(m.open)} <span class="note">פתוחות</span></div><div class="c ${m.late ? 'bad' : 'muted'}">${N(m.late)} באיחור · ${N(m.not_started)} לא התחילו</div></div>`).join('')}</div></div>
  <div class="tabs chips">${[['open', 'פתוחות'], ['mine', 'שלי'], ['approval', 'ממתין לאישור'], ['verify', 'ממתין לבדיקה חוזרת'], ['late', 'באיחור'], ['closed', 'נסגרו'], ['all', 'הכול']].map(([k, t]) => `<button class="chip ${tab === k ? 'on' : ''}" data-act="go" data-arg="tasks?tab=${k}">${t} ${N(d.tasks.filter(F[k]).length)}</button>`).join('')}</div>
  <div class="cards">${list.map((t) => taskCard(t, ref, p.hl === t.id, late(t))).join('') || `<div class="card">${empty('אין משימות בתצוגה הזו')}</div>`}</div>`;
  if (p.hl) setTimeout(() => document.getElementById('tk_' + p.hl)?.scrollIntoView({ block: 'center' }), 50);
};
function taskCard(t, ref, hl, late) {
  const idx = FLOW.indexOf(t.status === 'done' ? 'awaiting_verification' : t.status);
  const can = st.me.can_approve;
  const btn = (act, label, cls = 'sec') => `<button class="btn ${cls} sm" data-act="task" data-arg="${t.id}|${act}">${label}</button>`;
  let acts = '';
  if (t.status === 'new') acts += btn('start', 'התחל טיפול', 'pri');
  if (t.status === 'in_progress') acts += btn('submit', t.requires_approval && !t.approved_by ? 'הגש לאישור' : 'סמן כבוצע', 'pri');
  if (t.status === 'awaiting_approval') acts += can ? btn('approve', 'אשר', 'pri') + btn('reject', 'החזר לטיפול') : '<span class="note">ממתין לאישור בעלים / מנהל</span>';
  if (t.status === 'awaiting_verification') acts += btn('recheck_now', 'הרץ בדיקה חוזרת', 'pri') + (st.me.demo ? btn('simulate_fix', 'דמו: הדמה תיקון') : '');
  if (t.status === 'closed') acts += btn('reopen', 'פתח מחדש');
  if (t.status !== 'closed') acts += btn('log_time', 'תעד זמן');
  const v = t.verification;
  return `<div class="card tk sev-${t.severity === 'red' ? 'red' : t.severity === 'imp' ? 'imp' : 'yellow'} ${hl ? 'hl' : ''}" id="tk_${t.id}">
    <div class="tkh"><span class="t">${esc(t.title)}</span>${late ? '<span class="pill p-red">באיחור</span>' : ''}${t.requires_approval ? `<span class="pill p-yellow">${t.approved_by ? 'אושר ע"י ' + esc(t.approved_by) : 'דורש אישור'}</span>` : ''}</div>
    <div class="flow">${FLOW.filter((s) => s !== 'awaiting_approval' || t.requires_approval).map((s) => `<span class="${s === t.status || (t.status === 'done' && s === 'awaiting_verification') ? 'on' : FLOW.indexOf(s) < idx ? 'past' : ''}">${STATUS[s]}</span>`).join('')}</div>
    <div class="row small"><span>אחראי:</span><select class="inp sm" data-act-change="reassign" data-tid="${t.id}" aria-label="אחראי" ${t.status === 'closed' ? 'disabled' : ''}>${memberOpts(t.assignee)}</select><span class="muted">יעד ${N(dayLabel(t.due_day))}</span>${t.minutes_spent ? `<span class="muted">· ${N(t.minutes_spent)} דק' עבודה</span>` : ''}<a href="#/client/${t.client_id}" class="small" style="margin-inline-start:auto">לתיק הלקוח</a></div>
    ${t.description ? `<div class="small tx2">${esc(t.description)}</div>` : ''}
    ${t.plan?.length ? `<ol class="plan">${t.plan.map((x) => `<li><span>${esc(x.text)} ${SENS.has(x.actionType) ? `<span class="pill p-yellow">${esc(ACTION[x.actionType])}</span>` : ''}</span></li>`).join('')}</ol>` : ''}
    ${t.success ? `<div class="okbox small"><b>מדד הצלחה:</b> ${esc(t.success.text)}${t.recheck_day ? ` · בדיקה חוזרת ב-${N(dayLabel(t.recheck_day))}` : ''}</div>` : ''}
    ${v ? `<div class="okbox small" style="background:var(--${v.ok ? 'gbg' : 'rbg'})"><b>${v.ok ? 'אומת בנתונים' : 'הבדיקה החוזרת נכשלה'}:</b> עלות לליד ${N(money(v.before?.cpl))} ← ${N(money(v.after?.cpl))} · ${N(v.after?.leads)} לידים ב-${N(v.after?.days)} ימים</div>` : ''}
    <div class="row">${acts}</div>
    <details><summary>היסטוריה (${t.history.length})</summary><div class="hist">${t.history.map((h) => `<div>${N(dayLabel(h.day))} · ${esc(h.who)}: ${esc(h.a)}</div>`).join('')}</div></details></div>`;
}
A.task = async (b, arg) => {
  const [tid, action] = arg.split('|');
  let extra;
  if (action === 'reject') extra = prompt('סיבה (לא חובה)') || undefined;
  if (action === 'log_time') { extra = prompt('כמה דקות עבדת על המשימה?', '15'); if (!extra) return; }
  b.disabled = true;
  try {
    const r = await api(`/api/pulse/tasks/${tid}/${action}`, { method: 'POST', body: { extra } });
    toast(r.msg, r.ok ? '' : 'warn');
    if (st.tour) V.tourAfter(action);
    await refreshMe(); render();
  } finally { b.disabled = false; }
};
document.addEventListener('change', async (e) => {
  const s = e.target.closest('[data-act-change="reassign"]');
  if (!s) return;
  const r = await api(`/api/pulse/tasks/${s.dataset.tid}/reassign`, { method: 'POST', body: { extra: s.value } });
  toast(r.msg, r.ok ? '' : 'warn'); render();
});

// ================================================================ Ask ClientPulse
const chatLog = [];
V.ask = async (view, p) => {
  const meta = await api('/api/pulse/ask/suggestions');
  view.innerHTML = `<div class="card chat"><div class="mh"><b>${ic('chat', 16)} Ask ClientPulse</b><span class="sp"></span><span class="engine">${meta.engine ? 'מודל: ' + esc(meta.engine) + ' · מנסח רק מתוך נתוני המערכת' : 'מנוע כללים (אין מודל AI מחובר) · עונה רק מנתוני המערכת'}</span></div>
    <div class="msgs" id="msgs">${chatLog.length ? '' : `<div class="ma"><div>אני עונה רק מתוך הנתונים במערכת — עם המספרים שמאחורי כל תשובה ומה עוד לא ידוע. נסו:</div><div class="chips" style="margin-top:10px">${meta.suggestions.map((s) => `<button class="chip" data-act="ask" data-arg="${esc(s)}">${esc(s)}</button>`).join('')}</div></div>`}</div>
    <form class="composer" id="askF"><input class="inp" id="askQ" placeholder="למשל: למה לקוח מסוים הפך לאדום?" maxlength="500" autocomplete="off"><button class="btn pri">שאל</button></form></div>`;
  chatLog.forEach(paintMsg);
  $('#askF').onsubmit = (e) => { e.preventDefault(); const q = $('#askQ').value.trim(); if (q) doAsk(q); };
  if (p.q) { history.replaceState(null, '', '#/ask'); doAsk(p.q); }
};
function paintMsg(m) {
  const box = $('#msgs');
  if (!box) return;
  if (m.u) box.insertAdjacentHTML('beforeend', `<div class="mu">${esc(m.u)}</div>`);
  else box.insertAdjacentHTML('beforeend', `<div class="ma"><div>${esc(m.text)}</div>${m.evidence?.length ? `<ul class="ev">${m.evidence.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${m.links?.length ? `<div class="chips" style="margin-top:8px">${m.links.map((l) => `<button class="chip" data-act="go" data-arg="${esc(l.route)}">${esc(l.label)}</button>`).join('')}</div>` : ''}
    ${m.follow?.length ? `<div class="chips" style="margin-top:8px">${m.follow.map((f) => `<button class="chip" data-act="ask" data-arg="${esc(f)}">${esc(f)}</button>`).join('')}</div>` : ''}
    <div class="note" style="margin-top:6px">${m.engine === 'rules' ? 'מנוע כללים' : 'נוסח ע"י ' + esc(m.engine)}${m.engine_error ? ' · ' + esc(m.engine_error) : ''}</div></div>`);
  box.scrollTop = box.scrollHeight;
}
async function doAsk(q) {
  const u = { u: q }; chatLog.push(u); paintMsg(u);
  const inp = $('#askQ'); if (inp) inp.value = '';
  $('#msgs').insertAdjacentHTML('beforeend', '<div class="ma" id="thinking"><div class="sk" style="width:160px;height:12px"></div></div>');
  try { const r = await api('/api/pulse/ask', { method: 'POST', body: { q } }); chatLog.push(r); $('#thinking')?.remove(); paintMsg(r); }
  catch { $('#thinking')?.remove(); }
}
A.ask = (b, q) => doAsk(q);

// ================================================================ הזדמנויות · רווחיות · צוות · ערך · דוחות
V.opps = async (view) => {
  const list = await api('/api/pulse/opportunities');
  view.innerHTML = `<p class="tx2">הזדמנויות מזוהות מהנתונים בלבד. הערכת פוטנציאל מוצגת רק כשאפשר לחשב אותה — בלי הבטחות הכנסה.</p>
  <div class="cards">${list.map((o) => `<div class="card pad sev-imp"><div class="row"><a href="#/client/${o.client_id}"><b>${esc(o.client)}</b></a>${demoTag(o.is_demo)}</div>${oppCard(o, o.client_id)}</div>`).join('') || `<div class="card">${empty('לא זוהו כרגע הזדמנויות מבוססות נתונים')}</div>`}</div>`;
};
V.profit = async (view) => {
  const d = await api('/api/pulse/profit');
  view.innerHTML = `<div class="kpis">${kpi('הכנסה חודשית לסוכנות', money(d.total.fee))}${kpi('עלויות (עבודה + נוספות)', money(d.total.costs))}${kpi('רווח גולמי', money(d.total.profit))}${kpi('שיעור רווחיות', pctf(d.total.margin))}</div>
  <div class="card scroll"><table class="tbl"><tr><th>לקוח</th><th>הכנסה</th><th class="hide-m">שעות</th><th class="hide-m">עלות עבודה</th><th>רווח</th><th>רווחיות</th></tr>
  ${d.clients.map((c) => `<tr class="click" data-act="go" data-arg="client/${c.id}"><td>${esc(c.name)} ${demoTag(c.is_demo)}</td><td>${N(money(c.fee))}</td><td class="hide-m">${N(c.hours)}</td><td class="hide-m">${N(money(c.labor))}</td><td class="${c.profit < 0 ? 'bad' : ''}">${N(money(c.profit))}</td><td><span class="pill p-${c.margin < 0.2 ? 'red' : c.margin < 0.4 ? 'yellow' : 'green'}">${N(pctf(c.margin))}</span></td></tr>`).join('')}</table></div>
  <p class="note">${esc(d.note)}</p>${d.missing.length ? `<p class="small tx2">חסרים נתוני הכנסה ל-${N(d.missing.length)} לקוחות: ${d.missing.slice(0, 8).map((m) => `<a href="#/client/${m.id}">${esc(m.name)}</a>`).join(', ')}</p>` : ''}`;
};
V.team = async (view) => {
  const d = await api('/api/pulse/team');
  view.innerHTML = `<p class="tx2">מדידה של משימות ותוצאות מקצועיות בלבד — לא מעקב אחרי אנשים.</p>
  <div class="card scroll"><table class="tbl"><tr><th>עובד</th><th>תפקיד</th><th>לקוחות</th><th>פתוחות</th><th>באיחור</th><th>דחופות</th><th class="hide-m">זמן מתועד</th></tr>
  ${d.team.map((m) => `<tr><td>${esc(m.name)} ${m.is_demo ? demoTag(1) : ''}</td><td>${esc(m.role || '')}${m.approver ? ' · <span class="pill p-gray">מאשר</span>' : ''}</td><td>${N(m.clients)}</td><td>${N(m.open)}</td><td class="${m.late ? 'bad' : ''}">${N(m.late)}</td><td>${N(m.red)}</td><td class="hide-m">${N(Math.round(m.minutes / 6) / 10)} ש'</td></tr>`).join('')}</table></div>
  ${d.can_manage ? `<form class="card pad row" id="tmF" style="margin-top:14px"><input class="inp" id="tmN" placeholder="שם העובד" required><input class="inp" id="tmR" placeholder="תפקיד" value="מנהל/ת קמפיינים"><label class="row small"><input type="checkbox" id="tmA"> רשאי לאשר</label><button class="btn sec sm">הוספה</button></form><p class="note">עובדים כאן הם רשומות לשיוך משימות. גישה למערכת = משתמש P1 בחשבון. הרשאת אישור בפועל: בעלים / מנהל בחשבון.</p>` : ''}`;
  if (d.can_manage) view.insertAdjacentHTML('beforeend', `<form class="card pad" id="lgF" style="margin-top:14px"><div class="h2">${ic('team')} כניסה למערכת לעובד</div><div class="frm">
    <div class="fld"><label for="lgN">שם</label><input class="inp" id="lgN" required></div><div class="fld"><label for="lgE">אימייל</label><input class="inp" id="lgE" type="email" required dir="ltr"></div>
    <div class="fld"><label for="lgP">סיסמה ראשונית (10 תווים ומעלה)</label><input class="inp" id="lgP" type="text" minlength="10" required dir="ltr"></div>
    <div class="fld"><label for="lgR">הרשאה</label><select class="inp" id="lgR"><option value="member">עובד — מטפל במשימות, לא מאשר</option><option value="admin">מנהל — מאשר פעולות ומשנה הגדרות</option></select></div></div>
    <button class="btn pri sm">יצירת כניסה</button><p class="note">ההרשאות נאכפות בשרת. עובד לא יכול לאשר שינויי תקציב או קמפיין ולא לשנות ספים ואוטומציות.</p></form>`);
  const lg = $('#lgF');
  if (lg) lg.onsubmit = async (e) => { e.preventDefault(); const r = await api('/api/pulse/team/login', { method: 'POST', body: { name: $('#lgN').value, email: $('#lgE').value, password: $('#lgP').value, role: $('#lgR').value } }); toast(r.msg); await refreshMe(); render(); };
  const f = $('#tmF');
  if (f) f.onsubmit = async (e) => { e.preventDefault(); await api('/api/pulse/team', { method: 'POST', body: { name: $('#tmN').value, role: $('#tmR').value, approver: $('#tmA').checked } }); await refreshMe(); render(); };
};
V.impact = async (view) => {
  const d = await api('/api/pulse/impact');
  const tm = d.time;
  view.innerHTML = `<div class="kpis">${kpi('חריגות שזוהו', d.detected)}${kpi('טופלו', d.handled, d.handle_rate != null ? 'שיעור טיפול ' + pctf(d.handle_rate) : '')}${kpi('אומתו בנתונים', d.verified, 'בדיקה חוזרת הצליחה')}${kpi('זמן ממוצע עד טיפול', d.avg_days_to_handle != null ? d.avg_days_to_handle + ' ימים' : '—')}</div>
  <div class="grid g2"><div class="card pad"><div class="h2">${ic('trophy')} לפני ואחרי — רק טיפולים שאומתו במדידה</div>
    ${d.events.length ? `<table class="ft"><tr><th>טיפול</th><th>עלות לליד לפני</th><th>אחרי</th><th>הערכת חיסכון שבועי</th></tr>${d.events.map((e) => `<tr><td><a href="#/client/${e.client_id}">${esc(e.title)}</a></td><td>${N(money(e.before.cpl))}</td><td>${N(money(e.after.cpl))}</td><td>${N(e.estWeekly ? money(e.estWeekly) : '—')}</td></tr>`).join('')}</table><p class="note">הערכת חיסכון = (עלות לליד לפני − אחרי) × לידים ליום אחרי × 7. מוצגת רק כשהעלות ירדה. קשר סיבתי לטיפול לא מוכח — זו מדידה לפני/אחרי.</p>` : empty('עדיין אין טיפולים שאומתו בנתונים. סמנו משימה כבוצעה — המערכת תבדוק אוטומטית אם המדד חזר ליעד.')}</div>
  <div class="stack"><div class="card pad"><div class="h2">התרעות מוקדמות ואיכות</div><div class="kv"><span>נתפסו בצהוב ולא הגיעו לאדום</span><b>${N(d.early)}</b><span>סומנו "מועילה"</span><b>${N(d.useful)}</b><span>סומנו "התראת שווא"</span><b>${N(d.false_positives)}</b><span>משימות שנוצרו</span><b>${N(d.tasks)}</b></div></div>
    <div class="card pad"><div class="h2">הערכת זמן<span class="sp"></span><span class="pill p-gray">הערכה, לא מדידה</span></div>
      <p class="small">בדיקה ידנית: ${N(tm.manualMin)} דק' בחודש · עם המערכת: ${N(tm.sysMin)} דק' · חיסכון משוער: <b>${N(Math.round(tm.savedHours))} שעות</b></p>
      <form id="asF" class="frm"><div class="fld"><label for="as1">דק' לבדיקה ידנית של לקוח ביום</label><input class="inp" id="as1" type="number" min="0" value="${tm.assumptions.minPerClient}"></div><div class="fld"><label for="as2">דק' לטיפול בהתראה</label><input class="inp" id="as2" type="number" min="0" value="${tm.assumptions.minPerAlert}"></div><div class="fld"><label for="as3">ימי עבודה בחודש</label><input class="inp" id="as3" type="number" min="1" max="31" value="${tm.assumptions.workdays}"></div><button class="btn sec sm">עדכון הנחות</button></form><p class="note">${esc(tm.note)}</p></div></div></div>`;
  $('#asF').onsubmit = async (e) => { e.preventDefault(); await api('/api/pulse/impact/assumptions', { method: 'PUT', body: { minPerClient: Number($('#as1').value), minPerAlert: Number($('#as2').value), workdays: Number($('#as3').value) } }); render(); };
};
V.reports = async (view) => {
  const d = await api('/api/pulse/clients');
  view.innerHTML = `<div class="grid g2"><div class="card pad"><div class="h2">${ic('report')} דוח שבועי למשרד</div><p class="tx2 small">מצב התיק, טיפול ותוצאות, הלקוחות בעדיפות ומה עושים השבוע.</p><a class="btn pri sm" href="/api/pulse/reports/weekly.html" target="_blank" rel="noopener">פתיחה (להדפסה / PDF)</a></div>
  <div class="card pad"><div class="h2">${ic('users')} דוח ביצועים ללקוח</div><div class="row"><select class="inp" id="rc" style="flex:1">${d.clients.map((c) => `<option value="${c.id}">${esc(c.name)}${c.is_demo ? ' (דמו)' : ''}</option>`).join('')}</select><select class="inp" id="rd"><option value="7">7 ימים</option><option value="30" selected>30 ימים</option><option value="90">90 ימים</option></select></div>
    <div class="row" style="margin-top:10px"><button class="btn pri sm" data-act="openRep" data-arg="html">HTML</button><button class="btn sec sm" data-act="openRep" data-arg="pdf">PDF</button></div><p class="note">הדוח נבנה מנתונים קיימים בלבד: מדדים, השוואה לתקופה קודמת, גרף, מה טופל ואומת, וצעדים הבאים.</p></div></div>`;
};
A.openRep = (b, kind) => {
  if (window.__SNAPSHOT__) return toast('דוחות HTML ו-PDF נוצרים במערכת המלאה (בגרסת התצוגה אין שרת)', 'warn'); const u = `/api/pulse/reports/client/${$('#rc').value}.${kind}?days=${$('#rd').value}`; if (kind === 'pdf') location.href = u; else window.open(u, '_blank', 'noopener'); };

// ================================================================ אוטומציות · חיבורים · Demo Lab
V.automations = async (view) => {
  const d = await api('/api/pulse/automations');
  const can = st.me.can_approve;
  view.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="rule"><div style="flex:1"><b>בדיקה יומית אוטומטית בשרת</b><div class="small tx2">${esc(d.schedule)}</div></div><button class="sw ${d.auto_daily ? 'on' : ''}" data-act="rule" data-arg="auto_daily|${d.auto_daily ? 0 : 1}" ${can ? '' : 'disabled'} aria-label="בדיקה יומית"></button></div></div>
  <div class="card">${d.rules.map((r) => `<div class="rule"><div style="flex:1"><div><b>כאשר</b> ${esc(r.when)} <b>←</b> ${esc(r.then)}</div><div class="note">רץ ${N(r.runs)} פעמים · מניעת כפילות לפי מזהה ריצה · כישלון → עד 3 ניסיונות</div></div>
    <button class="btn sec sm" data-act="ruleTest" data-arg="${r.id}">בדיקה יבשה</button><button class="sw ${r.on ? 'on' : ''}" data-act="rule" data-arg="${r.id}|${r.on ? 0 : 1}" ${can ? '' : 'disabled'} aria-label="הפעלה"></button></div>`).join('')}</div>
  <p class="note">פעולות שמשנות תקציב, קמפיין או שולחות הודעה ללקוח לא מבוצעות אוטומטית — הן עוברות דרך אישור בעלים / מנהל במשימה.${can ? '' : ' שינוי כללים מותר לבעלים / מנהל.'}</p>
  <div class="card pad" style="margin-top:14px"><div class="h2">יומן ריצות</div><div class="scroll"><table class="tbl"><tr><th>כלל</th><th>תוצאה</th><th>סטטוס</th><th class="hide-m">ניסיונות</th></tr>${d.log.map((x) => `<tr><td>${esc(d.rules.find((r) => r.id === x.rule_id)?.when || x.rule_id)}</td><td>${esc(x.detail || '')}</td><td><span class="pill p-${x.status === 'ok' ? 'green' : 'red'}">${x.status === 'ok' ? 'בוצע' : 'נכשל'}</span></td><td class="hide-m">${N(x.attempts)}</td></tr>`).join('') || '<tr><td colspan="4">' + empty('עוד לא רצו אוטומציות') + '</td></tr>'}</table></div></div>`;
};
A.rule = async (b, arg) => { const [id, on] = arg.split('|'); await api(`/api/pulse/automations/${id}`, { method: 'PUT', body: { on: on === '1' } }); toast(on === '1' ? 'הופעל' : 'כובה'); render(); };
A.ruleTest = async (b, id) => {
  const r = await api(`/api/pulse/automations/${id}/test`, { method: 'POST' });
  modal(`<div class="mh"><b>בדיקה יבשה</b><span class="note">${esc(r.note)}</span><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div><div class="pad">${r.would.length ? `<ul class="ul">${r.would.map((w) => `<li>${esc(w.would)}</li>`).join('')}</ul>` : empty('במצב הנוכחי הכלל לא היה מבצע דבר (או שכבר בוצע — מניעת כפילות)')}</div>`);
};
V.integrations = async (view) => {
  const list = await api('/api/pulse/integrations');
  const S2 = { connected: ['green', 'מחובר'], available: ['imp', 'זמין'], off: ['none', 'כבוי'], not_connected: ['none', 'לא מחובר'] };
  view.innerHTML = `<p class="tx2">חיבור נחשב "מחובר" רק אחרי בדיקה מוצלחת מול השירות. מפתחות נשמרים בצד שרת בלבד. נתוני דמו מופרדים לגמרי מנתונים אמיתיים.</p>
  <div class="cards">${list.map((i) => `<div class="card pad"><div class="row"><b>${esc(i.name)}</b><span class="sp"></span><span class="pill p-${S2[i.status][0] === 'none' ? 'gray' : S2[i.status][0]}">${S2[i.status][1]}</span></div>${i.note ? `<p class="small tx2">${esc(i.note)}</p>` : ''}${i.needs ? `<p class="small"><b>מה צריך:</b> ${esc(i.needs)}</p>` : ''}</div>`).join('')}</div>
  <div class="card pad" style="margin-top:14px"><div class="h2">ארכיטקטורה</div><p class="small tx2">ספק נתונים (דמו / CSV / Meta / Google) → טבלת נתונים יומית אחת לכל לקוח → מנוע ניתוח סטטיסטי → מחזור חיים של התראות → משימות ואישורים → אוטומציות מתוזמנות בשרת → בדיקה חוזרת → הוכחת ערך. מנוע הניתוח לא יודע מאיזה ספק הגיעו הנתונים — לכן חיבור חדש לא דורש לשנות את הניתוח.</p></div>`;
};
V.lab = async (view) => {
  const d = await api('/api/pulse/lab');
  if (!d.demo) {
    view.innerHTML = `<div class="card pad"><div class="h2">${ic('flask')} Demo Lab</div><p class="tx2">Demo Lab פועל רק בסביבת דמו, כדי שתרחישים לא יגעו בנתונים אמיתיים.</p><button class="btn acc" data-act="startDemo">${ic('play', 15)} הפעל סביבת דמו</button></div>`;
    return;
  }
  const cl = (await api('/api/pulse/clients')).clients.filter((c) => c.is_demo);
  view.innerHTML = `<div class="card pad" style="margin-bottom:14px"><div class="row"><div style="flex:1"><b>שעון הדמו: ${N(st.me.ref_label)}</b> <span class="note">(+${N(d.offset)} ימים)</span><div class="small tx2">כל קידום מסנכרן את נתוני הדמו של היום החדש, מריץ את המנוע, האוטומציות והבדיקות החוזרות — כמו לילה אמיתי בשרת.</div></div>
    <button class="btn sec sm" data-act="advance" data-arg="1">+1 יום</button><button class="btn sec sm" data-act="advance" data-arg="3">+3 ימים</button><button class="btn sec sm" data-act="advance" data-arg="7">+7 ימים</button></div></div>
  <div class="row" style="margin-bottom:10px"><label class="small" for="labC">להפעיל על:</label><select class="inp" id="labC" style="flex:1;max-width:360px"><option value="">בחירה אוטומטית של לקוח ירוק</option>${cl.map((c) => `<option value="${c.id}">${esc(c.name)} · ${SL[c.status]}</option>`).join('')}</select></div>
  <div class="cards">${d.scenarios.map((s) => `<div class="card pad"><b>${esc(s.name)}</b><p class="small tx2">${esc(s.desc)}</p><button class="btn sec sm" data-act="scenario" data-arg="${s.id}">${ic('play', 13)} הפעל</button></div>`).join('')}</div>
  <div class="card pad" style="margin-top:14px"><div class="row"><div style="flex:1"><b>איפוס</b><div class="small tx2">בונה מחדש 50 לקוחות ומוחק משימות, התראות ויומנים של הדמו.</div></div><button class="btn sec sm" data-act="startDemo">איפוס דמו</button><button class="btn dng sm" data-act="removeDemo">הסרת הדמו</button></div></div>`;
};
A.scenario = async (b, sid) => {
  b.disabled = true;
  try {
    const r = await api('/api/pulse/lab/scenario', { method: 'POST', body: { scenario: sid, client_id: $('#labC')?.value || undefined } });
    toast(r.msg, r.ok ? '' : 'warn'); await refreshMe(); st.clients = null;
    if (r.route) go(r.route);
  } finally { b.disabled = false; }
};
A.removeDemo = async () => { if (!confirm('להסיר את כל נתוני הדמו? לקוחות אמיתיים לא נפגעים.')) return; await api('/api/pulse/demo', { method: 'DELETE' }); st.clients = null; await refreshMe(); go('home'); };

// ================================================================ סיור: חמש דקות בחיים של מנהל משרד פרסום
const TOUR = [
  { t: 'בוקר. פותחים מסך אחד', d: 'במקום לעבור על 50 חשבונות מודעות: הרמזור, מה דחוף ו"מה עושים היום" — מחושבים מהנתונים.', route: 'home' },
  { t: 'לקוח אדום — למה?', d: 'לוחצים על הפעולה הראשונה. רואים עובדות (מה השתנה), השערות לפי משקל בנתונים, ותוכנית פעולה עם מדד הצלחה.', run: 'openRed' },
  { t: 'פותחים משימה ומשייכים', d: 'בכרטיס ההתראה: בחרו עובד ולחצו "צור משימה ושייך" (או המשיכו — נפתח אוטומטית).', run: 'ensureTask' },
  { t: 'טיפול ואישור', d: 'העובד מתחיל טיפול ומגיש. שינוי תקציב / קמפיין עובר אישור מנהל. כאן זה קורה בלחיצה אחת.', run: 'handle' },
  { t: 'מדמים תיקון ומקדמים את השעון', d: 'בדמו מחילים את השפעת התיקון על הנתונים ומקדמים 4 ימים. השרת מריץ את הבדיקה החוזרת לבד.', run: 'fixAdvance' },
  { t: 'הוכחה: האם זה עבד?', d: 'המשימה נסגרה רק אם המדד חזר ליעד. מרכז הערך מציג לפני/אחרי מתוך מדידה.', route: 'impact' },
  { t: 'שואלים את הסוכן', d: '"מה השתנה בשבוע האחרון?" — תשובה עם ראיות מתוך יומן המערכת.', route: 'ask?q=' + encodeURIComponent('מה השתנה בשבוע האחרון?') },
];
A.tourStart = () => { st.tour = { i: 0 }; tourStep(); };
V.tourRender = () => {
  let el = document.getElementById('tour');
  if (!st.tour) { el?.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'tour'; el.className = 'card tour'; document.body.appendChild(el); }
  const s = TOUR[st.tour.i];
  el.innerHTML = `<div class="row"><span class="eyebrow">חמש דקות בחיים של מנהל משרד · ${st.tour.i + 1}/${TOUR.length}</span><span class="sp"></span><button class="iconbtn" data-act="tourEnd" aria-label="סגירה">${ic('x', 14)}</button></div>
    <div class="steps">${TOUR.map((_, i) => `<i class="${i <= st.tour.i ? 'on' : ''}"></i>`).join('')}</div><b>${esc(s.t)}</b><p class="small tx2">${esc(s.d)}</p>
    <div class="row">${st.tour.i < TOUR.length - 1 ? '<button class="btn pri sm" data-act="tourNext">הבא</button>' : '<button class="btn pri sm" data-act="tourEnd">סיום</button>'}</div>`;
};
A.tourNext = () => { st.tour.i++; tourStep(); };
A.tourEnd = () => { st.tour = null; V.tourRender(); };
V.tourAfter = () => {};
async function tourStep() {
  const s = TOUR[st.tour.i];
  try {
    if (s.route) go(s.route);
    if (s.run === 'openRed') {
      const o = await api('/api/pulse/overview');
      const first = o.today.find((x) => x.severity === 'red') || o.today[0];
      st.tour.client = first?.clientId; go(first ? 'client/' + first.clientId : 'clients');
    }
    if (s.run === 'ensureTask' && st.tour.client) {
      const d = await api(`/api/pulse/clients/${st.tour.client}`);
      const a = d.alerts[0];
      if (a) { const t = a.task || await api('/api/pulse/tasks', { method: 'POST', body: { alert_key: a.key } }); st.tour.task = t.id; go('task/' + t.id); }
    }
    if (s.run === 'handle' && st.tour.task) {
      for (const act of ['start', 'submit', 'approve']) {
        const r = await api(`/api/pulse/tasks/${st.tour.task}/${act}`, { method: 'POST', body: {} });
        if (!r.ok && act !== 'approve') break;
      }
      await refreshMe(); go('task/' + st.tour.task);
    }
    if (s.run === 'fixAdvance' && st.tour.task) {
      await api(`/api/pulse/tasks/${st.tour.task}/simulate_fix`, { method: 'POST', body: {} });
      const r = await api('/api/pulse/lab/advance', { method: 'POST', body: { days: 4 } });
      toast(r.msg); await refreshMe(); go('task/' + st.tour.task);
    }
  } catch { /* הודעה כבר הוצגה */ }
  V.tourRender();
}
