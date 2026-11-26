"use strict";
const $ = (s) => document.querySelector(s);
const main = $("#main");
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const eur = (x) => (x === null || x === undefined ? "–" : Number(x).toFixed(2) + " EUR");
const device = (() => { try { let d = localStorage.getItem("device"); if (!d) { d = crypto.randomUUID(); localStorage.setItem("device", d); } return d; } catch (e) { return "device-" + Math.random().toString(16).slice(2).padEnd(16, "0"); } })();
let opsToken = ""; const session = "s-" + Math.random().toString(16).slice(2, 10);

async function api(method, path, body, ops) {
  const headers = { "X-Device-Id": device };
  if (body !== undefined && typeof body !== "string") headers["Content-Type"] = "application/json";
  if (ops) headers["Authorization"] = "Bearer " + opsToken;
  const r = await fetch(path, { method, headers, body: body === undefined ? undefined : (typeof body === "string" ? body : JSON.stringify(body)) });
  const text = await r.text();
  let data; try { data = JSON.parse(text); } catch (e) { data = text; }
  if (!r.ok) throw new Error((data && data.error) || r.statusText);
  return data;
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { alert(e.message); } };

async function refreshStatus() {
  try { const s = await api("GET", "/status"); const n = $("#notice"); n.hidden = !s.notice; n.textContent = s.notice || ""; } catch (e) { /* the banner is optional */ }
}

// ------------------------------------------------------------------ shopper
const picked = new Set();
async function viewShop() {
  const q = h("input", { type: "search", placeholder: "Search brand or model", "aria-label": "Search" });
  const sort = h("select", { "aria-label": "Sort" }, h("option", { value: "price" }, "Price, low to high"), h("option", { value: "price_desc" }, "Price, high to low"), h("option", { value: "name" }, "Name"));
  const max = h("input", { type: "number", min: "0", placeholder: "Max price", "aria-label": "Maximum price" });
  const list = h("div", { class: "grid" }), cmp = h("div");
  async function load() {
    const p = new URLSearchParams({ q: q.value, sort: sort.value }); if (max.value) p.set("max_price", max.value);
    const items = await api("GET", "/products?" + p);
    list.replaceChildren(...items.map((it) => h("div", { class: "card" },
      h("h2", {}, `${it.brand} ${it.model}`),
      h("div", {}, it.best_offer ? `${eur(it.best_offer.price)} at ${it.best_offer.retailer}` : "no offer"),
      h("div", { class: "muted" }, `${it.retailers} retailers`),
      h("div", { class: "row" }, h("button", { onclick: guard(() => viewDetail(it.id)) }, "Details"),
        h("label", { class: "muted" }, h("input", { type: "checkbox", checked: picked.has(it.id), onchange: (e) => { e.target.checked ? picked.add(it.id) : picked.delete(it.id); renderCompare(); } }), " compare")))));
  }
  async function renderCompare() {
    cmp.replaceChildren();
    if (picked.size < 2 || picked.size > 3) { if (picked.size > 3) cmp.append(h("p", { class: "muted" }, "Pick at most three laptops.")); return; }
    const rows = await api("GET", "/products/compare?ids=" + [...picked].join(","));
    cmp.append(h("div", { class: "card" }, h("h2", {}, "Comparison"), h("table", {}, h("tr", {}, ["Laptop", "Best offer", "30-day reference", "vs reference", "Advice"].map((t) => h("th", {}, t))),
      rows.map((r) => h("tr", {}, h("td", {}, `${r.product.brand} ${r.product.model}`), h("td", {}, r.best_offer ? eur(r.best_offer.price) : "–"), h("td", {}, eur(r.reference_30d)),
        h("td", {}, r.discount_delta_pct === null ? "–" : r.discount_delta_pct + " %"), h("td", {}, h("span", { class: "badge " + r.action }, r.action)))))));
  }
  [q, sort, max].forEach((e) => e.addEventListener("change", guard(load)));
  main.replaceChildren(h("div", { class: "row" }, q, sort, max), cmp, list);
  await load(); await renderCompare();
}

