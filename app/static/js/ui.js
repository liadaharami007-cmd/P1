// רכיבי ממשק משותפים
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(", ") : `שגיאה ${res.status}`);
  }
  return data;
}

// ---------------------------------------------------------------- אייקונים (SVG בקו דק)
const P = {
  dashboard: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  audit: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M8 11l2 2 4-4"/>',
  tasks: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  external: '<path d="M14 3h7v7M10 14 21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
};
export const icon = (name, cls = "") =>
  `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`;

// ---------------------------------------------------------------- מילונים
export const SEVERITY = {
  critical: { label: "קריטי", ico: "⛔" }, high: { label: "חמור", ico: "▲" },
  medium: { label: "בינוני", ico: "●" }, low: { label: "נמוך", ico: "○" },
};
export const IMPACT = { high: "השפעה גבוהה על מכירות", medium: "השפעה בינונית", low: "השפעה נמוכה" };
export const SOURCE = {
  measured: { label: "נבדק בפועל", tip: "נמדד בדפדפן אמיתי שביקר באתר" },
  simulation: { label: "סימולציה", tip: "סימולציית לקוח מבוססת כללים על נתונים שנמדדו — לא לקוחות אמיתיים" },
  store_data: { label: "נתוני חנות", tip: "נתונים אמיתיים מחיבור לחנות" },
  ai: { label: "השערת AI", tip: "הערכה של מודל AI — יש לאמת" },
};
export const STEP_STATUS = {
  passed: { label: "עבר", ico: "✓" }, failed: { label: "נכשל", ico: "✕" },
  warning: { label: "אזהרה", ico: "!" }, skipped: { label: "לא נבדק", ico: "–" },
};
export const FINDING_STATUS = { open: "פתוח", in_progress: "בטיפול", done: "תוקן", dismissed: "לא רלוונטי" };
export const PERSONAS = {
  skeptic: { name: "הלקוח החשדן", emoji: "🧐", goal: "רוצה להיות בטוח שהחנות אמינה לפני שהוא משאיר כרטיס אשראי" },
  bargain: { name: "מחפש המחיר", emoji: "🏷️", goal: "רוצה לדעת מהר כמה זה עולה כולל משלוח, ולמצוא מבצע" },
  hesitant: { name: "המתלבט", emoji: "🤔", goal: "מתעניין, אבל צריך שכנוע וביטחון שאפשר להחזיר" },
  rushed: { name: "הממהר", emoji: "⚡", goal: "יודע מה הוא רוצה ורוצה לסיים קנייה בטלפון תוך דקה" },
  researcher: { name: "החוקר", emoji: "🔬", goal: "רוצה להבין לעומק את המוצר לפני החלטה" },
};
export const VERDICT = {
  likely_buy: { label: "כנראה יקנה", cls: "st-passed", ico: "✓" },
  hesitant: { label: "מתלבט", cls: "st-warning", ico: "?" },
  likely_leave: { label: "כנראה יעזוב", cls: "st-failed", ico: "✕" },
};
export let CATEGORIES = {
  journey: "מסע רכישה", trust: "אמון", speed: "מהירות", mobile: "מובייל", ux: "תוכן וחוויית משתמש", seo: "SEO ומדידה",
};
export const setCategories = (c) => { if (c) CATEGORIES = c; };

export const sevBadge = (s) => `<span class="badge sev-${s}"><span class="ico">${SEVERITY[s].ico}</span>${SEVERITY[s].label}</span>`;
export const srcBadge = (s) => `<span class="badge src-${s}" title="${esc(SOURCE[s].tip)}">${SOURCE[s].label}</span>`;
export const stepBadge = (s) => `<span class="badge st-${s}">${STEP_STATUS[s].ico} ${STEP_STATUS[s].label}</span>`;

// ---------------------------------------------------------------- ציון
export function grade(score) {
  if (score == null) return { label: "לא נבדק", color: "var(--neutral)" };
  if (score >= 80) return { label: "מצב טוב", color: "var(--good)" };
  if (score >= 50) return { label: "דורש שיפור", color: "var(--warning)" };
  return { label: "דורש טיפול דחוף", color: "var(--critical)" };
}

export function scoreRing(score, size = 150) {
  const r = (size - 16) / 2, c = 2 * Math.PI * r;
  const g = grade(score);
  const off = score == null ? c : c * (1 - score / 100);
  return `<div class="ring" style="width:${size}px;height:${size}px" role="img" aria-label="ציון ${score ?? "לא זמין"} מתוך 100, ${g.label}">
    <svg width="${size}" height="${size}"><circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="10"/>
    <circle class="ring-value" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${g.color}" stroke-width="10" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}"/></svg>
    <div class="ring-label"><div class="ring-num">${score ?? "—"}</div><div class="ring-of">מתוך 100</div></div></div>`;
}
export const gradeLabel = (score) => { const g = grade(score); return `<span class="grade"><span class="grade-dot" style="background:${g.color}"></span>${g.label}</span>`; };

