// @ts-check
// רכיבי ממשק משותפים. כל הטקסטים דרך t() (עברית/אנגלית).
import { t, locale, lang } from "./i18n.js";

/** @param {string} s @param {ParentNode} [root] @returns {any} */
export const $ = (s, root = document) => root.querySelector(s);
/** @param {string} s @param {ParentNode} [root] @returns {any[]} */
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

/** @param {unknown} s */
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => /** @type {Record<string,string>} */ ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export class ApiError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) { super(message); this.status = status; }
}

/**
 * קריאה ל-API. 401 מעביר למסך התחברות.
 * @param {string} path @param {RequestInit} [opts] @returns {Promise<any>}
 */
export async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(", ") : `${t("common.error")} ${res.status}`;
    if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new CustomEvent("p1:unauthorized"));
    throw new ApiError(msg, res.status);
  }
  return data;
}

// ---------------------------------------------------------------- אייקונים
/** @type {Record<string, string>} */
const P = {
  overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  audit: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  tasks: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
  account: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  admin: '<path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', chevron: '<path d="m6 9 6 6 6-6"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>', refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>', sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>', globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  wand: '<path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M15 9h0M17.8 6.2 19 5M3 21l9-9M12.2 6.2 11 5"/>',
  rocket: '<path d="M5 15c-1.5 1.5-2 4-2 6 2 0 4.5-.5 6-2M14 4c3-1.5 6-1 6-1s.5 3-1 6l-6 6-5-5z"/><circle cx="15" cy="9" r="1.6"/><path d="M9 10 5 10l2-3h4M14 15v4l3-2v-4"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>', browser: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>',
  megaphone: '<path d="M3 11v2a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1zM16 9a3 3 0 0 1 0 6M7 14l1.5 5h2.5l-1-5"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>', building: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1M10 21v-3h4v3"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  pen: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>', video: '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="m16 10 5-3v10l-5-3z"/>',
  layout: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M9 21V9"/>', handshake: '<path d="m11 17 2 2a1.4 1.4 0 0 0 2-2M14 14l2.5 2.5a1.4 1.4 0 0 0 2-2L15 11M3 13l4 4 1.5-1.5M3 6h4l4 3M21 6h-4l-6 5.5a1.4 1.4 0 0 0 2 2L16 11l5 4"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>', bolt: '<path d="M13 3 4 14h7l-1 7 9-11h-7z"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
};
/** @param {string} name @param {string} [cls] */
export const icon = (name, cls = "") =>
  `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`;

// ---------------------------------------------------------------- תגיות
const SEV_ICO = { critical: "⛔", high: "▲", medium: "●", low: "○" };
/** @param {"critical"|"high"|"medium"|"low"} s */
export const sevBadge = (s) => `<span class="badge sev-${s}"><span class="ico" aria-hidden="true">${SEV_ICO[s]}</span>${t("sev." + s)}</span>`;
/** @param {string} s @param {boolean} [off] */
export const srcBadge = (s, off = false) => `<span class="badge src-${s}${off ? " src-off" : ""}" title="${esc(t(`src.${s}.tip`))}">${t("src." + s)}${off ? " · " + t("src.notConnected") : ""}</span>`;
const STEP_ICO = { passed: "✓", failed: "✕", warning: "!", skipped: "–" };
/** @param {"passed"|"failed"|"warning"|"skipped"} s */
export const stepBadge = (s) => `<span class="badge st-${s}">${STEP_ICO[s]} ${t("step." + s)}</span>`;
export const STEP_ICON = STEP_ICO;

/** @type {Record<string,string>} */
export let CATEGORIES = {};
/** @param {Record<string,string>} he @param {Record<string,string>} en */
export const setCategories = (he, en) => { CATEGORIES = lang === "en" ? en : he; };

// ---------------------------------------------------------------- ציונים
/** @param {number|null|undefined} score */
export function grade(score) {
  if (score == null) return { label: t("common.notTested"), color: "var(--neutral)" };
  if (score >= 80) return { label: t("grade.good"), color: "var(--good)" };
  if (score >= 50) return { label: t("grade.fair"), color: "var(--warning)" };
  return { label: t("grade.poor"), color: "var(--critical)" };
}

/** @param {number|null} score @param {number} [size] */
export function scoreRing(score, size = 140) {
  const r = (size - 14) / 2, c = 2 * Math.PI * r;
  const g = grade(score);
  const off = score == null ? c : c * (1 - score / 100);
  return `<div class="ring" style="width:${size}px;height:${size}px" role="img" aria-label="${score ?? "—"} ${t("common.of100")} — ${g.label}">
    <svg width="${size}" height="${size}"><circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="9"/>
    <circle class="ring-value" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${g.color}" stroke-width="9" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${c}" data-off="${off}"/></svg>
    <div class="ring-label"><div class="ring-num">${score ?? "—"}</div><div class="ring-of">${t("common.of100")}</div></div></div>`;
}
/** אנימציית הטבעת אחרי הכנסה ל-DOM @param {ParentNode} root */
export function animateRings(root) {
  requestAnimationFrame(() => $$(".ring-value", root).forEach((el) => el.setAttribute("stroke-dashoffset", el.dataset.off)));
}
/** @param {number|null} score */
export const gradeLabel = (score) => { const g = grade(score); return `<span class="grade"><span class="grade-dot" style="background:${g.color}"></span>${g.label}</span>`; };

