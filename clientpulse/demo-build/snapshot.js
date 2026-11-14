// גרסת תצוגה לחיצה של ClientPulse OS: אותם מסכים בדיוק, על צילום מצב של סביבת הדמו (data.json) במקום שרת.
// קריאה (GET) מוגשת מהצילום. פעולות על לקוחות ומשימות מבוצעות בזיכרון הדפדפן (מתאפס ברענון); פעולות שדורשות שרת (שעון דמו, חיבורים, משתמשים) מסבירות זאת במפורש.
(function () {
  'use strict';
  window.__SNAPSHOT__ = true;
  var MSG = 'הפעולה הזו (שעון דמו, חיבורים, משתמשים והגדרות) פועלת במערכת המלאה בשרת. כל הפעולות על לקוחות ומשימות עובדות גם כאן.';
  var ready = fetch('data.json').then(function (r) { return r.json(); });
  var real = window.fetch.bind(window);
  function res(body, status) { return new Response(JSON.stringify(body), { status: status || 200, headers: { 'content-type': 'application/json' } }); }
  function toast(msg) {
    var box = document.querySelector('.toasts');
    if (!box) { box = document.createElement('div'); box.className = 'toasts'; document.body.appendChild(box); }
    var el = document.createElement('div');
    el.className = 'toast'; el.setAttribute('role', 'status');
    el.innerHTML = '<i class="dot d-imp" style="margin-top:7px"></i><div></div>';
    el.lastChild.textContent = msg;
    box.appendChild(el); setTimeout(function () { el.remove(); }, 7000);
  }
  window.fetch = async function (input, opts) {
    opts = opts || {};
    var url = typeof input === 'string' ? input : input.url;
    if (url.indexOf('/api/') !== 0) return real(input, opts);
    var D = await ready, m = (opts.method || 'GET').toUpperCase();
    if (m === 'GET') {
      if (D[url]) return res(D[url]);
      var mm = url.match(/^\/api\/pulse\/clients\/([^?]+)\?days=(\d+)/);
      if (mm) { var k = '/api/pulse/clients/' + mm[1] + '?days=' + (+mm[2] > 45 ? 90 : 30); if (D[k]) return res(D[k]); }
      var base = url.split('?')[0];
      if (D[base]) return res(D[base]);
      return res({ detail: 'המסך הזה לא נכלל בגרסת התצוגה' }, 404);
    }
    if (url === '/api/pulse/ask') {
      var q = (JSON.parse(opts.body || '{}').q || '').trim(), a = D.__ask__[q];
      if (a) return res(a);
      return res({ text: 'בגרסת התצוגה אפשר לבחור מהשאלות המוצעות. במערכת המלאה הסוכן עונה על כל שאלה מתוך הנתונים.', evidence: [], links: [],
        follow: Object.keys(D.__ask__).slice(0, 5), intent: 'unknown', engine: 'rules' });
    }
    if (url === '/api/pulse/notifications/read') return res({ ok: true });
    var body = {}; try { body = JSON.parse(opts.body || '{}'); } catch (e) { /* */ }
    var r = act(D, url, m, body);
    if (r) return res(r.body, r.status || 200);
    return res({ detail: MSG }, 409);
  };
  // ---- פעולות אמיתיות בתוך הדפדפן: משנות את נתוני הדמו בזיכרון, והמסכים מתעדכנים (מתאפס ברענון) ----
  var seq = 0, me = 'ניב';
  var ST = { new: 'חדש', in_progress: 'בטיפול', awaiting_approval: 'ממתין לאישור', awaiting_verification: 'ממתין לבדיקה חוזרת', closed: 'נסגר' };
  var HANDLED = { new: 'עוד לא — משימה פתוחה, הטיפול לא התחיל', in_progress: 'בטיפול עכשיו', awaiting_approval: 'טופל — ממתין לאישור מנהל', awaiting_verification: 'כן — טופל' };
  function walk(o, fn) { if (o && typeof o === 'object') { fn(o); for (var k in o) walk(o[k], fn); } }
  function ref(D) { return D['/api/pulse/state'].ref; }
  function dropBrief(D, cid, key) {
    var b = D['/api/pulse/brief']; if (!b) return;
    b.items = b.items.filter(function (x) { var a = x.action || {}; return !((a.route === 'client/' + cid || a.arg === key) && /nohandler|notstarted/.test(x.kind)); });
  }
  function setTask(D, t) {
    walk(D, function (o) {
      if (o.task_id === t.id && 'task_status' in o) { o.task_status = t.status; o.handled = HANDLED[t.status] || o.handled; o.owner_name = memberName(D, t.assignee); }
      if (o.id === t.id && o !== t && 'requires_approval' in o) { Object.assign(o, t); }
      if (o.task && o.task.id === t.id) o.task = t;
    });
  }
  function memberName(D, id) { var m = (D['/api/pulse/state'].team || []).find(function (x) { return x.id === id; }); return m ? m.name : '—'; }
  function findTask(D, id) { var t = null; walk(D, function (o) { if (!t && o.id === id && 'requires_approval' in o && o.history) t = o; }); return t; }
  function act(D, url, m, body) {
    var mm;
    if ((mm = url.match(/^\/api\/pulse\/tasks\/([^/]+)\/(\w+)$/)) && mm[1] !== 'manual') {
      var t = findTask(D, mm[1]), a = mm[2]; if (!t) return { body: { detail: 'משימה לא נמצאה' }, status: 404 };
      var st = t.status, msg = null;
      if (a === 'start' && st === 'new') { t.status = 'in_progress'; msg = 'התחיל/ה טיפול'; }
      else if (a === 'submit' && st === 'in_progress') { t.status = 'awaiting_verification'; t.recheck_day = ref(D) + 3; if (t.requires_approval) t.approved_by = me; msg = 'טופל. המערכת תבדוק אוטומטית בעוד 3 ימים אם המספרים חזרו ליעד'; }
      else if (a === 'approve' && st === 'awaiting_approval') { t.status = 'awaiting_verification'; t.approved_by = me; t.recheck_day = ref(D) + 3; msg = 'אושר. נקבעה בדיקה חוזרת אוטומטית בעוד 3 ימים'; }
      else if (a === 'reject' && st === 'awaiting_approval') { t.status = 'in_progress'; msg = 'הוחזר לטיפול'; }
      else if (a === 'reassign' && body.extra) { t.assignee = body.extra; msg = 'הועבר ל' + memberName(D, body.extra); }
      else if (a === 'log_time' && body.extra) { t.minutes_spent = (t.minutes_spent || 0) + (+body.extra || 0); msg = 'תועדו ' + body.extra + ' דקות'; }
      else if (a === 'recheck_now' || a === 'simulate_fix') return { body: { ok: false, msg: 'הבדיקה החוזרת רצה בשרת אחרי כמה ימים של נתונים — במערכת המלאה רואים אותה נסגרת לבד' } };
      if (!msg) return { body: { ok: false, msg: 'הפעולה לא זמינה בסטטוס "' + (ST[st] || st) + '"' } };
      t.history.push({ day: ref(D), t: Date.now() / 1000, who: me, a: msg });
      setTask(D, t);
      if (a === 'start') dropBrief(D, t.client_id, t.alert_key);
      return { body: { ok: true, msg: msg } };
    }
    if (url === '/api/pulse/tasks' && m === 'POST') {
      var card = null; walk(D, function (o) { if (!card && o.key === body.alert_key && 'owner_name' in o) card = o; });
      if (!card) return { body: { detail: 'החריגה לא נמצאה' }, status: 404 };
      if (card.task_id) return { body: findTask(D, card.task_id) || { id: card.task_id } };
      var team = D['/api/pulse/state'].team, owner = body.assignee || (team.find(function (x) { return x.name === card.owner_name; }) || team[0]).id;
      var nt = { id: 'snap' + (++seq), account_id: '', client_id: card.client_id, alert_key: card.key, title: card.title + ' · ' + card.client, severity: card.severity,
        description: '', plan: [{ text: card.next, actionType: 'check' }], success: { text: 'המדד חוזר לטווח התקין', days: 3 }, requires_approval: false, approved_by: null,
        assignee: owner, due_day: ref(D) + (card.severity === 'red' ? 1 : 3), status: 'new', created_by: me, created_day: ref(D), history: [{ day: ref(D), t: Date.now() / 1000, who: me, a: 'נוצרה משימה' }],
        minutes_spent: 0, client_name: card.client, verification: null, recheck_day: null };
      D['/api/pulse/tasks'].tasks.unshift(nt);
      Object.keys(D).forEach(function (k) { if (k.indexOf('/api/pulse/clients/' + card.client_id + '?') === 0) { D[k].tasks.unshift(nt); D[k].alerts.forEach(function (al) { if (al.key === card.key) al.task = nt; }); } });
      walk(D, function (o) { if (o.key === card.key && 'owner_name' in o) { o.task_id = nt.id; o.task_status = 'new'; o.handled = HANDLED.new; o.owner_name = memberName(D, owner); } });
      dropBrief(D, card.client_id, card.key);
      return { body: nt, status: 201 };
    }
    if ((mm = url.match(/^\/api\/pulse\/commitments\/(\d+)$/))) {
      var n = 0; walk(D, function (o) { if (String(o.id) === mm[1] && 'due_day' in o && 'text' in o) { o.status = body.status; n++; } });
      var b = D['/api/pulse/brief']; if (b) b.items = b.items.filter(function (x) { return !(x.action && x.action.arg === mm[1] && x.kind === 'commitment'); });
      return n ? { body: { ok: true, msg: 'ההתחייבות סומנה כבוצעה' } } : { body: { detail: 'לא נמצא' }, status: 404 };
    }
    if ((mm = url.match(/^\/api\/pulse\/clients\/([^/]+)\/(\w[\w-]*)$/))) {
      var keys = Object.keys(D).filter(function (k) { return k.indexOf('/api/pulse/clients/' + mm[1] + '?') === 0; });
      if (!keys.length) return null;
      var kind = mm[2];
      keys.forEach(function (k) {
        var d = D[k];
        if (kind === 'satisfaction') d.client.satisfaction = body.score;
        if (kind === 'notes') d.notes.unshift({ kind: body.kind, text: body.text, user_name: me });
        if (kind === 'contacts') d.contacts.push({ name: body.name, role: body.role, phone: body.phone });
        if (kind === 'commitments') d.commitments.unshift({ id: 900 + (++seq), text: body.text, owner: body.owner, due_day: ref(D) + (+body.due_in || 0), status: 'open' });
        if (kind === 'update-draft') {
          var r = d.result, a0 = d.alerts[0];
          var txt = 'היי, עדכון שבועי על הקמפיינים:\n• 7 הימים האחרונים: ' + r.rec.leads + ' לידים, עלות לליד ₪' + Math.round(r.rec.cpl || 0) + (r.base.cpl ? ' (לעומת ₪' + Math.round(r.base.cpl) + ' בממוצע).' : '.') +
            (a0 ? '\n• מה זיהינו: ' + a0.card.what + '\n• מה אנחנו עושים: ' + a0.card.next + '.' : '\n• הקמפיינים יציבים ובטווח התקין.') + '\nנמשיך לעקוב ונעדכן.';
          d.drafts.unshift({ id: 900 + (++seq), text: txt, channel: 'WhatsApp', status: 'draft' });
        }
      });
      var msgs = { satisfaction: 'שביעות הרצון עודכנה', notes: 'נשמר בתיק הלקוח', contacts: 'איש הקשר נוסף', commitments: 'ההתחייבות נשמרה', 'update-draft': 'הטיוטה נשמרה בלשונית "טיפול". אפשר להעתיק ולשלוח.' };
      return msgs[kind] ? { body: { ok: true, msg: msgs[kind] }, status: kind === 'satisfaction' || kind === 'update-draft' ? 200 : 201 } : null;
    }
    if (url === '/api/pulse/check') { var st0 = D['/api/pulse/state']; return { body: { n: st0.clients, ms: 11, new: 0, cleared: 0 } }; }
    if (url === '/api/pulse/alerts/feedback') return { body: { ok: true, msg: 'תודה — המשוב נשמר' } };
    return null;
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var h = a.getAttribute('href');
    if (h === '/' || h.indexOf('/api/') === 0) { e.preventDefault(); e.stopPropagation(); toast(h === '/' ? 'זה קישור למערכת P1 המלאה' : 'דוחות HTML ו-PDF נוצרים במערכת המלאה (בגרסת התצוגה אין שרת)'); }
  }, true);
  window.addEventListener('load', function () { setTimeout(function () { toast('הדגמה חיה על נתוני דמו: אפשר ללחוץ, ליצור משימות, להתחיל טיפול ולאשר. רענון מחזיר להתחלה.'); }, 900); });
})();
