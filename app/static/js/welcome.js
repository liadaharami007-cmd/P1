// @ts-check
// אתר שיווקי: מחשבון חיסכון שקוף + מסלולים מתוך מגבלות המערכת האמיתיות.
const nf = new Intl.NumberFormat("he-IL", { maximumFractionDigits: 1 });
const form = /** @type {HTMLFormElement} */ (document.getElementById("roi-form"));
/** @param {string} id */
const out = (id) => /** @type {HTMLElement} */ (document.getElementById(id));

function calc() {
  const fd = new FormData(form);
  /** @param {string} k */
  const n = (k) => Math.max(0, Number(fd.get(k)) || 0);
  const share = Math.min(100, n("share")) / 100;
  const hours = (n("checks") * n("minutes") / 60) * share;
  const money = hours * n("hourly");
  const net = money - n("price");
  out("roi-hours").textContent = nf.format(hours);
  out("roi-money").textContent = nf.format(Math.round(money));
  out("roi-net").textContent = nf.format(Math.round(net));
  out("roi-formula").textContent = `החישוב: ${n("checks")} בדיקות × ${n("minutes")} דק' × ${Math.round(share * 100)}% = ${nf.format(hours)} שעות · × ${n("hourly")} ₪ לשעה − ${n("price")} ₪ מנוי. הנתונים שלכם — לא הבטחה שלנו.`;
}
form.addEventListener("input", calc);
calc();

const LABEL = { daily: "יומי", weekly: "שבועי", monthly: "חודשי" };
fetch("/api/public/plans").then((r) => r.json()).then((d) => {
  out("plans-list").innerHTML = d.plans.map((/** @type {any} */ p) => `<article class="plan ${p.id === "pro" ? "featured" : ""}">
    <h3>${p.name}</h3><p class="who">${p.for}</p>
    <ul><li>${p.sites} אתרים</li><li>${p.audits_per_month} בדיקות בחודש</li><li>מעקב: ${p.monitor.map((/** @type {string} */ m) => /** @type {any} */ (LABEL)[m]).join(" · ")}</li>
    <li>${p.members} משתמשים</li><li>דוח PDF, Fix Studio, מרכז אישורים</li></ul>
    <p class="price">${p.price_label}</p></article>`).join("");
}).catch(() => { out("plans-list").textContent = "לא ניתן לטעון את המסלולים כרגע."; });
