// LifeCircle demo front end. Plain JavaScript, no build step.
// Each role gets its own screens; every screen is just a call to the API.

const $app = document.getElementById("app");
const $tabs = document.getElementById("tabs");
let session = JSON.parse(localStorage.getItem("lc_session") || "null");
let tab = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (d) => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const fmtDT = (d) => new Date(d).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

// Talks to the FastAPI server, or (on the live GitHub Pages demo) to the same
// FastAPI app running in the browser through window.LC_BACKEND.
async function api(path, opts = {}) {
  const auth = session ? "Bearer " + session.token : "";
  const body = opts.body ? JSON.stringify(opts.body) : "";
  let status, data;
  if (window.LC_BACKEND) {
    const r = await window.LC_BACKEND.request(opts.method || "GET", path, auth, body);
    status = r.status;
    try { data = JSON.parse(r.text || "{}"); } catch { data = {}; }
  } else {
    const headers = { "Content-Type": "application/json" };
    if (auth) headers.Authorization = auth;
    const res = await fetch(path.replace(/^\//, ""), { method: opts.method || "GET", headers, body: body || undefined });
    status = res.status;
    data = await res.json().catch(() => ({}));
  }
  if (status === 401 && session) { logout(); throw new Error("Signed out"); }
  if (status >= 400) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
  return data;
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 3500);
}

async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg); }
  catch (e) { toast(e.message); }
  render();
}

async function tickClock() {
  const c = await api("/demo/clock");
  document.getElementById("clock").textContent = "Demo time: " + fmtDT(c.now);
}

// ------------------------------------------------------------------ login
async function loginScreen() {
  $tabs.hidden = true;
  document.getElementById("logout").hidden = true;
  const accts = await api("/demo/accounts");
  const group = (role) => accts.filter((a) => a.role === role)
    .map((a) => `<button class="acct" data-login="${a.id}">${esc(a.name)}</button>`).join("");
  $app.innerHTML = `
    <h1>LifeCircle</h1>
    <div class="sub">Planned blood donations. Reliable backup when plans change.</div>
    <div class="card">
      <div class="label">Real sign-in is phone + OTP (POST /auth/login, demo code 1234).
      For the demo, pick a seeded account. Your login opens your own home.</div>
    </div>
    <h2>Patient family</h2>${group("family")}
    <h2>Blood bank staff</h2>${group("staff")}
    <h2>Donors</h2>${group("donor")}
    <p class="note">Staff accounts are created by the blood bank admin, never self-signup.</p>`;
  $app.querySelectorAll("[data-login]").forEach((b) => (b.onclick = async () => {
    session = await api(`/demo/login/${b.dataset.login}`, { method: "POST" });
    localStorage.setItem("lc_session", JSON.stringify(session));
    tab = null; render();
  }));
}

function logout() { session = null; localStorage.removeItem("lc_session"); render(); }

function setTabs(list) {
  if (!tab || !list.find((t) => t[0] === tab)) tab = list[0][0];
  $tabs.hidden = false;
  $tabs.innerHTML = list.map(([k, label]) => `<button class="${k === tab ? "on" : ""}" data-tab="${k}">${label}</button>`).join("");
  $tabs.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; render(); }));
}