/** @param {Record<string, number|null>|null} scores */
export function categoryBars(scores) {
  return `<div class="bars">${Object.entries(CATEGORIES).map(([k, label]) => {
    const v = scores ? scores[k] : null;
    return `<div class="bar-row"><span class="bar-label">${esc(label)}</span>${v == null
      ? `<span class="bar-na">${t("common.notTested")}</span>`
      : `<div class="bar-track" role="img" aria-label="${esc(label)}: ${v}"><div class="bar-fill" style="width:${v}%"></div></div><span class="bar-val">${v}</span>`}</div>`;
  }).join("")}</div>`;
}

/** @param {number|null|undefined} d */
export function delta(d) {
  if (d == null) return "";
  const cls = d > 0 ? "up" : d < 0 ? "down" : "flat";
  return `<span class="delta ${cls}">${d > 0 ? "▲ +" : d < 0 ? "▼ " : "± "}${d}</span>`;
}

/**
 * גרף קו אינטראקטיבי (סדרה אחת) עם crosshair ו-tooltip. רק נקודות אמיתיות.
 * @param {HTMLElement} el @param {{score:number|null, at:string, id:string}[]} points @param {string} label
 */
export function lineChart(el, points, label) {
  const pts = points.filter((p) => p.score != null);
  const W = 640, H = 200, padX = 28, padT = 14, padB = 26;
  const xs = (/** @type {number} */ i) => pts.length === 1 ? W / 2 : padX + (i * (W - padX * 2)) / (pts.length - 1);
  const ys = (/** @type {number} */ v) => padT + (1 - v / 100) * (H - padT - padB);
  const rtl = lang === "he";
  const X = (/** @type {number} */ i) => (rtl ? W - xs(i) : xs(i));
  const grid = [0, 50, 100].map((v) => `<line class="grid-line" x1="${padX}" x2="${W - padX}" y1="${ys(v)}" y2="${ys(v)}"/>
    <text class="axis-text" x="${rtl ? W - 4 : 4}" y="${ys(v) + 4}" text-anchor="${rtl ? "end" : "start"}">${v}</text>`).join("");
  const line = pts.map((p, i) => `${X(i)},${ys(/** @type {number} */ (p.score))}`).join(" ");
  const area = `${X(0)},${ys(0)} ${line} ${X(pts.length - 1)},${ys(0)}`;
  const fmt = (/** @type {string} */ iso) => new Date(iso).toLocaleDateString(locale(), { day: "numeric", month: "short" });
  const xl = pts.map((p, i) => (i === 0 || i === pts.length - 1 || pts.length <= 6) ? `<text class="axis-text" x="${X(i)}" y="${H - 6}" text-anchor="middle">${fmt(p.at)}</text>` : "").join("");
  const dots = pts.map((p, i) => `<rect class="hit" x="${X(i) - 20}" y="0" width="40" height="${H}" data-i="${i}"/><circle class="dot" cx="${X(i)}" cy="${ys(/** @type {number} */ (p.score))}" r="4.5"/>`).join("");
  el.innerHTML = `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${grid}
    <polygon class="area" points="${area}"/><polyline class="line" points="${line}"/><line class="crosshair" y1="${padT}" y2="${H - padB}" x1="-10" x2="-10"/>${dots}${xl}</svg>
    <div class="tooltip" hidden></div></div>`;
  const svg = $("svg", el), tip = $(".tooltip", el), cross = $(".crosshair", el);
  $$(".hit", el).forEach((h) => {
    h.addEventListener("mouseenter", () => {
      const i = +h.dataset.i, p = pts[i];
      const sx = svg.getBoundingClientRect().width / W;
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i));
      $$(".dot", el).forEach((d, j) => d.classList.toggle("on", j === i));
      tip.innerHTML = `<strong>${p.score}</strong> · ${esc(label)} · ${new Date(p.at).toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
      tip.style.left = `${X(i) * sx}px`; tip.style.top = `${ys(/** @type {number} */ (p.score)) * sx}px`; tip.hidden = false;
    });
    h.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("x1", "-10"); cross.setAttribute("x2", "-10"); });
    h.addEventListener("click", () => (location.hash = `#/audits/${pts[+h.dataset.i].id}`));
  });
}