function chart(history) {
  const W = 560, H = 140, pad = 28, ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Daily lowest price, last 30 days");
  if (history.length < 2) return svg;
  const ys = history.map((p) => p.price), lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
  const pts = history.map((p, i) => `${pad + (i * (W - 2 * pad)) / (history.length - 1)},${H - pad - ((p.price - lo) / span) * (H - 2 * pad)}`).join(" ");
  const line = document.createElementNS(ns, "polyline"); line.setAttribute("points", pts); svg.append(line);
  for (const [y, t] of [[H - pad, lo], [pad, hi]]) { const tx = document.createElementNS(ns, "text"); tx.setAttribute("x", 2); tx.setAttribute("y", y + 4); tx.textContent = t.toFixed(0); svg.append(tx); }
  return svg;
}

async function viewDetail(id) {
  const budget = h("input", { type: "number", min: "0", placeholder: "Budget (EUR)", "aria-label": "Budget" });
  const brands = h("input", { type: "text", placeholder: "Preferred brands, comma separated", "aria-label": "Preferred brands" });
  const box = h("div"), chat = h("div", { class: "chat card" });
  async function load() {
    const p = new URLSearchParams(); if (budget.value) p.set("budget", budget.value); if (brands.value.trim()) p.set("brands", brands.value.trim());
    const d = await api("GET", `/products/${encodeURIComponent(id)}/insights?` + p);
    const best = d.present.best_offer, r = d.recommendation, f = d.future;
    const target = h("input", { type: "number", min: "1", step: "0.01", placeholder: "Target price", "aria-label": "Target price" });
    box.replaceChildren(
      h("div", { class: "card" }, h("h2", {}, `${d.product.brand} ${d.product.model}`),
        h("div", {}, "Best offer: ", best ? `${eur(best.price)} at ${best.retailer}` : "none", best ? h("span", { class: "muted" }, `  (${best.freshness}, ${best.observed_at})`) : ""),
        h("div", { class: "row" }, h("span", { class: "badge " + r.action }, r.action.replace("_", " ")), r.reasons.join("; ")),
        r.caveats.length ? h("div", { class: "muted" }, "Caveats: " + r.caveats.join("; ")) : "",
        r.within_budget === false ? h("div", {}, "Above your budget.") : "",
        (r.alternatives || []).length ? h("div", {}, h("h3", {}, "Alternatives"), r.alternatives.map((a) => h("div", {}, `${a.brand} ${a.model}: ${eur(a.price)} at ${a.retailer}`))) : ""),
      h("div", { class: "card" }, h("h3", {}, "Past 30 days"), chart(d.past.history),
        h("div", { class: "muted" }, `Reference (median of daily lowest offers): ${eur(d.past.reference_30d)} over ${d.past.observation_days} days; ` + (d.past.discount_delta_pct === null ? "not enough days for a delta." : `current price ${d.past.discount_delta_pct} % vs reference.`))),
      (d.market && d.market.signals.length) ? h("div", { class: "card" }, h("h3", {}, "Market context"),
        d.market.signals.map((m) => h("div", {}, m.origin === "news"
          ? [`${m.label}: ${m.mentions} headlines from ${m.sources} sources in ${m.window_days} days. `, (m.examples || []).slice(0, 2).map((e) => e.link ? h("a", { href: e.link, rel: "noopener noreferrer", target: "_blank" }, e.title + " ") : e.title + " ")]
          : `${m.label} (${m.categories.join(", ")}): ${m.note || "operator note"}, until ${m.valid_until}.`)),
        h("div", { class: "muted" }, d.market.notice)) : "",
      h("div", { class: "card" }, h("h3", {}, "Next 7 days"), f.status === "MISSING" ? "No forecast yet." : h("div", {}, `Model ${f.model_id}, ${f.status}, generated ${f.generated_at}. Day 7: ${eur(f.prices[f.prices.length - 1])}.`), h("div", { class: "muted" }, f.caveat || "")),
      h("div", { class: "card" }, h("h3", {}, "Price watch"), h("div", { class: "row" }, target,
        h("button", { onclick: guard(async () => { await api("PUT", `/watches/${encodeURIComponent(id)}`, { targetPrice: Number(target.value) }); alert("Watch saved."); }) }, "Watch"))));
  }
  const ask = h("input", { type: "text", placeholder: "Ask about this price (or leave empty to explain)", "aria-label": "Question", maxlength: "400" });
  const send = guard(async () => {
    const res = await api("POST", "/assistant/ask", { productId: id, question: ask.value, sessionId: session, budget: budget.value ? Number(budget.value) : undefined });
    chat.append(h("div", { class: "q" }, ask.value || "Explain the recommendation"), h("div", { class: "a" }, res.answer), h("div", { class: "muted" }, `${res.label}${res.notice ? " · " + res.notice : ""} · route ${res.route}`));
    ask.value = ""; chat.scrollTop = chat.scrollHeight; refreshStatus();
  });
  ask.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  [budget, brands].forEach((e) => e.addEventListener("change", guard(load)));
  main.replaceChildren(h("button", { onclick: guard(viewShop) }, "← Back"), h("div", { class: "row" }, budget, brands), box,
    h("div", { class: "card" }, h("h3", {}, "Assistant"), chat, h("div", { class: "row" }, ask, h("button", { class: "primary", onclick: send }, "Ask"))));
  await load();
}

