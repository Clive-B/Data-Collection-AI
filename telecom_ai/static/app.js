"use strict";

const elements = {
  form: document.querySelector("#queryForm"),
  question: document.querySelector("#question"),
  characterCount: document.querySelector("#characterCount"),
  askButton: document.querySelector("#askButton"),
  serverStatus: document.querySelector("#serverStatus"),
  copilotStatus: document.querySelector("#copilotStatus"),
  copilotMessage: document.querySelector("#copilotMessage"),
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
  chartCaption: document.querySelector("#chartCaption"),
  chartDownloadButton: document.querySelector("#chartDownloadButton"),
  chartPanLeft: document.querySelector("#chartPanLeft"),
  chartPanRight: document.querySelector("#chartPanRight"),
  chartZoomIn: document.querySelector("#chartZoomIn"),
  chartZoomOut: document.querySelector("#chartZoomOut"),
  chartReset: document.querySelector("#chartReset"),
  chartWindowStatus: document.querySelector("#chartWindowStatus"),
  chartSelection: document.querySelector("#chartSelection"),
  statGrid: document.querySelector("#statGrid"),
  insightList: document.querySelector("#insightList"),
  evidenceSection: document.querySelector("#evidenceSection"),
  evidenceBody: document.querySelector("#evidenceBody"),
  evidenceCount: document.querySelector("#evidenceCount"),
  alternativeSection: document.querySelector("#alternativeSection"),
  alternativeList: document.querySelector("#alternativeList"),
  copyButton: document.querySelector("#copyButton"),
  importForm: document.querySelector("#importForm"),
  importOperator: document.querySelector("#importOperator"),
  importFile: document.querySelector("#importFile"),
  importButton: document.querySelector("#importButton"),
  importStatus: document.querySelector("#importStatus"),
};

let currentChart = null;
let currentChartType = "line";
let currentEvidence = [];
let chartViewport = { size: null, end: null };

const operatorColors = {
  MTN: "#ffcb05",
  AirtelTigo: "#1976d2",
  Telecel: "#e31b23",
};

function applyOperatorColor(element, operator) {
  element.style.setProperty("--operator-color", operatorColors[operator] || "#526074");
  element.dataset.operator = operator;
}

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

function setCopilotStatus(configured, model = null) {
  elements.copilotStatus.classList.toggle("offline", !configured);
  elements.copilotStatus.querySelector("span:last-child").textContent = configured
    ? `Adinkra ready · ${model}`
    : "Adinkra needs API key";
}

async function loadWorkspaceStatus() {
  try {
    const [healthResponse, statsResponse] = await Promise.all([fetch("/api/health"), fetch("/api/stats")]);
    if (!healthResponse.ok || !statsResponse.ok) throw new Error("Status endpoint unavailable");
    const health = await healthResponse.json();
    const stats = await statsResponse.json();
    setServerStatus(health.status === "ok");
    setCopilotStatus(Boolean(health.copilot?.configured), health.copilot?.model);
    document.querySelector("#workbookCount").textContent = formatCount(stats.workbooks);
    document.querySelector("#metricCount").textContent = formatCount(stats.metrics);
    document.querySelector("#observationCount").textContent = formatCount(stats.observations);
    document.querySelector("#numericCount").textContent = formatCount(stats.numeric_observations);
    document.querySelector("#qualityCount").textContent = formatCount(stats.quality_issues);
    document.querySelector("#coverageRange").textContent = `${stats.period.first} — ${stats.period.last}`;
    const operatorList = document.querySelector("#operatorList");
    const operatorsWithData = new Set(stats.operators);
    operatorList.replaceChildren(...(stats.supported_operators || stats.operators).map((operator) => {
      const badge = document.createElement("span");
      badge.textContent = operator;
      badge.className = "operator-badge";
      badge.classList.toggle("awaiting-data", !operatorsWithData.has(operator));
      if (!operatorsWithData.has(operator)) badge.title = "No imported data yet";
      applyOperatorColor(badge, operator);
      return badge;
    }));
  } catch (error) {
    setServerStatus(false);
    setCopilotStatus(false);
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
    row.dataset.operator = item.operator || "";
    row.dataset.period = item.period || "";
    const values = [item.operator, item.period, item.displayed_value, item.source];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 0) {
        cell.className = "operator-cell";
        applyOperatorColor(cell, item.operator);
      }
      if (index === 3) cell.className = "source-ref";
      row.appendChild(cell);
    });
    elements.evidenceBody.appendChild(row);
  });
}