/** השוואת לפני/אחרי לפי חלקים — שתי סדרות: לפני (אפור) ואחרי (כחול), עם מקרא ותוויות ערך. @param {any} cmp */
export function compareBars(cmp) {
  const rows = Object.entries(cmp.categories).map(([k, v]) => {
    const b = /** @type {any} */ (v);
    return `<div class="cmp-row"><span class="bar-label">${esc(CATEGORIES[k] || k)}</span>
      <div class="cmp-bars" role="img" aria-label="${esc(CATEGORIES[k] || k)}: ${b.before ?? "—"} → ${b.after ?? "—"}">
        <div class="cmp-before" style="width:${b.before ?? 0}%" title="${t("cmp.before")}: ${b.before ?? "—"}"></div>
        <div class="cmp-after" style="width:${b.after ?? 0}%" title="${t("cmp.after")}: ${b.after ?? "—"}"></div></div>
      <span class="num small" style="text-align:end">${b.after ?? "—"} ${delta(b.delta)}</span></div>`;
  }).join("");
  return `<div class="legend" style="margin-bottom:8px"><span><span class="swatch" style="background:var(--series-muted)"></span>${t("cmp.before")}</span>
    <span><span class="swatch" style="background:var(--series-1)"></span>${t("cmp.after")}</span></div>${rows}`;
}

// ---------------------------------------------------------------- כללי
/** @param {string|null|undefined} iso */
export function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
/** @param {string} url */
export function hostOf(url) { try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; } }
/** @param {number} ms */
export function fmtDuration(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** @param {string} msg @param {"success"|"error"|"info"} [kind] */
export function toast(msg, kind = "success") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="t-ico">${kind === "success" ? "✓" : kind === "error" ? "!" : "i"}</span><span>${esc(msg)}</span>`;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 250); }, kind === "error" ? 5000 : 2800);
}

/** @param {string} src @param {string} [caption] */
export function openLightbox(src, caption) {
  const d = $("#lightbox"); $("#lightbox-img").src = src; $("#lightbox-caption").textContent = caption || ""; d.showModal();
}
/** @param {string} html */
export function openModal(html) {
  $("#modal-body").innerHTML = html + `<div class="row" style="margin-top:18px;justify-content:flex-end"><button class="btn" data-close-modal>${t("common.close")}</button></div>`;
  $("#modal").showModal();
}

/** @param {string} id */
export const shotUrl = (id) => `/api/screenshots/${id}`;
/** @param {string|null|undefined} id @param {string} caption @param {boolean} [mobile] */
export function evidenceThumb(id, caption, mobile = false) {
  if (!id) return "";
  return `<button class="evidence${mobile ? " mobile" : ""}" data-shot="${id}" data-caption="${esc(caption)}" aria-label="${esc(caption)}">
    <img src="${shotUrl(id)}" alt="${esc(caption)}" loading="lazy"><span>${esc(caption)}</span></button>`;
}

/** Markdown בסיסי ובטוח @param {string} text */
export function md(text) {
  const lines = esc(text).split("\n");
  let html = "", list = /** @type {string|null} */ (null);
  const inline = (/** @type {string} */ s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
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

// ---------------------------------------------------------------- טופס בדיקה
/** @param {{ready:boolean, missing:string|null}} cap @param {boolean} [large] */
export function auditForm(cap, large = false) {
  if (!cap.ready) return `<div class="notice notice-warn">${t("form.browserMissing")} ${esc(cap.missing)}</div>`;
  return `<form class="audit-form" data-audit-form>
    <div class="row"><input class="input" name="url" type="text" inputmode="url" autocomplete="url" placeholder="${t("form.urlPlaceholder")}" required aria-label="URL">
    <button class="btn btn-primary${large ? " btn-lg" : ""}" type="submit">${icon("audit")} ${t("form.start")}</button></div>
    <label class="check" style="margin-top:12px"><input type="checkbox" name="confirm" required><span>${t("form.permission")}</span></label>
    <p class="form-error" style="margin-top:8px" hidden></p></form>`;
}
/** @param {ParentNode} root */
export function bindAuditForm(root) {
  $$("[data-audit-form]", root).forEach((form) => form.addEventListener("submit", async (/** @type {Event} */ e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form), err = $(".form-error", form);
    btn.disabled = true; err.hidden = true;
    const original = btn.innerHTML; btn.innerHTML = `<span class="spinner"></span> ${t("common.loading")}`;
    try {
      const a = await api("/api/audits", { method: "POST", body: JSON.stringify({ url: form.url.value, confirm_permission: form.confirm.checked }) });
      window.dispatchEvent(new CustomEvent("p1:usage"));
      location.hash = `#/audits/${a.id}`;
    } catch (ex) { err.textContent = /** @type {Error} */ (ex).message; err.hidden = false; btn.disabled = false; btn.innerHTML = original; }
  }));
}
