// ClientPulse OS — מעטפת: API, ניתוב, ניווט, חיפוש (⌘K), התראות, ערכת נושא, סיור הדגמה.
// כל נתון מגיע מהשרת (/api/pulse/*). אין כאן חישובים עסקיים — רק תצוגה.
import { V } from './views.js';

export const st = { me: null, route: 'home', params: {}, notif: false, pal: false, palQ: '', palI: 0, clients: null, tour: null, sheet: false };

// ---------------------------------------------------------------- עזרים
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const N = (x) => `<bdi class="num">${esc(x)}</bdi>`;
export const money = (x) => (x == null ? '—' : '₪' + Math.round(x).toLocaleString('en-US'));
export const pctf = (x, d = 0) => (x == null ? '—' : (x * 100).toFixed(d) + '%');
export const chg = (a, b, goodDown) => {
  if (a == null || b == null || !b) return '';
  const x = a / b - 1, bad = goodDown ? x > 0.05 : x < -0.05, good = goodDown ? x < -0.05 : x > 0.05;
  return `<span class="chg ${bad ? 'up' : good ? 'down' : 'muted'}">${N((x > 0 ? '+' : '') + Math.round(x * 100) + '%')}</span>`;
};
export const SL = { green: 'תקין', yellow: 'במעקב', red: 'דחוף' };
export const pill = (s) => `<span class="pill p-${s === 'imp' ? 'imp' : s}"><i class="dot d-${s === 'imp' ? 'imp' : s}"></i>${esc(SL[s] || 'הזדמנות')}</span>`;
export const dayLabel = (idx) => { const d = new Date(idx * 864e5); return d.getUTCDate() + '.' + (d.getUTCMonth() + 1); };
export const memberName = (id) => (st.me?.team || []).find((m) => m.id === id)?.name || id || '—';
export const demoTag = (on) => (on ? '<span class="badge-demo">דמו</span>' : '');

const I = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>', users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 14.8c1.6.8 2.6 2.6 3 5.2"/>',
  check: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="m8 12 3 3 5-6"/>', chat: '<path d="M4 5h16v11H9l-5 4z"/>', zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', flask: '<path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3"/><path d="M7 15h10"/>',
  plug: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>', moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>', play: '<path d="M7 4v16l13-8z"/>', back: '<path d="m9 6 6 6-6 6"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
  report: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>', coin: '<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.5c-.5-1-1.4-1.5-2.5-1.5-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1.2 0-2.1-.6-2.6-1.6M12 6.5V8M12 16v1.5"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>', team: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-3.6 3.8-5.5 7-5.5s6 1.9 7 5.5"/>', trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM5 5h3v3a3 3 0 0 1-3-3zM19 5h-3v3a3 3 0 0 0 3-3zM12 13v4M8 20h8"/>',
};
export const ic = (n, s) => `<svg class="ic" viewBox="0 0 24 24" ${s ? `style="width:${s}px;height:${s}px"` : ''}>${I[n] || ''}</svg>`;

export const NAV = [
  ['', [['home', 'רמזור · מה היום', 'home'], ['alerts', 'חריגות וטיפול', 'bell'], ['clients', 'לקוחות', 'users'], ['tasks', 'משימות ואישורים', 'check'], ['ask', 'Ask ClientPulse', 'chat']]],
  ['ניהול וצמיחה', [['opps', 'הזדמנויות', 'spark'], ['profit', 'רווחיות', 'coin'], ['team', 'צוות ועומסים', 'team'], ['impact', 'הוכחת ערך', 'trophy'], ['reports', 'דוחות', 'report']]],
  ['מערכת', [['automations', 'אוטומציות', 'zap'], ['integrations', 'חיבורים', 'plug'], ['lab', 'Demo Lab', 'flask']]],
];
const TITLE = { home: 'רמזור · מה היום', alerts: 'חריגות וטיפול', clients: 'לקוחות', client: 'תיק לקוח 360', tasks: 'משימות ואישורים', task: 'משימות ואישורים', ask: 'Ask ClientPulse', opps: 'הזדמנויות צמיחה',
  profit: 'רווחיות סוכנות', team: 'צוות ועומסים', impact: 'הוכחת ערך · לפני ואחרי', reports: 'דוחות', automations: 'מרכז אוטומציות', integrations: 'חיבורים', lab: 'Demo Lab' };