// ------------------------------------------------------------------ family
const FAMILY = {
  async home() {
    const h = await api("/family/home");
    const chip = (d) => `<span class="chip ${d.slot || ""} ${d.eligible_for_next ? "" : "off"}" title="${d.eligible_for_next ? "eligible" : "not eligible yet"}">${esc(d.name)}${d.slot === "backup" ? " (B)" : ""}</span>`;
    const reqs = h.requests.map((r) => `
      <div class="card hot"><div class="row"><b>${r.type === "urgent" ? "Urgent request" : "Plan change"}</b><span class="badge fill">${esc(r.status.replaceAll("_", " "))}</span></div>
      <ul class="steps">${r.steps.map((s) => `<li class="${s.done ? "done" : ""}">${esc(s.label)}${s.at ? ` <span class="label">· ${fmtDT(s.at)}</span>` : ""}</li>`).join("")}</ul>
      <div class="dashed"><b>${esc(r.message)}</b></div></div>`).join("");
    return `
      <h1>LifeCircle</h1>
      <div class="sub">${esc(h.patient.name)} · ${esc(h.patient.blood_group)} · transfusion every ${h.patient.cycle_days} days</div>
      <div class="card" style="text-align:center">
        <div class="label">Next transfusion</div>
        <div class="big">${fmtDate(h.next_transfusion)}</div>
        <div class="warn">${h.days_until === 0 ? "today" : `in ${h.days_until} days`}</div>
      </div>
      <div class="card pair">
        <div><div class="label">Confirmed</div><div class="name">${h.confirmed ? esc(h.confirmed.name) : "<span class='warn'>Not covered</span>"}</div>
          ${h.confirmed ? `<div class="label">${h.confirmed.status === "confirmed" ? "said yes" : "waiting for reply"}</div>` : ""}</div>
        <div><div class="label">Backup</div><div class="name">${h.backup ? esc(h.backup.name) : "<span class='muted'>None</span>"}</div></div>
      </div>
      <div class="card"><div class="label">Donor circle (faded = not eligible by this date)</div>
        <div class="chips" style="margin-top:6px">${h.circle.map(chip).join("")}</div>
        <div class="${h.circle_health.ok ? "ok" : "warn"}" style="margin-top:8px">${esc(h.circle_health.message)}</div>
      </div>
      ${reqs}
      <button class="primary" id="urgent">Request urgent help</button>
      <div class="note">Goes to District Blood Bank. You never need to call donors.<br>Blood bank does final screening.</div>`;
  },
  async plan() {
    const p = await api("/family/plan");
    const groups = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"];
    return `
      <h1>Plan and request</h1><div class="sub">Set once, we track it</div>
      <label class="field">Blood group</label>
      <div class="groups">${groups.map((g) => `<button data-g="${g}" class="${g === p.blood_group ? "on" : ""}">${g}</button>`).join("")}</div>
      <label class="field">Transfusion cycle (days)</label><input id="cycle" type="number" min="7" max="90" value="${p.cycle_days}">
      <label class="field">Last transfusion</label><input id="last" type="date" value="${p.last_transfusion_date}">
      <h2 style="color:var(--red)">Next date: ${fmtDate(p.next_transfusion)}</h2>
      <button class="primary" id="save">Save plan</button>`;
  },
  async updates() {
    const n = await api("/family/notifications");
    return `<h1>Updates</h1><div class="sub">Messages the app would send you (simulated)</div>
      ${n.map((x) => `<div class="list-item">${esc(x.text)}<div class="label">${fmtDT(x.at)}</div></div>`).join("") || "<p class='muted'>Nothing yet.</p>"}`;
  },
};

function bindFamily() {
  const u = document.getElementById("urgent");
  if (u) u.onclick = () => act(() => api("/family/urgent", { method: "POST", body: { note: "Requested from family home" } }), "Sent to District Blood Bank");
  let group = document.querySelector(".groups .on")?.dataset.g;
  document.querySelectorAll("[data-g]").forEach((b) => (b.onclick = () => {
    document.querySelectorAll("[data-g]").forEach((x) => x.classList.remove("on")); b.classList.add("on"); group = b.dataset.g;
  }));
  const s = document.getElementById("save");
  if (s) s.onclick = () => act(() => api("/family/plan", { method: "PUT", body: {
    blood_group: group, cycle_days: +document.getElementById("cycle").value, last_transfusion_date: document.getElementById("last").value } }), "Plan saved");
}

