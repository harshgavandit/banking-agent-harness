"use strict";
const $ = (id) => document.getElementById(id);
const rupees = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n);
let busy = false;
let ready = false;
function showError(message) { $("error").textContent = message; $("error").hidden = !message; }
function setBusy(value) {
  busy = value;
  $("message").disabled = value || !ready;
  $("send").disabled = value || !ready;
  $("confirm").disabled = value || !ready;
  document.querySelectorAll("[data-prompt]").forEach((button) => { button.disabled = value || !ready; });
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, credentials: "same-origin", headers: { "Content-Type": "application/json", ...options.headers } });
    const data = await response.json();
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail : "Please check your message and try again.";
      throw new Error(message);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The request timed out. Reload the page to check your latest account state before trying again.");
    throw error;
  } finally { clearTimeout(timeout); }
}
function messageElement(message) {
  const row = document.createElement("div"); row.className = "message " + message.role;
  const label = document.createElement("div"); label.className = "message-label"; label.textContent = message.role === "user" ? "YOU" : "BANKING ASSISTANT";
  const body = document.createElement("div"); body.className = "message-body"; body.textContent = message.text;
  row.append(label, body);
  for (const action of message.actions || []) {
    const detail = document.createElement("details"); detail.className = "action";
    const summary = document.createElement("summary"); summary.textContent = "✓ " + action.tool + (action.result.status ? " · " + action.result.status : " · verified result");
    const pre = document.createElement("pre"); pre.textContent = JSON.stringify(action.result, null, 2); detail.append(summary, pre); row.append(detail);
  }
  return row;
}
function render(data) {
  $("balance").textContent = rupees(data.account.balance);
  $("daily-limit").textContent = rupees(data.account.daily_limit);
  $("daily-used").textContent = rupees(data.account.daily_used);
  $("remaining").textContent = rupees(Math.max(0, data.account.daily_limit - data.account.daily_used));
  const people = $("beneficiaries"); people.replaceChildren();
  $("beneficiary-count").textContent = data.beneficiaries.length + " saved";
  for (const person of data.beneficiaries) {
    const row = document.createElement("div"); row.className = "beneficiary";
    const avatar = document.createElement("div"); avatar.className = "person-avatar"; avatar.textContent = person.name.split(" ").map((part) => part[0]).join("").slice(0, 2);
    const info = document.createElement("div"); info.className = "person-details";
    const name = document.createElement("strong"); name.textContent = person.name;
    const account = document.createElement("small"); account.textContent = "•••• " + person.account_last4;
    info.append(name, account); row.append(avatar, info);
    if (person.status !== "ACTIVE") { const badge = document.createElement("span"); badge.className = "blocked"; badge.textContent = "Blocked"; row.append(badge); }
    people.append(row);
  }
  if (data.messages.length) { $("messages").replaceChildren(...data.messages.map(messageElement)); }
  $("pending").hidden = !data.pending;
  if (data.pending) $("pending-description").textContent = rupees(data.pending.amount) + " to " + data.pending.beneficiary_name + " · Account ending " + data.pending.account_last4;
  $("messages").scrollTop = $("messages").scrollHeight;
}
async function send(text) {
  if (busy || !ready || !text.trim()) return;
  showError(""); setBusy(true);
  $("welcome")?.remove();
  $("messages").append(messageElement({ role: "user", text }));
  const thinking = document.createElement("div"); thinking.className = "thinking"; thinking.setAttribute("role", "status"); thinking.textContent = "Checking your request…"; $("messages").append(thinking); $("messages").scrollTop = $("messages").scrollHeight;
  $("message").value = "";
  try { render(await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text.trim() }) })); }
  catch (error) {
    thinking.remove(); showError(error.message || "Unable to connect. Please try again shortly.");
    try { render(await api("/api/session")); } catch (_) { /* Keep the visible request and error. */ }
  } finally { setBusy(false); $("message").focus(); }
}
$("chat-form").addEventListener("submit", (event) => { event.preventDefault(); send($("message").value); });
$("message").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); send($("message").value); } });
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => send(button.dataset.prompt)));
$("confirm").addEventListener("click", () => send("confirm"));
async function start() {
  setBusy(true);
  try {
    const data = await api("/api/session", { method: "POST" });
    render(data); ready = true;
    $("connection").textContent = "Your private demo session is ready"; $("connection").classList.add("ready");
  } catch (error) { $("connection").textContent = "Connection unavailable"; showError(error.message || "Unable to start a demo session. Please reload to retry."); }
  finally { setBusy(false); }
}
start();