export function categoryBars(scores) {
  return `<div class="bars">${Object.entries(CATEGORIES).map(([k, label]) => {
    const v = scores ? scores[k] : null;
    return `<div class="bar-row"><span class="bar-label">${label}</span>${v == null
      ? `<span class="bar-na">לא נבדק בסריקה זו</span>`
      : `<div class="bar-track" role="img" aria-label="${label}: ${v}"><div class="bar-fill" style="width:${v}%"></div></div><span class="bar-val">${v}</span>`}</div>`;
  }).join("")}</div>`;
}

// גרף מגמה — סדרה אחת, רק נקודות אמיתיות. מינימום 2 בדיקות.
export function trendChart(points) {
  const W = 600, H = 180, padX = 30, padY = 16;
  const xs = (i) => points.length === 1 ? W / 2 : padX + (i * (W - padX * 2)) / (points.length - 1);
  const ys = (v) => padY + (1 - v / 100) * (H - padY * 2);
  const grid = [0, 50, 100].map((v) => `<line class="grid-line" x1="${padX}" x2="${W - padX}" y1="${ys(v)}" y2="${ys(v)}"/>
    <text class="axis-text" x="${W - padX + 6}" y="${ys(v) + 4}" text-anchor="start">${v}</text>`).join("");
  const line = points.map((p, i) => `${xs(i)},${ys(p.score)}`).join(" ");
  const dots = points.map((p, i) => `<circle class="dot" cx="${xs(i)}" cy="${ys(p.score)}" r="5"/>
    <rect class="hit" x="${xs(i) - 18}" y="0" width="36" height="${H}" data-i="${i}"/>`).join("");
  return `<div class="trend"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="מגמת ציון לאורך ${points.length} בדיקות">
    ${grid}<polyline class="line" points="${line}"/>${dots}</svg><div class="tooltip" hidden></div></div>`;
}
export function bindTrend(root, points) {
  const box = root.querySelector(".trend"); if (!box) return;
  const tip = box.querySelector(".tooltip");
  box.querySelectorAll(".hit").forEach((h) => {
    h.addEventListener("mouseenter", () => {
      const p = points[+h.dataset.i];
      const dot = h.previousElementSibling.getBoundingClientRect(), b = box.getBoundingClientRect();
      tip.innerHTML = `ציון <strong>${p.score}</strong> · ${fmtDate(p.at)}`;
      tip.style.right = `${b.right - dot.right + dot.width / 2}px`; tip.style.top = `${dot.top - b.top}px`; tip.hidden = false;
    });
    h.addEventListener("mouseleave", () => (tip.hidden = true));
    h.addEventListener("click", () => (location.hash = `#/audits/${points[+h.dataset.i].id}`));
  });
}

// ---------------------------------------------------------------- כללי
export function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("he-IL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
export function hostOf(url) { try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; } }

export function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

export function openLightbox(src, caption) {
  const d = $("#lightbox"); $("#lightbox-img").src = src; $("#lightbox-caption").textContent = caption || ""; d.showModal();
}

export const shotUrl = (id) => `/api/screenshots/${id}`;
export function evidenceThumb(id, caption, mobile = false) {
  if (!id) return "";
  return `<button class="evidence${mobile ? " mobile" : ""}" data-shot="${id}" data-caption="${esc(caption)}" aria-label="הגדלת צילום מסך: ${esc(caption)}">
    <img src="${shotUrl(id)}" alt="${esc(caption)}" loading="lazy"><span>${esc(caption)}</span></button>`;
}

// Markdown בסיסי ובטוח (לצ'אט)
export function md(text) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd(); let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^#{1,6}\s+(.*)/))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
    else if (!line.trim()) close();
    else { close(); html += `<p>${inline(line)}</p>`; }
  }
  close(); return html;
}

// טופס התחלת בדיקה — משותף ללוח הבקרה ולעמוד הבדיקות
export function auditForm({ ready, missing }) {
  if (!ready) return `<div class="notice notice-warn">בדיקות בדפדפן לא זמינות בשרת הזה: ${esc(missing)}</div>`;
  return `<form class="audit-form" data-audit-form>
    <div class="row"><input class="input" name="url" type="text" inputmode="url" autocomplete="url" placeholder="https://your-store.co.il" required>
    <button class="btn btn-primary" type="submit">${icon("audit")} התחילו בדיקה</button></div>
    <label class="check" style="margin-top:12px"><input type="checkbox" name="confirm" required>
    <span>אני הבעלים של האתר או שיש לי הרשאה לבדוק אותו. הבדיקה גולשת באתר, מוסיפה מוצר לסל ומגיעה לקופה — <strong>בלי למלא פרטים ובלי לבצע הזמנה</strong>.</span></label>
    <p class="form-error small" style="color:var(--critical-text);margin:8px 0 0" hidden></p></form>`;
}
export function bindAuditForm(root) {
  root.querySelectorAll("[data-audit-form]").forEach((form) => form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]"), err = form.querySelector(".form-error");
    btn.disabled = true; err.hidden = true;
    try {
      const a = await api("/api/audits", { method: "POST", body: JSON.stringify({ url: form.url.value, confirm_permission: form.confirm.checked }) });
      location.hash = `#/audits/${a.id}`;
    } catch (ex) { err.textContent = ex.message; err.hidden = false; btn.disabled = false; }
  }));
}