// ------------------------------------------------------------------ donor
const DONOR = {
  async home() {
    const [h, alerts] = await Promise.all([api("/donor/home"), api("/donor/alerts")]);
    const al = alerts.map((a) => `
      <div class="card hot" style="text-align:center">
        <h2 style="margin-top:0">Can you donate today?</h2>
        <div class="big red">${esc(a.distance)}</div><div class="label">from you</div>
        <div class="card" style="text-align:left">
          <div class="row"><span class="label">Blood group</span><b>${esc(a.blood_group)}</b></div>
          <div class="row"><span class="label">Needed by</span><b>${fmtDT(a.needed_by)}</b></div>
          <div class="row"><span class="label">Where</span><b>${esc(a.where)}</b></div>
          <div class="row"><span class="label">Patient</span><b>${esc(a.patient.name)}</b></div>
        </div>
        <div class="note">${esc(a.privacy)}</div>
        <button class="primary" data-accept="${a.id}">Accept</button>
        <button class="secondary" data-decline="${a.id}">Not today</button>
        <div class="note">Final screening at the blood bank</div>
      </div>`).join("");
    const ap = h.upcoming.map((a) => `
      <div class="card hot">
        <h2 style="margin:0">Donation in ${a.days_until} days</h2>
        <div>${new Date(a.date).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} · ${a.slot === "backup" ? "<b>backup</b>" : "<b>confirmed</b>"}</div>
        <div class="label">${esc(a.where)} · for a ${esc(a.patient.blood_group)} patient</div>
        ${a.status === "confirmed" ? `<p class="ok">You said you're coming. Thank you!</p><button class="secondary" data-cancel="${a.id}">I can't make it any more</button>`
          : `<p><b>Still coming?</b></p><button class="primary" data-confirm="${a.id}">Yes, I'll come</button><button class="secondary" data-cancel="${a.id}">I can't make it</button>`}
      </div>`).join("");
    const rot = h.rotation.map((r) => r.position
      ? `<div class="card"><b>${r.position === 1 ? "You are first in the rotation" : `You are next after ${esc(r.after)}`}</b><div class="label">Fair rotation spreads donations out</div></div>`
      : `<div class="card"><b>Not in rotation for the next date</b><div class="label">You gave recently, so others go first</div></div>`).join("");
    return `
      <h1>Hi, ${esc(h.me.name.split(" ")[0])}</h1>
      <div class="sub">${h.me.verified ? '<span class="verified">Blood bank verified</span>' : "Not yet verified"}</div>
      ${al}${ap}
      <div class="card"><b>${h.me.last_donation_date ? "Last donated " + fmtDate(h.me.last_donation_date) : "No donations recorded"}</b>
        <div class="label">${h.eligible_now ? "Eligible now" : "Eligible from " + fmtDate(h.eligible_from)}</div></div>
      ${rot}
      <p class="label">SMS reminders: 2 days before, the day before, and the morning of.</p>
      <p><b>${esc(h.note)}</b></p>`;
  },
  async privacy() {
    const [p, r] = await Promise.all([api("/donor/privacy"), api("/donor/record")]);
    const t = (k, label) => `<div class="toggle"><span>${label}</span><input type="checkbox" data-p="${k}" ${p[k] ? "checked" : ""}></div>`;
    return `<h1>Privacy and record</h1>
      ${t("show_next_eligible_to_staff", "Show next eligible date to staff")}
      ${t("share_location_for_urgent", "Share location for urgent alerts")}
      ${t("urgent_alerts_enabled", "Urgent alerts from nearby")}
      <div class="card"><div class="label">Your record</div><div class="big">${esc(r.showed_up)}</div>
        <div>showed up when expected</div><div class="label">${esc(r.rule)}</div></div>
      ${r.history.map((x) => `<div class="list-item">${fmtDate(x.date)} · ${esc(x.outcome.replace("_", "-"))}${x.reason ? " (" + esc(x.reason) + ")" : ""}</div>`).join("")}
      <button class="secondary" id="delacct" style="margin-top:20px">Delete my account and number</button>
      <p class="note">Your upcoming slots are cancelled and backups promoted. The blood bank keeps past outcomes without your name.</p>`;
  },
  async updates() {
    const n = await api("/donor/notifications");
    return `<h1>Messages</h1><div class="sub">Simulated SMS / app messages</div>
      ${n.map((x) => `<div class="list-item">${esc(x.text)}<div class="label">${fmtDT(x.at)}</div></div>`).join("") || "<p class='muted'>Nothing yet.</p>"}`;
  },
};

function bindDonor() {
  document.querySelectorAll("[data-confirm]").forEach((b) => (b.onclick = () => act(() => api(`/donor/appointments/${b.dataset.confirm}/confirm`, { method: "POST" }), "Thanks, see you there")));
  document.querySelectorAll("[data-cancel]").forEach((b) => (b.onclick = () => act(() => api(`/donor/appointments/${b.dataset.cancel}/cancel`, { method: "POST" }), (r) => r.events.join(". "))));
  document.querySelectorAll("[data-accept]").forEach((b) => (b.onclick = () => act(() => api(`/donor/alerts/${b.dataset.accept}/accept`, { method: "POST" }), (r) => r.message)));
  document.querySelectorAll("[data-decline]").forEach((b) => (b.onclick = () => act(() => api(`/donor/alerts/${b.dataset.decline}/decline`, { method: "POST" }), "No problem")));
  const del = document.getElementById("delacct");
  if (del) del.onclick = async () => {
    if (!confirm("Delete your LifeCircle account and phone number? This cannot be undone.")) return;
    try { await api("/donor/account", { method: "DELETE" }); toast("Account deleted"); } catch (e) { toast(e.message); }
    logout();
  };
  document.querySelectorAll("[data-p]").forEach((i) => (i.onchange = () => act(() => api("/donor/privacy", { method: "PUT", body: { [i.dataset.p]: i.checked } }), "Saved")));
}

