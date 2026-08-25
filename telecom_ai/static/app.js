"use strict";

const elements = {
  form: document.querySelector("#queryForm"),
  question: document.querySelector("#question"),
  characterCount: document.querySelector("#characterCount"),
  askButton: document.querySelector("#askButton"),
  serverStatus: document.querySelector("#serverStatus"),
  emptyResult: document.querySelector("#emptyResult"),
  loadingResult: document.querySelector("#loadingResult"),
  answerCard: document.querySelector("#answerCard"),
  errorResult: document.querySelector("#errorResult"),
  errorText: document.querySelector("#errorText"),
  resultRegion: document.querySelector("#resultRegion"),
  answerText: document.querySelector("#answerText"),
  intentLabel: document.querySelector("#intentLabel"),
  governanceRow: document.querySelector("#governanceRow"),
  analysisSection: document.querySelector("#analysisSection"),
  analysisId: document.querySelector("#analysisId"),
  chartFrame: document.querySelector("#chartFrame"),
  statGrid: document.querySelector("#statGrid"),
  insightList: document.querySelector("#insightList"),
  evidenceSection: document.querySelector("#evidenceSection"),
  evidenceBody: document.querySelector("#evidenceBody"),
  evidenceCount: document.querySelector("#evidenceCount"),
  alternativeSection: document.querySelector("#alternativeSection"),
  alternativeList: document.querySelector("#alternativeList"),
  copyButton: document.querySelector("#copyButton"),
};

const intentLabels = {
  trend: "Trend analysis",
  compare: "Operator comparison",
  latest: "Latest reported value",
  lookup: "Data lookup",
  quality: "Quality review",
  missing_periods: "Coverage review",
  list_metrics: "Metric catalogue",
  clarify: "Clarification required",
  hold: "Governance hold",
  operational_escalation: "Human review required",
};

function formatCount(value) {
  return new Intl.NumberFormat("en-GH").format(Number(value || 0));
}

function setServerStatus(online) {
  elements.serverStatus.classList.toggle("offline", !online);
  elements.serverStatus.querySelector("span:last-child").textContent = online ? "Server online" : "Server offline";
}

async function loadWorkspaceStatus() {
  try {
    const [healthResponse, statsResponse] = await Promise.all([fetch("/api/health"), fetch("/api/stats")]);
    if (!healthResponse.ok || !statsResponse.ok) throw new Error("Status endpoint unavailable");
    const health = await healthResponse.json();
    const stats = await statsResponse.json();
    setServerStatus(health.status === "ok");
    document.querySelector("#workbookCount").textContent = formatCount(stats.workbooks);
    document.querySelector("#metricCount").textContent = formatCount(stats.metrics);
    document.querySelector("#observationCount").textContent = formatCount(stats.observations);
    document.querySelector("#numericCount").textContent = formatCount(stats.numeric_observations);
    document.querySelector("#qualityCount").textContent = formatCount(stats.quality_issues);
    document.querySelector("#coverageRange").textContent = `${stats.period.first} — ${stats.period.last}`;
    const operatorList = document.querySelector("#operatorList");
    operatorList.replaceChildren(...stats.operators.map((operator) => {
      const badge = document.createElement("span");
      badge.textContent = operator;
      return badge;
    }));
  } catch (error) {
    setServerStatus(false);
  }
}

function showState(state) {
  elements.emptyResult.hidden = state !== "empty";
  elements.loadingResult.hidden = state !== "loading";
  elements.answerCard.hidden = state !== "answer";
  elements.errorResult.hidden = state !== "error";
  elements.resultRegion.setAttribute("aria-busy", state === "loading" ? "true" : "false");
}

function governanceClass(releaseClass) {
  if (["R-D", "R-E"].includes(releaseClass)) return "hold";
  if (["R-B", "R-C"].includes(releaseClass)) return "warn";
  return "";
}

function addGovernanceBadge(text, className = "") {
  const badge = document.createElement("span");
  badge.className = `governance-badge ${className}`.trim();
  badge.textContent = text;
  elements.governanceRow.appendChild(badge);
}

function renderEvidence(evidence) {
  elements.evidenceBody.replaceChildren();
  elements.evidenceSection.hidden = evidence.length === 0;
  elements.evidenceCount.textContent = `${evidence.length} source${evidence.length === 1 ? "" : "s"}`;
  evidence.forEach((item) => {
    const row = document.createElement("tr");
    const values = [item.operator, item.period, item.displayed_value, item.source];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 3) cell.className = "source-ref";
      row.appendChild(cell);
    });
    elements.evidenceBody.appendChild(row);
  });
}

