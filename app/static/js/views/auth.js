// @ts-check
import { t } from "../i18n.js";
import { $, api, icon } from "../ui.js";

/** @param {HTMLElement} root @param {{onDone: () => void, switchLang: () => void}} opts */
export async function authView(root, { onDone, switchLang }) {
  document.title = "P1 AI";
  let cfg = { signup_allowed: true, has_users: true };
  try { cfg = await api("/api/auth/config"); } catch { /* */ }
  let mode = cfg.has_users ? "login" : "register";
  const draw = () => {
    const reg = mode === "register";
    root.innerHTML = `<div class="auth-wrap">
      <section class="auth-side"><div class="logo" style="color:#fff;padding:0"><span class="logo-mark">P1</span>P1 AI</div>
        <div><h1>${t("app.tagline")}</h1><ul><li>${t("dash.point1t")}</li><li>${t("dash.point2t")}</li><li>${t("dash.point3t")}</li></ul></div>
        <div class="tiny" style="color:#8f8db8">© P1 AI</div></section>
      <main class="auth-main"><div class="auth-card">
        <div class="row" style="justify-content:space-between;margin-bottom:28px"><span class="logo" style="padding:0"><span class="logo-mark">P1</span>P1 AI</span>
          <button class="btn btn-ghost btn-sm" id="lang">${icon("globe")} ${t("common.language")}</button></div>
        <h2>${reg ? t("auth.register") : t("auth.login")}</h2><p class="muted" style="margin-bottom:22px">${t("auth.subtitle")}</p>
        ${reg && !cfg.has_users ? `<div class="notice notice-info" style="margin-bottom:16px"><span class="ico">i</span>${t("auth.firstUser")}</div>` : ""}
        ${reg && !cfg.signup_allowed ? `<div class="notice notice-warn">${t("auth.signupClosed")}</div>` : `
        <form id="auth-form" class="stack" novalidate>
          ${reg ? `<div class="field"><label for="f-name">${t("auth.name")}</label><input class="input" id="f-name" name="name" autocomplete="name"></div>
          <div class="field"><label for="f-biz">${t("auth.business")}</label><input class="input" id="f-biz" name="business_name" autocomplete="organization"></div>` : ""}
          <div class="field"><label for="f-email">${t("auth.email")}</label><input class="input ltr" id="f-email" name="email" type="email" autocomplete="email" required></div>
          <div class="field"><label for="f-pass">${t("auth.password")}</label><input class="input ltr" id="f-pass" name="password" type="password" autocomplete="${reg ? "new-password" : "current-password"}" required minlength="${reg ? 10 : 1}">
            ${reg ? `<span class="tiny muted">${t("auth.passwordHint")}</span>` : ""}</div>
          <p class="form-error" id="auth-err" hidden></p>
          <button class="btn btn-primary btn-lg" type="submit">${reg ? t("auth.register") : t("auth.login")}</button>
        </form>`}
        ${cfg.signup_allowed || !reg ? `<p style="margin-top:18px;text-align:center"><a href="#" id="toggle">${reg ? t("auth.toLogin") : t("auth.toRegister")}</a></p>` : ""}
      </div></main></div>`;
    $("#lang", root).onclick = switchLang;
    const tg = $("#toggle", root);
    if (tg) tg.onclick = (/** @type {Event} */ e) => { e.preventDefault(); mode = reg ? "login" : "register"; draw(); };
    const form = $("#auth-form", root);
    if (!form) return;
    $("input", form).focus();
    form.onsubmit = async (/** @type {Event} */ e) => {
      e.preventDefault();
      const err = $("#auth-err", root), btn = $("button[type=submit]", form);
      err.hidden = true; btn.disabled = true;
      const body = Object.fromEntries(new FormData(form).entries());
      try {
        await api(reg ? "/api/auth/register" : "/api/auth/login", { method: "POST", body: JSON.stringify({ ...body, locale: document.documentElement.lang }) });
        onDone();
      } catch (ex) { err.textContent = /** @type {Error} */ (ex).message; err.hidden = false; btn.disabled = false; }
    };
  };
  draw();
}