function chartPeriods() {
  return [...new Set((currentChart?.series || []).flatMap((series) => (series.points || []).map((point) => String(point.period))))].sort();
}

function matchingEvidence(operator, period) {
  return currentEvidence.find((item) => item.operator === operator && String(item.period) === String(period));
}

function selectChartEvidence(detail) {
  const evidence = matchingEvidence(detail.operator, detail.period);
  const source = evidence?.source || "Source reference is not included in this result set.";
  elements.chartSelection.hidden = false;
  elements.chartSelection.textContent = `${detail.operator} · ${detail.period}: ${detail.formattedValue}. Source: ${source}`;
  elements.evidenceBody.querySelectorAll("tr").forEach((row) => {
    row.classList.toggle("selected-evidence", row.dataset.operator === detail.operator && row.dataset.period === String(detail.period));
  });
}

function resetChartInteraction() {
  chartViewport = { size: null, end: null };
  elements.chartSelection.hidden = true;
  elements.chartSelection.textContent = "";
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

function recommendedChartType(response) {
  const series = response.chart?.series || [];
  const metric = response.analysis?.metric || "";
  if (series.length > 1 && ["latest", "lookup"].includes(response.intent)) return "donut";
  if (series.length > 1 && response.intent === "compare") return "bar";
  if (series.length === 1 && /rate|percent|penetration|share|%/i.test(metric) && response.intent === "latest") return "gauge";
  return "line";
}

function renderSelectedChart(type) {
  if (!currentChart || !window.AdinkraCharts) return;
  currentChartType = type;
  const periods = chartPeriods();
  const end = chartViewport.end === null ? periods.length : Math.min(periods.length, chartViewport.end);
  const size = chartViewport.size === null ? periods.length : Math.min(periods.length, chartViewport.size);
  const start = Math.max(0, end - size);
  chartViewport.end = end;
  elements.chartCaption.textContent = window.AdinkraCharts.render(elements.chartFrame, currentChart, type, {
    viewport: { start, end },
    evidence: currentEvidence,
    onSelect: selectChartEvidence,
  });
  const visible = periods.slice(start, end);
  elements.chartWindowStatus.textContent = visible.length
    ? `Showing ${visible[0]} to ${visible[visible.length - 1]} · ${visible.length} of ${periods.length} periods`
    : "No reporting periods available";
  elements.chartPanLeft.disabled = start === 0;
  elements.chartPanRight.disabled = end >= periods.length;
  elements.chartZoomIn.disabled = visible.length <= Math.min(3, periods.length);
  elements.chartZoomOut.disabled = visible.length >= periods.length;
  document.querySelectorAll("[data-chart-type]").forEach((button) => {
    const selected = button.dataset.chartType === type;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
}

function renderAnalysis(response) {
  const analysis = response.analysis || {};
  const statistics = analysis.statistics || [];
  const insights = analysis.insights || [];
  const hasAnalysis = Boolean(response.chart?.series?.length && statistics.length);
  elements.analysisSection.hidden = !hasAnalysis;
  elements.chartFrame.replaceChildren();
  elements.statGrid.replaceChildren();
  elements.insightList.replaceChildren();
  if (!hasAnalysis) return;

  elements.analysisId.textContent = `Analysis ${response.analysis_id}`;
  currentChart = response.chart;
  resetChartInteraction();
  renderSelectedChart(recommendedChartType(response));

  statistics.forEach((item) => {
    const card = document.createElement("article");
    card.className = "stat-card";
    applyOperatorColor(card, item.operator);
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
  currentEvidence = response.evidence || [];
  elements.answerText.textContent = response.answer;
  elements.intentLabel.textContent = intentLabels[response.intent] || "Direct answer";
  elements.governanceRow.replaceChildren();
  const governance = response.governance;
  const stateClass = governanceClass(governance.release_class);
  addGovernanceBadge(`${governance.release_class} · ${governance.release_decision}`, stateClass);
  addGovernanceBadge(`${governance.uncertainty_class} uncertainty`, stateClass);
  addGovernanceBadge("Source-grounded");
  addGovernanceBadge("Human authority final");
  const copilot = response.copilot || {};
  elements.copilotMessage.hidden = !copilot.message;
  elements.copilotMessage.textContent = copilot.message || "";
  if (copilot.status === "ready") {
    addGovernanceBadge(`Adinkra · ${copilot.model}`);
  } else if (copilot.status === "skipped_by_governance") {
    addGovernanceBadge("OpenAI transfer blocked", "hold");
  } else if (copilot.status === "not_configured") {
    addGovernanceBadge("Local answer · API key needed", "warn");
  } else if (copilot.status === "fallback") {
    addGovernanceBadge("Local fallback", "warn");
  }
  renderAnalysis(response);
  renderEvidence(currentEvidence);
  renderAlternatives(response.alternatives || []);
  showState("answer");
  elements.answerCard.focus({ preventScroll: true });
}

async function submitQuestion(question) {
  elements.askButton.disabled = true;
  showState("loading");
  try {
    const response = await fetch("/api/copilot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    renderAnswer(await response.json());
  } catch (error) {
    elements.errorText.textContent = "The Adinkra service did not respond. Confirm the server is running, then try again.";
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

document.querySelectorAll("[data-chart-type]").forEach((button) => {
  button.addEventListener("click", () => renderSelectedChart(button.dataset.chartType));
});

elements.chartDownloadButton.addEventListener("click", () => {
  if (!currentChart || !window.AdinkraCharts) return;
  window.AdinkraCharts.download(elements.chartFrame, currentChart.title, currentChartType);
});

function changeChartWindow(action) {
  const total = chartPeriods().length;
  if (!total) return;
  let size = chartViewport.size === null ? total : chartViewport.size;
  let end = chartViewport.end === null ? total : chartViewport.end;
  if (action === "in") size = Math.max(Math.min(3, total), Math.floor(size * 0.7));
  if (action === "out") size = Math.min(total, Math.ceil(size / 0.7));
  const step = Math.max(1, Math.floor(size / 3));
  if (action === "left") end = Math.max(size, end - step);
  if (action === "right") end = Math.min(total, end + step);
  if (action === "reset") { size = total; end = total; }
  end = Math.max(size, Math.min(total, end));
  chartViewport = { size, end };
  renderSelectedChart(currentChartType);
}

elements.chartPanLeft.addEventListener("click", () => changeChartWindow("left"));
elements.chartPanRight.addEventListener("click", () => changeChartWindow("right"));
elements.chartZoomIn.addEventListener("click", () => changeChartWindow("in"));
elements.chartZoomOut.addEventListener("click", () => changeChartWindow("out"));
elements.chartReset.addEventListener("click", () => changeChartWindow("reset"));

elements.importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = elements.importFile.files[0];
  if (!file) return;
  elements.importButton.disabled = true;
  elements.importStatus.className = "import-status working";
  elements.importStatus.textContent = `Importing ${file.name}… Keep this page open while Excel is processed.`;
  try {
    const response = await fetch("/api/data/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Operator": elements.importOperator.value,
        "X-Filename": encodeURIComponent(file.name),
      },
      body: file,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || `Import failed (${response.status})`);
    elements.importStatus.className = "import-status success";
    elements.importStatus.textContent = `${payload.message} The database now contains ${formatCount(payload.observations)} observations.`;
    elements.importFile.value = "";
    await loadWorkspaceStatus();
  } catch (error) {
    elements.importStatus.className = "import-status error";
    elements.importStatus.textContent = error.message || "The data import failed.";
  } finally {
    elements.importButton.disabled = false;
  }
});

showState("empty");
updateCharacterCount();
loadWorkspaceStatus();