async function viewWatch() {
  const [w, a] = await Promise.all([api("GET", "/watches"), api("GET", "/alerts")]);
  main.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "My watches"), w.length ? h("table", {}, w.map((x) => h("tr", {}, h("td", {}, x.laptop_id), h("td", {}, eur(x.target_price)), h("td", {}, x.enabled ? "active" : "paused"),
      h("td", {}, h("button", { onclick: guard(async () => { await api("PUT", `/watches/${encodeURIComponent(x.laptop_id)}`, { targetPrice: x.target_price, enabled: !x.enabled }); viewWatch(); }) }, x.enabled ? "Pause" : "Resume"),
        " ", h("button", { onclick: guard(async () => { await api("DELETE", `/watches/${encodeURIComponent(x.laptop_id)}`); viewWatch(); }) }, "Delete"))))) : h("p", { class: "muted" }, "No watches yet. Open a laptop and set a target price.")),
    h("div", { class: "card" }, h("h2", {}, "Alerts"), a.length ? h("table", {}, a.map((x) => h("tr", {}, h("td", {}, x.laptop_id), h("td", {}, `${eur(x.price)} at ${x.retailer}`), h("td", {}, x.read_at ? "read" : "new")))) : h("p", { class: "muted" }, "No alerts."),
      a.some((x) => !x.read_at) ? h("button", { onclick: guard(async () => { await api("POST", "/alerts/read", { ids: a.filter((x) => !x.read_at).map((x) => x.id) }); viewWatch(); }) }, "Mark all read") : ""));
}

