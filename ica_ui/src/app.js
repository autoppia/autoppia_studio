const DEFAULT_API_URL = "http://127.0.0.1:8080";
const MODE_LABELS = { api_only: "API", web_only: "Web", hybrid: "Hybrid" };

const state = {
  apiUrl: localStorage.getItem("ica_api_url") || new URLSearchParams(location.search).get("api") || DEFAULT_API_URL,
  harvesters: [],
  companies: [],
  runs: [],
  selectedHarvesters: new Set(),
  selectedProjects: new Set(),
  selectedModes: new Set(),
  activeTab: "overview",
  expandedRunId: "",
  lastRunGroupId: "",
  filters: { group: "", harvester: "", project: "", mode: "", status: "" },
  loading: false,
  running: false,
};

const el = (id) => document.getElementById(id);
const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`;
const modeLabel = (mode) => MODE_LABELS[mode] || "Default";
const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function avg(items, selector) {
  if (!items.length) return 0;
  return items.reduce((sum, item) => sum + Number(selector(item) || 0), 0) / items.length;
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 18 ? `${text.slice(0, 18)}...` : text;
}

function setError(message) {
  const node = el("errorBanner");
  if (!message) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.textContent = message;
}

function api(path) {
  return `${state.apiUrl.replace(/\/+$/, "")}${path}`;
}

async function getJson(path) {
  const response = await fetch(api(path));
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`);
  return response.json();
}

function titleForHarvester(item) {
  if (item.displayName) return item.displayName;
  if (item.name === "claude_code") return "Claude Code Harvester";
  if (item.name === "codex") return "Codex Harvester";
  return "Agentic Harvester";
}

function updateKpis() {
  const completed = state.runs.filter((run) => run.status === "completed");
  const passed = completed.filter((run) => run.passed);
  const avgScore = avg(completed, (run) => run.score);
  const avgRecall = avg(completed, (run) => run.taskRecall);
  const cells = state.selectedHarvesters.size * state.selectedProjects.size * Math.max(state.selectedModes.size, 1);
  el("kpiRuns").textContent = String(completed.length);
  el("kpiPassed").textContent = `${passed.length} pass`;
  el("kpiScore").textContent = pct(avgScore);
  el("kpiRecall").textContent = pct(avgRecall);
  el("kpiSelected").textContent = String(cells);
}

function renderTabs() {
  document.querySelectorAll("[data-tab]").forEach((node) => {
    const tab = node.getAttribute("data-tab");
    const active = tab === state.activeTab;
    if (node.classList.contains("tab")) {
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-selected", active ? "true" : "false");
    }
  });
  document.querySelectorAll(".tab-panel").forEach((node) => {
    node.hidden = node.id !== `panel-${state.activeTab}`;
  });
}

function renderSelectionSummary() {
  const cells = state.selectedHarvesters.size * state.selectedProjects.size * Math.max(state.selectedModes.size, 1);
  const modes = Array.from(state.selectedModes).map(modeLabel).join(", ") || "No modes selected";
  el("selectionSummary").innerHTML = `
    <div class="summary-row"><span>Harvesters</span><strong>${state.selectedHarvesters.size}/${state.harvesters.length}</strong></div>
    <div class="summary-row"><span>Demo companies</span><strong>${state.selectedProjects.size}/${state.companies.length}</strong></div>
    <div class="summary-row"><span>Modes</span><strong>${escapeHtml(modes)}</strong></div>
    <div class="summary-row"><span>Matrix size</span><strong>${cells}</strong><small>runs</small></div>
  `;
  el("harvestersCount").textContent = `${state.selectedHarvesters.size} selected`;
  el("companiesCount").textContent = `${state.selectedProjects.size} selected`;
}

function renderHarvesters() {
  const html = state.harvesters
    .map((item) => {
      const selected = state.selectedHarvesters.has(item.name);
      return `
        <button class="miner-card ${escapeHtml(item.name)} ${selected ? "is-selected" : ""}" data-harvester="${escapeHtml(item.name)}" type="button">
          <div class="card-top">
            <div>
              <div class="card-title">${escapeHtml(titleForHarvester(item))}</div>
              <div class="card-id">${escapeHtml(item.name)}</div>
            </div>
            <span class="badge">${escapeHtml(item.status || "ready")}</span>
          </div>
          <p class="card-desc">${escapeHtml(item.description || "")}</p>
          <div class="miner-flags">
            <span class="surface">tasks</span>
            <span class="surface">solutions</span>
            <span class="surface">agent plan</span>
          </div>
        </button>`;
    })
    .join("");
  el("harvestersGrid").innerHTML = html || `<div class="empty">No harvesters found.</div>`;
  document.querySelectorAll("[data-harvester]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-harvester");
      if (state.selectedHarvesters.has(value)) state.selectedHarvesters.delete(value);
      else state.selectedHarvesters.add(value);
      render();
    });
  });
}

