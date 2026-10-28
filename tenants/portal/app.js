const config = window.DEMO_CONFIG || { apiBase: "", name: "Payer demo" };
const api = (config.apiBase || "").replace(/\/$/, "");
const demoName = config.name || "Payer demo";
document.getElementById("brand-name").textContent = demoName;
document.getElementById("mark").textContent = demoName.slice(0, 1).toUpperCase();

const stage = document.getElementById("stage");
const thread = document.getElementById("thread");
const suggestions = document.getElementById("suggestions");
const voiceStatus = document.getElementById("voice-status");
const turns = [];
let screenContext = "";
let view = "home";
let callLive = false;
let recognizer = null;
let synthesizer = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}
function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toLocaleString("en-US", { style: "currency", currency: "USD" });
}
function day(value) {
  return value ? String(value).slice(0, 10) : "—";
}
function pill(status) {
  return `<span class="pill pill-${esc(String(status || "").toLowerCase())}">${esc(status)}</span>`;
}
function person(row) {
  return `${row.first_name || ""} ${row.last_name || ""}`.trim();
}

async function get(path) {
  const response = await fetch(`${api}${path}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The portal could not load this record");
  return body;
}

function setNav(next) {
  view = next;
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === next);
  });
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("search-input").value = "";
    openView(button.dataset.view);
  });
});

document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const q = document.getElementById("search-input").value.trim();
  if (view === "authorizations") showAuthorizations(q);
  else if (view === "members") showMembers(q);
  else if (view === "care") showCare(q);
  else showClaims(q);
});

function openView(next, q = "") {
  if (next === "home") showHome();
  else if (next === "claims") showClaims(q);
  else if (next === "authorizations") showAuthorizations(q);
  else if (next === "members") showMembers(q);
  else showCare(q);
}

function count(rows, key, name) {
  const match = (rows || []).find((row) => row[key] === name);
  return match ? match[key === "claim_status" ? "claims" : key === "status" ? "authorizations" : "records"] : 0;
}

async function showHome() {
  setNav("home");
  screenContext = "";
  suggest([
    "How many claims are denied?",
    "Which care programs have the most members?",
    "Find member Adler and summarize their claims",
  ]);
  stage.innerHTML = "<p>Loading the demo portfolio…</p>";
  try {
    const summary = await get("/portal/summary");
    const denied = count(summary.claims_by_status, "claim_status", "Denied");
    const pendingAuth = count(summary.authorizations_by_status, "status", "Pending");
    stage.innerHTML = `
      <div class="banner">
        <h1>Welcome to the ${esc(demoName)} provider portal</h1>
        <p>Claims, authorizations, members, and care programs from this demo database.</p>
      </div>
      <div class="stats">
        <div class="stat"><span>Members</span><strong>${esc(summary.members)}</strong></div>
        <div class="stat"><span>Denied claims</span><strong>${esc(denied)}</strong></div>
        <div class="stat"><span>Pending authorizations</span><strong>${esc(pendingAuth)}</strong></div>
        <div class="stat"><span>Care programs</span><strong>${esc((summary.care_by_program || []).length)}</strong></div>
      </div>
      <div class="cards">
        <button class="card" data-jump="claims" data-status="Denied"><strong>Check claim status</strong><span>Open denied claims</span></button>
        <button class="card" data-jump="authorizations" data-status="Pending"><strong>Check authorization</strong><span>Open pending requests</span></button>
        <button class="card" data-jump="members"><strong>Find a member</strong><span>Plan and coverage dates</span></button>
        <button class="card" data-jump="care"><strong>Care management</strong><span>Programs, risk, and follow-up</span></button>
      </div>
      <div class="panel"><h2>Claims by status</h2>${statusTable(summary.claims_by_status, "claim_status", "claims")}</div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

function statusTable(rows, label, value) {
  if (!rows || !rows.length) return "<p>No rows yet.</p>";
  return `<table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>
    ${rows.map((row) => `<tr><td>${pill(row[label])}</td><td>${esc(row[value])}</td></tr>`).join("")}
  </tbody></table>`;
}

async function showClaims(q = "", status = "") {
  setNav("claims");
  screenContext = "";
  suggest(["How many claims are denied?", "Summarize the denied claims"]);
  stage.innerHTML = "<p>Loading claims…</p>";
  try {
    const data = await get(`/portal/claims?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`);
    const rows = data.claims || [];
    stage.innerHTML = `<div class="panel"><h2>${status ? esc(status) + " claims" : "Claims"}</h2>
      ${rows.length ? `<table><thead><tr><th>Claim</th><th>Member</th><th>Service date</th><th>Status</th><th>Billed</th><th>Paid</th></tr></thead><tbody>
        ${rows.map((row) => `<tr class="clickable" data-claim="${esc(row.claim_id)}"><td>${esc(row.claim_number)}</td><td>${esc(person(row))}<br><span class="muted">${esc(row.member_number)}</span></td><td>${esc(day(row.service_date))}</td><td>${pill(row.claim_status)}</td><td>${esc(money(row.billed_amount))}</td><td>${esc(money(row.paid_amount))}</td></tr>`).join("")}
      </tbody></table>` : "<p>No claims match.</p>"}</div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showClaim(id) {
  setNav("claims");
  stage.innerHTML = "<p>Loading claim…</p>";
  try {
    const data = await get(`/portal/claims/${encodeURIComponent(id)}`);
    const claim = data.claim;
    screenContext = `Claim ${claim.claim_number} (${claim.claim_id}) status ${claim.claim_status}. Member ${person(claim)} ${claim.member_number} id ${claim.member_id}. Service date ${day(claim.service_date)}. Billed ${claim.billed_amount}, allowed ${claim.allowed_amount}, paid ${claim.paid_amount}. Diagnosis ${claim.diagnosis_code} ${claim.diagnosis}. Procedure ${claim.procedure_code} ${claim.procedure_name}. Provider ${claim.provider_name}. Authorization ${claim.authorization_number || "none"} status ${claim.authorization_status || "none"}.`;
    suggest([
      `What is the status of claim ${claim.claim_number}?`,
      "Is there an authorization on this claim?",
      "Summarize this member's claims",
    ]);
    const auth = claim.authorization_number
      ? `${esc(claim.authorization_number)} ${pill(claim.authorization_status)}`
      : "No authorization is linked to this claim.";
    stage.innerHTML = `<div class="panel">
      <button class="back" data-jump="claims" type="button">Back to claims</button>
      <div class="detail-head"><h2>Claim ${esc(claim.claim_number)}</h2>${pill(claim.claim_status)}</div>
      <p>${esc(person(claim))} · ${esc(claim.member_number)} · ${esc(claim.plan_name)} (${esc(claim.plan_type)})</p>
      <div class="amounts">
        <div><span>Billed</span><strong>${esc(money(claim.billed_amount))}</strong></div>
        <div><span>Allowed</span><strong>${esc(money(claim.allowed_amount))}</strong></div>
        <div><span>Paid</span><strong>${esc(money(claim.paid_amount))}</strong></div>
      </div>
      <div class="split">
        <div>
          <p><strong>Provider</strong><br>${esc(claim.provider_name)}<br><span class="muted">${esc(claim.specialty)} · NPI ${esc(claim.npi_number)}</span></p>
          <p><strong>Service</strong><br>${esc(day(claim.service_date))} · ${esc(claim.place_of_service)}<br>${esc(claim.diagnosis_code)} ${esc(claim.diagnosis)}<br>${esc(claim.procedure_code)} ${esc(claim.procedure_name)}</p>
        </div>
        <div>
          <p><strong>Authorization on this claim</strong><br>${auth}</p>
          <p class="muted">This database stores status and amounts. It does not store a denial reason code or a medical-policy document.</p>
          <button type="button" id="ask-claim">Ask the assistant</button>
        </div>
      </div>
    </div>`;
    document.getElementById("ask-claim").addEventListener("click", () => ask(`What is the status of claim ${claim.claim_number}?`));
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showAuthorizations(q = "", status = "") {
  setNav("authorizations");
  screenContext = "";
  suggest(["How many authorizations are pending?", "How many authorizations are denied?"]);
  stage.innerHTML = "<p>Loading authorizations…</p>";
  try {
    const data = await get(`/portal/authorizations?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`);
    const rows = data.authorizations || [];
    stage.innerHTML = `<div class="panel"><h2>${status ? esc(status) + " authorizations" : "Authorizations"}</h2>
      ${rows.length ? `<table><thead><tr><th>Authorization</th><th>Member</th><th>Service</th><th>Requested</th><th>Status</th></tr></thead><tbody>
        ${rows.map((row) => `<tr class="clickable" data-auth="${esc(row.authorization_id)}"><td>${esc(row.authorization_number)}</td><td>${esc(person(row))}</td><td>${esc(row.service_type)}</td><td>${esc(day(row.request_date))}</td><td>${pill(row.status)}</td></tr>`).join("")}
      </tbody></table>` : "<p>No authorizations match.</p>"}</div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showAuthorization(id) {
  setNav("authorizations");
  stage.innerHTML = "<p>Loading authorization…</p>";
  try {
    const data = await get(`/portal/authorizations/${encodeURIComponent(id)}`);
    const auth = data.authorization;
    screenContext = `Authorization ${auth.authorization_number} status ${auth.status}. Member ${person(auth)} ${auth.member_number} id ${auth.member_id}. Service ${auth.service_type}. Request ${day(auth.request_date)}, approval ${day(auth.approval_date)}, ${day(auth.start_date)} to ${day(auth.end_date)}, ${auth.authorized_units} units. Diagnosis ${auth.diagnosis_code}. Procedure ${auth.procedure_code}. Provider ${auth.provider_name}.`;
    suggest([`What is the status of authorization ${auth.authorization_number}?`, "Summarize this member's authorizations"]);
    stage.innerHTML = `<div class="panel">
      <button class="back" data-jump="authorizations" type="button">Back to authorizations</button>
      <div class="detail-head"><h2>${esc(auth.authorization_number)}</h2>${pill(auth.status)}</div>
      <p>${esc(person(auth))} · ${esc(auth.member_number)} · ${esc(auth.plan_name)}</p>
      <p>${esc(auth.service_type)} · requested ${esc(day(auth.request_date))} · ${esc(day(auth.start_date))} to ${esc(day(auth.end_date))} · ${esc(auth.authorized_units)} units</p>
      <p>${esc(auth.diagnosis_code)} ${esc(auth.diagnosis)}<br>${esc(auth.procedure_code)} ${esc(auth.procedure_name)}</p>
      <p>${esc(auth.provider_name)} · ${esc(auth.specialty)}</p>
    </div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showMembers(q = "") {
  setNav("members");
  screenContext = "";
  suggest(["Find member Adler and summarize their claims"]);
  stage.innerHTML = "<p>Loading members…</p>";
  try {
    const data = await get(`/portal/members?q=${encodeURIComponent(q)}`);
    const rows = data.members || [];
    stage.innerHTML = `<div class="panel"><h2>Members</h2>
      <p class="muted">Plan and coverage dates are the eligibility fields stored for this demo.</p>
      ${rows.length ? `<table><thead><tr><th>Member</th><th>Number</th><th>Plan</th><th>Effective</th><th>Location</th></tr></thead><tbody>
        ${rows.map((row) => `<tr class="clickable" data-member="${esc(row.member_id)}"><td>${esc(person(row))}</td><td>${esc(row.member_number)}</td><td>${esc(row.plan_name)}</td><td>${esc(day(row.effective_date))}</td><td>${esc(row.city)}, ${esc(row.state)}</td></tr>`).join("")}
      </tbody></table>` : "<p>No members match.</p>"}</div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showMember(id) {
  setNav("members");
  stage.innerHTML = "<p>Loading member…</p>";
  try {
    const data = await get(`/portal/members/${encodeURIComponent(id)}`);
    const member = data.member;
    screenContext = `Member ${person(member)} ${member.member_number} id ${member.member_id}. Plan ${member.plan_name} ${member.plan_type}. Effective ${day(member.effective_date)}, termination ${day(member.termination_date)}.`;
    suggest([
      `Summarize claims for ${person(member)}`,
      `What authorizations does ${person(member)} have?`,
      `Is ${person(member)} in a care program?`,
    ]);
    const claims = (data.claims || []).slice(0, 8).map((row) => `<tr class="clickable" data-claim="${esc(row.claim_id)}"><td>${esc(row.claim_number)}</td><td>${esc(day(row.service_date))}</td><td>${pill(row.claim_status)}</td><td>${esc(money(row.paid_amount))}</td></tr>`).join("");
    const auths = (data.authorizations || []).map((row) => `<tr class="clickable" data-auth="${esc(row.authorization_id)}"><td>${esc(row.authorization_number)}</td><td>${esc(row.service_type)}</td><td>${pill(row.status)}</td></tr>`).join("");
    const care = (data.care || []).map((row) => `<tr><td>${esc(row.program_type)}</td><td>${pill(row.status)}</td><td>${esc(row.risk_level)}</td><td>${esc(day(row.next_followup_date))}</td></tr>`).join("");
    stage.innerHTML = `<div class="panel">
      <button class="back" data-jump="members" type="button">Back to members</button>
      <h2>${esc(person(member))}</h2>
      <p>${esc(member.member_number)} · DOB ${esc(day(member.date_of_birth))} · ${esc(member.city)}, ${esc(member.state)}</p>
      <p>${esc(member.plan_name)} (${esc(member.plan_type)}) · effective ${esc(day(member.effective_date))}${member.termination_date ? ` · ends ${esc(day(member.termination_date))}` : ""}</p>
      <h2>Claims</h2>${claims ? `<table><tbody>${claims}</tbody></table>` : "<p>No claims.</p>"}
      <h2>Authorizations</h2>${auths ? `<table><tbody>${auths}</tbody></table>` : "<p>No authorizations.</p>"}
      <h2>Care management</h2>${care ? `<table><tbody>${care}</tbody></table>` : "<p>No care enrollment.</p>"}
    </div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

async function showCare(q = "") {
  setNav("care");
  screenContext = "";
  suggest(["Which care programs have the most members?"]);
  stage.innerHTML = "<p>Loading care management…</p>";
  try {
    const data = await get(`/portal/care?q=${encodeURIComponent(q)}`);
    const rows = data.care || [];
    stage.innerHTML = `<div class="panel"><h2>Care management</h2>
      ${rows.length ? `<table><thead><tr><th>Member</th><th>Program</th><th>Status</th><th>Risk</th><th>Follow-up</th><th>Outcome</th></tr></thead><tbody>
        ${rows.map((row) => `<tr class="clickable" data-member="${esc(row.member_id)}"><td>${esc(person(row))}</td><td>${esc(row.program_type)}</td><td>${pill(row.status)}</td><td>${esc(row.risk_level)}</td><td>${esc(day(row.next_followup_date))}</td><td>${esc(row.outcome || "")}</td></tr>`).join("")}
      </tbody></table>` : "<p>No care records match.</p>"}</div>`;
  } catch (error) {
    stage.innerHTML = `<p class="error-text">${esc(error.message)}</p>`;
  }
}

stage.addEventListener("click", (event) => {
  const claim = event.target.closest("[data-claim]");
  const auth = event.target.closest("[data-auth]");
  const member = event.target.closest("[data-member]");
  const jump = event.target.closest("[data-jump]");
  if (claim) showClaim(claim.dataset.claim);
  else if (auth) showAuthorization(auth.dataset.auth);
  else if (member) showMember(member.dataset.member);
  else if (jump) {
    const status = jump.dataset.status || "";
    if (jump.dataset.jump === "claims") showClaims("", status);
    else if (jump.dataset.jump === "authorizations") showAuthorizations("", status);
    else openView(jump.dataset.jump);
  }
});

function suggest(items) {
  suggestions.innerHTML = "";
  items.forEach((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", () => ask(text));
    suggestions.appendChild(button);
  });
}

function addBubble(text, role) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
  return bubble;
}

async function post(path, message) {
  const response = await fetch(`${api}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history: turns.slice(-8), context: screenContext }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The assistant could not answer");
  return body.answer;
}

async function ask(message, path = "/chat") {
  addBubble(message, "user");
  const pending = addBubble("Looking in the demo database…", "agent");
  try {
    const answer = await post(path, message);
    pending.textContent = answer;
    turns.push({ role: "user", content: message }, { role: "assistant", content: answer });
    return answer;
  } catch (error) {
    pending.textContent = error.message;
    pending.classList.add("error");
    return "";
  }
}

document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  ask(message);
});

async function speechConfig() {
  const response = await fetch(`${api}/speech/token`, { method: "POST" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Voice is not available");
  return SpeechSDK.SpeechConfig.fromAuthorizationToken(body.token, body.region);
}

async function startCall() {
  callLive = true;
  document.getElementById("mic").classList.add("live");
  document.getElementById("mic").textContent = "Stop";
  voiceStatus.textContent = "Listening";
  const speech = await speechConfig();
  speech.speechRecognitionLanguage = "en-US";
  speech.speechSynthesisVoiceName = "en-US-JennyNeural";
  recognizer = new SpeechSDK.SpeechRecognizer(speech, SpeechSDK.AudioConfig.fromDefaultMicrophoneInput());
  synthesizer = new SpeechSDK.SpeechSynthesizer(speech);
  recognizer.recognized = async (_sender, event) => {
    if (!callLive || event.result.reason !== SpeechSDK.ResultReason.RecognizedSpeech) return;
    const heard = event.result.text.trim();
    if (!heard) return;
    voiceStatus.textContent = "Looking up the answer";
    const reply = await ask(heard, "/voice");
    if (!reply || !callLive) return;
    voiceStatus.textContent = "Speaking";
    recognizer.stopContinuousRecognitionAsync(() => {
      synthesizer.speakTextAsync(reply, () => {
        if (!callLive) return;
        recognizer.startContinuousRecognitionAsync();
        voiceStatus.textContent = "Listening";
      });
    });
  };
  recognizer.startContinuousRecognitionAsync();
}

function endCall() {
  callLive = false;
  document.getElementById("mic").classList.remove("live");
  document.getElementById("mic").textContent = "Voice";
  voiceStatus.textContent = "Voice ready";
  if (recognizer) recognizer.stopContinuousRecognitionAsync();
  if (synthesizer) synthesizer.close();
  recognizer = null;
  synthesizer = null;
}

document.getElementById("mic").addEventListener("click", async () => {
  if (callLive) {
    endCall();
    return;
  }
  if (typeof SpeechSDK === "undefined") {
    voiceStatus.textContent = "The voice library did not load.";
    return;
  }
  try {
    await startCall();
  } catch (error) {
    endCall();
    voiceStatus.textContent = error.message;
  }
});

addBubble("Ask about a claim, authorization, member, or care program. The microphone uses the same assistant.", "agent");
showHome();
