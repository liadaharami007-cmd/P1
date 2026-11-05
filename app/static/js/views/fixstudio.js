// @ts-check
// P1 Fix Studio — מבעיה לפתרון מוחשי: טקסט, מבנה, עיצוב, קוד, תצוגה מקדימה אמיתית ו-Before/After.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { $, $$, api, CATEGORIES, esc, evidenceThumb, fmtDate, hostOf, icon, sevBadge, srcBadge, toast } from "../ui.js";

const STATUSES = ["proposed", "approved", "applied", "rejected"];

/** @param {HTMLElement} view @param {{id: string|null}} params */
export async function fixStudioView(view, { id }) {
  if (!id) {
    const audits = await api("/api/audits");
    const done = audits.find((/** @type {any} */ a) => a.status === "done");
    setTitle(t("fix.title"));
    if (!done) {
      view.innerHTML = `<div class="card empty"><h3>${t("fix.title")}</h3><p>${t("fix.sub")}</p><a class="btn btn-primary" style="margin-top:12px" href="#/audits">${t("common.newAudit")}</a></div>`;
      return;
    }
    location.replace(`#/fix/${done.id}`);
    return;
  }
  const data = await api(`/api/audits/${id}/fixes`);
  const a = data.audit;
  setTitle(`${t("fix.title")} · ${a.site_name || hostOf(a.site_url)}`, `<a class="btn btn-sm" href="#/audits/${id}">${t("mc.report")}</a>`);
  /** @type {any[]} */ const fixes = data.fixes;
  const want = new URLSearchParams(location.hash.split("?")[1] || "").get("f");
  let selected = fixes.find((x) => x.finding.id === want) || fixes.find((x) => x.fix.preview.supported) || fixes[0];
  let listFilter = "all";

  view.innerHTML = `<div class="fs">
    <aside class="fs-list card">
      <div class="row" style="justify-content:space-between;margin-bottom:10px"><div><strong>${t("fix.sub")}</strong></div></div>
      <div class="seg" id="fs-filter" style="margin-bottom:10px"><button class="on" data-f="all">${t("fix.all")} (${fixes.length})</button>
        <button data-f="preview">${t("fix.withPreview")} (${fixes.filter((x) => x.fix.preview.supported).length})</button></div>
      ${a.is_demo ? `<div class="notice notice-info small" style="margin-bottom:8px"><span class="ico">i</span>${t("demo.storeNote")}</div>` : ""}
      <div id="fs-items"></div></aside>
    <section id="fs-detail"></section></div>`;

  const drawList = () => {
    const items = fixes.filter((x) => listFilter === "all" || x.fix.preview.supported);
    $("#fs-items", view).innerHTML = items.map((x) => `<button class="fs-item ${x === selected ? "on" : ""}" data-id="${x.finding.id}">
      <span class="fs-prio num">${x.finding.priority ?? "·"}</span>
      <span class="fs-item-main"><span class="fs-item-title">${esc(x.finding.title)}</span>
        <span class="row" style="gap:5px;margin-top:5px">${sevBadge(x.finding.severity)}<span class="badge outline">${t("fix.kind." + x.fix.kind)}</span>
        ${x.fix.preview.supported ? `<span class="badge st-running" title="${t("fix.withPreview")}">${icon("wand")}</span>` : ""}
        ${x.finding.fix_status && x.finding.fix_status !== "proposed" ? `<span class="badge st-${x.finding.fix_status === "applied" ? "passed" : x.finding.fix_status === "rejected" ? "skipped" : "warning"}">${t("fix.status." + x.finding.fix_status)}</span>` : ""}</span></span></button>`).join("");
    $$(".fs-item", view).forEach((b) => b.addEventListener("click", () => {
      selected = fixes.find((x) => x.finding.id === b.dataset.id);
      history.replaceState(null, "", `#/fix/${id}?f=${selected.finding.id}`);
      drawList(); drawDetail();
      if (innerWidth < 900) $("#fs-detail", view).scrollIntoView({ behavior: "smooth" });
    }));
  };
  $$("#fs-filter button", view).forEach((b) => b.addEventListener("click", () => {
    listFilter = b.dataset.f; $$("#fs-filter button", view).forEach((x) => x.classList.toggle("on", x === b)); drawList();
  }));

  const section = (/** @type {number} */ n, /** @type {string} */ title, /** @type {string} */ body, /** @type {string} */ extra = "") =>
    `<div class="fs-sec"><div class="fs-sec-head"><span class="fs-num">${n}</span><h3>${title}</h3>${extra}</div><div class="fs-sec-body">${body}</div></div>`;

  const drawDetail = () => {
    if (!selected) { $("#fs-detail", view).innerHTML = `<div class="card empty">${t("find.none")}</div>`; return; }
    const f = selected.finding, x = selected.fix, pv = selected.preview;
    const shot = f.evidence?.screenshot_id;
    const copyBlock = (/** @type {string} */ text) => `<div class="fs-copy"><span style="white-space:pre-line">${esc(text)}</span>
      <button class="icon-btn" data-copy="${esc(text)}" aria-label="${t("fix.copyBtn")}">${icon("copy")}</button></div>`;
    const suggested = `<p class="fs-summary">${esc(x.summary)}</p>
      ${x.copy?.length ? `<h5>${t("fix.copy")}</h5>${x.copy.map((/** @type {any} */ c) => `<div class="tiny muted" style="margin-top:6px">${esc(c.label)}</div>${copyBlock(c.text)}`).join("")}` : ""}
      ${x.structure?.length ? `<h5>${t("fix.structure")}</h5><ol class="fs-ol">${x.structure.map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}
      ${x.design?.length ? `<h5>${t("fix.design")}</h5><ul class="fs-ol">${x.design.map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
      ${x.code?.snippet ? `<h5>${t("fix.code")} <span class="badge outline ltr">${esc(x.code.lang)}</span></h5><div class="fs-code ltr"><pre>${esc(x.code.snippet)}</pre>
        <button class="icon-btn" data-copy="${esc(x.code.snippet)}" aria-label="${t("fix.copyBtn")}">${icon("copy")}</button></div>` : ""}
      <h5>${t("fix.steps")}</h5><ol class="fs-ol">${x.steps.map((/** @type {string} */ s) => `<li>${esc(s)}</li>`).join("")}</ol>
      ${x.usps_found?.length ? `<div class="tiny muted" style="margin-top:10px">${t("fix.usps")}: ${x.usps_found.map((/** @type {string} */ u) => `<span class="badge outline">${esc(u)}</span>`).join(" ")}</div>` : ""}
      ${x.has_placeholders ? `<div class="notice small" style="margin-top:10px"><span class="ico">i</span>${t("fix.placeholders")}</div>` : ""}
      <div class="tiny faint" style="margin-top:8px">${t("fix.engine")}: ${t("fix.engine." + x.engine)}</div>`;
    const previewBody = !x.preview.supported ? `<p class="muted">${t("fix.noPreview")}</p>` : `
      <div class="row"><button class="btn btn-primary" id="fs-gen">${icon("wand")} ${pv?.status === "done" ? t("fix.regenerate") : t("fix.generate")}</button>
        <span class="tiny muted">${pv?.created_at ? fmtDate(pv.created_at) : ""} · ${esc(x.preview.device === "mobile" ? t("evidence.mobile") : t("evidence.desktop"))}</span></div>
      <div id="fs-gen-state" style="margin-top:10px">${pv?.status === "failed" ? `<div class="notice notice-error small"><span class="ico">!</span>${t("fix.failed")} ${esc(pv.error)}</div>` : ""}</div>
      <p class="tiny muted" style="margin-top:8px">${t("fix.isolated")}</p>`;
    const ba = pv?.status === "done" && pv.before_shot && pv.after_shot ? `
      <div class="ba ${x.preview.device === "mobile" ? "ba-mobile" : ""}" id="ba"><img src="/api/screenshots/${pv.after_shot}" alt="after">
        <div class="ba-before" id="ba-before"><img src="/api/screenshots/${pv.before_shot}" alt="before"></div>
        <div class="ba-handle" id="ba-handle"><span>⇆</span></div>
        <span class="ba-tag ba-tag-b">${t("cmp.before")}</span><span class="ba-tag ba-tag-a">${t("cmp.after")}</span></div>
      <input type="range" min="0" max="100" value="50" id="ba-range" class="ba-range" aria-label="${t("fix.drag")}">
      <div class="row tiny muted" style="justify-content:space-between"><span>${t("fix.problemMarked")}</span><span>${t("fix.drag")}</span></div>
      <div class="row" style="margin-top:8px">${(pv.applied || []).map((/** @type {any} */ o) => `<span class="badge ${o.ok ? "st-passed" : "st-failed"} ltr">${o.ok ? "✓" : "✕"} ${esc(o.op)}${o.target ? ":" + esc(o.target) : ""}</span>`).join("")}</div>`
      : `<p class="muted small">${x.preview.supported ? t("fix.generate") + " ↑" : "—"}</p>`;
    const status = `<div class="seg" id="fs-status">${STATUSES.map((s) => `<button data-s="${s}" class="${(f.fix_status || "proposed") === s ? "on" : ""}">${t("fix.status." + s)}</button>`).join("")}</div>
      <p class="tiny muted" style="margin-top:8px">${t("fix.statusNote")}</p>`;

    $("#fs-detail", view).innerHTML = `<div class="card fs-card">
      <div class="row" style="justify-content:space-between;margin-bottom:6px"><div class="row">${sevBadge(f.severity)}${srcBadge(f.source)}
        <span class="badge outline">${esc(CATEGORIES[f.category] || f.category)}</span><span class="badge outline">${t("fix.kind." + x.kind)}</span></div>
        <span class="tiny muted">${t("fix.priority")} #${f.priority ?? "—"}</span></div>
      <h2 class="fs-title">${esc(f.title)}</h2>
      ${section(1, t("fix.problem"), `<p>${esc(f.detail)}</p>`)}
      ${section(2, t("fix.evidence"), shot ? `<div style="max-width:420px">${evidenceThumb(shot, f.title)}</div>` : `<p class="muted small">${f.evidence?.agent ? esc(f.evidence.agent) : ""} ${f.evidence?.page_url ? `<span class="ltr">${esc(f.evidence.page_url)}</span>` : "—"}</p>`)}
      ${section(3, t("fix.impact"), `<p><strong>${t("impact." + f.impact)}</strong> <span class="tiny muted">${t("find.impactNote")}</span></p><p class="muted" style="margin-top:4px">${esc(f.why_it_matters)}</p>`)}
      ${section(4, t("fix.suggested"), suggested)}
      ${section(5, t("fix.preview"), previewBody)}
      ${section(6, t("fix.beforeAfter"), ba)}
      ${section(7, t("fix.applyStatus"), status)}
    </div>`;

    $$("[data-copy]", view).forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast(t("fix.copied")); } catch { toast(t("common.error"), "error"); }
    }));
    $$("#fs-status button", view).forEach((b) => b.addEventListener("click", async () => {
      try {
        await api(`/api/findings/${f.id}/fix`, { method: "PATCH", body: JSON.stringify({ status: b.dataset.s }) });
        f.fix_status = b.dataset.s; toast(t("fix.status." + b.dataset.s)); drawList(); drawDetail();
      } catch (e) { toast(/** @type {Error} */ (e).message, "error"); }
    }));
    const gen = $("#fs-gen", view);
    if (gen) gen.onclick = async () => {
      gen.disabled = true;
      $("#fs-gen-state", view).innerHTML = `<div class="notice notice-info small"><span class="spinner"></span>${t("fix.generating")}</div>`;
      try {
        selected.preview = await api(`/api/findings/${f.id}/preview`, { method: "POST" });
        drawDetail();
        if (selected.preview.status === "done") $("#ba", view)?.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (e) { toast(/** @type {Error} */ (e).message, "error"); gen.disabled = false; $("#fs-gen-state", view).innerHTML = ""; }
    };
    const range = /** @type {HTMLInputElement|null} */ (view.querySelector("#ba-range"));
    if (range) {
      const setPos = (/** @type {number} */ v) => {
        $("#ba-before", view).style.clipPath = `inset(0 ${100 - v}% 0 0)`;
        $("#ba-handle", view).style.left = `${v}%`;
      };
      range.addEventListener("input", () => setPos(+range.value)); setPos(50);
      const box = $("#ba", view);
      const drag = (/** @type {PointerEvent} */ ev) => { const r = box.getBoundingClientRect(); const v = Math.min(100, Math.max(0, ((ev.clientX - r.left) / r.width) * 100)); range.value = String(v); setPos(v); };
      box.addEventListener("pointerdown", (/** @type {PointerEvent} */ ev) => { drag(ev); box.setPointerCapture(ev.pointerId); box.onpointermove = drag; });
      box.addEventListener("pointerup", () => { box.onpointermove = null; });
    }
  };
  drawList(); drawDetail();
}