function renderModes() {
  const modes = Array.from(new Set(state.companies.flatMap((company) => (company.benchmarkModes || []).map((mode) => mode.modeId))));
  el("modeChips").innerHTML = modes
    .map((mode) => `<button class="chip ${state.selectedModes.has(mode) ? "is-active" : ""}" data-mode="${escapeHtml(mode)}" type="button">${escapeHtml(modeLabel(mode))}</button>`)
    .join("");
  document.querySelectorAll("[data-mode]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-mode");
      if (state.selectedModes.has(value)) state.selectedModes.delete(value);
      else state.selectedModes.add(value);
      render();
    });
  });
}

function renderCompanies() {
  const html = state.companies
    .map((company) => {
      const selected = state.selectedProjects.has(company.projectId);
      const surfaces = (company.surfaceKinds || [])
        .map((surface) => `<span class="surface">${escapeHtml(surface)}</span>`)
        .join("");
      return `
        <button class="company-card ${selected ? "is-selected" : ""}" data-project="${escapeHtml(company.projectId)}" type="button">
          <div class="card-top">
            <div>
              <div class="card-title">${escapeHtml(company.name)}</div>
              <div class="card-id">${escapeHtml(company.projectId)}</div>
            </div>
            <span class="badge">${Number(company.taskCount || 0)} tasks</span>
          </div>
          <p class="card-desc">${escapeHtml(company.description || "")}</p>
          <div class="surfaces">
            ${surfaces}
            ${company.authRequired ? `<span class="surface">auth</span>` : ""}
          </div>
        </button>`;
    })
    .join("");
  el("companiesGrid").innerHTML = html || `<div class="empty">No demo companies found.</div>`;
  document.querySelectorAll("[data-project]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-project");
      if (state.selectedProjects.has(value)) state.selectedProjects.delete(value);
      else state.selectedProjects.add(value);
      render();
    });
  });
}

function statusClass(run) {
  if (run.status === "failed") return "status fail";
  if (run.passed) return "status pass";
  return "status";
}

function groupRuns(runs) {
  const groups = new Map();
  for (const run of runs) {
    const key = run.runGroupId || "ungrouped";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(run);
  }
  return Array.from(groups.entries())
    .map(([runGroupId, items]) => ({
      runGroupId,
      items,
      createdAt: items[0]?.createdAt || "",
      total: items.length,
      passed: items.filter((run) => run.passed).length,
      avgScore: avg(items, (run) => run.score),
      avgTaskRecall: avg(items, (run) => run.taskRecall),
      avgTaskPrecision: avg(items, (run) => run.taskPrecision),
      avgSolutionScore: avg(items, (run) => run.solutionScore),
      avgInventoryScore: avg(items, (run) => run.inventoryScore),
    }))
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
}

function filteredRuns() {
  return state.runs.filter((run) => {
    if (state.filters.group && run.runGroupId !== state.filters.group) return false;
    if (state.filters.harvester && run.harvesterName !== state.filters.harvester) return false;
    if (state.filters.project && run.projectId !== state.filters.project) return false;
    if (state.filters.mode && String(run.mode || "") !== state.filters.mode) return false;
    if (state.filters.status === "pass" && !run.passed) return false;
    if (state.filters.status === "fail" && run.passed) return false;
    return true;
  });
}

function selectedReportGroup() {
  const groups = groupRuns(state.runs);
  if (!groups.length) return null;
  return groups.find((group) => group.runGroupId === state.filters.group) || groups.find((group) => group.runGroupId === state.lastRunGroupId) || groups[0];
}

function setSelectOptions(id, options, value, allLabel) {
  const node = el(id);
  if (!node) return;
  const current = value || "";
  node.innerHTML = [`<option value="">${escapeHtml(allLabel)}</option>`, ...options].join("");
  node.value = current;
}

