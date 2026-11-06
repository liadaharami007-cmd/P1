// @ts-check
// "החשבונות שלי": כל עסק מחבר את הכלים שלו. פרטים נשמרים מוצפנים ונבדקים מול הספק. סודות לא מוצגים אף פעם.
import { setTitle } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, icon, toast } from "../ui.js";

const ST = { connected: ["st-passed", "cn.st.connected"], saved: ["st-warning", "cn.st.saved"], error: ["st-failed", "cn.st.error"], not_connected: ["", "cn.st.none"] };

/** @param {HTMLElement} view */
export async function connectView(view) {
  setTitle(t("cn.title"));
  view.innerHTML = `<div></div>`;
  const root = /** @type {HTMLElement} */ (view.firstElementChild);
  const load = async () => {
    const d = await api("/api/connections");
    root.innerHTML = `<div class="stack">
      <p class="muted small">${t("cn.sub")}</p>
      <section class="card"><div class="card-head"><div><h2>${t("cn.embed")}</h2><div class="card-sub">${t("cn.embedSub")}</div></div><span class="badge st-passed">${t("cn.anySite")}</span></div>
        <pre class="snippet ltr" id="snip">${esc(d.embed.snippet)}</pre>
        <div class="row"><button class="btn btn-sm btn-primary" id="copy">${icon("copy")}${t("cn.copy")}</button><button class="btn btn-sm btn-ghost" id="rotate">${t("cn.rotate")}</button></div>
        <p class="tiny faint" style="margin-top:8px">${t("cn.embedNote")}</p></section>
      ${d.items.map((/** @type {any} */ p) => { const st = /** @type {any} */ (ST)[p.status] || ST.not_connected; return `<section class="card">
        <div class="card-head"><div><h2>${esc(p.name)}</h2><div class="card-sub">${esc(p.unlocks)}</div></div><span class="badge ${st[0]}">${t(st[1])}</span></div>
        ${p.error ? `<div class="notice notice-error" style="margin-bottom:10px"><span class="ico">!</span><span class="small">${esc(p.error)}</span></div>` : ""}
        ${p.data ? `<p class="small" style="margin-bottom:10px">${esc(Object.entries(p.data).filter(([k]) => k !== "source").map(([k, v]) => `${k}: ${v}`).join(" · "))}</p>` : ""}
        ${p.oauth ? (p.oauth.ready ? `<a class="btn btn-sm ${p.oauth.linked ? "" : "btn-primary"}" href="/api/oauth/google/start" style="margin-bottom:10px">G ${p.oauth.linked ? t("cn.googleRelink") : t("cn.google")}</a>`
          : `<div class="notice notice-warn" style="margin-bottom:10px"><span class="ico">!</span><span class="small">${esc(p.oauth.missing)}</span></div>`) : ""}
        <form class="stack-sm conn-form" data-p="${p.provider}" novalidate>${p.fields.map((/** @type {any} */ f) => `<label class="small">${esc(f.label)}
          <input class="input ${f.secret ? "" : "ltr"}" name="${f.key}" ${f.secret ? `type="password" autocomplete="off" placeholder="${esc(f.hint || "")}"` : `value="${esc(f.value || "")}"`} dir="ltr"></label>`).join("")}
          <div class="row"><button class="btn btn-sm btn-primary">${t("cn.save")}</button>${p.status !== "not_connected" ? `<button type="button" class="btn btn-sm" data-test="${p.provider}">${t("cn.test")}</button>
            <button type="button" class="btn btn-sm btn-ghost" data-del="${p.provider}">${t("cn.remove")}</button>` : ""}</div>
          <p class="tiny faint">${t("int.how")} ${esc(p.how)}</p></form></section>`; }).join("")}
      <a class="small" href="#/integrations">${t("cn.all")}</a></div>`;
  };
  root.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = /** @type {HTMLFormElement} */ (e.target);
    const values = Object.fromEntries([...new FormData(f).entries()].filter(([, v]) => String(v).trim()).map(([k, v]) => [k, String(v)]));
    try { const r = await api(`/api/connections/${f.dataset.p}`, { method: "PUT", body: JSON.stringify({ values }) });
      toast(r.status === "connected" ? t("cn.ok") : r.status === "saved" ? t("cn.st.saved") : r.error, r.status === "error" ? "error" : "success"); load(); }
    catch (err) { toast(/** @type {Error} */ (err).message, "error"); }
  });
  root.addEventListener("click", async (e) => {
    const b = /** @type {HTMLElement} */ (e.target).closest("button");
    if (!b) return;
    try {
      if (b.id === "copy") { await navigator.clipboard.writeText(/** @type {HTMLElement} */ (root.querySelector("#snip")).textContent || ""); toast(t("cn.copied")); }
      if (b.id === "rotate") { await api("/api/embed/rotate", { method: "POST" }); toast(t("cn.rotated")); load(); }
      if (b.dataset.test) { const r = await api(`/api/connections/${b.dataset.test}/test`, { method: "POST" }); toast(r.status === "connected" ? t("cn.ok") : r.error || t("cn.st.saved"), r.status === "error" ? "error" : "success"); load(); }
      if (b.dataset.del) { await api(`/api/connections/${b.dataset.del}`, { method: "DELETE" }); load(); }
    } catch (err) { toast(/** @type {Error} */ (err).message, "error"); }
  });
  await load();
}