// ------------------------------------------------------------------ operator
async function viewOps() {
  if (!opsToken) {
    const t = h("input", { type: "password", placeholder: "Operator token", "aria-label": "Operator token" });
    main.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Operator console"), h("div", { class: "row" }, t, h("button", { class: "primary", onclick: guard(async () => { opsToken = t.value; await api("GET", "/ops/mode", undefined, true); viewOps(); }) }, "Sign in"))));
    return;
  }
  const [mode, placement, jobs, models, traces, review, imports] = await Promise.all(["mode", "placement", "jobs", "models", "traces", "review-queue", "imports"].map((p) => api("GET", "/ops/" + p, undefined, true)));
  const ov = h("select", { "aria-label": "Mode" }, ["GREEN", "AMBER", "RED"].map((m) => h("option", { value: m }, m))), hrs = h("input", { type: "number", value: "1", min: "1", max: "24", "aria-label": "Hours" });
  const file = h("input", { type: "file", accept: ".csv,.json", "aria-label": "Import file" });
  const sig = mode.signals;
  main.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "Operating mode"), h("div", { class: "row" }, h("span", { class: "badge " + mode.mode }, mode.mode), `target pool ${mode.placement_target}, policy v${mode.policy_version}`),
      h("div", { class: "muted" }, `${mode.reason} · since ${mode.since}`),
      h("div", { class: "muted" }, `Carbon ${sig.intensity ?? "–"} gCO2e/kWh · price ${sig.price ?? "–"} EUR/kWh · renewable ${sig.renewable ? "yes" : "no"}` + (mode.override ? ` · override ${mode.override.mode} until ${mode.override.expires_at}` : "")),
      h("div", { class: "row" }, ov, hrs, h("button", { onclick: guard(async () => { await api("PUT", "/ops/mode-override", { mode: ov.value, hours: Number(hrs.value) }, true); viewOps(); }) }, "Override"),
        h("button", { onclick: guard(async () => { await api("DELETE", "/ops/mode-override", undefined, true); viewOps(); }) }, "Clear"), h("button", { onclick: guard(async () => { await api("POST", "/ops/step", "", true); viewOps(); }) }, "Run control loop once"))),
    h("div", { class: "card" }, h("h2", {}, "Price import"), h("div", { class: "row" }, file, h("button", { onclick: guard(async () => {
      if (!file.files[0]) return; const f = file.files[0]; const res = await api("POST", `/ops/imports?format=${f.name.endsWith(".json") ? "json" : "csv"}&source=${encodeURIComponent(f.name)}`, await f.text(), true); alert(JSON.stringify(res, null, 1)); viewOps(); }) }, "Import")),
      h("table", {}, imports.slice(0, 5).map((i) => h("tr", {}, h("td", {}, i.started_at), h("td", {}, i.source), h("td", {}, i.status), h("td", {}, `+${i.inserted} / rejected ${i.rejected}`))))),
    h("div", { class: "card" }, h("h2", {}, "Forecast jobs and models"), h("div", { class: "muted" }, "Open jobs: " + (jobs.open.join(", ") || "none")),
      h("table", {}, models.map((m) => h("tr", {}, h("td", {}, m.model_id), h("td", {}, m.active ? "active" : ""), h("td", {}, m.pinned ? "pinned" : ""), h("td", {}, `MAE ${m.mae === null ? "–" : m.mae.toFixed(2)} (baseline ${m.baseline_mae === null ? "–" : m.baseline_mae.toFixed(2)})`)))),
      h("table", {}, jobs.log.slice(0, 8).map((j) => h("tr", {}, h("td", {}, j.decided_at), h("td", {}, j.laptop_id), h("td", {}, j.decision), h("td", {}, j.reason), h("td", {}, j.gco2e === null ? "" : j.gco2e.toExponential(2) + " gCO2e est."))))),
    h("div", { class: "card" }, h("h2", {}, "Placement"), h("table", {}, placement.decisions.slice(0, 6).map((d) => h("tr", {}, h("td", {}, d.decided_at), h("td", {}, d.outcome), h("td", {}, d.target_pool), h("td", {}, d.reason))))),
    h("div", { class: "card" }, h("h2", {}, "Assistant traces"), h("table", {}, traces.slice(0, 8).map((t) => h("tr", {}, h("td", {}, t.created_at), h("td", {}, t.route), h("td", {}, t.mode), h("td", {}, "V" + t.v_score), h("td", {}, t.reason)))),
      h("h3", {}, "Review queue"), review.length ? h("table", {}, review.map((r) => h("tr", {}, h("td", {}, r.question), h("td", {}, r.reason), h("td", {}, r.decision || [["approved", "Approve"], ["rejected", "Reject"]].map(([v, l]) => h("button", { onclick: guard(async () => { await api("POST", `/ops/review-queue/${r.id}/decision`, { decision: v }, true); viewOps(); }) }, l)))))) : h("p", { class: "muted" }, "Nothing flagged.")));
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", guard(async () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  await ({ shop: viewShop, watch: viewWatch, ops: viewOps })[b.dataset.view]();
})));
guard(viewShop)(); refreshStatus(); setInterval(refreshStatus, 60000);
