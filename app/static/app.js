// P1 AI — ממשק משתמש. כל כפתור כאן קורא ל-API אמיתי בשרת.
const $ = (s) => document.querySelector(s);
const state = { convId: null, chatReady: false, busy: false };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Markdown בסיסי ובטוח (קודם מנקים HTML, אחר כך מעצבים)
function md(text) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const inline = (s) => s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^#{1,6}\s+(.*)/))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
    else if (!line.trim()) { close(); }
    else { close(); html += `<p>${inline(line)}</p>`; }
  }
  close();
  return html;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `שגיאה ${res.status}`);
  return data;
}

// ---------------- סטטוס ----------------
async function loadStatus() {
  const s = await api("/api/status");
  const c = s.capabilities;
  state.chatReady = c.chat.ready;
  const item = (label, cap) => `<span><span class="dot ${cap.ready ? "on" : "off"}"></span>${label}</span>`;
  $("#status").innerHTML = item("צ'אט AI", c.chat) + item("חקירת אתרים", c.website_research) + item("שמירת שיחות", c.conversation_storage);
  if (!c.chat.ready) {
    $("#banner").hidden = false;
    $("#banner").innerHTML = `הצ'אט עם ה-AI עדיין לא מחובר: חסר <code>${esc(c.chat.missing)}</code>. הוסיפו אותו לקובץ <code>.env</code> והפעילו מחדש את השרת. חקירת אתרים עובדת כבר עכשיו בלשונית "חקירת אתר".`;
  }
  updateComposer();
}

function updateComposer() {
  const disabled = !state.chatReady || state.busy;
  $("#chat-input").disabled = disabled;
  $("#chat-send").disabled = disabled;
  $("#chat-send").textContent = state.busy ? "חושב…" : "שלח";
  if (!state.chatReady) $("#chat-input").placeholder = "הצ'אט יופעל אחרי הוספת ANTHROPIC_API_KEY";
}

// ---------------- שיחות ----------------
async function loadConversations() {
  const convs = await api("/api/conversations");
  $("#conv-list").innerHTML = convs.map((c) => `
    <li class="${c.id === state.convId ? "active" : ""}">
      <button class="open" data-id="${c.id}" title="${esc(c.title)}">${esc(c.title)}</button>
      <button class="del" data-id="${c.id}" title="מחק שיחה" aria-label="מחק שיחה">✕</button>
    </li>`).join("");
}

function renderItems(items) {
  const box = $("#messages");
  if (!items.length) {
    box.innerHTML = `<div class="empty"><h2>שיחה חדשה</h2><p>כתבו הודעה כדי להתחיל.</p></div>`;
    return;
  }
  box.innerHTML = items.map((it) => {
    if (it.type === "user") return `<div class="msg user">${md(it.text)}</div>`;
    if (it.type === "assistant") return `<div class="msg assistant">${md(it.text)}</div>`;
    if (it.type === "tool_use") return `<div class="msg tool">🔍 מפעיל כלי: ${esc(it.name)} <span class="ltr">${esc(it.input?.url ?? "")}</span></div>`;
    if (it.type === "tool_result") {
      if (!it.ok) return `<div class="msg tool">⚠️ הבדיקה נכשלה: ${esc(it.error || "")}</div>`;
      const link = it.report_id ? ` · <a href="#" data-report="${it.report_id}">לדוח המלא</a>` : "";
      return `<div class="msg tool">✅ האתר נבדק (ציון ${esc(it.score)}/100)${link}</div>`;
    }
    return "";
  }).join("");
  box.scrollTop = box.scrollHeight;
}

async function openConversation(id) {
  state.convId = id;
  const conv = await api(`/api/conversations/${id}`);
  renderItems(conv.items);
  loadConversations();
}

async function newConversation() {
  const conv = await api("/api/conversations", { method: "POST" });
  await openConversation(conv.id);
  $("#chat-input").focus();
}

async function sendMessage(text) {
  if (!state.convId) {
    const conv = await api("/api/conversations", { method: "POST" });
    state.convId = conv.id;
  }
  const box = $("#messages");
  if (box.querySelector(".empty")) box.innerHTML = "";
  box.insertAdjacentHTML("beforeend", `<div class="msg user">${md(text)}</div><div class="msg tool" id="thinking">⏳ P1 חושב… (בדיקת אתר יכולה לקחת עד דקה)</div>`);
  box.scrollTop = box.scrollHeight;
  state.busy = true; updateComposer();
  try {
    const conv = await api(`/api/conversations/${state.convId}/messages`, { method: "POST", body: JSON.stringify({ text }) });
    renderItems(conv.items);
    if (conv.notice) box.insertAdjacentHTML("beforeend", `<div class="msg notice">${esc(conv.notice)}</div>`);
  } catch (e) {
    $("#thinking")?.remove();
    box.insertAdjacentHTML("beforeend", `<div class="msg error">שגיאה: ${esc(e.message)}<br><small>ההודעה לא נשמרה — אפשר לנסות שוב.</small></div>`);
    $("#chat-input").value = text;
  } finally {
    state.busy = false; updateComposer();
    loadConversations();
  }
}

// ---------------- חקירת אתרים ----------------
const SEV = { high: "חמור", medium: "בינוני", low: "קל" };

