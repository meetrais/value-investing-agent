"use strict";

const form = document.querySelector("#research-form");
const query = document.querySelector("#query");
const errorBox = document.querySelector("#error");
const emptyState = document.querySelector("#empty-state");
const loadingState = document.querySelector("#loading-state");
const resultView = document.querySelector("#result");
const submitButton = document.querySelector("#submit-button");
let currentResult = null;

query.setAttribute("aria-describedby", "query-hint");

document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    query.value = button.dataset.query;
    query.focus();
  });
});

function setBusy(busy) {
  document.querySelector(".report-panel").setAttribute("aria-busy", String(busy));
  form.querySelectorAll("button, textarea, select").forEach((control) => {
    control.disabled = busy;
  });
  submitButton.textContent = busy ? "Researching…" : "Begin research →";
  loadingState.hidden = !busy;
  emptyState.hidden = busy || currentResult !== null;
  resultView.hidden = busy || currentResult === null;
  document.querySelector("#report-state").textContent = busy
    ? "RESEARCHING"
    : currentResult ? "RESEARCH COMPLETE" : "AWAITING A QUESTION";
}

function showResult(data) {
  document.querySelector("#result-query").textContent = data.query;
  const timestamp = new Date(data.retrieved_at_utc).toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  });
  document.querySelector("#result-meta").textContent = `Retrieved ${timestamp} UTC · ${data.model}`;
  // The report is escaped on the server; Google's suggestions stay inside a script-free sandbox.
  document.querySelector("#report-frame").srcdoc = data.exports.html;
  const sources = document.querySelector("#sources");
  sources.replaceChildren();
  data.sources.forEach((source) => {
    const url = new URL(source.uri);
    if (!["https:", "http:"].includes(url.protocol)) return;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = url.href;
    link.textContent = source.title;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    item.append(link);
    sources.append(item);
  });
  document.querySelector("#source-count").textContent = `(${sources.children.length})`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!query.value.trim()) {
    query.setCustomValidity("Enter a ticker, company, or research question.");
    query.reportValidity();
    return;
  }
  errorBox.hidden = true;
  const payload = { query: query.value.trim(), timeout: Number(document.querySelector("#timeout").value) };
  setBusy(true);
  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : "Check your question and time limit, then try again.");
    }
    showResult(data);
    currentResult = data;
  } catch (error) {
    errorBox.textContent = error instanceof TypeError
      ? "Could not reach the research server. Check that it is running, then try again."
      : error.message;
    errorBox.hidden = false;
  } finally {
    setBusy(false);
    if (errorBox.hidden) document.querySelector("#result-query").focus();
  }
});

query.addEventListener("input", () => query.setCustomValidity(""));

document.querySelectorAll("[data-format]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!currentResult) return;
    const format = button.dataset.format;
    const mime = { md: "text/markdown", html: "text/html", json: "application/json" }[format];
    const url = URL.createObjectURL(new Blob([currentResult.exports[format]], { type: `${mime};charset=utf-8` }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `investment-research.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
});