// ------------------------------------------------------------------ staff
let chosenRequest = null;
const STAFF = {
  async queue() {
    const q = await api("/staff/queue");
    return `<h1>Request queue</h1><div class="sub">District Blood Bank · on shift ${esc(session.name)}</div>
      ${q.map((r) => `
        <div class="card ${r.type === "urgent" ? "hot" : ""}">
          <div class="row"><b>${esc(r.patient)}, ${esc(r.blood_group)}</b><span class="badge ${r.type === "urgent" ? "fill" : ""}">${r.type}</span></div>
          <div class="label">Needed by ${fmtDT(r.needed_by)} · ${esc(r.status.replaceAll("_", " "))} · ${r.alerts_sent} alerted</div>
          ${r.note ? `<div class="label">${esc(r.note)}</div>` : ""}
          <p><b>Suggested:</b> ${esc(r.suggested_action)}</p>
          ${r.confirmed_donor ? `<p>Confirmed: <b>${esc(r.confirmed_donor.name)}</b> <span class="phone">${esc(r.confirmed_donor.phone)}</span></p>` : ""}
          ${r.status === "sent_to_bank" ? `<button class="small primary" data-approve="${r.id}">Approve</button>` : ""}
          ${["circle_alerted", "nearby_alerted"].includes(r.status) ? `<button class="small secondary" data-escalate="${r.id}">Escalate now</button>` : ""}
          <button class="small secondary" data-choose="${r.id}">Choose a donor</button>
        </div>`).join("") || "<p class='muted'>Queue is empty. Routine planned donations need no action.</p>"}`;
  },
  async donors() {
    if (!chosenRequest) return `<h1>Choose a donor</h1><p class="muted">Pick "Choose a donor" on a request in the queue.</p>`;
    const c = await api(`/staff/requests/${chosenRequest}/candidates`);
    return `<h1>Choose a donor</h1><div class="sub">Request #${c.request_id} · ${esc(c.status.replaceAll("_", " "))} · circle first, then nearest</div>
      ${c.candidates.map((d) => `
        <div class="card ${d.rank === 1 ? "hot" : ""}">
          <div class="row"><b>${esc(d.name)}</b><span class="badge ${d.rank === 1 ? "fill" : ""}">${d.rank}</span></div>
          <div class="label">${d.verified ? '<span class="verified">Blood bank verified</span>' : "unverified"} · ${d.tier === "circle" ? "patient's circle" : "nearby"} · ${esc(d.blood_group)}${d.exact_match ? " (exact)" : ""}</div>
          <div class="label">${esc(d.distance)} · ${d.reliability === "0 of 0" ? "new donor" : "showed up " + esc(d.reliability)} · eligible · alert: ${esc(d.alert)}</div>
          <div class="phone">${esc(d.phone)} (staff only)</div>
          <button class="small primary" data-confirmdonor="${d.id}">Confirm</button>
        </div>`).join("") || "<p class='muted'>No eligible donors found within 10 km.</p>"}
      <p class="note">${esc(c.note)}</p>`;
  },
  async today() {
    const t = await api("/staff/today");
    const outs = [["donated", "Donated"], ["deferred", "Deferred"], ["no_show", "No-show"], ["excused", "Excused"]];
    return `<h1>Today's donations</h1><div class="sub">${t.rows.length} scheduled · mark each outcome</div>
      ${t.rows.map((r) => `
        <div class="card"><div class="row"><b>${esc(r.donor.name)}</b><span class="label">${esc(r.kind)}</span></div>
          <div class="label">for ${esc(r.for)} · <span class="phone">${esc(r.donor.phone)}</span></div>
          ${outs.map(([k, l]) => `<button class="small ${k === "donated" ? "primary" : "secondary"}" data-out="${k}" data-donor="${r.donor.id}" data-appt="${r.appointment_id ?? ""}" data-req="${r.request_id ?? ""}">${l}</button>`).join("")}
        </div>`).join("") || "<p class='muted'>Nobody expected today.</p>"}
      <p class="warn">${esc(t.rule)}</p>`;
  },
  async log() {
    const [d, a] = await Promise.all([api("/staff/donors"), api("/staff/audit/phone-views")]);
    return `<h1>Donors and audit</h1>
      ${d.map((x) => `<div class="list-item"><b>${esc(x.name)}</b> · ${esc(x.blood_group)} · <span class="phone">${esc(x.phone)}</span><br>
        <span class="label">${x.verified ? "verified" : "<b>unverified</b>"} · next eligible ${esc(x.next_eligible_date)} · ${x.reliability === "0 of 0" ? "new donor" : "showed up " + esc(x.reliability)}</span>
        ${x.verified ? "" : `<button class="small secondary" data-verify="${x.id}">Verify</button>`}</div>`).join("")}
      <h2>Phone number views (latest ${a.length})</h2>
      ${a.slice(0, 15).map((x) => `<div class="list-item label">${fmtDT(x.at)} · ${esc(x.staff)} saw donor #${x.donor_id} · ${esc(x.context)}</div>`).join("")}`;
  },
};