function renderFilters() {
  const groups = groupRuns(state.runs).map(
    (group) =>
      `<option value="${escapeHtml(group.runGroupId)}">${escapeHtml(shortId(group.runGroupId))} - ${group.total} runs - ${pct(group.avgScore)}</option>`
  );
  const harvesters = [...new Set(state.runs.map((run) => run.harvesterName).filter(Boolean))]
    .sort()
    .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`);
  const projects = [...new Map(state.runs.map((run) => [run.projectId, run.projectName || run.projectId])).entries()]
    .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
    .map(([id, name]) => `<option value="${escapeHtml(id)}">${escapeHtml(name)}</option>`);
  const modes = [...new Set(state.runs.map((run) => String(run.mode || "")).filter(Boolean))]
    .sort()
    .map((mode) => `<option value="${escapeHtml(mode)}">${escapeHtml(modeLabel(mode))}</option>`);
  setSelectOptions("filterGroup", groups, state.filters.group, "All groups");
  setSelectOptions("filterHarvester", harvesters, state.filters.harvester, "All harvesters");
  setSelectOptions("filterProject", projects, state.filters.project, "All companies");
  setSelectOptions("filterMode", modes, state.filters.mode, "All modes");
  const status = el("filterStatus");
  if (status) status.value = state.filters.status;
}

function renderLatestRuns() {
  const html = state.runs
    .slice(0, 12)
    .map(
      (run) => `
        <button class="run-card" data-expand="${escapeHtml(run.runId)}" type="button">
          <div class="run-line">
            <strong>${escapeHtml(run.projectName || run.projectId)}</strong>
            <span class="${statusClass(run)}">${run.status === "failed" ? "fail" : run.passed ? "pass" : "check"}</span>
          </div>
          <div class="run-meta mono">
            <span>${escapeHtml(run.harvesterName)}</span>
            <span>${escapeHtml(modeLabel(run.mode))}</span>
            <span>${pct(run.score)}</span>
          </div>
        </button>`
    )
    .join("");
  el("latestRuns").innerHTML = html || `<div class="empty">${state.loading ? "Loading..." : "No runs yet."}</div>`;
}

function scoreCell(value, passed) {
  const width = Math.max(0, Math.min(100, Math.round((Number(value) || 0) * 100)));
  return `
    <div class="score-cell">
      <span class="mono">${pct(value)}</span>
      <span class="score-track"><i class="score-fill ${passed ? "" : "warn"}" style="width:${width}%"></i></span>
    </div>`;
}

function phaseCell(score, passed, meta = "") {
  return `
    <div class="phase-cell ${passed ? "pass" : "fail"}">
      <strong>${pct(score)}</strong>
      ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
    </div>`;
}

function renderRunGroupReport() {
  const group = selectedReportGroup();
  const node = el("runGroupReport");
  if (!node) return;
  if (!group) {
    node.innerHTML = `<div class="empty">No run group yet. Select harvesters and companies, then run the matrix.</div>`;
    return;
  }

  const byProject = new Map();
  for (const run of group.items) {
    const key = run.projectId || "unknown";
    if (!byProject.has(key)) byProject.set(key, []);
    byProject.get(key).push(run);
  }

  const projectCards = Array.from(byProject.entries())
    .map(([projectId, runs]) => {
      const projectName = runs[0]?.projectName || projectId;
      const missingCount = runs.reduce((sum, run) => sum + Number((run.missing || []).length), 0);
      const rows = runs
        .map(
          (run) => `
            <tr>
              <td class="mono">${escapeHtml(run.harvesterName)}</td>
              <td>${escapeHtml(modeLabel(run.mode))}</td>
              <td>${phaseCell(run.taskRecall, run.taskDiscoveryPassed, `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} matched`)}</td>
              <td>${phaseCell(run.solutionScore, run.solutionDiscoveryPassed, `${Number(run.solutionCount || 0)} plans`)}</td>
              <td>${phaseCell(run.inventoryScore, run.inventoryPassed, "inventory")}</td>
              <td><span class="${run.passed ? "status pass" : "status"}">${run.passed ? "pass" : "needs work"}</span></td>
            </tr>`
        )
        .join("");
      return `
        <article class="group-card">
          <div class="group-card-head">
            <div>
              <h3>${escapeHtml(projectName)}</h3>
              <div class="card-id">${escapeHtml(projectId)}</div>
            </div>
            <span class="${missingCount ? "status" : "status pass"}">${missingCount ? `${missingCount} gaps` : "complete"}</span>
          </div>
          <div class="phase-grid">
            ${metric("Runs", String(runs.length))}
            ${metric("Pass rate", `${runs.filter((run) => run.passed).length}/${runs.length}`)}
            ${metric("Task recall", pct(avg(runs, (run) => run.taskRecall)))}
            ${metric("Task precision", pct(avg(runs, (run) => run.taskPrecision)))}
            ${metric("Solution score", pct(avg(runs, (run) => run.solutionScore)))}
            ${metric("Inventory", pct(avg(runs, (run) => run.inventoryScore)))}
          </div>
          <div class="mini-table-wrap">
            <table class="mini-table">
              <thead>
                <tr>
                  <th>Harvester</th>
                  <th>Mode</th>
                  <th>Tasks</th>
                  <th>Solutions</th>
                  <th>Inventory</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </article>`;
    })
    .join("");

  node.innerHTML = `
    <div class="group-summary">
      <div>
        <div class="eyebrow">Run group</div>
        <h2>${escapeHtml(shortId(group.runGroupId))}</h2>
        <div class="card-id">${escapeHtml(group.runGroupId)}</div>
      </div>
      <div class="summary-pill"><span>${group.total}</span><small>runs</small></div>
      <div class="summary-pill"><span>${group.passed}/${group.total}</span><small>pass</small></div>
      <div class="summary-pill"><span>${pct(group.avgScore)}</span><small>overall</small></div>
      <div class="summary-pill"><span>${pct(group.avgTaskRecall)}</span><small>task recall</small></div>
      <div class="summary-pill"><span>${pct(group.avgSolutionScore)}</span><small>solution score</small></div>
    </div>
    <div class="group-cards">${projectCards}</div>`;
}

function renderResults() {
  const runs = filteredRuns();
  el("emptyResults").hidden = runs.length > 0;
  el("emptyResults").textContent = state.runs.length ? "No runs match the current filters." : "Run the selected matrix to populate results.";
  el("resultsBody").innerHTML = runs
    .map((run) => {
      const expanded = state.expandedRunId === run.runId;
      const missing = run.missing || [];
      const taskMissing = run.taskMissingTaskIds || [];
      const taskExtra = run.taskExtraTaskNames || [];
      const solutionMissing = run.solutionMissingTaskIds || [];
      const solutionIncomplete = run.solutionIncompleteTaskIds || [];
      const inventoryMissing = run.inventoryMissing || [];
      return `
        <tr>
          <td><strong>${escapeHtml(run.projectName || run.projectId)}</strong><div class="card-id">${escapeHtml(run.projectId)}</div></td>
          <td class="mono">${escapeHtml(run.harvesterName)}</td>
          <td>${escapeHtml(modeLabel(run.mode))}</td>
          <td>${scoreCell(run.score, run.passed)}</td>
          <td>${phaseCell(run.taskRecall, run.taskDiscoveryPassed, `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} matched`)}</td>
          <td>${phaseCell(run.solutionScore, run.solutionDiscoveryPassed, `${Number(run.solutionCount || 0)} deliverables`)}</td>
          <td>${phaseCell(run.inventoryScore, run.inventoryPassed, `${inventoryMissing.length} gaps`)}</td>
          <td class="${missing.length ? "warn" : "good"}">${missing.length}</td>
          <td><button class="detail-btn" data-expand="${escapeHtml(run.runId)}" type="button">${expanded ? "-" : "+"}</button></td>
        </tr>
        ${
          expanded
            ? `<tr class="detail-row">
                <td colspan="9">
                  <div class="detail-grid">
                    ${metric("Precision", pct(run.taskPrecision))}
                    ${metric("Inventory", pct(run.inventoryScore))}
                    ${metric("Task gaps", String(taskMissing.length))}
                    ${metric("Solution gaps", String(solutionMissing.length + solutionIncomplete.length))}
                    ${metric("Run group", run.runGroupId, true)}
                    ${metric("Created", new Date(run.createdAt).toLocaleString())}
                  </div>
                  <div class="detail-lists">
                    ${listBlock("Missing tasks", taskMissing)}
                    ${listBlock("Extra proposed tasks", taskExtra)}
                    ${listBlock("Missing solutions", solutionMissing)}
                    ${listBlock("Incomplete solutions", solutionIncomplete)}
                    ${listBlock("Inventory gaps", inventoryMissing)}
                  </div>
                </td>
              </tr>`
            : ""
        }`;
    })
    .join("");
  document.querySelectorAll("[data-expand]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-expand");
      state.expandedRunId = state.expandedRunId === value ? "" : value;
      state.activeTab = "runs";
      renderResults();
      renderLatestRuns();
      renderTabs();
    });
  });
}

function metric(label, value, mono = false) {
  return `<div class="metric"><small>${escapeHtml(label)}</small><strong class="${mono ? "mono" : ""}">${escapeHtml(value)}</strong></div>`;
}

function listBlock(label, items) {
  const values = items || [];
  return `
    <div class="list-block ${values.length ? "has-items" : ""}">
      <small>${escapeHtml(label)}</small>
      <strong>${values.length ? escapeHtml(values.join(", ")) : "None"}</strong>
    </div>`;
}

function render() {
  el("apiUrlInput").value = state.apiUrl;
  const runDisabled = state.running || state.loading || !state.selectedHarvesters.size || !state.selectedProjects.size;
  for (const id of ["runButton", "runButtonOverview"]) {
    const button = el(id);
    if (!button) continue;
    button.disabled = runDisabled;
    button.textContent = state.running ? "Running..." : "Run matrix";
  }
  for (const id of ["runState", "runStateRuns"]) {
    const node = el(id);
    if (node) node.textContent = state.running ? "running" : state.loading ? "loading" : "idle";
  }
  renderTabs();
  renderHarvesters();
  renderModes();
  renderCompanies();
  renderLatestRuns();
  renderFilters();
  renderRunGroupReport();
  renderResults();
  renderSelectionSummary();
  updateKpis();
}

async function loadData() {
  state.loading = true;
  setError("");
  render();
  try {
    const [harvesters, companies, runs] = await Promise.all([
      getJson("/ica/harvesters"),
      getJson("/ica/demo-companies"),
      getJson("/ica/runs"),
    ]);
    state.harvesters = harvesters.harvesters || [];
    state.companies = companies.demoCompanies || [];
    state.runs = runs.runs || [];
    state.lastRunGroupId = state.runs[0]?.runGroupId || "";
    state.selectedHarvesters = new Set(state.harvesters.map((item) => item.name));
    state.selectedProjects = new Set(state.companies.map((item) => item.projectId));
    state.selectedModes = new Set(state.companies.flatMap((company) => (company.benchmarkModes || []).map((mode) => mode.modeId)));
  } catch (error) {
    setError(error.message || "Failed to load ICA data");
  } finally {
    state.loading = false;
    render();
  }
}

async function runMatrix() {
  state.running = true;
  setError("");
  render();
  try {
    const response = await fetch(api("/ica/runs"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        harvesterNames: Array.from(state.selectedHarvesters),
        projectIds: Array.from(state.selectedProjects),
        modeIds: Array.from(state.selectedModes),
        email: "ica-owner@example.com",
      }),
    });
    if (!response.ok) throw new Error((await response.text()) || `Run failed: ${response.status}`);
    const data = await response.json();
    state.lastRunGroupId = data.runGroupId || "";
    state.filters.group = state.lastRunGroupId;
    state.runs = [...(data.runs || []), ...state.runs];
    state.activeTab = "runs";
  } catch (error) {
    setError(error.message || "ICA run failed");
  } finally {
    state.running = false;
    render();
  }
}

function bindControls() {
  el("apiUrlInput").addEventListener("change", (event) => {
    state.apiUrl = event.target.value.trim() || DEFAULT_API_URL;
    localStorage.setItem("ica_api_url", state.apiUrl);
    loadData();
  });
  el("reloadButton").addEventListener("click", loadData);
  el("runButton").addEventListener("click", runMatrix);
  el("runButtonOverview").addEventListener("click", runMatrix);
  document.querySelectorAll("[data-tab]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      state.activeTab = node.getAttribute("data-tab") || "overview";
      render();
    });
  });
  el("toggleHarvesters").addEventListener("click", () => {
    state.selectedHarvesters =
      state.selectedHarvesters.size === state.harvesters.length ? new Set() : new Set(state.harvesters.map((item) => item.name));
    render();
  });
  el("toggleProjects").addEventListener("click", () => {
    state.selectedProjects =
      state.selectedProjects.size === state.companies.length ? new Set() : new Set(state.companies.map((item) => item.projectId));
    render();
  });
  [
    ["filterGroup", "group"],
    ["filterHarvester", "harvester"],
    ["filterProject", "project"],
    ["filterMode", "mode"],
    ["filterStatus", "status"],
  ].forEach(([id, key]) => {
    const node = el(id);
    if (!node) return;
    node.addEventListener("change", (event) => {
      state.filters[key] = event.target.value;
      state.expandedRunId = "";
      render();
    });
  });
  el("clearFilters").addEventListener("click", () => {
    state.filters = { group: "", harvester: "", project: "", mode: "", status: "" };
    state.expandedRunId = "";
    render();
  });
}

bindControls();
loadData();
