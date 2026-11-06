// @ts-check
// בונה דפי נחיתה: יצירה מתיאור → תצוגה מקדימה (מחשב/טלפון) → עריכה בשיחה → גרסאות → ייצוא → פרסום באישור.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";
import { openActionModal } from "./approvals.js";

/** @param {HTMLElement} view */
export async function pagesView(view) {
  const id = new URLSearchParams(location.hash.split("?")[1] || "").get("id");
  setTitle(t("pg.title"));
  const list = await api("/api/pages");
  if (!id) {
    view.innerHTML = `<div class="stack">
      ${list.ai ? "" : `<div class="notice notice-warn"><span class="ico">!</span><span>${t("st.noAi")} <a href="#/integrations">${t("nav.integrations")}</a></span></div>`}
      <form class="card stack" id="pg-new" novalidate><h2 style="font-size:16px">${t("pg.new")}</h2>
        <textarea class="input" name="brief" rows="3" placeholder="${t("pg.ph")}"></textarea>
        <div class="row" style="justify-content:space-between"><span class="tiny faint">${t("pg.note")}</span>
        <button class="btn btn-primary" ${list.ai ? "" : "disabled"}>${icon("sparkle")}${t("pg.create")}</button></div></form>
      ${list.items.length ? `<div class="list">${list.items.map((/** @type {any} */ p) => `<a class="list-item" href="#/pages?id=${p.id}"><strong class="small">${esc(p.title)}</strong>
        <span class="badge ${p.status === "published" ? "st-passed" : ""}">${t("pg.st." + p.status)}</span><span class="tiny faint" style="margin-inline-start:auto">v${p.version}</span></a>`).join("")}</div>` : ""}</div>`;
    const f = /** @type {HTMLFormElement} */ (view.querySelector("#pg-new"));
    f.onsubmit = async (e) => { e.preventDefault(); const b = /** @type {HTMLButtonElement} */ (f.querySelector("button")); b.disabled = true; b.innerHTML = `<span class="spinner"></span>${t("st.working")}`;
      try { const p = await api("/api/pages", { method: "POST", body: JSON.stringify({ brief: new FormData(f).get("brief") }) }); location.hash = `#/pages?id=${p.id}`; }
      catch (err) { toast(/** @type {Error} */ (err).message, "error"); b.disabled = false; b.textContent = t("pg.create"); } };
    return;
  }
  let device = "mobile";
  const draw = async () => {
    const p = await api(`/api/pages/${id}`);
    view.innerHTML = `<div class="pg-wrap">
      <div class="pg-side stack">
        <div class="row" style="justify-content:space-between"><strong>${esc(p.title)}</strong><span class="badge ${p.status === "published" ? "st-passed" : ""}">${t("pg.st." + p.status)} · v${p.version}</span></div>
        ${p.spec.missing_info.length ? `<div class="out-missing small"><div class="out-key">${t("st.f.missing_info")}</div>${p.spec.missing_info.map(esc).join(" · ")}</div>` : ""}
        <form id="pg-edit" class="stack" novalidate><textarea class="input" name="instruction" rows="3" placeholder="${t("pg.editPh")}"></textarea>
          <button class="btn btn-primary btn-sm">${icon("wand")}${t("pg.edit")}</button></form>
        <div class="row"><a class="btn btn-sm" href="/api/pages/${id}/export">${icon("download")}${t("pg.export")}</a>
          ${p.status === "published" ? `<a class="btn btn-sm" href="/p/${id}/" target="_blank" rel="noopener">${t("pg.open")}</a><button class="btn btn-sm btn-ghost" id="pg-unpub">${t("pg.unpublish")}</button>`
            : `<button class="btn btn-sm" id="pg-pub">${t("pg.publish")}</button>`}</div>
        <details><summary class="small">${t("pg.versions")} (${p.versions.length})</summary><div class="stack-sm" style="margin-top:8px">${p.versions.map((/** @type {any} */ v) =>
          `<div class="row small"><span>v${v.version}</span><span class="muted truncate" style="flex:1">${esc(v.note || "")}</span>${v.version !== p.version ? `<button class="btn btn-sm btn-ghost" data-v="${v.version}">${t("pg.restore")}</button>` : ""}</div>`).join("")}</div></details>
        <a class="small" href="#/pages">← ${t("pg.all")}</a></div>
      <div class="pg-preview"><div class="seg"><button data-d="mobile" class="${device === "mobile" ? "on" : ""}">${t("pg.mobile")}</button><button data-d="desktop" class="${device === "desktop" ? "on" : ""}">${t("pg.desktop")}</button></div>
        <div class="pg-frame ${device}"><iframe title="preview" src="/api/pages/${id}/preview?v=${p.version}" sandbox="allow-same-origin"></iframe></div></div></div>`;
    view.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { device = /** @type {HTMLElement} */ (b).dataset.d || "mobile"; draw(); }));
    const ef = /** @type {HTMLFormElement} */ (view.querySelector("#pg-edit"));
    ef.onsubmit = async (e) => { e.preventDefault(); const b = /** @type {HTMLButtonElement} */ (ef.querySelector("button")); b.disabled = true; b.innerHTML = `<span class="spinner"></span>`;
      try { await api(`/api/pages/${id}/edit`, { method: "POST", body: JSON.stringify({ instruction: new FormData(ef).get("instruction") }) }); draw(); }
      catch (err) { toast(/** @type {Error} */ (err).message, "error"); b.disabled = false; b.textContent = t("pg.edit"); } };
    view.querySelector("#pg-pub")?.addEventListener("click", async () => { try { openActionModal(await api(`/api/pages/${id}/publish`, { method: "POST" }), draw); } catch (err) { toast(/** @type {Error} */ (err).message, "error"); } });
    view.querySelector("#pg-unpub")?.addEventListener("click", async () => { await api(`/api/pages/${id}/unpublish`, { method: "POST" }); draw(); });
    view.querySelectorAll("[data-v]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/pages/${id}/restore`, { method: "POST", body: JSON.stringify({ version: Number(/** @type {HTMLElement} */ (b).dataset.v) }) }); draw(); }));
  };
  await draw();
}
