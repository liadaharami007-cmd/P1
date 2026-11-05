import { setTitle } from "../app.js";
import { api, esc, md } from "../ui.js";

export async function assistantView(view, _p, app) {
  setTitle("עוזר AI");
  const ready = app.status.capabilities.chat.ready;
  const state = { convId: null, busy: false };
  view.innerHTML = `${ready ? "" : `<div class="notice notice-warn" style="margin-bottom:16px"><div><strong>העוזר עדיין לא מחובר ל-Claude.</strong>
      חסר <code class="ltr">ANTHROPIC_API_KEY</code> בקובץ <code class="ltr">.env</code>. כל שאר המערכת (בדיקות, סימולציות, דוחות) עובדת בלעדיו.
      העוזר לא מציג תשובות מדומות.</div></div>`}
    <div class="chat-layout">
      <div class="chat-side card" style="padding:12px"><button class="btn btn-primary" id="new-conv">+ שיחה חדשה</button><ul class="conv-list" id="conv-list"></ul></div>
      <div class="card chat-main"><div class="messages" id="messages"><div class="empty"><h3>שאלו את P1 על החנות שלכם</h3>
        <p>לדוגמה: "תבדוק את האתר shop.co.il ותגיד לי מה הכי פוגע במכירות"</p></div></div>
        <form class="composer" id="chat-form"><textarea class="input" id="chat-input" rows="2"
          placeholder="${ready ? "כתבו הודעה… (Enter לשליחה)" : "העוזר יופעל אחרי הוספת ANTHROPIC_API_KEY"}" ${ready ? "" : "disabled"}></textarea>
          <button class="btn btn-primary" id="send" ${ready ? "" : "disabled"}>שלח</button></form></div></div>`;
  const $ = (s) => view.querySelector(s);

  const renderItems = (items) => {
    const box = $("#messages");
    box.innerHTML = items.length ? items.map((it) => {
      if (it.type === "user") return `<div class="msg user">${md(it.text)}</div>`;
      if (it.type === "assistant") return `<div class="msg assistant">${md(it.text)}</div>`;
      if (it.type === "tool_use") return `<div class="msg tool">🔍 מפעיל כלי: ${esc(it.name)} <span class="ltr">${esc(it.input?.url ?? "")}</span></div>`;
      if (it.type === "tool_result") return `<div class="msg tool">${it.ok ? `✅ האתר נבדק (ציון ${esc(it.score)}/100)` : `⚠️ הבדיקה נכשלה: ${esc(it.error || "")}`}</div>`;
      return "";
    }).join("") : `<div class="empty"><h3>שיחה חדשה</h3></div>`;
    box.scrollTop = box.scrollHeight;
  };
  const loadList = async () => {
    const convs = await api("/api/conversations");
    $("#conv-list").innerHTML = convs.map((c) => `<li class="${c.id === state.convId ? "active" : ""}">
      <button class="open" data-id="${c.id}">${esc(c.title)}</button><button class="del" data-del="${c.id}" aria-label="מחיקת שיחה">✕</button></li>`).join("");
  };
  const open = async (id) => { state.convId = id; renderItems((await api(`/api/conversations/${id}`)).items); loadList(); };

  $("#new-conv").onclick = async () => open((await api("/api/conversations", { method: "POST" })).id);
  $("#conv-list").onclick = async (e) => {
    const d = e.target.closest("[data-del]"), o = e.target.closest("[data-id]");
    if (d && confirm("למחוק את השיחה?")) {
      await api(`/api/conversations/${d.dataset.del}`, { method: "DELETE" });
      if (state.convId === d.dataset.del) { state.convId = null; renderItems([]); }
      loadList();
    } else if (o) open(o.dataset.id);
  };
  $("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); } });
  $("#chat-form").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("#chat-input").value.trim();
    if (!text || state.busy || !ready) return;
    if (!state.convId) state.convId = (await api("/api/conversations", { method: "POST" })).id;
    const box = $("#messages");
    if (box.querySelector(".empty")) box.innerHTML = "";
    box.insertAdjacentHTML("beforeend", `<div class="msg user">${md(text)}</div><div class="msg tool" id="thinking"><span class="spinner" style="display:inline-block;vertical-align:middle"></span> P1 חושב…</div>`);
    $("#chat-input").value = ""; state.busy = true; $("#send").disabled = true;
    try {
      const conv = await api(`/api/conversations/${state.convId}/messages`, { method: "POST", body: JSON.stringify({ text }) });
      renderItems(conv.items);
      if (conv.notice) box.insertAdjacentHTML("beforeend", `<div class="msg notice-msg">${esc(conv.notice)}</div>`);
    } catch (err) {
      view.querySelector("#thinking")?.remove();
      box.insertAdjacentHTML("beforeend", `<div class="msg error">שגיאה: ${esc(err.message)} — ההודעה לא נשמרה, אפשר לנסות שוב.</div>`);
      $("#chat-input").value = text;
    } finally { state.busy = false; $("#send").disabled = false; loadList(); }
  };
  loadList();
}
