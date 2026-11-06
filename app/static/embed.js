/* P1 AI — קליטת פניות מטפסים בכל אתר (Wix, WordPress, Shopify, אתר מותאם…).
   לא משנה את הטופס ולא חוסם את השליחה הרגילה: רק שולח עותק של שם/טלפון/מייל/הודעה ל-CRM של P1.
   לעולם לא שולח סיסמאות, פרטי אשראי או שדות נסתרים. */
(function () {
  var s = document.currentScript; if (!s) return;
  var key = s.getAttribute("data-p1-key"); var base = s.src.replace(/\/embed\.js.*$/, "");
  if (!key) return;
  function pick(form) {
    var out = { name: "", phone: "", email: "", message: "" }, extra = [];
    var els = form.querySelectorAll("input, textarea, select");
    for (var i = 0; i < els.length; i++) {
      var el = els[i], t = (el.type || "").toLowerCase(), ac = (el.getAttribute("autocomplete") || "").toLowerCase();
      var id = ((el.name || "") + " " + (el.id || "") + " " + (el.placeholder || "") + " " + (el.getAttribute("aria-label") || "")).toLowerCase();
      if (!el.value || /password|hidden|file|submit|button|checkbox|radio/.test(t) || /^cc-|card|cvv|cvc|אשראי/.test(ac + " " + id)) continue;
      var v = String(el.value).slice(0, 1000);
      if (t === "email" || /mail|מייל|דוא/.test(id)) out.email = out.email || v;
      else if (t === "tel" || /phone|tel|טלפון|נייד/.test(id)) out.phone = out.phone || v;
      else if (/name|שם/.test(id) && !out.name) out.name = v;
      else if (el.tagName === "TEXTAREA" || /message|msg|הודעה|פרטים/.test(id)) out.message = out.message || v;
      else if (t !== "search") extra.push(v);
    }
    if (extra.length && !out.message) out.message = extra.join(" · ").slice(0, 1000);
    return out;
  }
  document.addEventListener("submit", function (e) {
    var f = e.target; if (!f || f.getAttribute("data-p1-ignore") !== null || f.getAttribute("role") === "search") return;
    var d = pick(f); if (!d.phone && !d.email) return;  // רק טפסי פנייה
    d.page = location.href.slice(0, 500);
    var body = JSON.stringify(d), url = base + "/api/collect/" + encodeURIComponent(key);
    try { if (!navigator.sendBeacon || !navigator.sendBeacon(url, body)) fetch(url, { method: "POST", body: body, keepalive: true, mode: "no-cors" }); } catch (_) {}
  }, true);
})();
