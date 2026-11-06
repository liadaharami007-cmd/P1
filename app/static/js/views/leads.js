// @ts-check
// לידים ופניות: רשימה אמיתית (מוזנת ידנית היום), סטטוסים, וסיווג + טיוטת תשובה ע"י AI (לא נשלחת אוטומטית).
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast, openModal, $ } from "../ui.js";

const ST = ["new", "contacted", "won", "lost"];

/** @param {HTMLElement} view */
export async function leadsView(view) {
  view.innerHTML = `<div></div>`;
  const root = /** @type {HTMLElement} */ (view.firstElementChild);
  const load = async () => {
    const d = await api("/api/leads");
    const S = d.summary;
    setTitle(t("ld.title"), `<button class="btn btn-sm btn-primary" id="add-lead">${icon("plus")}<span class="btn-label">${t("ld.add")}</span></button>`);
    root.innerHTML = `<div class="stack">
      <div class="kpis val-kpis"><div class="kpi"><div class="kpi-num">${S.total}</div><div class="kpi-label">${t("ld.total")}</div></div>
        <div class="kpi attn"><div class="kpi-num">${S.unanswered_24h}</div><div class="kpi-label">${t("ld.stale")}</div></div>
        <div class="kpi"><div class="kpi-num">${S.new}</div><div class="kpi-label">${t("ld.st.new")}</div></div>
        <div class="kpi"><div class="kpi-num">${S.won}</div><div class="kpi-label">${t("ld.st.won")}</div></div></div>
      <div class="card"><div class="card-head"><div><h2>${t("ld.funnel")}</h2><div class="card-sub">${t("ld.funnelSub")}</div></div><span class="badge src-measured">${t("src.measured")}</span></div>
        <div class="funnel">${["new", "contacted", "won", "lost"].map((s) => `<div class="funnel-stage st-${s}"><span class="num">${d.funnel.stages[s]}</span><small>${t("ld.st." + s)}</small></div>`).join("")}</div>
        <div class="row small" style="margin-top:10px;gap:16px"><span>${t("ld.winRate")} <strong>${d.funnel.win_rate == null ? "—" : d.funnel.win_rate + "%"}</strong></span>
          <span>${t("ld.openValue")} <strong>₪${d.funnel.open_value}</strong></span><span>${t("ld.wonValue")} <strong>₪${d.funnel.won_value}</strong></span>
          ${S.followups_due ? `<span class="chip warn">${t("ld.due", { n: S.followups_due })}</span>` : ""}</div>
        ${d.funnel.win_rate_note ? `<p class="tiny faint" style="margin-top:6px">${esc(d.funnel.win_rate_note)}</p>` : ""}</div>
      <p class="tiny faint">${t("ld.note")}</p>
      ${d.items.length ? `<div class="stack">${d.items.map((/** @type {any} */ l) => `<article class="card lead">
        <div class="row" style="justify-content:space-between"><div><strong>${esc(l.name)}</strong> <span class="tiny faint">${esc(l.channel || "")} · ${esc(l.contact || "")} · ${new Date(l.created_at).toLocaleString()}</span></div>
          <select class="input lead-st" data-id="${l.id}" style="width:auto">${ST.map((s) => `<option value="${s}" ${s === l.status ? "selected" : ""}>${t("ld.st." + s)}</option>`).join("")}</select></div>
        <p class="small" style="margin-top:6px;white-space:pre-line">${esc(l.message || "")}</p>
        ${l.ai ? `<div class="lead-ai"><span class="badge src-ai">${t("src.ai")} · ${esc(l.ai.model || "")}</span>
          <div class="small" style="margin-top:6px"><strong>${t("ld.intent")}</strong> ${esc(l.ai.intent)} · <strong>${t("ld.urgency")}</strong> ${esc(l.ai.urgency)}</div>
          <div class="small muted">${esc(l.ai.summary)}</div>
          <div class="out-field"><div class="out-key">${t("ld.draft")}</div><p style="white-space:pre-line">${esc(l.ai.draft_reply)}</p></div>
          <div class="small"><strong>${t("ld.next")}</strong> ${esc(l.ai.next_step)}</div></div>` : ""}
        <div class="row small" style="margin-top:8px;gap:8px"><label>${t("ld.followUp")} <input class="input lead-fu" type="datetime-local" data-id="${l.id}" value="${l.follow_up_at ? esc(l.follow_up_at.slice(0, 16)) : ""}" style="width:auto;height:32px"></label>
          <label>${t("ld.value")} <input class="input lead-val" type="number" min="0" data-id="${l.id}" value="${l.value ?? ""}" style="width:110px;height:32px"></label></div>
        <div class="row" style="margin-top:8px"><button class="btn btn-sm" data-triage="${l.id}" ${d.ai ? "" : "disabled title='" + esc(t("st.noAi")) + "'"}>${icon("sparkle")}${t("ld.triage")}</button>
          <button class="btn btn-sm btn-ghost" data-del="${l.id}">${t("common.delete")}</button></div></article>`).join("")}</div>`
        : `<div class="card empty">${t("ld.empty")}</div>`}</div>`;
  };
  const addForm = () => {
    openModal(`<h3>${t("ld.add")}</h3><form id="lead-form" class="stack" novalidate>
      <div class="field"><label for="l-name">${t("ld.name")}</label><input class="input" id="l-name" name="name" required></div>
      <div class="field"><label for="l-contact">${t("ld.contact")}</label><input class="input ltr" id="l-contact" name="contact"></div>
      <div class="field"><label for="l-ch">${t("ld.channel")}</label><select class="input" id="l-ch" name="channel">${["whatsapp", "phone", "form", "email", "instagram", "other"].map((c) => `<option value="${c}">${t("ld.ch." + c)}</option>`).join("")}</select></div>
      <div class="field"><label for="l-msg">${t("ld.message")}</label><textarea class="input" id="l-msg" name="message" rows="3"></textarea></div>
      <button class="btn btn-primary" type="submit">${t("ag.save")}</button></form>`);
    const f = /** @type {HTMLFormElement} */ ($("#lead-form"));
    f.onsubmit = async (e) => { e.preventDefault();
      try { await api("/api/leads", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(f).entries())) }); $("#modal").close(); load(); }
      catch (err) { toast(/** @type {Error} */ (err).message, "error"); } };
  };
  const onClick = async (/** @type {Event} */ e) => {
    const b = /** @type {HTMLButtonElement|null} */ (/** @type {HTMLElement} */ (e.target).closest("button"));
    if (!b) return;
    try {
      if (b.id === "add-lead") return addForm();
      if (b.dataset.triage) { b.disabled = true; b.innerHTML = `<span class="spinner"></span>`; await api(`/api/leads/${b.dataset.triage}/triage`, { method: "POST" }); return load(); }
      if (b.dataset.del) { await api(`/api/leads/${b.dataset.del}`, { method: "DELETE" }); return load(); }
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); load(); }
  };
  root.addEventListener("click", onClick);
  root.addEventListener("change", async (e) => {
    const s = /** @type {HTMLSelectElement} */ (e.target);
    if (s.classList.contains("lead-st")) { await api(`/api/leads/${s.dataset.id}`, { method: "PATCH", body: JSON.stringify({ status: s.value }) }); load(); }
    if (s.classList.contains("lead-fu")) { await api(`/api/leads/${s.dataset.id}`, { method: "PATCH", body: JSON.stringify({ follow_up_at: s.value ? new Date(s.value).toISOString() : "" }) }); toast(t("ld.saved")); }
    if (s.classList.contains("lead-val")) { await api(`/api/leads/${s.dataset.id}`, { method: "PATCH", body: JSON.stringify({ value: Number(s.value) || 0 }) }); load(); }
  });
  document.getElementById("topbar-actions")?.addEventListener("click", onClick);
  await load();
  return () => document.getElementById("topbar-actions")?.removeEventListener("click", onClick);
}
