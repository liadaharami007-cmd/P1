// @ts-check
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, md } from "../ui.js";

/** @param {HTMLElement} view @param {any} _p @param {any} app */
export async function assistantView(view, _p, app) {
  setTitle(t("nav.assistant"));
  const ready = app.status.capabilities.chat.ready;
  const state = { convId: /** @type {string|null} */ (null), busy: false };
  view.innerHTML = `${ready ? "" : `<div class="notice notice-warn" style="margin-bottom:14px"><span class="ico">!</span><span>${t("chat.off")}</span></div>`}
    <div class="chat-layout"><div class="chat-side card"><button class="btn btn-primary" id="new-conv">${t("chat.new")}</button><ul class="conv-list" id="conv-list"></ul></div>
      <div class="card chat-main"><div class="messages" id="messages"><div class="empty"><h3>${t("chat.empty")}</h3><p>${t("chat.example")}</p></div></div>
        <form class="composer" id="chat-form"><textarea class="input" id="chat-input" rows="2" placeholder="${ready ? t("chat.placeholder") : t("chat.disabled")}" ${ready ? "" : "disabled"}></textarea>
          <button class="btn btn-primary" id="send" ${ready ? "" : "disabled"}>${t("chat.send")}</button></form></div></div>`;
  const $ = (/** @type {string} */ s) => /** @type {any} */ (view.querySelector(s));
  const renderItems = (/** @type {any[]} */ items) => {
    const box = $("#messages");
    box.innerHTML = items.length ? items.map((it) => {
      if (it.type === "user") return `<div class="msg user">${md(it.text)}</div>`;
      if (it.type === "assistant") return `<div class="msg assistant">${md(it.text)}</div>`;
      if (it.type === "tool_use") return `<div class="msg tool">↗ ${esc(it.name)} <span class="ltr">${esc(it.input?.url ?? "")}</span></div>`;
      if (it.type === "tool_result") return `<div class="msg tool">${it.ok ? `✓ ${esc(it.url || "")} — ${esc(it.score)}/100` : `! ${esc(it.error || "")}`}</div>`;
      return "";
    }).join("") : `<div class="empty"><h3>${t("chat.empty")}</h3></div>`;
    box.scrollTop = box.scrollHeight;
  };
  const loadList = async () => {
    const convs = await api("/api/conversations");
    $("#conv-list").innerHTML = convs.map((/** @type {any} */ c) => `<li class="${c.id === state.convId ? "active" : ""}">
      <button class="open" data-id="${c.id}">${esc(c.title)}</button><button class="del" data-del="${c.id}" aria-label="${t("common.delete")}">✕</button></li>`).join("");
  };
  const open = async (/** @type {string} */ id) => { state.convId = id; renderItems((await api(`/api/conversations/${id}`)).items); loadList(); };
  $("#new-conv").onclick = async () => open((await api("/api/conversations", { method: "POST" })).id);
  $("#conv-list").onclick = async (/** @type {Event} */ e) => {
    const tg = /** @type {HTMLElement} */ (e.target);
    const d = /** @type {HTMLElement|null} */ (tg.closest("[data-del]")), o = /** @type {HTMLElement|null} */ (tg.closest("[data-id]"));
    if (d && confirm(t("chat.confirmDelete"))) {
      await api(`/api/conversations/${d.dataset.del}`, { method: "DELETE" });
      if (state.convId === d.dataset.del) { state.convId = null; renderItems([]); }
      loadList();
    } else if (o) open(o.dataset.id || "");
  };
  $("#chat-input").addEventListener("keydown", (/** @type {KeyboardEvent} */ e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); } });
  $("#chat-form").onsubmit = async (/** @type {Event} */ e) => {
    e.preventDefault();
    const text = $("#chat-input").value.trim();
    if (!text || state.busy || !ready) return;
    if (!state.convId) state.convId = (await api("/api/conversations", { method: "POST" })).id;
    const box = $("#messages");
    if (box.querySelector(".empty")) box.innerHTML = "";
    box.insertAdjacentHTML("beforeend", `<div class="msg user">${md(text)}</div><div class="msg tool" id="thinking"><span class="spinner"></span> ${t("chat.thinking")}</div>`);
    $("#chat-input").value = ""; state.busy = true; $("#send").disabled = true;
    try {
      const conv = await api(`/api/conversations/${state.convId}/messages`, { method: "POST", body: JSON.stringify({ text }) });
      renderItems(conv.items);
      if (conv.notice) box.insertAdjacentHTML("beforeend", `<div class="msg tool">${esc(conv.notice)}</div>`);
    } catch (err) {
      view.querySelector("#thinking")?.remove();
      box.insertAdjacentHTML("beforeend", `<div class="msg error">${esc(/** @type {Error} */ (err).message)}</div>`);
      $("#chat-input").value = text;
    } finally { state.busy = false; $("#send").disabled = false; loadList(); }
  };
  loadList();
}
