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
V.home = async (view) => {
  const [b, o, ab] = await Promise.all([api('/api/pulse/brief'), api('/api/pulse/overview'), api('/api/pulse/alerts')]);
  const c = b.counts, hour = new Date().getHours(), greet = hour < 12 ? 'בוקר טוב' : hour < 18 ? 'צהריים טובים' : 'ערב טוב';
  const tm = o.time;
  view.innerHTML = `
  <div class="hello"><div><h2>${greet}, ${esc(st.me.user.name)}</h2>
    <div class="meta"><span>${b.since ? 'מה השתנה מאז הכניסה הקודמת שלך' : 'תמונת המצב של היום'} · נתונים עד ${N(st.me.ref_label)}</span>${o.demo ? '<span class="mock">דמו</span>' : ''}</div></div>
    <div class="sp"></div>${o.demo && !window.__SNAPSHOT__ ? `<button class="btn sec sm" data-act="tourStart">${ic('play', 14)} הדגמה: 5 דקות בחיים של מנהל</button>` : ''}</div>
  <div class="lights">${[['red', 'דחוף', c.red], ['yellow', 'במעקב', c.yellow], ['green', 'תקין', c.green], ['nodata', 'אין מספיק מידע', c.nodata]].map(([k, t, n]) =>
    `<button class="light l-${k}" data-act="go" data-arg="clients?f=${k}"><i></i><b>${N(n)}</b><span>${t}</span></button>`).join('')}
    ${tm ? `<div class="light saved-mini"><span class="note">נבדקו ${N(tm.clients)} חשבונות ב-${N(tm.scan_ms)} מ"ש</span><b>~${N(Math.round(tm.saved_min / 6) / 10)} שעות</b><span class="note">בדיקה ידנית שנחסכה היום (הערכה)</span></div>` : ''}</div>
  <div class="card pad brief"><div class="h2">${ic('zap')} מה דורש אותך עכשיו<span class="sp"></span><span class="note">${b.items.length} הכי חשובים, לפי חומרה, דחיפות והשפעה${b.more ? ` · ועוד ${N(b.more)} ב<a href="#/alerts">כל החריגות</a>` : ''}</span></div>
    ${b.items.length ? b.items.map((x, i) => `<div class="bi sev-${x.severity === 'imp' ? 'imp' : x.severity === 'green' ? 'green' : x.severity}"><span class="n">${i + 1}</span><div class="bt"><b>${esc(x.title)}</b><div class="small tx2">${esc(x.detail)}</div></div>
      <button class="btn ${i < 3 ? 'pri' : 'sec'} sm" ${x.action.route ? `data-act="go" data-arg="${esc(x.action.route)}"` : `data-act="${esc(x.action.act)}" data-arg="${esc(x.action.arg)}"`}>${esc(x.action.label)}</button></div>`).join('')
    : empty('אין כרגע שום דבר דחוף. כל הלקוחות בטווח התקין ולכל בעיה יש מטפל.')}</div>
  ${b.verified.length ? `<div class="card pad" style="margin-top:14px"><div class="h2">${ic('trophy')} טופל ואומת בנתונים</div>${b.verified.map((v) => `<div class="fi"><a href="#/client/${v.client_id}">${esc(v.title)}</a><span class="sp"></span><span class="ok small">עלות לליד ${N(money(v.before.cpl))} ← ${N(money(v.after.cpl))}</span></div>`).join('')}</div>` : ''}
  <div class="card pad" style="margin-top:14px"><div class="h2">${ic('users')} רמזור הלקוחות<span class="sp"></span><a class="small" href="#/clients">לרשימה המלאה</a></div>
    <div class="tiles">${ab.board.map((x) => `<button class="tile t-${x.improved && x.status === 'green' ? 'imp' : x.status}" data-act="go" data-arg="client/${x.id}" title="${esc(x.title)}"><b>${esc(x.name)}</b><span>${esc(x.status === 'nodata' ? 'אין מספיק מידע' : x.title)}</span></button>`).join('')}</div></div>`;
};
A.setSat = async (b, arg) => { const [cid, n] = arg.split('|'); await api(`/api/pulse/clients/${cid}/satisfaction`, { method: 'PUT', body: { score: Number(n) } }); toast('שביעות הרצון עודכנה'); render(); };
A.commitDone = async (b, id) => { const r = await api(`/api/pulse/commitments/${id}`, { method: 'PATCH', body: { status: 'done' } }); toast(r.msg); render(); };

// ================================================================ ניתוח מודעות (הבקשה של יובל: מה לשפר בהצעה, בקופי ובקריאייטיב)
V.ads = async (view, p) => {
  const d = await api('/api/pulse/ads' + (p.client ? `?client=${encodeURIComponent(p.client)}` : ''));
  const an = d.analysis, s = an.summary;
  const tone = { red: 'p-red', yellow: 'p-yellow', green: 'p-green' };
  view.innerHTML = `<div class="row" style="margin-bottom:12px"><select class="inp" id="adC" style="flex:1;max-width:460px" aria-label="לקוח">${d.clients.map((c) => `<option value="${c.id}" ${d.client && c.id === d.client.id ? 'selected' : ''}>${esc(c.name)} · ${esc(c.headline)}</option>`).join('')}</select>
    <span class="engine">${d.ai ? 'הצעות קופי: ' + esc(d.ai) : 'בדיקה לפי כללים · הצעות קופי יופעלו עם Gemini'}</span></div>
  ${d.note ? `<div class="card pad">${esc(d.note)}</div>` : ''}
  ${s ? `<div class="card pad" style="margin-bottom:14px"><div class="row"><div><h3 style="margin:0">${esc(d.client.name)} ${demoTag(d.client.is_demo)}</h3><div class="note">${esc(s.note)}</div></div><span class="sp"></span>
    <div class="sv"><div class="note">מסקנה</div><b>${esc(s.headline)}</b></div>${s.waste ? `<div class="sv"><div class="note">כסף שהולך על מודעות חלשות (7 ימים)</div><b class="bad">${N(money(s.waste))}</b></div>` : ''}${s.winner ? `<div class="sv"><div class="note">המנצחת</div><b class="ok">${esc(s.winner)}</b></div>` : ''}</div></div>` : ''}
  <div class="stack">${an.ads.map((a) => `<div class="card pad sev-${a.tone === 'green' ? 'green' : a.tone}">
    <div class="row"><b>${esc(a.name)}</b>${demoTag(a.is_demo)}<span class="pill ${tone[a.tone]}">${esc(a.verdict)}</span><span class="sp"></span>
      <span class="small tx2">הוצאה ${N(money(a.spend))} · CTR ${N(pctf(a.ctr, 2))} · המרה ${N(pctf(a.cvr, 1))} · עלות לליד ${N(money(a.cpl))} · תדירות ${N(a.frequency)}</span></div>
    <div class="adbox"><div class="adh">${esc(a.headline)}</div><div class="small">${esc(a.text)}</div><div class="row small" style="margin-top:6px">${Object.entries(a.checks).map(([k, v]) => `<span class="pill ${v ? 'p-green' : 'p-red'}">${v ? '✓' : '✗'} ${esc(k)}</span>`).join('')}</div></div>
    ${a.recs.length ? `<div class="recs">${a.recs.map((r) => `<div class="rec"><span class="pill p-gray">${esc(r.area)}</span><div><b>${esc(r.issue)}</b> — ${esc(r.why)}<div class="small">מה לעשות: ${esc(r.do)}</div></div></div>`).join('')}</div>` : '<p class="small ok">אין מה לתקן במודעה הזו לפי הנתונים.</p>'}
    <div class="row" style="margin-top:10px">${a.recs.length ? `<button class="btn pri sm" data-act="adRewrite" data-arg="${esc(a.id)}">${ic('spark', 13)} הצע קופי משופר</button><button class="btn sec sm" data-act="oppTask" data-arg="${esc(d.client.id)}|${esc(a.name + ': ' + a.recs[0].do)}">צור משימה</button>` : ''}</div>
    <div id="rw_${esc(a.id)}"></div></div>`).join('') || (d.note ? '' : `<div class="card">${empty('אין מודעות להצגה')}</div>`)}</div>`;
  $('#adC').onchange = (e) => go('ads?client=' + e.target.value);
};
A.adRewrite = async (b, id) => {
  b.disabled = true; b.textContent = 'כותב…';
  try {
    const r = await api(`/api/pulse/ads/${encodeURIComponent(id)}/rewrite`, { method: 'POST' });
    document.getElementById('rw_' + id).innerHTML = `<div class="recs" style="margin-top:10px">${r.variants.map((v) => `<div class="rec"><span class="pill p-imp">גרסה</span><div><b>${esc(v.headline)}</b><div class="small">${esc(v.text)}</div><div class="note">${esc(v.why)}</div></div><button class="btn sec sm" data-act="copy" data-arg="${esc(v.headline + '\n' + v.text)}">העתק</button></div>`).join('')}<p class="note">נכתב ע"י ${esc(r.engine)} מתוך המודעה והבעיות שזוהו. לבדוק לפני שימוש.</p></div>`;
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
  const d = await api('/api/pulse/clients');
  st.clients = d.clients;
  const f = p.f || 'all', q = p.q || '';
  const rowsF = d.clients.filter((c) => (f === 'all' || (f === 'improved' ? c.improved : c.status === f)) && (!q || c.name.includes(q) || (c.industry || '').includes(q)));
  const cnt = (k) => d.clients.filter((c) => (k === 'all' ? 1 : k === 'improved' ? c.improved : c.status === k)).length;
  view.innerHTML = `<div class="card"><div class="toolbar"><input class="inp" id="cq" placeholder="חיפוש לקוח או ענף" value="${esc(q)}" style="flex:1;min-width:160px">
    <div class="chips">${[['all', 'הכול'], ['red', 'דחוף'], ['yellow', 'במעקב'], ['green', 'תקין'], ['nodata', 'אין מספיק מידע'], ['improved', 'השתפרו']].map(([k, t]) => `<button class="chip ${f === k ? 'on' : ''}" data-act="go" data-arg="clients?f=${k}">${t} ${N(cnt(k))}</button>`).join('')}</div>
    <button class="btn sec sm" data-act="addClient">+ לקוח</button></div>
    <div class="list"><div class="rw hd"><span>לקוח</span><span>מצב</span><span class="c-cpl">עלות לליד 7 ימים</span><span class="c-leads">לידים</span><span class="c-owner">אחראי</span><span>הנושא המרכזי</span></div>
    ${rowsF.map((c) => `<button class="rw" data-act="go" data-arg="client/${c.id}"><span class="nm"><span class="ring" style="--v:${c.health ?? 0};--c:var(--${c.health == null ? 'line2' : c.health >= 75 ? 'g' : c.health >= 45 ? 'y' : 'r'});width:30px;height:30px"><b style="width:24px;height:24px;font-size:10.5px">${N(c.health ?? '—')}</b></span><span style="min-width:0"><span class="t">${esc(c.name)}</span> ${demoTag(c.is_demo)}<div class="s">${esc(c.industry || '')}</div></span></span>
      <span>${pill(c.status)}</span><span class="c-cpl">${N(money(c.cpl))}${chg(c.cpl, c.base_cpl, true)}</span><span class="c-leads">${N(c.leads)}</span><span class="c-owner">${esc(memberName(c.owner))}</span>
      <span class="iss">${c.alerts.length ? esc(c.alerts[0].title) + (c.alerts.length > 1 ? ` <span class="note">+${c.alerts.length - 1}</span>` : '') + (c.alerts[0].handling && c.alerts[0].handling !== 'open' ? ` <span class="pill p-gray">${esc(HANDLING[c.alerts[0].handling])}</span>` : '') : c.improved ? '<span class="pill p-imp">השתפר</span>' : c.lowData ? '<span class="note">מעט נתונים</span>' : '<span class="muted">—</span>'}</span></button>`).join('') || empty('אין לקוחות בסינון הזה')}</div></div>`;
  const inp = $('#cq');
  inp.oninput = () => { clearTimeout(inp._t); inp._t = setTimeout(() => { history.replaceState(null, '', `#/clients?f=${f}&q=${encodeURIComponent(inp.value)}`); V.clients(view, { f, q: inp.value }).then(() => { const i = $('#cq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 250); };
};

A.addClient = () => modal(`<div class="mh"><b>לקוח חדש</b><div class="sp"></div><button class="iconbtn" data-act="close">${ic('x')}</button></div>
  <form class="pad" id="ncF">${clientFields({})}<button class="btn pri" style="margin-top:10px">שמירה</button></form>`) || bindClientForm(null);
function clientFields(c) {
  const f = (k, l, t = 'number', v = c[k]) => `<div class="fld"><label for="f_${k}">${l}</label><input class="inp" id="f_${k}" name="${k}" type="${t}" ${t === 'number' ? 'step="any" min="0"' : ''} value="${v == null ? '' : esc(v)}"></div>`;
  return `<div class="frm">${f('name', 'שם הלקוח', 'text')}${f('industry', 'ענף', 'text')}<div class="fld"><label for="f_owner">אחראי</label><select class="inp" id="f_owner" name="owner">${memberOpts(c.owner)}</select></div>
  ${f('target_cpl', 'יעד עלות לליד (₪)', 'number', c.goals?.targetCpl ?? c.target_cpl)}${f('monthly_budget', 'תקציב פרסום חודשי (₪)', 'number', c.goals?.monthlyBudget ?? c.monthly_budget)}${f('website', 'אתר / דף נחיתה', 'url')}</div>
  <div class="h2" style="margin-top:12px">רווחיות לסוכנות <span class="note">(נפרד מתקציב הפרסום)</span></div>
  <div class="frm">${f('fee_monthly', 'הכנסה חודשית לסוכנות (₪)')}${f('hours_monthly', 'שעות עבודה בחודש')}${f('hourly_cost', 'עלות שעה (₪)')}${f('other_costs_monthly', 'עלויות נוספות בחודש (₪)')}</div>`;
}
function readClientForm(form) {
  const o = {};
  new FormData(form).forEach((v, k) => { if (v === '') { o[k] = null; return; } o[k] = ['name', 'industry', 'owner', 'website'].includes(k) ? v : Number(v); });
  if (!o.name) delete o.name;
  return o;
}
function bindClientForm(cid) {
  const form = $(cid ? '#ecF' : '#ncF');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const body = readClientForm(form);
    const r = await api(cid ? `/api/pulse/clients/${cid}` : '/api/pulse/clients', { method: cid ? 'PATCH' : 'POST', body });
    closeModal(); toast(cid ? 'נשמר. הניתוח עודכן.' : 'הלקוח נוסף. עכשיו ייבאו נתונים (CSV) כדי שהמנוע ינתח אותו.');
    st.clients = null; await refreshMe(); go('client/' + r.id);
  };
}

// ================================================================ תיק לקוח 360
V.client = async (view, p) => {
  const days = Number(p.days || 30), metric = p.m || 'cpl';
  const d = await api(`/api/pulse/clients/${encodeURIComponent(p.id)}?days=${days}`);
  const c = d.client, r = d.result, h = r.health, top = d.alerts[0];
  const met = (l, a, b, fmt, goodDown) => `<div class="met"><div class="l">${l}</div><div class="v">${N(a == null ? '—' : fmt(a))}</div><div class="c">${chg(a, b, goodDown)} <span class="note">מול ${N(b == null ? '—' : fmt(b))}</span></div></div>`;
  view.innerHTML = `<a class="back" href="#/clients">${ic('back', 14)} כל הלקוחות</a>
  <div class="ch">${healthRing(h.score)}<div><h2>${esc(c.name)} ${demoTag(c.is_demo)}</h2><div class="meta2" style="margin:4px 0 0">${pill(r.status)} <span>${esc(c.industry || '')}</span><span>אחראי: ${esc(memberName(c.owner))}</span><span>${esc((c.platforms || []).join(' · '))}</span><span>מקור נתונים: ${esc({ demo: 'דמו', csv: 'CSV', manual: 'לא יובאו נתונים' }[c.source] || c.source)}</span></div></div>
    <div class="sp"></div><div class="row"><a class="btn sec sm" href="/api/pulse/reports/client/${c.id}.html?days=30" target="_blank" rel="noopener">${ic('report', 14)} דוח ללקוח</a><a class="btn sec sm" href="/api/pulse/reports/client/${c.id}.pdf?days=30">PDF</a>
    <button class="btn sec sm" data-act="go" data-arg="ask?q=${encodeURIComponent('למה ' + c.name + ' במצב הזה?')}">${ic('chat', 14)} שאל על הלקוח</button><button class="btn sec sm" data-act="editClient" data-arg="${c.id}">הגדרות ויעדים</button></div></div>
  ${r.lowData ? `<div class="okbox" style="background:var(--ybg);margin-bottom:12px">${esc(r.info[0] || 'מעט נתונים')}</div>` : ''}
  ${top ? alertCard(top, d, true) : r.improved ? `<div class="card al imp" style="margin-bottom:14px"><div class="alh">${pill('imp')}<span class="t">שיפור מובהק</span><span class="engine">ביטחון ${esc(r.improved.confidence)}</span></div><p>${esc(r.improved.what)}</p></div>` : `<div class="card pad okbox" style="margin-bottom:14px">${ic('check', 15)} אין חריגות פתוחות. כל המדדים בטווח ההיסטורי של הלקוח${r.goals.targetCpl ? ' ובהתאם ליעד' : ''}.</div>`}
  <div class="card pad" style="margin-bottom:14px"><div class="h2">ביצועים<span class="sp"></span>
    <div class="seg">${[['cpl', 'עלות לליד'], ['leads', 'לידים'], ['spend', 'הוצאה'], ['ctr', 'CTR']].map(([k, t]) => `<button class="${metric === k ? 'on' : ''}" data-act="go" data-arg="client/${c.id}?days=${days}&m=${k}">${t}</button>`).join('')}</div>
    <div class="seg">${[30, 60, 90].map((n) => `<button class="${days === n ? 'on' : ''}" data-act="go" data-arg="client/${c.id}?days=${n}&m=${metric}">${n} יום</button>`).join('')}</div></div>
    <div class="mets" style="margin-bottom:12px">${met('הוצאה 7 ימים', r.rec.spend, r.base.spend / 3, money)}${met('לידים 7 ימים', r.rec.leads, r.base.leads / 3, (v) => Math.round(v))}${met('עלות לליד', r.rec.cpl, r.base.cpl, money, true)}${met('CTR', r.rec.ctr, r.base.ctr, (v) => pctf(v, 2))}${met('המרה לליד', r.rec.cvr, r.base.cvr, (v) => pctf(v, 1))}${met('CPM', r.rec.cpm, r.base.cpm, money, true)}</div>
    <div id="chartBox"></div><div class="legend" style="margin-top:6px">${metric === 'cpl' ? '<span><i style="background:var(--acc)"></i>ממוצע נע 7 ימים</span><span><i style="background:var(--line2)"></i>יומי</span>' : ''}${r.goals.targetCpl && metric === 'cpl' ? '<span><i style="background:var(--g)"></i>יעד</span>' : ''}<span class="note">"מול" = ממוצע 21 הימים שלפני השבוע האחרון</span></div></div>
  <div class="grid g2">
    <div class="stack">
      ${d.alerts.slice(1).map((a) => alertCard(a, d, false)).join('')}
      <div class="card pad"><div class="h2">${ic('report')} ציר זמן חכם</div><div class="tl">${timeline(d).map((e) => `<div class="tli ${e.k}"><div>${esc(e.t)}</div><div class="w">${N(dayLabel(e.day))}${e.who ? ' · ' + esc(e.who) : ''}</div></div>`).join('') || empty('אין עדיין אירועים')}</div></div>
    </div>
    <div class="stack">
      <div class="card pad"><div class="h2">${ic('check')} משימות</div>${d.tasks.length ? d.tasks.map((t) => `<button class="act" style="width:100%;margin-bottom:6px" data-act="go" data-arg="task/${t.id}"><div style="text-align:start"><b>${esc(t.title.split(' · ')[0])}</b><div class="small tx2">${esc(STATUS[t.status])} · ${esc(memberName(t.assignee))}</div></div></button>`).join('') : empty('אין משימות')}
        <button class="btn sec sm" data-act="manualTask" data-arg="${c.id}">+ משימה ידנית</button></div>
      <div class="card pad"><div class="h2">${ic('users')} אנשי קשר ושביעות רצון</div>
        ${d.contacts.map((x) => `<div class="fi"><div><b>${esc(x.name)}</b> <span class="note">${esc(x.role || '')}</span><div class="small tx2"><bdi>${esc(x.phone || '')}</bdi> ${x.email ? '· <bdi>' + esc(x.email) + '</bdi>' : ''}</div></div></div>`).join('') || '<p class="small tx2">אין אנשי קשר</p>'}
        <form id="ctF" class="row" style="margin-top:8px"><input class="inp" id="ctN" placeholder="שם" required style="flex:1;min-width:100px"><input class="inp" id="ctR" placeholder="תפקיד" style="width:110px"><input class="inp" id="ctP" placeholder="טלפון" style="width:120px" dir="ltr"><button class="btn sec sm">הוספה</button></form>
        <div class="row" style="margin-top:12px"><span class="small">שביעות רצון${c.satisfaction ? ` (כרגע ${N(c.satisfaction)}/5)` : ' (לא תועדה)'}:</span>${[1, 2, 3, 4, 5].map((n) => `<button class="chip ${c.satisfaction === n ? 'on' : ''}" data-act="setSat" data-arg="${c.id}|${n}">${n}</button>`).join('')}</div></div>
      <div class="card pad"><div class="h2">${ic('check')} התחייבויות ללקוח</div>
        ${d.commitments.map((x) => `<div class="bi sev-${x.status !== 'open' ? 'green' : x.due_day < d.ref ? 'red' : 'yellow'}"><div class="bt"><b style="${x.status !== 'open' ? 'text-decoration:line-through;color:var(--mute)' : ''}">${esc(x.text)}</b><div class="small tx2">${esc(memberName(x.owner))} · יעד ${N(dayLabel(x.due_day))}${x.status === 'open' && x.due_day < d.ref ? ' · באיחור' : x.status === 'done' ? ' · בוצע' : x.status === 'cancelled' ? ' · בוטל' : ''}</div></div>${x.status === 'open' ? `<button class="btn sec sm" data-act="commitDone" data-arg="${x.id}">בוצע</button>` : ''}</div>`).join('') || '<p class="small tx2">אין התחייבויות פתוחות</p>'}
        <form id="cmF" class="row" style="margin-top:8px"><input class="inp" id="cmT" placeholder="מה הבטחנו ללקוח" required minlength="2" style="flex:1;min-width:140px"><select class="inp" id="cmO" aria-label="אחראי">${memberOpts(c.owner)}</select><input class="inp" id="cmD" type="number" min="0" max="180" value="3" style="width:70px" aria-label="תוך ימים"><button class="btn sec sm">הוספה</button></form></div>
      <div class="card pad"><div class="h2">${ic('chart')} היסטוריית הרמזור</div>${d.status_history.map((x) => `<div class="fi"><span class="tm">${N(dayLabel(x.day))}</span>${pill(x.status)}<div class="small">${esc(x.reason || '')}</div></div>`).join('') || '<p class="small tx2">אין עדיין שינויים</p>'}</div>
      ${d.decisions.length ? `<div class="card pad"><div class="h2">${ic('check')} החלטות ותוצאות</div>${d.decisions.map((x) => `<div class="fi"><span class="tm">${N(dayLabel(x.day))}</span><div class="small"><b>${x.decision === 'approve' ? 'אושר' : 'נדחה'}</b> ע"י ${esc(x.by_name)}: ${esc(x.title)}${x.rationale ? `<div class="note">${esc(x.rationale)}</div>` : ''}<div class="${x.outcome === 'אומת בנתונים' ? 'ok' : x.outcome ? 'bad' : 'note'}">תוצאה: ${esc(x.outcome || 'ממתין לבדיקה חוזרת')}</div></div></div>`).join('')}</div>` : ''}
      ${c.is_demo ? `<a class="card pad setl" href="#/ads?client=${c.id}">${ic('spark')}<b>ניתוח המודעות של הלקוח</b><span class="note">מה לשפר בהצעה, בקופי ובקריאייטיב</span></a>` : ''}
      ${d.opportunities.length ? `<div class="card pad"><div class="h2"><i class="dot d-imp"></i> הזדמנויות</div>${d.opportunities.map((o) => oppCard(o, c.id)).join('')}</div>` : ''}
      <div class="card pad"><div class="h2">${ic('trophy')} ציון בריאות: ${N(h.score ?? 'אין מספיק מידע')}<span class="sp"></span><span class="note">ביטחון ${esc(h.confidence)}</span></div>
        ${h.parts.length ? `<table class="ft">${h.parts.map((x) => `<tr><td>${esc(x.label)}</td><td class="bad">${N(x.points)}</td></tr>`).join('')}</table>` : '<p class="small tx2">אין קנסות — 100.</p>'}<p class="note">${esc(h.formula)}</p></div>
      <div class="card pad"><div class="h2">סיכון נטישה<span class="sp"></span>${d.risk.level === 'unknown' ? '<span class="pill p-gray">אין מספיק נתונים</span>' : `<span class="pill p-${d.risk.level === 'high' ? 'red' : d.risk.level === 'medium' ? 'yellow' : 'green'}">${{ high: 'גבוה', medium: 'בינוני', low: 'נמוך' }[d.risk.level]}</span>`}</div><ul class="ul">${d.risk.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>${d.risk.note ? `<p class="note">${esc(d.risk.note)}</p>` : ''}</div>
      <div class="card pad"><div class="h2">${ic('coin')} רווחיות לסוכנות</div>${d.profit ? `<div class="kv"><span>הכנסה חודשית</span><b>${N(money(d.profit.fee))}</b><span>עלות עבודה</span><span>${N(money(d.profit.labor))} (${N(d.profit.hours)} ש')</span><span>עלויות נוספות</span><span>${N(money(d.profit.other))}</span><span>רווח גולמי</span><b class="${d.profit.profit < 0 ? 'bad' : 'ok'}">${N(money(d.profit.profit))} · ${N(pctf(d.profit.margin))}</b><span>תקציב פרסום 30 יום</span><span class="muted">${N(money(d.profit.ad_spend_30))} (של הלקוח)</span></div>${d.profit.complete ? '' : '<p class="note">חסרות שעות או עלות שעה — הרווחיות חלקית.</p>'}` : '<p class="small tx2">לא הוזנה הכנסה חודשית. הוסיפו בהגדרות כדי לראות רווחיות.</p>'}</div>
      ${d.drafts.length ? `<div class="card pad"><div class="h2">${ic('chat')} טיוטות ללקוח</div>${d.drafts.map((x) => `<div class="hyp"><div class="small">${esc(x.text).replace(/\n/g, '<br>')}</div><div class="row" style="margin-top:8px"><span class="note">${esc(x.channel || '')} · ${x.status === 'approved' ? 'אושר ע"י ' + esc(x.approved_by) : 'טיוטה'}</span><span class="sp"></span><button class="btn sec sm" data-act="copy" data-arg="${esc(x.text)}">העתק</button>${x.status !== 'approved' && st.me.can_approve ? `<button class="btn sec sm" data-act="approveDraft" data-arg="${x.id}">אשר</button>` : ''}</div></div>`).join('')}<p class="note">השליחה ידנית — WhatsApp / Email לא מחוברים.</p></div>` : ''}
      <div class="card pad"><div class="h2">${ic('chat')} הערות, שיחות והחלטות</div>
        <form id="noteF"><div class="row"><select class="inp" id="nk"><option value="note">הערה</option><option value="call">שיחה</option><option value="meeting">פגישה</option><option value="decision">החלטה</option></select><input class="inp" id="nt" placeholder="מה סוכם / מה קרה" style="flex:1" required maxlength="4000"><button class="btn sec sm">שמור</button></div></form>
        ${d.notes.map((n) => `<div class="fi"><span class="pill p-gray">${{ note: 'הערה', call: 'שיחה', meeting: 'פגישה', decision: 'החלטה' }[n.kind]}</span><div>${esc(n.text)}<div class="note">${esc(n.user_name || '')}</div></div></div>`).join('')}</div>
      ${!c.is_demo ? `<div class="card pad"><div class="h2">${ic('plug')} ייבוא נתונים (CSV)</div><p class="small tx2">ייצוא יומי מ-Meta Ads Manager / Google Ads. עמודות: date, spend, impressions, clicks, leads · אופציונלי: sales, revenue. כותרות בעברית נתמכות.</p>
        <input type="file" accept=".csv,text/csv" id="csvF" class="inp" style="width:100%"><button class="btn sec sm" style="margin-top:8px" data-act="importCsv" data-arg="${c.id}">ייבוא</button><div id="csvR" class="note"></div></div>` : ''}
    </div></div>`;
  // גרף
  const s = d.series, roll = d.rolling;
  const labels = s.map((x) => x.date.slice(8, 10) + '.' + Number(x.date.slice(5, 7)));
  if (metric === 'cpl') {
    const rm = Object.fromEntries(roll.map((x) => [x.date, x.cpl]));
    chart($('#chartBox'), { labels, target: r.goals.targetCpl, fmt: (v) => money(v), series: [{ name: 'יומי', color: 'var(--line2)', w: 1.2, vals: s.map((x) => x.cpl) }, { name: 'ממוצע נע 7 ימים', color: 'var(--acc)', w: 2.4, vals: s.map((x) => rm[x.date] ?? null) }] });
  } else {
    const k = metric, fmt = k === 'spend' ? money : k === 'ctr' ? (v) => v.toFixed(2) + '%' : (v) => Math.round(v);
    chart($('#chartBox'), { labels, fmt, series: [{ name: { leads: 'לידים', spend: 'הוצאה', ctr: 'CTR' }[k], color: 'var(--acc)', vals: s.map((x) => x[k]) }] });
  }
  $('#ctF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/contacts`, { method: 'POST', body: { name: $('#ctN').value, role: $('#ctR').value || null, phone: $('#ctP').value || null } }); render(); };
  $('#cmF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/commitments`, { method: 'POST', body: { text: $('#cmT').value, owner: $('#cmO').value, due_in: Number($('#cmD').value) } }); toast('ההתחייבות נשמרה ותיכנס לרמזור אם תאחר'); render(); };
  $('#noteF').onsubmit = async (e) => { e.preventDefault(); await api(`/api/pulse/clients/${c.id}/notes`, { method: 'POST', body: { kind: $('#nk').value, text: $('#nt').value } }); toast('נשמר בתיק הלקוח'); render(); };
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
A.oppTask = async (b, arg) => { const [cid, title] = arg.split('|'); const t = await api('/api/pulse/tasks/manual', { method: 'POST', body: { client_id: cid, title, source: 'opportunity', due_days: 7 } }); toast('נוצרה משימה מהזדמנות'); go('task/' + t.id); };
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