function renderReport(r) {
  if (!r.ok) {
    $("#report").innerHTML = `<div class="card"><h3>הבדיקה נכשלה</h3><p class="ltr">${esc(r.requested_url)}</p><p>${esc(r.error)}</p>
      ${(r.issues || []).map(issueHtml).join("")}</div>`;
    return;
  }
  const f = r.facts;
  const yes = (b) => (b ? "כן" : "לא");
  const fact = (k, v) => `<div><span>${k}:</span> ${v}</div>`;
  $("#report").innerHTML = `
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <div><h3 style="margin:0">${esc(f.title || "(ללא כותרת)")}</h3><a class="ltr" href="${esc(r.final_url)}" target="_blank" rel="noopener">${esc(r.final_url)}</a></div>
        <div class="score">${r.score}<small style="font-size:16px">/100</small></div>
      </div>
    </div>
    <div class="card"><h3>בעיות שנמצאו (${r.issues.length})</h3>${r.issues.map(issueHtml).join("") || "<p>לא נמצאו בעיות בבדיקות האוטומטיות.</p>"}</div>
    <div class="card"><h3>נתונים שנמדדו</h3><div class="facts">
      ${fact("זמן תגובה", `${(r.response_ms / 1000).toFixed(2)} שנ'`)}
      ${fact("קוד HTTP", r.status_code)}
      ${fact("גודל HTML", `${Math.round(r.html_bytes / 1024)}KB`)}
      ${fact("מותאם מובייל", yes(f.has_viewport))}
      ${fact("טלפונים", esc(f.phones.join(", ") || "—"))}
      ${fact("מיילים", esc(f.emails.join(", ") || "—"))}
      ${fact("וואטסאפ", yes(f.whatsapp_link))}
      ${fact("טפסים", f.forms)}
      ${fact("כלי מדידה", esc(f.tracking_tools.join(", ") || "—"))}
      ${fact("פלטפורמה", esc(f.platform.join(", ") || "לא זוהתה"))}
      ${fact("מילים בעמוד", f.word_count)}
      ${fact("תמונות בלי alt", `${f.images_without_alt}/${f.images}`)}
      ${fact("robots.txt", yes(f.robots_txt))}
      ${fact("sitemap.xml", yes(f.sitemap_xml))}
      ${fact("קישורים שנבדקו", `${f.links_checked} (שבורים: ${f.broken_links.length})`)}
      ${fact("כפתורי פעולה", esc(f.cta_texts.slice(0, 5).join(" | ") || "—"))}
    </div></div>`;
}

function issueHtml(i) {
  return `<div class="issue ${i.severity}"><h4><span class="sev ${i.severity}">${SEV[i.severity] || ""}</span>${esc(i.title)}</h4>
    <p>${esc(i.detail)}</p><p><strong>למה זה פוגע במכירות:</strong> ${esc(i.sales_impact)}</p>
    <p><strong>מה לעשות:</strong> ${esc(i.recommendation)}</p></div>`;
}

async function loadReports() {
  const reps = await api("/api/research");
  $("#report-list").innerHTML = reps.map((r) => `<li><button data-report="${r.id}">
    <span class="ltr">${esc(r.final_url || r.url)}</span> — ${r.ok ? `ציון ${r.score}, ${r.issue_count} בעיות` : "נכשל"} · ${new Date(r.created_at).toLocaleString("he-IL")}
  </button></li>`).join("") || "<li class='hint'>עוד לא בוצעו בדיקות.</li>";
}

async function showReport(id) {
  switchView("research");
  renderReport(await api(`/api/research/${id}`));
  window.scrollTo(0, 0);
}

function switchView(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  $("#view-chat").hidden = name !== "chat";
  $("#view-research").hidden = name !== "research";
  if (name === "research") loadReports();
}

// ---------------- אירועים ----------------
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
$("#new-conv").addEventListener("click", newConversation);
$("#conv-list").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.classList.contains("del")) {
    if (!confirm("למחוק את השיחה?")) return;
    await api(`/api/conversations/${b.dataset.id}`, { method: "DELETE" });
    if (state.convId === b.dataset.id) { state.convId = null; renderItems([]); }
    loadConversations();
  } else openConversation(b.dataset.id);
});
document.body.addEventListener("click", (e) => {
  const a = e.target.closest("[data-report]");
  if (a) { e.preventDefault(); showReport(a.dataset.report); }
});
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#chat-input").value.trim();
  if (!text || state.busy || !state.chatReady) return;
  $("#chat-input").value = "";
  sendMessage(text);
});
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); }
});
$("#research-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter; btn.disabled = true; btn.textContent = "בודק…";
  $("#report").innerHTML = `<div class="card">⏳ מוריד ובודק את האתר…</div>`;
  try { renderReport(await api("/api/research", { method: "POST", body: JSON.stringify({ url: $("#research-url").value }) })); }
  catch (err) { $("#report").innerHTML = `<div class="card">שגיאה: ${esc(err.message)}</div>`; }
  finally { btn.disabled = false; btn.textContent = "בדוק אתר"; loadReports(); }
});

loadStatus().catch((e) => { $("#banner").hidden = false; $("#banner").textContent = "השרת לא זמין: " + e.message; });
loadConversations();