function bindStaff() {
  document.querySelectorAll("[data-approve]").forEach((b) => (b.onclick = () => act(() => api(`/staff/requests/${b.dataset.approve}/approve`, { method: "POST" }),
    (r) => `Circle alerted: ${r.circle_alerted}${r.nearby_alerted ? `, nearby alerted: ${r.nearby_alerted}` : ""}`)));
  document.querySelectorAll("[data-escalate]").forEach((b) => (b.onclick = () => act(() => api(`/staff/requests/${b.dataset.escalate}/escalate`, { method: "POST" }), (r) => `Nearby donors alerted: ${r.nearby_alerted}`)));
  document.querySelectorAll("[data-choose]").forEach((b) => (b.onclick = () => { chosenRequest = b.dataset.choose; tab = "donors"; render(); }));
  document.querySelectorAll("[data-confirmdonor]").forEach((b) => (b.onclick = () => act(() => api(`/staff/requests/${chosenRequest}/confirm`, { method: "POST", body: { donor_id: +b.dataset.confirmdonor } }), (r) => `${r.donor} confirmed`)));
  document.querySelectorAll("[data-verify]").forEach((b) => (b.onclick = () => act(() => api(`/staff/donors/${b.dataset.verify}/verify`, { method: "POST" }), "Verified")));
  document.querySelectorAll("[data-out]").forEach((b) => (b.onclick = () => act(() => api("/staff/outcomes", { method: "POST", body: {
    donor_id: +b.dataset.donor, outcome: b.dataset.out,
    appointment_id: b.dataset.appt ? +b.dataset.appt : null, request_id: b.dataset.req ? +b.dataset.req : null } }), "Outcome recorded")));
}

// ------------------------------------------------------------------ router
const ROLES = {
  family: { tabs: [["home", "Home"], ["plan", "Plan"], ["updates", "Updates"]], screens: FAMILY, bind: bindFamily },
  donor: { tabs: [["home", "Home"], ["privacy", "Privacy"], ["updates", "Messages"]], screens: DONOR, bind: bindDonor },
  staff: { tabs: [["queue", "Queue"], ["donors", "Donors"], ["today", "Today"], ["log", "Log"]], screens: STAFF, bind: bindStaff },
};

async function render() {
  if (window.LC_BACKEND) {
    try { await window.LC_BACKEND.ready; }
    catch (e) { $app.innerHTML = `<p class="warn">Could not start the demo: ${esc(e.message)}. Please refresh.</p>`; return; }
  }
  tickClock().catch(() => {});
  if (!session) return loginScreen();
  document.getElementById("logout").hidden = false;
  const r = ROLES[session.role];
  setTabs(r.tabs);
  try { $app.innerHTML = await r.screens[tab](); r.bind(); }
  catch (e) { $app.innerHTML = `<p class="warn">${esc(e.message)}</p>`; }
}

document.getElementById("logout").onclick = logout;
document.getElementById("reset").onclick = () => act(() => api("/demo/reset", { method: "POST" }), "Demo data reset");
document.querySelectorAll("[data-advance]").forEach((b) => (b.onclick = () => act(() => api("/demo/advance", { method: "POST", body: { minutes: +b.dataset.advance } }), "Clock moved 15 minutes")));
document.querySelectorAll("[data-advance-days]").forEach((b) => (b.onclick = () => act(() => api("/demo/advance", { method: "POST", body: { days: +b.dataset.advanceDays } }), "Clock moved 1 day")));
render();