function renderAlternatives(alternatives) {
  elements.alternativeList.replaceChildren();
  elements.alternativeSection.hidden = alternatives.length === 0;
  alternatives.forEach((alternative) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion-chip";
    button.textContent = alternative;
    button.addEventListener("click", () => {
      elements.question.value = `Show latest ${alternative}`;
      updateCharacterCount();
      elements.question.focus();
    });
    elements.alternativeList.appendChild(button);
  });
}

function displayValue(value, suffix = "") {
  if (value === null || value === undefined) return "Not available";
  return `${new Intl.NumberFormat("en-GH", { maximumFractionDigits: 2 }).format(value)}${suffix}`;
}

function renderAnalysis(response) {
  const analysis = response.analysis || {};
  const statistics = analysis.statistics || [];
  const insights = analysis.insights || [];
  const hasAnalysis = Boolean(response.chart_svg && statistics.length);
  elements.analysisSection.hidden = !hasAnalysis;
  elements.chartFrame.replaceChildren();
  elements.statGrid.replaceChildren();
  elements.insightList.replaceChildren();
  if (!hasAnalysis) return;

  elements.analysisId.textContent = `Analysis ${response.analysis_id}`;
  const parsed = new DOMParser().parseFromString(response.chart_svg, "image/svg+xml");
  const svg = parsed.documentElement;
  if (svg.nodeName.toLowerCase() === "svg" && !parsed.querySelector("parsererror")) {
    elements.chartFrame.appendChild(document.importNode(svg, true));
  }

  statistics.forEach((item) => {
    const card = document.createElement("article");
    card.className = "stat-card";
    const title = document.createElement("strong");
    title.textContent = item.operator;
    const range = document.createElement("span");
    range.textContent = `${item.first_period} to ${item.last_period}`;
    const change = document.createElement("b");
    change.textContent = displayValue(item.percent_change, "%");
    const label = document.createElement("small");
    label.textContent = "Total change";
    const yoy = document.createElement("small");
    yoy.textContent = `Latest YoY: ${displayValue(item.latest_year_over_year_percent, "%")}`;
    card.append(title, range, change, label, yoy);
    elements.statGrid.appendChild(card);
  });

  insights.forEach((insight) => {
    const item = document.createElement("li");
    item.textContent = insight;
    elements.insightList.appendChild(item);
  });
}

function renderAnswer(response) {
  elements.answerText.textContent = response.answer;
  elements.intentLabel.textContent = intentLabels[response.intent] || "Direct answer";
  elements.governanceRow.replaceChildren();
  const governance = response.governance;
  const stateClass = governanceClass(governance.release_class);
  addGovernanceBadge(`${governance.release_class} · ${governance.release_decision}`, stateClass);
  addGovernanceBadge(`${governance.uncertainty_class} uncertainty`, stateClass);
  addGovernanceBadge("Source-grounded");
  addGovernanceBadge("Human authority final");
  renderAnalysis(response);
  renderEvidence(response.evidence || []);
  renderAlternatives(response.alternatives || []);
  showState("answer");
  elements.answerCard.focus({ preventScroll: true });
}

async function submitQuestion(question) {
  elements.askButton.disabled = true;
  showState("loading");
  try {
    const response = await fetch("/api/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    renderAnswer(await response.json());
  } catch (error) {
    elements.errorText.textContent = "The local service did not respond. Confirm the server is running, then try again.";
    showState("error");
    setServerStatus(false);
  } finally {
    elements.askButton.disabled = false;
  }
}

function updateCharacterCount() {
  elements.characterCount.textContent = elements.question.value.length;
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = elements.question.value.trim();
  if (question) submitQuestion(question);
});

elements.question.addEventListener("input", updateCharacterCount);
elements.question.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key === "Enter") elements.form.requestSubmit();
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.question.value = button.dataset.question;
    updateCharacterCount();
    elements.form.requestSubmit();
  });
});

elements.copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(elements.answerText.textContent);
    elements.copyButton.querySelector("span").textContent = "✓";
    setTimeout(() => { elements.copyButton.querySelector("span").textContent = "□"; }, 1200);
  } catch (error) {
    elements.copyButton.title = "Copy unavailable in this browser";
  }
});

showState("empty");
updateCharacterCount();
loadWorkspaceStatus();