// ---------------------------------------------------------------- API
export async function api(path, opts = {}) {
  const o = { method: opts.method || 'GET', headers: {}, credentials: 'same-origin' };
  if (opts.body !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(opts.body); }
  const r = await fetch(path, o);
  if (r.status === 401) { st.me = null; renderAuth(); throw new Error('auth'); }
  const data = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text();
  if (!r.ok) { const msg = (data && data.detail) ? (typeof data.detail === 'string' ? data.detail : 'הנתונים שנשלחו לא תקינים') : 'שגיאה ' + r.status; toast(msg, 'bad'); throw new Error(msg); }
  return data;
}

export function toast(msg, kind) {
  let box = document.querySelector('.toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; document.body.appendChild(box); }
  const el = document.createElement('div');
  el.className = 'toast'; el.setAttribute('role', 'status');
  el.innerHTML = `<i class="dot d-${kind === 'bad' ? 'red' : kind === 'warn' ? 'yellow' : 'green'}" style="margin-top:7px"></i><div>${esc(msg)}</div>`;
  box.appendChild(el); setTimeout(() => el.remove(), 5200);
}

// ---------------------------------------------------------------- ערכת נושא (העדפה מקומית בלבד)
const THEME_KEY = 'clientpulse.theme';
function theme() { try { return localStorage.getItem(THEME_KEY) || 'light'; } catch { return 'light'; } }
function applyTheme(t) { document.documentElement.setAttribute('data-theme', t); document.querySelector('meta[name=theme-color]')?.setAttribute('content', t === 'light' ? '#F5F5F3' : '#0B0C0E'); try { localStorage.setItem(THEME_KEY, t); } catch { /* פרטי */ } }

// ---------------------------------------------------------------- ניתוב
export function go(r) { if (location.hash === '#/' + r) render(); else location.hash = '#/' + r; }
function parse() {
  const h = location.hash.replace(/^#\/?/, '') || 'home';
  const [path, qs] = h.split('?');
  const [route, id] = path.split('/');
  const params = Object.fromEntries(new URLSearchParams(qs || ''));
  if (id) params.id = decodeURIComponent(id);
  return { route: TITLE[route] ? route : 'home', params };
}

// ---------------------------------------------------------------- כניסה (משתמשי P1)
function renderAuth(mode = 'login') {
  document.getElementById('app').innerHTML = `<div class="center"><form class="card auth" id="authF">
    <div class="brand" style="padding:0"><div class="logo"><i></i></div><div>ClientPulse OS<small>מערכת הפעלה למשרדי פרסום · חלק מ-P1</small></div></div>
    <h1>${mode === 'login' ? 'כניסה' : 'פתיחת חשבון סוכנות'}</h1><p class="muted small">אותו חשבון כמו P1. כל סוכנות רואה רק את הנתונים שלה.</p>
    ${mode === 'register' ? '<div class="fld"><label for="an">שם</label><input class="inp" id="an" autocomplete="name"></div><div class="fld"><label for="aa">שם הסוכנות</label><input class="inp" id="aa"></div>' : ''}
    <div class="fld"><label for="ae">אימייל</label><input class="inp" id="ae" type="email" required autocomplete="email" dir="ltr"></div>
    <div class="fld"><label for="ap">סיסמה</label><input class="inp" id="ap" type="password" required minlength="8" autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}" dir="ltr"></div>
    <button class="btn pri" style="width:100%;margin-top:8px">${mode === 'login' ? 'כניסה' : 'יצירת חשבון'}</button>
    <p class="small muted" style="text-align:center;margin-top:14px"><a href="#" id="authSw">${mode === 'login' ? 'אין חשבון? פתיחת חשבון' : 'יש חשבון? כניסה'}</a></p>
  </form></div>`;
  document.getElementById('authSw').onclick = (e) => { e.preventDefault(); renderAuth(mode === 'login' ? 'register' : 'login'); };
  document.getElementById('authF').onsubmit = async (e) => {
    e.preventDefault();
    const body = { email: document.getElementById('ae').value.trim(), password: document.getElementById('ap').value };
    if (mode === 'register') { body.name = document.getElementById('an').value.trim() || undefined; body.account_name = document.getElementById('aa').value.trim() || undefined; }
    try { await api('/api/auth/' + (mode === 'login' ? 'login' : 'register'), { method: 'POST', body }); boot(); } catch { /* toast כבר הוצג */ }
  };
}

// ---------------------------------------------------------------- מעטפת
function shell() {
  const navHtml = NAV.map(([g, items]) => (g ? `<div class="grp">${g}</div>` : '') + items.map(([r, t, i]) => `<a href="#/${r}" data-r="${r}">${ic(i)}<span>${t}</span><span class="ct" data-ct="${r}" hidden></span></a>`).join('')).join('');
  document.getElementById('app').innerHTML = `
  <aside class="sb"><div class="brand"><div class="logo"><i></i></div><div>ClientPulse OS<small id="agencyName"></small></div></div>
    <nav class="nav" aria-label="ניווט ראשי">${navHtml}</nav>
    <div class="sbfoot">
      <div class="clock" id="clockBox"></div>
      <div class="row2"><button class="btn sec sm" style="flex:1" data-act="theme" id="themeBtn"></button><a class="btn sec sm" style="flex:1" href="/">P1</a><button class="btn sec sm" style="flex:1" data-act="logout">יציאה</button></div>
    </div></aside>
  <div class="main">
    <header class="tb"><h1 id="ttl"></h1><span class="mock" id="demoMark" hidden>${window.__SNAPSHOT__ ? 'תצוגה לחיצה · נתוני דמו' : 'נתוני דמו'}</span><div class="sp"></div>
      <button class="kbd" data-act="palette" aria-label="חיפוש">${ic('search', 15)}<span>חיפוש לקוח או מסך</span><kbd>⌘K</kbd></button>
      <button class="btn pri sm" data-act="check" id="runBtn">הרץ בדיקה</button>
      <button class="iconbtn" data-act="notif" aria-label="התראות">${ic('bell')}<span id="bellC"></span></button>
    </header>
    <main class="view" id="view"></main></div>
  <nav class="bn" aria-label="ניווט">
    ${[['home', 'פיקוד', 'home'], ['clients', 'לקוחות', 'users'], ['tasks', 'משימות', 'check'], ['ask', 'שאל', 'chat']].map(([r, t, i]) => `<a href="#/${r}" data-r="${r}">${ic(i)}${t}</a>`).join('')}
    <button data-act="more">${ic('more')}עוד</button></nav>
  <div class="sheet" id="sheet"></div>
  <div class="ov" id="palOv"><div class="pal" role="dialog" aria-label="חיפוש"><input id="palIn" placeholder="חפש לקוח, מסך או פעולה…" autocomplete="off"><div class="res" id="palRes"></div></div></div>
  <div class="ov" id="modalOv"><div class="modal" id="modal" role="dialog"></div></div>
  <div class="card panel" id="notifP"></div>`;
  document.body.onclick = onClick;
}

export function chrome() {
  const me = st.me;
  document.getElementById('agencyName').textContent = me.agency || 'Agency Command Center';
  document.getElementById('demoMark').hidden = !me.demo;
  document.getElementById('clockBox').innerHTML = me.demo
    ? `<div class="row2"><div style="flex:1"><div class="l">יום הדמו</div><div class="v">${N(me.ref_label)}</div></div><button class="btn sec sm" data-act="advance" title="קדם את שעון הדמו ביום">+1 יום</button></div>`
    : `<div class="l">נתונים עד</div><div class="v">${N(me.ref_label)}</div><div class="l">${esc(me.user.name)} · ${me.can_approve ? 'מאשר/ת פעולות' : 'צפייה וטיפול'}</div>`;
  document.getElementById('themeBtn').innerHTML = ic(theme() === 'dark' ? 'sun' : 'moon', 15);
  const b = document.getElementById('bellC');
  b.innerHTML = me.unread ? `<span class="dotc">${me.unread > 99 ? '99+' : me.unread}</span>` : '';
  document.querySelectorAll('[data-r]').forEach((a) => a.classList.toggle('on', a.dataset.r === (st.route === 'client' ? 'clients' : st.route === 'task' ? 'tasks' : st.route)));
  document.getElementById('ttl').textContent = TITLE[st.route] || '';
}

export async function refreshMe() { st.me = await api('/api/pulse/state'); chrome(); }

export async function render() {
  const p = parse();
  st.route = p.route; st.params = p.params;
  if (!st.me) return;
  chrome();
  const view = document.getElementById('view');
  view.innerHTML = `<div class="stack"><div class="sk" style="height:80px"></div><div class="sk" style="height:220px"></div></div>`;
  window.scrollTo(0, 0);
  try {
    if (!st.me.clients && !['lab', 'integrations', 'client', 'alerts'].includes(st.route)) { await V.welcome(view); return; }
    await (V[st.route] || V.home)(view, st.params);
  } catch (e) {
    if (e.message !== 'auth') view.innerHTML = `<div class="card pad empty"><b>משהו נכשל בטעינת המסך.</b><p>${esc(e.message)}</p><button class="btn sec" data-act="reload">נסה שוב</button></div>`;
  }
  if (st.tour) V.tourRender();
}

export function modal(html) { document.getElementById('modal').innerHTML = html; document.getElementById('modalOv').classList.add('on'); }
export function closeModal() { document.getElementById('modalOv').classList.remove('on'); }

// ---------------------------------------------------------------- פעולות גלובליות
async function onClick(e) {
  const ov = e.target.closest('.ov');
  if (ov && e.target === ov) { ov.classList.remove('on'); st.pal = false; return; }
  const a = e.target.closest('[data-act]');
  if (!a) { if (st.notif && !e.target.closest('#notifP')) toggleNotif(false); return; }
  const act = a.dataset.act, arg = a.dataset.arg;
  if (V.actions[act]) { e.preventDefault(); return V.actions[act](a, arg, e); }
  switch (act) {
    case 'theme': applyTheme(theme() === 'dark' ? 'light' : 'dark'); chrome(); break;
    case 'logout': await api('/api/auth/logout', { method: 'POST' }).catch(() => {}); st.me = null; renderAuth(); break;
    case 'check': {
      a.disabled = true; a.textContent = 'בודק…';
      try { const r = await api('/api/pulse/check', { method: 'POST' }); toast(`נותחו ${r.n} לקוחות ב-${r.ms} מ"ש · ${r.new} חריגות חדשות · ${r.cleared} חזרו לתקין`); await refreshMe(); await render(); }
      finally { a.disabled = false; a.textContent = 'הרץ בדיקה'; } break;
    }
    case 'advance': { const r = await api('/api/pulse/lab/advance', { method: 'POST', body: { days: Number(arg || 1) } }); toast(r.msg); await refreshMe(); await render(); break; }
    case 'notif': toggleNotif(!st.notif); break;
    case 'palette': openPal(); break;
    case 'go': closeModal(); toggleNotif(false); closeSheet(); go(arg); break;
    case 'close': closeModal(); break;
    case 'reload': render(); break;
    case 'more': openSheet(); break;
    default: break;
  }
}

function openSheet() {
  const s = document.getElementById('sheet');
  s.innerHTML = NAV.flatMap(([, items]) => items).filter(([r]) => !['home', 'clients', 'tasks', 'ask'].includes(r))
    .map(([r, t, i]) => `<a class="it" href="#/${r}" data-act="go" data-arg="${r}" style="display:flex;gap:10px;padding:12px 14px">${ic(i)}${t}</a>`).join('')
    + `<div class="row" style="padding:10px 14px"><button class="btn sec sm" data-act="theme">ערכת נושא</button><a class="btn sec sm" href="/">P1</a><button class="btn sec sm" data-act="logout">יציאה</button></div>`;
  s.classList.add('on'); st.sheet = true;
  setTimeout(() => document.addEventListener('click', closeSheetOutside, { once: true }), 0);
}
function closeSheetOutside(e) { if (!e.target.closest('#sheet')) closeSheet(); }
function closeSheet() { document.getElementById('sheet')?.classList.remove('on'); st.sheet = false; }

async function toggleNotif(on) {
  st.notif = on;
  const p = document.getElementById('notifP');
  if (!p) return;
  p.classList.toggle('on', on);
  if (!on) return;
  const list = await api('/api/pulse/notifications');
  p.innerHTML = `<div class="mh"><b>התראות פנימיות</b><div class="sp"></div><span class="note">מתוך האוטומציות · לא נשלחות החוצה</span></div>` + (list.length
    ? list.map((n) => `<button class="ni ${n.read ? '' : 'unread'}" data-act="go" data-arg="${esc(n.route || 'home')}"><i class="dot d-${n.kind === 'danger' || n.kind === 'escalation' ? 'red' : n.kind === 'warn' ? 'yellow' : n.kind === 'success' ? 'green' : 'imp'}" style="margin-top:7px"></i><div><div>${esc(n.text)}</div><div class="note">יום ${N(dayLabel(n.day))}</div></div></button>`).join('')
    : '<div class="empty">אין התראות</div>');
  if (st.me.unread) { await api('/api/pulse/notifications/read', { method: 'POST' }); st.me.unread = 0; chrome(); }
}

// ---------------------------------------------------------------- חיפוש גלובלי ⌘K
async function openPal() {
  st.pal = true; st.palQ = ''; st.palI = 0;
  if (!st.clients) st.clients = (await api('/api/pulse/clients')).clients;
  document.getElementById('palOv').classList.add('on');
  const inp = document.getElementById('palIn');
  inp.value = ''; inp.focus(); renderPal();
  inp.oninput = () => { st.palQ = inp.value; st.palI = 0; renderPal(); };
}
function palItems() {
  const q = st.palQ.trim();
  const screens = NAV.flatMap(([, items]) => items).map(([r, t, i]) => ({ g: 'מסכים', t, r, i }));
  const cl = (st.clients || []).map((c) => ({ g: 'לקוחות', t: c.name, r: 'client/' + c.id, s: c.status, sub: c.alerts[0]?.title || SL[c.status] }));
  const acts = [{ g: 'פעולות', t: 'הרץ בדיקה עכשיו', act: 'check' }, { g: 'פעולות', t: 'שאל: מה קורה היום במשרד?', r: 'ask?q=' + encodeURIComponent('מה קורה היום במשרד?') }];
  const all = [...screens, ...cl, ...acts];
  return q ? all.filter((x) => x.t.includes(q) || (x.sub || '').includes(q)).slice(0, 14) : [...acts, ...screens, ...cl.filter((c) => c.s === 'red')].slice(0, 14);
}
function renderPal() {
  const items = palItems();
  let g = '';
  document.getElementById('palRes').innerHTML = items.length ? items.map((x, i) => {
    const head = x.g !== g ? `<div class="grp">${(g = x.g)}</div>` : '';
    return head + `<button class="it ${i === st.palI ? 'on' : ''}" data-act="${x.act || 'go'}" data-arg="${esc(x.r || '')}">${x.s ? `<i class="dot d-${x.s}"></i>` : ic(x.i || 'back', 15)}<span>${esc(x.t)}</span>${x.sub ? `<span class="note" style="margin-inline-start:auto">${esc(x.sub)}</span>` : ''}</button>`;
  }).join('') : '<div class="empty">לא נמצא</div>';
}
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (st.me) openPal(); }
  if (e.key === 'Escape') { document.querySelectorAll('.ov.on').forEach((o) => o.classList.remove('on')); st.pal = false; toggleNotif(false); }
  if (st.pal && ['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) {
    const items = palItems();
    if (e.key === 'Enter') { const x = items[st.palI]; if (x) { document.getElementById('palOv').classList.remove('on'); st.pal = false; if (x.act) document.getElementById('runBtn').click(); else go(x.r); } }
    else { st.palI = (st.palI + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % Math.max(1, items.length); renderPal(); }
    e.preventDefault();
  }
});

// ---------------------------------------------------------------- גרף SVG אינטראקטיבי (בלי ספריות)
export function chart(el, { labels, series, target, fmt = (v) => v, h = 220 }) {
  const W = 760, H = h, P = { l: 46, r: 12, t: 12, b: 26 };
  const vals = series.flatMap((s) => s.vals).filter((v) => v != null).concat(target != null ? [target] : []);
  if (vals.length < 2) { el.innerHTML = '<div class="empty">אין מספיק נתונים לגרף</div>'; return; }
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08; lo = Math.max(0, lo - pad); hi += pad;
  const n = labels.length, X = (i) => P.l + (i * (W - P.l - P.r)) / Math.max(1, n - 1), Y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => { const v = lo + (hi - lo) * f; return `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${P.l - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="10" fill="var(--mute)">${esc(fmt(v))}</text>`; }).join('');
  const paths = series.map((s) => {
    let d = '', pen = false;
    s.vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1) + ' '; pen = true; });
    return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w || 2}" stroke-linejoin="round" stroke-linecap="round" ${s.dash ? 'stroke-dasharray="4 4"' : ''}/>`;
  }).join('');
  const tl = target != null ? `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(target)}" y2="${Y(target)}" stroke="var(--g)" stroke-dasharray="5 5"/><text x="${W - P.r}" y="${Y(target) - 4}" text-anchor="end" font-size="10" fill="var(--g)">יעד</text>` : '';
  const xl = labels.map((l, i) => (i % Math.ceil(n / 8) === 0 ? `<text x="${X(i)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--mute)">${esc(l)}</text>` : '')).join('');
  el.innerHTML = `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="גרף">${grid}${tl}${paths}${xl}<line class="cx" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" stroke="var(--line2)" visibility="hidden"/></svg><div class="tip"></div></div>`;
  const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), cx = el.querySelector('.cx');
  svg.addEventListener('mousemove', (ev) => {
    const r = svg.getBoundingClientRect(), x = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((x - P.l) / (W - P.l - P.r)) * (n - 1))));
    cx.setAttribute('x1', X(i)); cx.setAttribute('x2', X(i)); cx.setAttribute('visibility', 'visible');
    tip.innerHTML = `<b>${esc(labels[i])}</b>` + series.map((s) => `<div><i class="dot" style="background:${s.color}"></i> ${esc(s.name)}: ${N(s.vals[i] == null ? '—' : fmt(s.vals[i]))}</div>`).join('');
    tip.classList.add('on');
    const px = (X(i) / W) * r.width;
    tip.style.left = Math.min(r.width - 150, Math.max(0, px - 70)) + 'px'; tip.style.top = '6px';
  });
  svg.addEventListener('mouseleave', () => { tip.classList.remove('on'); cx.setAttribute('visibility', 'hidden'); });
}

// ---------------------------------------------------------------- אתחול
export async function boot() {
  applyTheme(theme());
  try { st.me = await api('/api/pulse/state'); } catch { return; }
  shell();
  window.onhashchange = render;
  await render();
}
boot();
