const DEFAULT_API_URL = location.hostname === "studio.autoppia.com" ? "https://api-studio.autoppia.com" : "http://127.0.0.1:8080";
const LOCAL_API_CANDIDATES = ["http://127.0.0.1:8080", "http://localhost:8080", "http://127.0.0.1:8100", "http://localhost:8100"];
const MODE_LABELS = {
  web_only: "Web",
  api_only: "API",
  documents_only: "Docs",
  code_only: "Code",
  web_api: "Web + API",
  web_documents: "Web + Docs",
  web_code: "Web + Code",
  api_documents: "API + Docs",
  api_code: "API + Code",
  documents_code: "Docs + Code",
  web_api_documents: "Web + API + Docs",
  web_api_code: "Web + API + Code",
  web_documents_code: "Web + Docs + Code",
  api_documents_code: "API + Docs + Code",
  all_sources: "All sources",
  hybrid: "Hybrid",
};

/* ---------- source / mode taxonomy ---------- */
// The four input sources a CompanyHarvester can be benchmarked against.
const SOURCES = [
  { key: "web", short: "Web", token: "web" },
  { key: "api", short: "API", token: "api" },
  { key: "documents", short: "Docs", token: "documents" },
  { key: "code", short: "Code", token: "code" },
];
const SOURCE_BY_KEY = Object.fromEntries(SOURCES.map((s) => [s.key, s]));
const SOURCE_ORDER = SOURCES.map((s) => s.key);

// Backend surface kinds (IcaSurfaceKind) collapse onto the four canonical
// sources the UI groups by. Anything not listed (already canonical, e.g. "web"
// / "api") passes through unchanged, plus the legacy "docs" alias.
const SURFACE_KIND_TO_SOURCE = {
  web: "web",
  openapi: "api",
  api_docs: "api",
  document_url: "documents",
  file: "documents",
  knowledge_note: "documents",
  code_repository: "code",
  code_file: "code",
  docs: "documents",
};
function normalizeSourceKey(key) {
  return SURFACE_KIND_TO_SOURCE[key] || key;
}

// Decode which sources a benchmark mode covers from its modeId.
function modeSources(modeId) {
  const id = String(modeId || "");
  if (id === "all_sources") return [...SOURCE_ORDER];
  if (id === "hybrid") return [...SOURCE_ORDER];
  const found = SOURCE_ORDER.filter((key) => id.split("_").includes(key));
  return found.length ? found : [];
}

// Source-count grouping used to avoid dumping all 15 modes as one wall.
const MODE_GROUPS = [
  { key: "single", label: "Single source", hint: "1 input source" },
  { key: "two", label: "Two sources", hint: "2 combined" },
  { key: "three", label: "Three sources", hint: "3 combined" },
  { key: "all", label: "All sources", hint: "every source" },
];
function modeGroupKey(modeId) {
  if (String(modeId) === "all_sources") return "all";
  const n = modeSources(modeId).length;
  if (n >= 4) return "all";
  if (n === 3) return "three";
  if (n === 2) return "two";
  return "single";
}

// Render the source-token chips (Web/API/Docs/Code) a mode covers.
function sourceChips(modeId, opts = {}) {
  const active = new Set(modeSources(modeId));
  return `<span class="src-chips${opts.dim ? " dim" : ""}">${SOURCES.map(
    (s) => `<span class="src-chip src-${s.token} ${active.has(s.key) ? "on" : "off"}">${s.short}</span>`
  ).join("")}</span>`;
}

function initialApiUrl() {
  const params = new URLSearchParams(location.search);
  const fromQuery = params.get("api");
  if (fromQuery) return fromQuery;
  const stored = localStorage.getItem("ica_api_url") || "";
  const isLocal = ["127.0.0.1", "localhost"].includes(location.hostname);
  if (isLocal) {
    localStorage.setItem("ica_api_url", DEFAULT_API_URL);
    return DEFAULT_API_URL;
  }
  return stored || DEFAULT_API_URL;
}

const TABS = ["overview", "sources", "leaderboard", "harvesters", "companies", "runs"];

function routeFromUrl() {
  const params = new URLSearchParams(location.search);
  const openRunId = params.get("run") || "";
  const openGroupId = params.get("group") || "";
  let activeTab = TABS.includes(params.get("tab")) ? params.get("tab") : "runs";
  // a run / group deep-link always lives under the Runs tab
  if (openRunId || openGroupId) activeTab = "runs";
  return { activeTab, openGroupId, openRunId };
}

const initialRoute = routeFromUrl();

const state = {
  apiUrl: initialApiUrl(),
  harvesters: [],
  companies: [],
  runs: [],
  selectedHarvesters: new Set(),
  selectedProjects: new Set(),
  selectedModes: new Set(),
  activeTab: initialRoute.activeTab,
  openGroupId: initialRoute.openGroupId,
  openRunId: initialRoute.openRunId,
  lastRunGroupId: "",
  sourceDim: "harvester",
  filters: { group: "", harvester: "", project: "", mode: "", status: "", phase: "" },
  companyFilter: { search: "", sources: new Set(), sort: "name" },
  expandedCompanies: new Set(),
  detailTab: "overview",
  loading: false,
  running: false,
};

/* ---------- routing ---------- */

function buildUrl({ tab, group, run }) {
  const params = new URLSearchParams();
  if (tab && tab !== "overview") params.set("tab", tab);
  if (group) params.set("group", group);
  if (run) params.set("run", run);
  const qs = params.toString();
  return qs ? `${location.pathname}?${qs}` : location.pathname;
}

// Update the address bar to match current state without re-navigating.
function syncUrl(replace = false) {
  const url = buildUrl({ tab: state.activeTab, group: state.openGroupId, run: state.openRunId });
  const current = `${location.pathname}${location.search}`;
  if (url === current) return;
  history[replace ? "replaceState" : "pushState"]({}, "", url);
}

// Navigate to a new route (pushes history), then re-render.
function go({ tab = state.activeTab, group = "", run = "", detailTab }) {
  // entering a different run / group resets the detail sub-tab to Overview
  if (group !== state.openGroupId || run !== state.openRunId) state.detailTab = "overview";
  if (detailTab) state.detailTab = detailTab;
  state.activeTab = tab;
  state.openGroupId = group;
  state.openRunId = run;
  syncUrl(false);
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

const el = (id) => document.getElementById(id);
const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0));
const pct = (value) => `${Math.round(clamp01(value) * 100)}%`;
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

function gradeClass(v) {
  const n = clamp01(v);
  if (n >= 0.7) return "g-good";
  if (n >= 0.4) return "g-warn";
  return "g-bad";
}

/* ---------- plain-language layer ---------- */

// Short, jargon-busting definitions surfaced through info dots and tooltips.
const GLOSSARY = {
  harvester:
    "A miner profile that implements the CompanyHarvester contract: given a company's surfaces it discovers tasks, plans solutions and (optionally) executes them.",
  taskRecall: "Share of the company's expected benchmark tasks the harvester managed to discover.",
  taskPrecision: "Of the tasks the harvester proposed, how many were real expected tasks (not invented).",
  solution: "How complete and valid the proposed solution plans are — connectors, tools, trajectories and skills.",
  agentExec: "Whether an agent following the discovered plan actually passes the company's task tests.",
  gaps: "Things the harvester missed or invented: missing tasks/solutions, hallucinated tools or connectors, failed tests.",
  matrixSize: "Evaluation cells the next run produces = selected harvesters × companies × source modes.",
  passRate: "Share of completed evaluations that met the pass threshold.",
  avgScore: "Average benchmark score across every completed evaluation.",
  sourceMode: "Which input surfaces (Web, API, Docs, Code) a harvester may use for that evaluation.",
  needsWork: "The evaluation completed, but its score is below the pass threshold.",
};

// Inline info tooltip. Uses a native title so it works without extra wiring.
function infoDot(text) {
  const t = escapeHtml(text);
  return `<span class="info-dot" tabindex="0" role="note" aria-label="${t}" title="${t}">i</span>`;
}

// Turn a raw backend error (often a Pydantic ValidationError dump) into a short,
// human sentence, keeping the full text available for the "technical detail" toggle.
function humanizeError(raw) {
  const msg = String(raw || "").trim();
  if (!msg) return { summary: "The evaluation failed without an error message.", detail: "" };
  const validation = msg.match(/(\d+)\s+validation errors?\s+for\s+([A-Za-z0-9_]+)/i);
  if (validation) {
    const n = Number(validation[1]);
    return {
      summary: `The harvester returned malformed output — ${n} field${n === 1 ? "" : "s"} failed validation for ${validation[2]}.`,
      detail: msg,
    };
  }
  if (/timeout|timed out/i.test(msg)) {
    return { summary: "The harvester timed out before returning a result.", detail: msg };
  }
  if (/connection|ECONNREFUSED|network/i.test(msg)) {
    return { summary: "Could not reach the harvester runtime (connection error).", detail: msg };
  }
  const firstLine = msg.split("\n")[0].trim().slice(0, 200);
  return { summary: firstLine || "The evaluation failed.", detail: msg.length > firstLine.length ? msg : "" };
}

// Human-readable label for a run group, e.g. "3 harvesters × 19 companies · Web".
function runGroupLabel(group) {
  const items = (group && group.items) || [];
  if (!items.length) return shortId(group ? group.runGroupId : "");
  const hs = [...new Set(items.map((r) => r.harvesterName))];
  const cs = [...new Set(items.map((r) => r.projectId))];
  const ms = [...new Set(items.map((r) => String(r.mode || "")))];
  const hPart = hs.length === 1 ? harvesterLabel(hs[0]) : `${hs.length} harvesters`;
  const cPart =
    cs.length === 1 ? items.find((r) => r.projectId === cs[0])?.projectName || cs[0] : `${cs.length} companies`;
  const mPart = ms.length === 1 ? modeLabel(ms[0]) : `${ms.length} modes`;
  return `${hPart} × ${cPart} · ${mPart}`;
}

// Qualitative time expectation for a matrix of N eval cells (honest, not fake-precise).
function runSizeHint(cells) {
  if (cells <= 0) return "";
  if (cells <= 4) return "usually under a minute or two";
  if (cells <= 24) return "usually a few minutes";
  if (cells <= 60) return "can take several minutes";
  return "can take 10+ minutes";
}

// Boilerplate auto-wrapper descriptions add no information — hide them.
function meaningfulDescription(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (/^web-only ICA wrapper for the legacy/i.test(value)) return "";
  return value;
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
  const response = await fetch(api(path), { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`);
  return response.json();
}

async function canUseApiUrl(baseUrl) {
  try {
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/health`, { cache: "no-store" });
    return response.ok;
  } catch (_error) {
    return false;
  }
}

async function resolveApiUrl() {
  if (await canUseApiUrl(state.apiUrl)) return state.apiUrl;
  const isLocal = ["127.0.0.1", "localhost"].includes(location.hostname);
  const candidates = isLocal
    ? [state.apiUrl, DEFAULT_API_URL, ...LOCAL_API_CANDIDATES]
    : [state.apiUrl, DEFAULT_API_URL];
  const uniqueCandidates = [...new Set(candidates.filter(Boolean).map((item) => item.replace(/\/+$/, "")))];
  for (const candidate of uniqueCandidates) {
    if (await canUseApiUrl(candidate)) {
      state.apiUrl = candidate;
      localStorage.setItem("ica_api_url", candidate);
      return candidate;
    }
  }
  throw new Error(`Failed to fetch ICA API. Tried: ${uniqueCandidates.join(", ")}`);
}

function titleForHarvester(item) {
  if (item.displayName) return item.displayName;
  if (item.name === "claude_code") return "Claude Code Harvester";
  if (item.name === "codex") return "Codex Harvester";
  return "Agentic Harvester";
}

function harvesterLabel(name) {
  const found = state.harvesters.find((h) => h.name === name);
  return found ? titleForHarvester(found) : name;
}

/* ---------- chart helpers ---------- */

function bar(label, value, opts = {}) {
  const w = Math.round(clamp01(value) * 100);
  const cls = opts.colorByGrade ? gradeClass(value) : "";
  const labelHtml = opts.labelHtml || `<span class="bar-label">${escapeHtml(label)}</span>`;
  return `
    <div class="bar-row">
      ${labelHtml}
      <span class="bar-track"><i class="bar-fill ${cls}" style="width:${w}%"></i></span>
      <span class="bar-val">${pct(value)}</span>
    </div>`;
}

function sparkline(values, opts = {}) {
  const pts = values.map((v) => clamp01(v));
  if (pts.length < 2) {
    return `<svg viewBox="0 0 100 28" preserveAspectRatio="none" style="width:100%;height:100%"></svg>`;
  }
  const w = 100;
  const h = 28;
  const step = w / (pts.length - 1);
  const coords = pts.map((v, i) => [i * step, h - 3 - v * (h - 6)]);
  const line = coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w} ${h} L0 ${h} Z`;
  const stroke = opts.stroke || "#1f2937";
  const titleEl = opts.title ? `<title>${escapeHtml(opts.title)}</title>` : "";
  return `
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%">
      ${titleEl}
      <defs><linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${stroke}" stop-opacity="0.22"/>
        <stop offset="1" stop-color="${stroke}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#sparkFill)"/>
      <path d="${line}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        vector-effect="non-scaling-stroke"/>
    </svg>`;
}

// Circular progress ring (overall score) — color-coded by grade.
function scoreRing(value, opts = {}) {
  const size = opts.size || 104;
  const stroke = opts.stroke || 11;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - clamp01(value));
  const sub = opts.label ? `<small>${escapeHtml(opts.label)}</small>` : "";
  return `
    <div class="score-ring ${gradeClass(value)}" style="width:${size}px;height:${size}px">
      <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
        <circle class="sr-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
        <circle class="sr-arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
          stroke-linecap="round" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"
          transform="rotate(-90 ${size / 2} ${size / 2})"/>
      </svg>
      <div class="sr-center"><strong style="font-size:${Math.round(size * 0.24)}px">${pct(value)}</strong>${sub}</div>
    </div>`;
}

// Pass/fail donut.
function donut(passed, total, opts = {}) {
  const size = opts.size || 104;
  const stroke = opts.stroke || 11;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const rate = total ? passed / total : 0;
  const off = c * (1 - rate);
  return `
    <div class="score-ring donut" style="width:${size}px;height:${size}px">
      <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
        <circle class="sr-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
        <circle class="sr-arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
          stroke-linecap="round" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"
          transform="rotate(-90 ${size / 2} ${size / 2})"/>
      </svg>
      <div class="sr-center"><strong style="font-size:${Math.round(size * 0.22)}px">${passed}/${total}</strong><small>passed</small></div>
    </div>`;
}

function statTile(label, value, opts = {}) {
  const tone = opts.tone ? ` tone-${opts.tone}` : "";
  const info = opts.info ? ` ${infoDot(opts.info)}` : "";
  return `<div class="stat-tile${tone}"><strong>${escapeHtml(String(value))}</strong><small>${escapeHtml(label)}${info}</small></div>`;
}

// Compact labelled bar (used in run-group cards / mini charts).
function miniBar(label, value) {
  const w = Math.round(clamp01(value) * 100);
  return `
    <div class="mini-bar">
      <span class="mb-label">${escapeHtml(label)}</span>
      <span class="mb-track"><i class="mb-fill ${gradeClass(value)}" style="width:${w}%"></i></span>
      <span class="mb-val">${pct(value)}</span>
    </div>`;
}

// Ranked horizontal comparison chart for a dimension (harvesters / companies / modes).
function compareChart(stats, emptyLabel, opts = {}) {
  if (!stats.length) return `<div class="empty compact">${escapeHtml(emptyLabel)}</div>`;
  const max = Math.max(...stats.map((s) => clamp01(s.score)), 0.0001);
  return `
    <div class="cmp-chart">
      ${stats
        .map((item, i) => {
          const w = Math.round((clamp01(item.score) / max) * 100);
          const cmpPhase = (label, value) =>
            `<span class="cmp-ph"><em>${escapeHtml(label)}</em><span class="cmp-ph-track"><i class="${gradeClass(value)}" style="width:${Math.round(clamp01(value) * 100)}%"></i></span><b>${pct(value)}</b></span>`;
          return `
            <div class="cmp-row">
              <div class="cmp-label" title="${escapeHtml(item.label)}">
                <span class="cmp-rank${i < 3 ? ` m${i + 1}` : ""}">${i + 1}</span>
                <span class="cmp-name">${escapeHtml(item.label)}</span>
                ${opts.chips ? opts.chips(item) : ""}
              </div>
              <div class="cmp-overall">
                <span class="cmp-track"><i class="cmp-fill ${gradeClass(item.score)}" style="width:${w}%"></i></span>
                <b class="cmp-val ${gradeClass(item.score)}">${pct(item.score)}</b>
              </div>
              <div class="cmp-phases">
                ${cmpPhase("Task", item.taskRecall)}
                ${cmpPhase("Solution", item.solutionScore)}
                ${item.executionApplicable ? cmpPhase("Agent", item.executionScore) : cmpPhase("Agent", 0)}
                <span class="cmp-pass">${item.passed}/${item.completed || item.total} pass${item.gaps ? ` · ${item.gaps} gaps` : ""}</span>
              </div>
            </div>`;
        })
        .join("")}
    </div>`;
}

// Scatter plot — task discovery (x) vs solution discovery (y), one dot per eval.
function scatterChart(points, opts = {}) {
  const w = 360;
  const h = 280;
  const padL = 40;
  const padB = 34;
  const padT = 12;
  const padR = 14;
  const innerW = w - padL - padR;
  const innerH = h - padB - padT;
  const sx = (v) => padL + clamp01(v) * innerW;
  const sy = (v) => padT + (1 - clamp01(v)) * innerH;
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((t) => {
      const major = t === 0.5;
      return `
      <line x1="${sx(t).toFixed(1)}" y1="${padT}" x2="${sx(t).toFixed(1)}" y2="${padT + innerH}" class="sc-grid${major ? " major" : ""}"/>
      <line x1="${padL}" y1="${sy(t).toFixed(1)}" x2="${padL + innerW}" y2="${sy(t).toFixed(1)}" class="sc-grid${major ? " major" : ""}"/>
      <text x="${sx(t).toFixed(1)}" y="${h - padB + 14}" class="sc-tick" text-anchor="middle">${Math.round(t * 100)}</text>
      <text x="${padL - 6}" y="${(sy(t) + 3).toFixed(1)}" class="sc-tick" text-anchor="end">${Math.round(t * 100)}</text>`;
    })
    .join("");
  // jitter overlapping points deterministically by index so they don't fully overlap
  const dots = points
    .map((p, i) => {
      const jx = ((i % 3) - 1) * 2.2;
      const jy = ((Math.floor(i / 3) % 3) - 1) * 2.2;
      return `
      <circle cx="${(sx(p.x) + jx).toFixed(1)}" cy="${(sy(p.y) + jy).toFixed(1)}" r="5.5" class="sc-dot ${p.passed ? "pass" : "fail"}">
        <title>${escapeHtml(p.label)} — task ${pct(p.x)} · solution ${pct(p.y)}</title>
      </circle>`;
    })
    .join("");
  return `
    <div class="scatter-card">
      <svg viewBox="0 0 ${w} ${h}" class="scatter-svg" preserveAspectRatio="xMidYMid meet">
        ${grid}
        <line x1="${padL}" y1="${padT + innerH}" x2="${padL + innerW}" y2="${padT + innerH}" class="sc-axis"/>
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + innerH}" class="sc-axis"/>
        ${dots}
        <text x="${padL + innerW / 2}" y="${h - 2}" class="sc-axis-label" text-anchor="middle">Task discovery %</text>
        <text x="12" y="${padT + innerH / 2}" class="sc-axis-label" text-anchor="middle" transform="rotate(-90 12 ${padT + innerH / 2})">Solution discovery %</text>
      </svg>
      <div class="scatter-side">
        <p>${escapeHtml(opts.hint || "Each dot is one eval cell. Top-right = strong on both phases.")}</p>
        <div class="scatter-legend">
          <span class="sc-key pass">passed</span>
          <span class="sc-key fail">needs work</span>
        </div>
      </div>
    </div>`;
}

// Section wrapper with a header — used to break the detail views into clear blocks.
function rgSection(title, sub, body) {
  return `
    <section class="rg-section">
      <div class="rg-section-head">
        <h3>${escapeHtml(title)}</h3>
        ${sub ? `<span class="rg-section-sub">${escapeHtml(sub)}</span>` : ""}
      </div>
      ${body}
    </section>`;
}

/* ---------- aggregates ---------- */

function completedRuns() {
  return state.runs.filter((run) => run.status === "completed");
}

function harvesterStats() {
  const completed = completedRuns();
  const map = new Map();
  for (const run of completed) {
    const key = run.harvesterName || "unknown";
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(run);
  }
  return Array.from(map.entries())
    .map(([name, runs]) => ({
      name,
      runs,
      count: runs.length,
      passed: runs.filter((r) => r.passed).length,
      score: avg(runs, (r) => r.score),
      taskRecall: avg(runs, (r) => r.taskRecall),
      taskPrecision: avg(runs, (r) => r.taskPrecision),
      solutionScore: avg(runs, (r) => r.solutionScore),
      inventoryScore: avg(runs, (r) => r.inventoryScore),
      executionApplicable: runs.filter((r) => r.agentExecutionApplicable).length,
      executionPassed: runs.filter((r) => r.agentExecutionApplicable && r.agentExecutionPassed).length,
      executionScore: avg(runs.filter((r) => r.agentExecutionApplicable), (r) => r.agentExecutionScore),
    }))
    .sort((a, b) => b.score - a.score);
}

function summarizeRuns(runs) {
  const completed = runs.filter((run) => run.status === "completed");
  const passed = completed.filter((run) => run.passed);
  const gaps = completed.reduce((sum, run) => sum + Number((run.missing || []).length), 0);
  const taskExtras = completed.reduce((sum, run) => sum + Number((run.taskExtraTaskNames || []).length), 0);
  const execApplicable = completed.filter((run) => run.agentExecutionApplicable);
  return {
    total: runs.length,
    completed: completed.length,
    passed: passed.length,
    failed: runs.filter((run) => run.status === "failed").length,
    score: avg(completed, (run) => run.score),
    taskRecall: avg(completed, (run) => run.taskRecall),
    taskPrecision: avg(completed, (run) => run.taskPrecision),
    solutionScore: avg(completed, (run) => run.solutionScore),
    inventoryScore: avg(completed, (run) => run.inventoryScore),
    executionApplicable: execApplicable.length,
    executionPassed: execApplicable.filter((run) => run.agentExecutionPassed).length,
    executionScore: avg(execApplicable, (run) => run.agentExecutionScore),
    gaps,
    taskExtras,
  };
}

function dimensionStats(runs, key, labeler = (value) => value) {
  const map = new Map();
  for (const run of runs) {
    const id = String(run[key] || "default");
    if (!map.has(id)) map.set(id, []);
    map.get(id).push(run);
  }
  return Array.from(map.entries())
    .map(([id, items]) => ({ id, label: labeler(id, items), items, ...summarizeRuns(items) }))
    .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
}

function topHarvesterName() {
  const ranked = harvesterStats();
  if (ranked.length) return ranked[0].name;
  return state.harvesters[0]?.name || "";
}

/* ---------- KPIs + charts ---------- */

function updateKpis() {
  const completed = completedRuns();
  const passed = completed.filter((run) => run.passed);
  const avgScore = avg(completed, (run) => run.score);
  const avgRecall = avg(completed, (run) => run.taskRecall);
  const passRate = completed.length ? passed.length / completed.length : 0;

  el("kpiRuns").textContent = String(completed.length);
  el("kpiPassed").textContent = `${passed.length} passed`;
  el("kpiScore").textContent = pct(avgScore);
  el("kpiRecall").textContent = pct(avgRecall);
  el("kpiPassRate").textContent = pct(passRate);
  el("kpiPassRateSub").textContent = `${passed.length}/${completed.length || 0} runs`;

  // Info dots (rendered once; cheap to keep idempotent).
  const setInfo = (id, text) => {
    const node = el(id);
    if (node && !node.dataset.done) {
      node.innerHTML = infoDot(text);
      node.dataset.done = "1";
    }
  };
  setInfo("kpiScoreInfo", GLOSSARY.avgScore);
  setInfo("kpiPassRateInfo", GLOSSARY.passRate);
  setInfo("kpiRecallInfo", GLOSSARY.taskRecall);

  const trend = [...completed].reverse().map((r) => r.score);
  el("kpiScoreSpark").innerHTML = sparkline(trend.length ? trend : [avgScore, avgScore], {
    title: `Score of the last ${Math.min(trend.length, 40) || 0} completed evaluations (oldest → newest)`,
  });
  const cap = el("kpiScoreSparkCap");
  if (cap) cap.textContent = completed.length ? `trend · last ${Math.min(completed.length, 40)} completed` : "";
}

function renderCharts() {
  // Phase performance reflects the top-ranked harvester (not the fleet average),
  // so the panel highlights the current leader's phase breakdown.
  const ranked = harvesterStats();
  const top = ranked[0] || null;
  const tag = el("phaseBarsTag");
  if (tag) tag.textContent = top ? harvesterLabel(top.name) : "top harvester";
  const phaseInfo = el("phaseBarsInfo");
  if (phaseInfo && !phaseInfo.dataset.done) {
    phaseInfo.innerHTML = infoDot("Phase-by-phase breakdown for the current top-ranked harvester.");
    phaseInfo.dataset.done = "1";
  }
  if (top) {
    el("phaseBars").innerHTML = [
      bar("Task discovery", top.taskRecall, { colorByGrade: true }),
      bar("Solution disc.", top.solutionScore, { colorByGrade: true }),
      bar("Agent exec", top.executionApplicable ? top.executionScore : 0, { colorByGrade: true }),
      bar("Task precision", top.taskPrecision, { colorByGrade: true }),
    ].join("");
  } else {
    el("phaseBars").innerHTML = `<div class="empty">No completed runs yet.</div>`;
  }

  const stats = ranked.slice(0, 5);
  el("harvesterRankMini").innerHTML =
    stats
      .map((s, i) => {
        const medal = i < 3 ? `<span class="medal m${i + 1}">${i + 1}</span>` : `<span class="medal">${i + 1}</span>`;
        const labelHtml = `<span class="bar-label">${medal}${escapeHtml(harvesterLabel(s.name))}</span>`;
        return bar(s.name, s.score, { labelHtml });
      })
      .join("") || `<div class="empty">No completed runs yet.</div>`;
}

/* ---------- leaderboard ---------- */

function renderLeaderboard() {
  const stats = harvesterStats();
  el("leaderCount").textContent = `${stats.length} harvester${stats.length === 1 ? "" : "s"}`;
  const node = el("leaderboard");
  if (!stats.length) {
    node.innerHTML = `<div class="empty">${state.loading ? "Loading..." : "Run the matrix to build the leaderboard."}</div>`;
    return;
  }
  // Grade-coloured phase bar with its value — same colour language as the rest of the app.
  const leaderPhase = (label, value, tip) => `
    <div class="lp-row" title="${escapeHtml(tip)}">
      <span class="lp-label">${escapeHtml(label)}</span>
      <span class="lp-track"><i class="lp-fill ${gradeClass(value)}" style="width:${Math.round(clamp01(value) * 100)}%"></i></span>
      <b class="lp-val ${gradeClass(value)}">${pct(value)}</b>
    </div>`;
  node.innerHTML = stats
    .map((s, i) => {
      const rankCls = i < 3 ? ` m${i + 1}` : "";
      return `
        <div class="leader-row ${i === 0 ? "top" : ""}">
          <div class="leader-rank${rankCls}">${i + 1}</div>
          <div class="leader-id">
            <div class="name">${escapeHtml(harvesterLabel(s.name))}</div>
            <div class="sub mono">${escapeHtml(s.name)} · ${s.passed}/${s.count} passed</div>
          </div>
          <div class="leader-bars">
            ${leaderPhase("Task discovery", s.taskRecall, GLOSSARY.taskRecall)}
            ${leaderPhase("Solution discovery", s.solutionScore, GLOSSARY.solution)}
            ${leaderPhase("Inventory", s.inventoryScore, "Coverage of the company's expected inventory of connectors, tools and knowledge.")}
          </div>
          <div class="leader-score">
            <b class="${gradeClass(s.score)}">${pct(s.score)}</b>
            <small>avg score</small>
          </div>
        </div>`;
    })
    .join("");
}

/* ---------- tabs ---------- */

const TAB_TITLES = {
  overview: "Overview",
  sources: "Source coverage",
  leaderboard: "Leaderboard",
  harvesters: "Harvesters",
  companies: "Demo companies",
  runs: "Runs",
};
// Contextual eyebrow shown above the page title in the top bar — aids wayfinding.
const TAB_EYEBROWS = {
  overview: "Benchmark control center",
  sources: "Web · API · Docs · Code coverage",
  leaderboard: "Ranked by average score",
  harvesters: "Miner profiles under test",
  companies: "Evaluation targets",
  runs: "Grouped evaluation history",
};

function renderTabs() {
  document.querySelectorAll(".nav-item[data-tab]").forEach((node) => {
    const tab = node.getAttribute("data-tab");
    const active = tab === state.activeTab;
    node.classList.toggle("is-active", active);
    node.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((node) => {
    node.hidden = node.id !== `panel-${state.activeTab}`;
  });
  const title = el("pageTitle");
  if (title) title.textContent = TAB_TITLES[state.activeTab] || "Overview";
  const eyebrow = el("topEyebrow");
  if (eyebrow) eyebrow.textContent = TAB_EYEBROWS[state.activeTab] || "Company Harvester Benchmark";
}

function renderSelectionSummary() {
  const cells = state.selectedHarvesters.size * state.selectedProjects.size * Math.max(state.selectedModes.size, 0);
  const timeHint = cells > 0 ? runSizeHint(cells) : "";
  el("selectionSummary").innerHTML = `
    <div class="summary-row"><span>Harvesters</span><strong>${state.selectedHarvesters.size}/${state.harvesters.length}</strong></div>
    <div class="summary-row"><span>Demo companies</span><strong>${state.selectedProjects.size}/${state.companies.length}</strong></div>
    <div class="summary-row"><span>Source modes</span><strong>${state.selectedModes.size}/${allModeIds().length}</strong></div>
    <div class="summary-row"><span>Matrix size ${infoDot(GLOSSARY.matrixSize)}</span><strong>${cells}</strong><small>eval cells</small></div>
    ${timeHint ? `<div class="summary-hint">A run of ${cells} cell${cells === 1 ? "" : "s"} ${timeHint}.</div>` : ""}
  `;
  el("harvestersCount").textContent = `${state.selectedHarvesters.size} selected`;
  el("companiesCount").textContent = `${state.selectedProjects.size} selected`;
}

function renderHarvesters() {
  const statsByName = new Map(harvesterStats().map((s) => [s.name, s]));
  const html = state.harvesters
    .map((item) => {
      const selected = state.selectedHarvesters.has(item.name);
      const status = String(item.status || "ready");
      const s = statsByName.get(item.name);
      const perf = s
        ? `<div class="hc-perf">
            <div class="hc-perf-ring">${scoreRing(s.score, { label: "avg score", size: 72, stroke: 8 })}</div>
            <div class="hc-perf-bars">
              ${miniBar("Task discovery", s.taskRecall)}
              ${miniBar("Solution discovery", s.solutionScore)}
              ${s.executionApplicable ? miniBar("Agent execution", s.executionScore) : ""}
              <div class="hc-perf-foot">${s.passed}/${s.count} evals passed</div>
            </div>
          </div>`
        : `<div class="hc-perf empty compact">No completed evaluations yet — run this harvester to see its scores.</div>`;
      return `
        <article class="company-card2 harvester-card2 ${escapeHtml(item.name)} ${selected ? "is-selected" : ""}">
          <div class="cc-head">
            <button class="cc-select" data-harvester="${escapeHtml(item.name)}" type="button" aria-pressed="${selected}" title="Include ${escapeHtml(titleForHarvester(item))} in the next run">
              <span class="cc-check" aria-hidden="true"></span>
              <span class="cc-title-wrap">
                <span class="card-title">${escapeHtml(titleForHarvester(item))}</span>
                <span class="card-id">${escapeHtml(item.name)}</span>
              </span>
            </button>
            <span class="badge status-badge ${status === "ready" ? "ok" : ""}" title="${escapeHtml(status === "ready" ? "Ready to be benchmarked" : status)}">${escapeHtml(status)}</span>
          </div>
          <p class="card-desc full">${escapeHtml(item.description || "")}</p>
          ${perf}
          <div class="miner-flags" title="Phases this harvester implements">
            <span class="surface" title="${escapeHtml(GLOSSARY.taskRecall)}">tasks</span>
            <span class="surface" title="${escapeHtml(GLOSSARY.solution)}">solutions</span>
            <span class="surface" title="${escapeHtml(GLOSSARY.agentExec)}">agent plan</span>
          </div>
        </article>`;
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

function allModeIds() {
  return Array.from(new Set(state.companies.flatMap((company) => (company.benchmarkModes || []).map((mode) => mode.modeId))));
}

function modesInGroup(modes, groupKey) {
  return modes
    .filter((m) => modeGroupKey(m) === groupKey)
    .sort((a, b) => modeSources(a).length - modeSources(b).length || a.localeCompare(b));
}

// Source-token chips for an explicit list of surface keys (web/api/documents/code).
// opts.showAll renders all four sources with on/off state; otherwise only the active ones.
function sourceChipsFromKeys(keys, opts = {}) {
  const active = new Set((keys || []).map(normalizeSourceKey));
  const list = opts.showAll ? SOURCES : SOURCES.filter((s) => active.has(s.key));
  return `<span class="src-chips${opts.showAll ? "" : " dim"}">${list
    .map((s) => `<span class="src-chip src-${s.token} ${active.has(s.key) ? "on" : "off"}">${s.short}</span>`)
    .join("")}</span>`;
}

// The sources a demo company actually exposes, derived from its real surface
// kinds. We deliberately do NOT union the benchmark modes here: a code-only
// company can still ship an `all_sources` mode, which would otherwise light up
// every chip and misrepresent the company.
function companySourceKeys(company) {
  const keys = new Set();
  (company.surfaceKinds || []).forEach((k) => {
    const source = SURFACE_KIND_TO_SOURCE[k];
    if (source) keys.add(source);
  });
  return [...keys];
}

// Grouped source-mode selector used in the run-selection controls.
function renderModes() {
  const node = el("modeSelector");
  const countNode = el("modeSelCount");
  const modes = allModeIds();
  if (countNode) countNode.textContent = `${state.selectedModes.size}/${modes.length} selected`;
  if (!node) return;
  if (!modes.length) {
    node.innerHTML = `<div class="empty compact">No benchmark modes available.</div>`;
    return;
  }
  node.innerHTML = MODE_GROUPS.map((grp) => {
    const groupModes = modesInGroup(modes, grp.key);
    if (!groupModes.length) return "";
    const selCount = groupModes.filter((m) => state.selectedModes.has(m)).length;
    const allOn = selCount === groupModes.length;
    return `
      <div class="mode-group">
        <div class="mode-group-head">
          <span class="mode-group-title">${escapeHtml(grp.label)}<small>${selCount}/${groupModes.length}</small></span>
          <button class="chip tiny" data-mode-group="${grp.key}" type="button">${allOn ? "Clear" : "All"}</button>
        </div>
        <div class="mode-chip-row">
          ${groupModes
            .map(
              (m) => `
              <button class="mode-chip ${state.selectedModes.has(m) ? "is-active" : ""}" data-mode="${escapeHtml(m)}" type="button" title="${escapeHtml(modeLabel(m))}">
                <span class="mode-chip-label">${escapeHtml(modeLabel(m))}</span>
                ${sourceChips(m, { dim: true })}
              </button>`
            )
            .join("")}
        </div>
      </div>`;
  }).join("");

  node.querySelectorAll("[data-mode]").forEach((n) =>
    n.addEventListener("click", () => {
      const v = n.getAttribute("data-mode");
      if (state.selectedModes.has(v)) state.selectedModes.delete(v);
      else state.selectedModes.add(v);
      render();
    })
  );
  node.querySelectorAll("[data-mode-group]").forEach((n) =>
    n.addEventListener("click", () => {
      const key = n.getAttribute("data-mode-group");
      const gm = modesInGroup(modes, key);
      const allOn = gm.every((m) => state.selectedModes.has(m));
      gm.forEach((m) => (allOn ? state.selectedModes.delete(m) : state.selectedModes.add(m)));
      render();
    })
  );
}

function companyModeGroupsHtml(company) {
  const modes = (company.benchmarkModes || []).map((m) => m.modeId);
  const rows = MODE_GROUPS.map((grp) => {
    const gm = modesInGroup(modes, grp.key);
    if (!gm.length) return "";
    return `
      <div class="cc-mg-row">
        <span class="cc-mg-label">${escapeHtml(grp.label)}<small>${gm.length}</small></span>
        <span class="cc-mg-chips">${gm.map((m) => `<span class="mini-chip" title="${escapeHtml(m)}">${escapeHtml(modeLabel(m))}</span>`).join("")}</span>
      </div>`;
  }).join("");
  return `<div class="cc-modegroups">${rows || `<div class="empty compact">No benchmark modes.</div>`}</div>`;
}

function companyTasksHtml(company) {
  const tasks = company.tasks || [];
  if (!tasks.length) return `<div class="empty compact">No tasks listed for this company.</div>`;
  return `<div class="cc-task-list">${tasks
    .map(
      (t) => `
      <div class="cc-task">
        <div class="cc-task-top">
          <strong>${escapeHtml(t.name || t.taskId)}</strong>
          <span class="surface">${escapeHtml(t.riskClass || "read")}</span>
        </div>
        <p>${escapeHtml(t.prompt || "")}</p>
        <div class="cc-task-meta">
          ${sourceChipsFromKeys(t.expectedSurfaces)}
          <span class="mono">${escapeHtml(t.taskId || "")}</span>
        </div>
        ${t.successCriteria ? `<div class="success-criteria">${escapeHtml(t.successCriteria)}</div>` : ""}
      </div>`
    )
    .join("")}</div>`;
}

// Apply the companies-tab search / source / sort controls.
function filteredCompanies() {
  const { search, sources, sort } = state.companyFilter;
  const q = search.trim().toLowerCase();
  let list = state.companies.filter((company) => {
    if (q) {
      const hay = `${company.name || ""} ${company.projectId || ""} ${company.description || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (sources.size) {
      const keys = new Set(companySourceKeys(company));
      for (const s of sources) if (!keys.has(s)) return false;
    }
    return true;
  });
  const taskCount = (c) => Number(c.taskCount || (c.tasks || []).length || 0);
  const modeCount = (c) => (c.benchmarkModes || []).length;
  list = list.slice().sort((a, b) => {
    if (sort === "tasks") return taskCount(b) - taskCount(a) || String(a.name).localeCompare(String(b.name));
    if (sort === "modes") return modeCount(b) - modeCount(a) || String(a.name).localeCompare(String(b.name));
    if (sort === "selected") {
      const sa = state.selectedProjects.has(a.projectId) ? 0 : 1;
      const sb = state.selectedProjects.has(b.projectId) ? 0 : 1;
      return sa - sb || String(a.name).localeCompare(String(b.name));
    }
    return String(a.name).localeCompare(String(b.name));
  });
  return list;
}

function renderCompanySourceFilter() {
  const node = el("companySourceFilter");
  if (!node) return;
  const activeCount = state.companyFilter.sources.size;
  const label = `<span class="csf-label" title="A company must expose every selected surface to match">Has all${activeCount ? ` (${activeCount})` : ""}:</span>`;
  node.innerHTML =
    label +
    SOURCES.map(
      (s) => `<button class="csf-chip src-${s.token} ${state.companyFilter.sources.has(s.key) ? "is-active" : ""}" data-source-filter="${s.key}" type="button"><span class="csf-dot"></span>${escapeHtml(s.short)}</button>`
    ).join("");
  node.querySelectorAll("[data-source-filter]").forEach((n) =>
    n.addEventListener("click", () => {
      const key = n.getAttribute("data-source-filter");
      if (state.companyFilter.sources.has(key)) state.companyFilter.sources.delete(key);
      else state.companyFilter.sources.add(key);
      renderCompanies();
    })
  );
}

function renderCompanies() {
  renderCompanySourceFilter();
  const search = el("companySearch");
  if (search && search.value !== state.companyFilter.search) search.value = state.companyFilter.search;
  const sort = el("companySort");
  if (sort) sort.value = state.companyFilter.sort;

  const companies = filteredCompanies();
  const countNode = el("companyFilterCount");
  if (countNode) {
    countNode.textContent =
      companies.length === state.companies.length
        ? `${state.companies.length} companies`
        : `${companies.length} of ${state.companies.length}`;
  }

  const html = companies
    .map((company) => {
      const selected = state.selectedProjects.has(company.projectId);
      const expanded = state.expandedCompanies.has(company.projectId);
      const modeCount = (company.benchmarkModes || []).length;
      const taskCount = Number(company.taskCount || (company.tasks || []).length || 0);
      return `
        <article class="company-card2 ${selected ? "is-selected" : ""}">
          <div class="cc-head">
            <button class="cc-select" data-project="${escapeHtml(company.projectId)}" type="button" aria-pressed="${selected}">
              <span class="cc-check" aria-hidden="true"></span>
              <span class="cc-title-wrap">
                <span class="card-title">${escapeHtml(company.name)}</span>
                <span class="card-id">${escapeHtml(company.projectId)}</span>
              </span>
            </button>
            <div class="cc-badges">
              <span class="badge">${taskCount} task${taskCount === 1 ? "" : "s"}</span>
            </div>
          </div>
          ${(() => {
            const desc = meaningfulDescription(company.description);
            return desc ? `<p class="card-desc">${escapeHtml(desc)}</p>` : "";
          })()}
          <div class="cc-foot">
            <div class="cc-sources">
              ${sourceChipsFromKeys(companySourceKeys(company), { showAll: true })}
              ${company.authRequired ? `<span class="surface">auth</span>` : ""}
            </div>
            <span class="cc-modecount">${modeCount} mode${modeCount === 1 ? "" : "s"}</span>
          </div>
          <button class="cc-inspect ${expanded ? "is-open" : ""}" data-inspect="${escapeHtml(company.projectId)}" type="button">
            ${expanded ? "Hide details" : `Inspect ${taskCount} task${taskCount === 1 ? "" : "s"}`}
            <span class="cc-caret" aria-hidden="true">▾</span>
          </button>
          ${
            expanded
              ? `<div class="cc-expand-body">
                  <div class="cc-modes-wrap">
                    <span class="cc-sub">Benchmark modes</span>
                    ${companyModeGroupsHtml(company)}
                  </div>
                  <div>
                    <span class="cc-sub">Tasks</span>
                    ${companyTasksHtml(company)}
                  </div>
                </div>`
              : ""
          }
        </article>`;
    })
    .join("");
  el("companiesGrid").innerHTML = html || `<div class="empty">No demo companies match the current filters.</div>`;

  document.querySelectorAll("[data-project]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-project");
      if (state.selectedProjects.has(value)) state.selectedProjects.delete(value);
      else state.selectedProjects.add(value);
      render();
    });
  });
  document.querySelectorAll("[data-inspect]").forEach((node) => {
    node.addEventListener("click", () => {
      const value = node.getAttribute("data-inspect");
      if (state.expandedCompanies.has(value)) state.expandedCompanies.delete(value);
      else state.expandedCompanies.add(value);
      renderCompanies();
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

// When a phase is selected, the pass/fail status filter applies to that phase
// instead of the overall run, so you can isolate (say) every eval whose Solution
// Discovery failed. Selecting the execution phase also hides non-applicable evals.
function phasePassed(run, phase) {
  switch (phase) {
    case "task":
      return Boolean(run.taskDiscoveryPassed);
    case "solution":
      return Boolean(run.solutionDiscoveryPassed);
    case "execution":
      return Boolean(run.agentExecutionPassed);
    default:
      return Boolean(run.passed);
  }
}

function filteredRuns() {
  const phase = state.filters.phase || "";
  return state.runs.filter((run) => {
    if (state.filters.group && run.runGroupId !== state.filters.group) return false;
    if (state.filters.harvester && run.harvesterName !== state.filters.harvester) return false;
    if (state.filters.project && run.projectId !== state.filters.project) return false;
    if (state.filters.mode && String(run.mode || "") !== state.filters.mode) return false;
    if (phase === "execution" && !run.agentExecutionApplicable) return false;
    if (state.filters.status === "pass" && !phasePassed(run, phase)) return false;
    if (state.filters.status === "fail" && phasePassed(run, phase)) return false;
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
      `<option value="${escapeHtml(group.runGroupId)}">${escapeHtml(runGroupLabel(group))} · ${pct(group.avgScore)}</option>`
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
  const phase = el("filterPhase");
  if (phase) phase.value = state.filters.phase || "";

  // Surface how many filters are active on the collapsed <details> summary.
  const activeCount = Object.values(state.filters).filter(Boolean).length;
  const badge = el("filtersActive");
  if (badge) {
    badge.hidden = activeCount === 0;
    badge.textContent = `${activeCount} active`;
  }
  const panel = el("filtersPanel");
  if (panel && activeCount && !panel.open) panel.open = true;
}

function renderLatestRuns() {
  const html = state.runs
    .slice(0, 14)
    .map(
      (run) => `
        <button class="run-card" data-expand="${escapeHtml(run.runId)}" type="button">
          <div class="run-line">
            <strong>${escapeHtml(run.projectName || run.projectId)}</strong>
            <span class="${statusClass(run)}" title="${escapeHtml(run.status === "failed" ? "The evaluation errored" : run.passed ? "Passed the score threshold" : GLOSSARY.needsWork)}">${run.status === "failed" ? "fail" : run.passed ? "pass" : "needs work"}</span>
          </div>
          <div class="run-meta mono">
            <span>${escapeHtml(harvesterLabel(run.harvesterName))}</span>
            <span>${escapeHtml(modeLabel(run.mode))}</span>
            <span class="run-score">${pct(run.score)}</span>
          </div>
        </button>`
    )
    .join("");
  el("latestRuns").innerHTML = html || `<div class="empty">${state.loading ? "Loading..." : "No runs yet."}</div>`;
}

function scoreCell(value, passed) {
  const width = Math.round(clamp01(value) * 100);
  return `
    <div class="score-cell">
      <span class="mono">${pct(value)}</span>
      <span class="score-track"><i class="score-fill ${passed ? "" : "warn"}" style="width:${width}%"></i></span>
    </div>`;
}

function phaseCell(score, passed, meta = "") {
  const width = Math.round(clamp01(score) * 100);
  return `
    <div class="phase-cell ${passed ? "pass" : "fail"}">
      <strong>${pct(score)}</strong>
      <span class="pc-mini"><i class="pc-fill" style="width:${width}%"></i></span>
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
              <td class="mono">${escapeHtml(harvesterLabel(run.harvesterName))}</td>
              <td>${escapeHtml(modeLabel(run.mode))}</td>
              <td>${phaseCell(run.taskRecall, run.taskDiscoveryPassed, `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} matched`)}</td>
              <td>${phaseCell(run.solutionScore, run.solutionDiscoveryPassed, `${Number(run.solutionCount || 0)} plans`)}</td>
              <td>${run.agentExecutionApplicable ? phaseCell(run.agentExecutionScore, run.agentExecutionPassed, "agent exec") : `<span class="phase-na">n/a</span>`}</td>
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
            ${(() => {
              const applicable = runs.filter((run) => run.agentExecutionApplicable);
              return metric("Agent exec", applicable.length ? pct(avg(applicable, (run) => run.agentExecutionScore)) : "n/a");
            })()}
          </div>
          <div class="mini-table-wrap">
            <table class="mini-table">
              <thead>
                <tr>
                  <th>Harvester</th>
                  <th>Mode</th>
                  <th>Tasks</th>
                  <th>Solutions</th>
                  <th>Agent exec</th>
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
      <div class="summary-pill hero">
        <div class="eyebrow">Run group</div>
        <h2>${escapeHtml(shortId(group.runGroupId))}</h2>
        <div class="card-id">${escapeHtml(group.runGroupId)}</div>
      </div>
      <div class="summary-pill"><span>${group.total}</span><small>runs</small></div>
      <div class="summary-pill"><span>${group.passed}/${group.total}</span><small>pass</small></div>
      <div class="summary-pill"><span>${pct(group.avgScore)}</span><small>overall</small></div>
      <div class="summary-pill"><span>${pct(group.avgTaskRecall)}</span><small>task recall</small></div>
      <div class="summary-pill"><span>${pct(group.avgSolutionScore)}</span><small>solution</small></div>
    </div>
    <div class="group-cards">${projectCards}</div>`;
}

function gapsListHtml(gapRuns) {
  if (!gapRuns.length) return `<div class="empty compact">No gaps in this run group.</div>`;
  return `
    <div class="gaps-list">
      ${gapRuns
        .map(
          (run) => `
            <div class="gap-row">
              <div>
                <strong>${escapeHtml(run.projectName || run.projectId)}</strong>
                <span>${escapeHtml(harvesterLabel(run.harvesterName))} · ${escapeHtml(modeLabel(run.mode))}</span>
              </div>
              <div class="gap-tags">
                ${(run.missing || []).length ? `<span class="status">${(run.missing || []).length} missing</span>` : ""}
                ${(run.taskExtraTaskNames || []).length ? `<span class="status">${(run.taskExtraTaskNames || []).length} extra tasks</span>` : ""}
              </div>
            </div>`
        )
        .join("")}
    </div>`;
}

function failedEvalsHtml(runs) {
  const failed = runs.filter((r) => r.status === "failed" || (r.error && String(r.error).trim()));
  if (!failed.length) return "";
  return rgSection(
    "Failed evaluations",
    `${failed.length} eval${failed.length === 1 ? "" : "s"} returned an error`,
    `<div class="failed-list">
      ${failed
        .map((r) => {
          const { summary, detail } = humanizeError(r.error);
          return `
        <div class="failed-row">
          <div class="failed-head">
            <strong>${escapeHtml(r.projectName || r.projectId)}</strong>
            <span class="failed-meta">${escapeHtml(harvesterLabel(r.harvesterName))} · ${escapeHtml(modeLabel(r.mode))}</span>
            ${sourceChips(r.mode, { dim: true })}
          </div>
          <p class="failed-summary">${escapeHtml(summary)}</p>
          ${
            detail
              ? `<details class="failed-detail"><summary>Technical detail</summary><code class="failed-error">${escapeHtml(detail)}</code></details>`
              : ""
          }
        </div>`;
        })
        .join("")}
    </div>`
  );
}

function runGroupDetailAnalysisHtml(runs) {
  const summary = summarizeRuns(runs);
  const completed = runs.filter((r) => r.status === "completed");
  const harvesterCompare = dimensionStats(completed, "harvesterName", (id) => harvesterLabel(id));
  const companyCompare = dimensionStats(completed, "projectId", (id, items) => items[0]?.projectName || id);
  const modeCompare = dimensionStats(completed, "mode", (id) => modeLabel(id));
  const gapRuns = runs.filter((run) => (run.missing || []).length || (run.taskExtraTaskNames || []).length);
  const points = completed.map((r) => ({
    x: r.taskRecall,
    y: r.solutionScore,
    passed: r.passed,
    label: `${r.projectName || r.projectId} · ${harvesterLabel(r.harvesterName)} · ${modeLabel(r.mode)}`,
  }));

  const phaseChart = `
    <div class="bar-chart">
      ${bar("Task recall", summary.taskRecall, { colorByGrade: true })}
      ${bar("Task precis.", summary.taskPrecision, { colorByGrade: true })}
      ${bar("Solution", summary.solutionScore, { colorByGrade: true })}
      ${summary.executionApplicable ? bar("Agent exec", summary.executionScore, { colorByGrade: true }) : ""}
    </div>`;

  // The scatter needs a few points to read as a distribution. For tiny groups
  // (a single eval) it looks broken, so we swap in a compact eval snapshot.
  const rightBlock =
    points.length >= 3
      ? rgSection("Task vs solution discovery", "one dot per eval cell", scatterChart(points))
      : rgSection(
          "Evaluation snapshot",
          `${completed.length} completed eval${completed.length === 1 ? "" : "s"}`,
          evalSnapshotHtml(completed)
        );

  // Harvester + company comparisons only earn a full row each when there's more
  // than one to rank; otherwise pair them so the layout stays dense.
  const bothSingle = harvesterCompare.length <= 1 && companyCompare.length <= 1;
  const harvesterSection = rgSection(
    "Score by harvester",
    `${harvesterCompare.length} harvester${harvesterCompare.length === 1 ? "" : "s"} ranked`,
    compareChart(harvesterCompare, "No completed evals.")
  );
  const companySection = rgSection(
    "Score by demo company",
    `${companyCompare.length} compan${companyCompare.length === 1 ? "y" : "ies"} ranked`,
    compareChart(companyCompare, "No completed evals.")
  );

  return `
    ${failedEvalsHtml(runs)}
    <div class="rg-two">
      ${rgSection("Phase performance", "average across all evaluations", phaseChart)}
      ${rightBlock}
    </div>
    ${
      bothSingle
        ? `<div class="rg-two">${harvesterSection}${companySection}</div>`
        : `${harvesterSection}${companySection}`
    }
    ${rgSection(
      "Score by source mode",
      `${modeCompare.length} mode${modeCompare.length === 1 ? "" : "s"} ranked`,
      compareChart(modeCompare, "No completed evals.", { chips: (item) => sourceChips(item.id, { dim: true }) })
    )}
    ${gapRuns.length ? rgSection("Gaps", `${gapRuns.length} evaluation${gapRuns.length === 1 ? "" : "s"} with gaps`, gapsListHtml(gapRuns)) : ""}`;
}

// Compact snapshot for tiny run groups where a scatter plot would look empty.
function evalSnapshotHtml(completed) {
  if (!completed.length) return `<div class="empty compact">No completed evals.</div>`;
  return `<div class="eval-snapshot">${completed
    .map((run) => {
      const statusLabel = run.passed ? "pass" : "needs work";
      return `
        <button class="eval-snap-row run-row" data-open-run="${escapeHtml(run.runId)}" type="button">
          <div class="eval-snap-id">
            <strong>${escapeHtml(run.projectName || run.projectId)}</strong>
            <span>${escapeHtml(harvesterLabel(run.harvesterName))} · ${escapeHtml(modeLabel(run.mode))}</span>
          </div>
          <div class="eval-snap-phases">
            <span class="esp"><em>Task</em><b class="${gradeClass(run.taskRecall)}">${pct(run.taskRecall)}</b></span>
            <span class="esp"><em>Sol.</em><b class="${gradeClass(run.solutionScore)}">${pct(run.solutionScore)}</b></span>
            <span class="esp"><em>Agent</em><b class="${run.agentExecutionApplicable ? gradeClass(run.agentExecutionScore) : ""}">${run.agentExecutionApplicable ? pct(run.agentExecutionScore) : "n/a"}</b></span>
          </div>
          <div class="eval-snap-right">
            <span class="${run.passed ? "status pass" : "status"}">${statusLabel}</span>
            <b class="eval-snap-score ${gradeClass(run.score)}">${pct(run.score)}</b>
          </div>
        </button>`;
    })
    .join("")}</div>`;
}

function resultRowsHtml(runs) {
  return runs
    .map((run) => {
      const missing = run.missing || [];
      return `
        <tr class="run-row" data-open-run="${escapeHtml(run.runId)}" tabindex="0" role="link">
          <td><strong>${escapeHtml(run.projectName || run.projectId)}</strong><div class="card-id">${escapeHtml(run.projectId)}</div></td>
          <td class="mono">${escapeHtml(harvesterLabel(run.harvesterName))}</td>
          <td>${escapeHtml(modeLabel(run.mode))}</td>
          <td>${scoreCell(run.score, run.passed)}</td>
          <td>${phaseCell(run.taskRecall, run.taskDiscoveryPassed, `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} matched`)}</td>
          <td>${phaseCell(run.solutionScore, run.solutionDiscoveryPassed, `${Number(run.solutionCount || 0)} deliverables`)}</td>
          <td>${
            run.agentExecutionApplicable
              ? phaseCell(run.agentExecutionScore, run.agentExecutionPassed, `${Number(run.agentExecutionExecutedTasks || 0)}/${Number(run.agentExecutionExpectedTasks || 0)} tests`)
              : `<span class="phase-na">n/a</span>`
          }</td>
          <td class="${missing.length ? "warn" : "good"}">${missing.length}</td>
          <td><span class="row-open" aria-hidden="true">Open →</span></td>
        </tr>`;
    })
    .join("");
}

function resultsTableHtml(runs) {
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Demo company</th>
            <th>Harvester</th>
            <th title="${escapeHtml(GLOSSARY.sourceMode)}">Mode</th>
            <th>Score</th>
            <th title="${escapeHtml(GLOSSARY.taskRecall)}">Task discovery</th>
            <th title="${escapeHtml(GLOSSARY.solution)}">Solution discovery</th>
            <th title="${escapeHtml(GLOSSARY.agentExec)}">Agent execution</th>
            <th title="${escapeHtml(GLOSSARY.gaps)}">Gaps</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${resultRowsHtml(runs)}</tbody>
      </table>
    </div>`;
}

// ----- single-eval detail building blocks (shared across its sub-tabs) -----

function runHero(run) {
  const statusLabel = run.passed ? "pass" : run.status === "failed" ? "fail" : "needs work";
  return `
    <div class="rd-hero">
      <div class="rd-hero-id">
        <div class="eyebrow">Evaluation</div>
        <h3>${escapeHtml(run.projectName || run.projectId)}</h3>
        <div class="rd-hero-meta">
          <span class="surface">${escapeHtml(harvesterLabel(run.harvesterName))}</span>
          <span class="surface">${escapeHtml(modeLabel(run.mode))}</span>
          <span class="${statusClass(run)}">${statusLabel}</span>
        </div>
        <div class="rd-sources">
          <span class="cc-sub">Input sources</span>
          ${sourceChips(run.mode)}
        </div>
      </div>
      ${scoreRing(run.score, { label: "overall", size: 112 })}
    </div>`;
}

function runPhaseScores(run) {
  const taskMissing = run.taskMissingTaskIds || [];
  const taskExtra = run.taskExtraTaskNames || [];
  const solutionMissing = run.solutionMissingTaskIds || [];
  const solutionIncomplete = run.solutionIncompleteTaskIds || [];
  const originGaps =
    (run.solutionInvalidOriginIds || []).length +
    (run.solutionHallucinatedToolNames || []).length +
    (run.solutionHallucinatedConnectorIds || []).length;
  return rgSection(
    "Phase scores",
    "task discovery · solution discovery · agent execution",
    `<div class="phase-detail-grid">
      ${phaseDetailCard("Task discovery", run.taskDiscoveryPassed, run.taskRecall, [
        ["Matched", `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)}`],
        ["Precision", pct(run.taskPrecision)],
        ["Missing", String(taskMissing.length)],
        ["Extra", String(taskExtra.length)],
      ])}
      ${phaseDetailCard("Solution discovery", run.solutionDiscoveryPassed, run.solutionScore, [
        ["Solutions", `${Number(run.solutionCount || 0)}/${Number(run.expectedSolutionTasks || 0)}`],
        ["Missing", String(solutionMissing.length)],
        ["Incomplete", String(solutionIncomplete.length)],
        ["Origin gaps", String(originGaps)],
      ])}
      ${executionPhaseCard(run)}
    </div>`
  );
}

function runGapsSection(run) {
  const taskMissing = run.taskMissingTaskIds || [];
  const taskExtra = run.taskExtraTaskNames || [];
  const solutionMissing = run.solutionMissingTaskIds || [];
  const solutionIncomplete = run.solutionIncompleteTaskIds || [];
  const solutionInvalidOrigins = run.solutionInvalidOriginIds || [];
  const solutionHallucinatedTools = run.solutionHallucinatedToolNames || [];
  const solutionHallucinatedConnectors = run.solutionHallucinatedConnectorIds || [];
  const solutionExtraTasks = run.solutionExtraTaskIds || [];
  const agentExecutionFailed = run.agentExecutionFailedTaskIds || [];
  const inventoryMissing = run.inventoryMissing || [];
  const hasGaps =
    taskMissing.length ||
    taskExtra.length ||
    solutionMissing.length ||
    solutionIncomplete.length ||
    solutionInvalidOrigins.length ||
    solutionHallucinatedTools.length ||
    solutionHallucinatedConnectors.length ||
    solutionExtraTasks.length ||
    agentExecutionFailed.length ||
    inventoryMissing.length;
  if (!hasGaps) return "";
  const blocks = [
    ["Missing tasks", taskMissing],
    ["Extra proposed tasks", taskExtra],
    ["Missing solutions", solutionMissing],
    ["Incomplete solutions", solutionIncomplete],
    ["Invalid origins", solutionInvalidOrigins],
    ["Hallucinated tools", solutionHallucinatedTools],
    ["Hallucinated connectors", solutionHallucinatedConnectors],
    ["Extra solution tasks", solutionExtraTasks],
    ["Execution failed tasks", agentExecutionFailed],
    ["Inventory gaps", inventoryMissing],
  ];
  const withItems = blocks.filter(([, items]) => (items || []).length);
  const clean = blocks.filter(([, items]) => !(items || []).length).map(([label]) => label.toLowerCase());
  const cleanNote = clean.length
    ? `<div class="gaps-clean"><span class="gaps-clean-ic" aria-hidden="true">✓</span>No ${clean.join(", ")}.</div>`
    : "";
  return rgSection(
    "Gaps & extras",
    "what the harvester missed or added",
    `<div class="detail-lists">
      ${withItems.map(([label, items]) => listBlock(label, items)).join("")}
    </div>
    ${cleanNote}`
  );
}

function singleRunOverview(run) {
  const err = run.error ? humanizeError(run.error) : null;
  return `
    ${runHero(run)}
    ${
      err
        ? `<div class="error-note"><strong>Evaluation error</strong><p class="failed-summary">${escapeHtml(err.summary)}</p>${
            err.detail
              ? `<details class="failed-detail"><summary>Technical detail</summary><code>${escapeHtml(err.detail)}</code></details>`
              : ""
          }</div>`
        : ""
    }
    ${runPhaseScores(run)}
    ${runGapsSection(run)}
    <div class="rd-foot">
      <span>Run <b class="mono">${escapeHtml(shortId(run.runGroupId))}</b></span>
      <span>Eval <b class="mono">${escapeHtml(shortId(run.runId))}</b></span>
      <span>Created <b>${escapeHtml(new Date(run.createdAt).toLocaleString())}</b></span>
    </div>`;
}

// Content for a single eval's sub-tab.
function singleRunTabContent(run, tab) {
  switch (tab) {
    case "task":
      return rgSection(
        "Task discovery inspection",
        `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} expected tasks matched`,
        taskDiscoveryInspectHtml(run)
      );
    case "solution":
      return rgSection(
        "Solution discovery inspection",
        "connectors · tools · trajectories · skills · agent provider",
        solutionDiscoveryInspectHtml(run)
      );
    case "execution":
      return rgSection(
        "Agent execution",
        "task tests against the demo company",
        run.agentExecutionApplicable ? agentExecutionInspectHtml(run) : executionPhaseCard(run)
      );
    case "raw":
      return rgSection(
        "Raw evaluation data",
        "summarized API payload",
        `<pre class="raw-json">${escapeHtml(JSON.stringify(run, null, 2))}</pre>`
      );
    default:
      return singleRunOverview(run);
  }
}

// Agent execution phase card: keeps the scored pass/fail view when execution
// applies, otherwise shows a neutral "not implemented" state with the reason —
// so a skipped run never reads as a perfect 100% pass.
function executionPhaseCard(run) {
  if (run.agentExecutionApplicable) {
    const passedIds = run.agentExecutionPassedTaskIds || [];
    const failedIds = run.agentExecutionFailedTaskIds || [];
    return phaseDetailCard("Agent execution", run.agentExecutionPassed, run.agentExecutionScore, [
      ["Executed", `${Number(run.agentExecutionExecutedTasks || 0)}/${Number(run.agentExecutionExpectedTasks || 0)}`],
      ["Passed", String(passedIds.length)],
      ["Failed", String(failedIds.length)],
      ["Score", pct(run.agentExecutionScore)],
    ]);
  }
  const reason = run.agentExecutionSkippedReason || "Execution tests are not implemented for this run.";
  return `
    <div class="phase-detail-card skipped">
      <div class="phase-detail-top">
        <strong>Agent execution</strong>
        <span class="phase-skip-tag">not implemented</span>
      </div>
      <p class="phase-skip-note">${escapeHtml(reason)}</p>
    </div>`;
}

function agentExecutionInspectHtml(run) {
  const results = run.agentExecutionResults || [];
  return `
    <div class="task-inspect-list">
      ${
        results.length
          ? results
              .map((result) => {
                const assertions = result.assertions || [];
                return `
                  <div class="task-inspect-card ${result.passed ? "pass" : "fail"}">
                    <div class="task-inspect-title">
                      <strong>${escapeHtml(result.taskId || "task")}</strong>
                      <span class="${result.passed ? "status pass" : "status"}">${result.passed ? "passed" : "failed"}</span>
                    </div>
                    <div class="task-meta-row">
                      <span>${escapeHtml(pct(result.score || 0))}</span>
                      <span>${escapeHtml(result.agentId || "")}</span>
                    </div>
                    <div class="extra-tags">${(result.executedTools || []).map((tool) => `<span class="surface">${escapeHtml(tool)}</span>`).join("")}</div>
                    <div class="assertion-list">
                      ${assertions
                        .map(
                          (assertion) => `
                            <div class="match-row">
                              <small>${escapeHtml(assertion.passed ? "pass" : "fail")}</small>
                              <b>${escapeHtml(assertion.label || "assertion")}</b>
                              <span class="mono">${escapeHtml(String(assertion.actual ?? ""))}</span>
                            </div>`
                        )
                        .join("")}
                    </div>
                    ${result.error ? `<div class="success-criteria">${escapeHtml(result.error)}</div>` : ""}
                  </div>`;
              })
              .join("")
          : `<div class="empty compact">No execution tests were run for this eval.</div>`
      }
    </div>`;
}

function findRun(runId) {
  return state.runs.find((run) => run.runId === runId) || null;
}

function findGroup(groupId) {
  return groupRuns(state.runs).find((group) => group.runGroupId === groupId) || null;
}

function breadcrumbHtml(trail) {
  // trail: [{label, route|null}] — last item is current (no link)
  return `
    <nav class="crumbs" aria-label="Breadcrumb">
      ${trail
        .map((item, i) => {
          const sep = i ? `<span class="crumb-sep">/</span>` : "";
          if (item.route) {
            return `${sep}<button class="crumb-link" data-go='${escapeHtml(JSON.stringify(item.route))}' type="button">${escapeHtml(item.label)}</button>`;
          }
          return `${sep}<span class="crumb-current">${escapeHtml(item.label)}</span>`;
        })
        .join("")}
    </nav>`;
}

function runsOverviewHtml(groups) {
  const all = groups.flatMap((g) => g.items);
  const summary = summarizeRuns(all);
  const passRate = summary.completed ? summary.passed / summary.completed : 0;
  // oldest -> newest so the sparkline reads left to right
  const trend = [...groups].reverse().map((g) => g.avgScore);
  return `
    <div class="runs-ov">
      <div class="runs-ov-rings">
        ${scoreRing(summary.score, { label: "avg score", size: 96 })}
        ${donut(summary.passed, summary.completed, { size: 96 })}
      </div>
      <div class="runs-ov-stats">
        ${statTile("Run groups", groups.length)}
        ${statTile("Evaluations", all.length)}
        ${statTile("Pass rate", pct(passRate), { info: GLOSSARY.passRate })}
        ${statTile("Gaps", summary.gaps, { info: GLOSSARY.gaps, ...(summary.gaps ? { tone: "warn" } : {}) })}
      </div>
      <div class="runs-ov-trend">
        <div class="rot-head"><span>Score by run group</span><b>${pct(summary.score)}</b></div>
        <div class="rot-spark">${sparkline(trend.length > 1 ? trend : [summary.score, summary.score], { stroke: "#1f2937", title: "Average score of each run group, oldest → newest" })}</div>
        <div class="rot-foot"><span>oldest</span><span>newest</span></div>
      </div>
    </div>`;
}

function renderRunsListView() {
  const runs = filteredRuns();
  const groups = groupRuns(runs);
  el("emptyResults").hidden = groups.length > 0;
  el("emptyResults").textContent = state.runs.length
    ? "No run groups match the current filters."
    : `No run groups returned by ${state.apiUrl}. Reload or run one of the presets.`;

  const overview = el("runsOverview");
  if (overview) {
    overview.hidden = groups.length === 0;
    overview.innerHTML = groups.length ? runsOverviewHtml(groups) : "";
  }

  el("runGroupsList").innerHTML = groups
    .map((group) => {
      const harvesters = new Set(group.items.map((run) => run.harvesterName));
      const companies = new Set(group.items.map((run) => run.projectId));
      const modes = new Set(group.items.map((run) => String(run.mode || "")));
      const summary = summarizeRuns(group.items);
      const passTone = summary.completed && summary.passed === summary.completed ? "good" : summary.passed ? "" : "warn";
      return `
        <article class="run-group-card">
          <button class="run-group-main" data-open-group="${escapeHtml(group.runGroupId)}" type="button">
            <div class="rgc-id">
              <div class="eyebrow">Run</div>
              <h3>${escapeHtml(runGroupLabel(group))}</h3>
              <span class="rgc-date">${escapeHtml(new Date(group.createdAt).toLocaleString())} · <span class="mono rgc-hash">${escapeHtml(shortId(group.runGroupId))}</span></span>
              <div class="rgc-chips">
                <span class="surface">${group.total} eval${group.total === 1 ? "" : "s"}</span>
                <span class="surface">${harvesters.size} harvester${harvesters.size === 1 ? "" : "s"}</span>
                <span class="surface">${companies.size} compan${companies.size === 1 ? "y" : "ies"}</span>
                <span class="surface">${modes.size} mode${modes.size === 1 ? "" : "s"}</span>
                ${summary.failed ? `<span class="surface bad">${summary.failed} failed</span>` : ""}
              </div>
            </div>
            <div class="rgc-mid">
              <div class="rgc-bars">
                ${miniBar("Task discovery", summary.taskRecall)}
                ${miniBar("Solution discovery", summary.solutionScore)}
                ${
                  summary.executionApplicable
                    ? miniBar("Agent execution", summary.executionScore)
                    : `<div class="mini-bar mini-bar-na"><span class="mb-label">Agent execution</span><span class="mb-na">n/a</span></div>`
                }
              </div>
            </div>
            <div class="rgc-pass ${passTone}">
              <strong>${summary.passed}/${summary.completed || group.total}</strong>
              <small>passed</small>
              ${summary.executionApplicable ? `<span class="rgc-pass-sub">exec ${summary.executionPassed}/${summary.executionApplicable}</span>` : ""}
            </div>
            ${scoreRing(group.avgScore, { size: 66, stroke: 8 })}
            <span class="run-group-open" aria-hidden="true">Open →</span>
          </button>
        </article>`;
    })
    .join("");

  document.querySelectorAll("[data-open-group]").forEach((node) => {
    node.addEventListener("click", () => {
      go({ tab: "runs", group: node.getAttribute("data-open-group") });
    });
  });
}

/* ---------- run detail sub-tabs ---------- */

const RUN_GROUP_TABS = [
  { key: "overview", label: "Overview" },
  { key: "companies", label: "Companies" },
  { key: "harvesters", label: "Harvesters" },
  { key: "task", label: "Task Discovery" },
  { key: "solution", label: "Solution Discovery" },
  { key: "execution", label: "Agent Execution" },
  { key: "raw", label: "Raw Data" },
];
const SINGLE_RUN_TABS = [
  { key: "overview", label: "Overview" },
  { key: "task", label: "Task Discovery" },
  { key: "solution", label: "Solution Discovery" },
  { key: "execution", label: "Agent Execution" },
  { key: "raw", label: "Raw Data" },
];

function detailSubtabs(tabs, active) {
  return `<div class="subtabs" role="tablist">${tabs
    .map(
      (t) =>
        `<button class="subtab ${t.key === active ? "is-active" : ""}" data-detail-tab="${t.key}" type="button" role="tab" aria-selected="${t.key === active}">${escapeHtml(t.label)}</button>`
    )
    .join("")}</div>`;
}

function resolveDetailTab(tabs) {
  return tabs.some((t) => t.key === state.detailTab) ? state.detailTab : "overview";
}

function groupBy(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }
  return map;
}

// Compact harvester × mode × phase table for one company / harvester slice.
function evalMiniTable(runs) {
  const rows = runs
    .map(
      (run) => `
        <tr class="run-row" data-open-run="${escapeHtml(run.runId)}" tabindex="0" role="link">
          <td class="mono">${escapeHtml(harvesterLabel(run.harvesterName))}</td>
          <td>${escapeHtml(modeLabel(run.mode))}</td>
          <td>${phaseCell(run.taskRecall, run.taskDiscoveryPassed, `${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)}`)}</td>
          <td>${phaseCell(run.solutionScore, run.solutionDiscoveryPassed, `${Number(run.solutionCount || 0)} plans`)}</td>
          <td>${
            run.agentExecutionApplicable
              ? phaseCell(run.agentExecutionScore, run.agentExecutionPassed, `${Number(run.agentExecutionExecutedTasks || 0)}/${Number(run.agentExecutionExpectedTasks || 0)}`)
              : `<span class="phase-na">n/a</span>`
          }</td>
          <td><span class="${run.passed ? "status pass" : run.status === "failed" ? "status fail" : "status"}">${run.status === "failed" ? "fail" : run.passed ? "pass" : "needs work"}</span></td>
        </tr>`
    )
    .join("");
  return `
    <div class="mini-table-wrap">
      <table class="mini-table">
        <thead>
          <tr><th>Harvester</th><th>Mode</th><th>Task</th><th>Solution</th><th>Agent exec</th><th>Status</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// Collapsible per-eval card used inside the phase tabs.
function evalAccordion(run, scoreVal, scoreLabel, body) {
  const statusLabel = run.status === "failed" ? "fail" : run.passed ? "pass" : "needs work";
  return `
    <details class="eval-acc">
      <summary>
        <span class="eval-acc-main">
          <strong>${escapeHtml(run.projectName || run.projectId)}</strong>
          <span class="eval-acc-meta">${escapeHtml(harvesterLabel(run.harvesterName))} · ${escapeHtml(modeLabel(run.mode))}</span>
        </span>
        <span class="eval-acc-right">
          <span class="eval-acc-score ${gradeClass(scoreVal)}"><b>${pct(scoreVal)}</b><em>${escapeHtml(scoreLabel)}</em></span>
          <span class="${statusClass(run)}">${statusLabel}</span>
          <span class="eval-acc-caret" aria-hidden="true">▾</span>
        </span>
      </summary>
      <div class="eval-acc-body">${body}</div>
    </details>`;
}

// Ranked bar list for one numeric field of dimensionStats output.
function phaseRankList(stats, key) {
  if (!stats.length) return `<div class="empty compact">No data.</div>`;
  return `<div class="bar-chart">${stats
    .slice()
    .sort((a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0))
    .map((s) => bar(s.label, s[key], { colorByGrade: true }))
    .join("")}</div>`;
}

/* ---------- run group detail tabs ---------- */

function groupOverviewTab(runs) {
  // The full per-cell table can be dozens of rows — keep the Overview digestible
  // by collapsing it behind a details toggle (and pointing at the phase tabs).
  const tableSection = `
    <section class="rg-section">
      <details class="all-evals" ${runs.length <= 12 ? "open" : ""}>
        <summary>
          <span class="all-evals-title">All evaluations</span>
          <span class="all-evals-sub">${runs.length} eval cell${runs.length === 1 ? "" : "s"} · click a row for detail</span>
          <span class="all-evals-caret" aria-hidden="true">▾</span>
        </summary>
        <div class="all-evals-body">${resultsTableHtml(runs)}</div>
      </details>
    </section>`;
  return `
    ${runGroupDetailAnalysisHtml(runs)}
    ${tableSection}`;
}

function groupCompaniesTab(runs) {
  const completed = runs.filter((r) => r.status === "completed");
  const compare = dimensionStats(completed, "projectId", (id, items) => items[0]?.projectName || id);
  const byProject = groupBy(runs, (r) => r.projectId || "unknown");
  const cards = [...byProject.entries()]
    .map(([projectId, items]) => {
      const company = state.companies.find((c) => c.projectId === projectId);
      const name = items[0]?.projectName || projectId;
      const s = summarizeRuns(items);
      const taskCount = company ? Number(company.taskCount || (company.tasks || []).length || 0) : 0;
      return `
        <article class="group-card">
          <div class="group-card-head">
            <div>
              <h3>${escapeHtml(name)}</h3>
              <div class="card-id">${escapeHtml(projectId)}</div>
            </div>
            <span class="${s.completed && s.passed === s.completed ? "status pass" : "status"}">${s.passed}/${s.completed || items.length} pass</span>
          </div>
          ${
            company
              ? `<div class="cc-sources"><span class="cc-sub">Sources</span>${sourceChipsFromKeys(companySourceKeys(company), { showAll: true })}${company.authRequired ? `<span class="surface">auth</span>` : ""}</div>`
              : `<div class="empty compact">Company metadata not loaded.</div>`
          }
          <div class="phase-grid">
            ${metric("Evals", String(items.length))}
            ${metric("Score", pct(s.score))}
            ${metric("Task recall", pct(s.taskRecall))}
            ${metric("Solution", pct(s.solutionScore))}
            ${metric("Agent exec", s.executionApplicable ? pct(s.executionScore) : "n/a")}
          </div>
          ${company ? `<div class="cc-modes-wrap"><span class="cc-sub">Benchmark modes</span>${companyModeGroupsHtml(company)}</div>` : ""}
          ${evalMiniTable(items)}
          ${
            company
              ? `<details class="eval-acc"><summary><span class="eval-acc-main"><strong>Tasks</strong><span class="eval-acc-meta">${taskCount} benchmark task${taskCount === 1 ? "" : "s"}</span></span><span class="eval-acc-right"><span class="eval-acc-caret" aria-hidden="true">▾</span></span></summary><div class="eval-acc-body">${companyTasksHtml(company)}</div></details>`
              : ""
          }
        </article>`;
    })
    .join("");
  return `
    ${rgSection("Score by demo company", `${compare.length} compan${compare.length === 1 ? "y" : "ies"} ranked`, compareChart(compare, "No completed evals."))}
    ${rgSection("Demo companies in this run", `${byProject.size} compan${byProject.size === 1 ? "y" : "ies"} evaluated`, `<div class="group-cards">${cards}</div>`)}`;
}

function groupHarvestersTab(runs) {
  const completed = runs.filter((r) => r.status === "completed");
  const compare = dimensionStats(completed, "harvesterName", (id) => harvesterLabel(id));
  const byHarvester = groupBy(runs, (r) => r.harvesterName || "unknown");
  const cards = [...byHarvester.entries()]
    .map(([harvester, items]) => {
      const s = summarizeRuns(items);
      return `
        <article class="group-card">
          <div class="group-card-head">
            <div>
              <h3>${escapeHtml(harvesterLabel(harvester))}</h3>
              <div class="card-id">${escapeHtml(harvester)}</div>
            </div>
            ${scoreRing(s.score, { size: 58, stroke: 7 })}
          </div>
          <div class="bar-chart">
            ${bar("Task discovery", s.taskRecall, { colorByGrade: true })}
            ${bar("Solution discovery", s.solutionScore, { colorByGrade: true })}
            ${s.executionApplicable ? bar("Agent execution", s.executionScore, { colorByGrade: true }) : ""}
          </div>
          <div class="phase-grid">
            ${metric("Evals", String(items.length))}
            ${metric("Pass rate", `${s.passed}/${s.completed || items.length}`)}
            ${metric("Precision", pct(s.taskPrecision))}
            ${metric("Agent exec", s.executionApplicable ? `${s.executionPassed}/${s.executionApplicable}` : "n/a")}
          </div>
          ${evalMiniTable(items)}
        </article>`;
    })
    .join("");
  return `
    ${rgSection("Score by harvester", `${compare.length} harvester${compare.length === 1 ? "" : "s"} ranked`, compareChart(compare, "No completed evals."))}
    ${rgSection("Per-harvester breakdown", `${byHarvester.size} harvester${byHarvester.size === 1 ? "" : "s"} evaluated`, `<div class="group-cards">${cards}</div>`)}`;
}

function groupTaskTab(runs) {
  const completed = runs.filter((r) => r.status === "completed");
  const summary = summarizeRuns(completed);
  const matched = completed.reduce((a, r) => a + Number(r.matchedTasks || 0), 0);
  const expected = completed.reduce((a, r) => a + Number(r.expectedTasks || 0), 0);
  const missing = completed.reduce((a, r) => a + (r.taskMissingTaskIds || []).length, 0);
  const extra = completed.reduce((a, r) => a + (r.taskExtraTaskNames || []).length, 0);
  const byCompany = dimensionStats(completed, "projectId", (id, items) => items[0]?.projectName || id);
  const byHarvester = dimensionStats(completed, "harvesterName", (id) => harvesterLabel(id));
  const stats = `
    <div class="phase-grid">
      ${metric("Recall", pct(summary.taskRecall))}
      ${metric("Precision", pct(summary.taskPrecision))}
      ${metric("Matched", `${matched}/${expected}`)}
      ${metric("Missing", String(missing))}
      ${metric("Extra", String(extra))}
    </div>`;
  const perEval =
    completed.map((run) => evalAccordion(run, run.taskRecall, "task recall", taskDiscoveryInspectHtml(run))).join("") ||
    `<div class="empty compact">No completed evals.</div>`;
  return `
    ${rgSection("Task discovery summary", "expected vs discovered tasks across all evals", stats)}
    ${rgSection("Recall by demo company", "", phaseRankList(byCompany, "taskRecall"))}
    ${rgSection("Recall by harvester", "", phaseRankList(byHarvester, "taskRecall"))}
    ${rgSection("Per-eval inspection", `${completed.length} completed eval${completed.length === 1 ? "" : "s"}`, perEval)}`;
}

function groupSolutionTab(runs) {
  const completed = runs.filter((r) => r.status === "completed");
  const summary = summarizeRuns(completed);
  const count = (sel) => completed.reduce((a, r) => a + (r[sel] || []).length, 0);
  const solutions = completed.reduce((a, r) => a + Number(r.solutionCount || 0), 0);
  const stats = `
    <div class="phase-grid">
      ${metric("Avg score", pct(summary.solutionScore))}
      ${metric("Solutions", String(solutions))}
      ${metric("Missing", String(count("solutionMissingTaskIds")))}
      ${metric("Incomplete", String(count("solutionIncompleteTaskIds")))}
      ${metric("Halluc. tools", String(count("solutionHallucinatedToolNames")))}
      ${metric("Halluc. connectors", String(count("solutionHallucinatedConnectorIds")))}
      ${metric("Invalid origins", String(count("solutionInvalidOriginIds")))}
    </div>`;
  const perEval =
    completed.map((run) => evalAccordion(run, run.solutionScore, "solution", solutionDiscoveryInspectHtml(run))).join("") ||
    `<div class="empty compact">No completed evals.</div>`;
  return `
    ${rgSection("Solution discovery summary", "connectors · tools · trajectories · skills · agent provider", stats)}
    ${rgSection("Per-eval inspection", `${completed.length} completed eval${completed.length === 1 ? "" : "s"}`, perEval)}`;
}

function groupExecutionTab(runs) {
  const completed = runs.filter((r) => r.status === "completed");
  const applicable = completed.filter((r) => r.agentExecutionApplicable);
  const skipped = completed.filter((r) => !r.agentExecutionApplicable);
  const passedTests = applicable.reduce((a, r) => a + (r.agentExecutionPassedTaskIds || []).length, 0);
  const failedTests = applicable.reduce((a, r) => a + (r.agentExecutionFailedTaskIds || []).length, 0);
  const summary = summarizeRuns(completed);
  const stats = `
    <div class="phase-grid">
      ${metric("Applicable", String(applicable.length))}
      ${metric("Skipped", String(skipped.length))}
      ${metric("Avg score", applicable.length ? pct(summary.executionScore) : "n/a")}
      ${metric("Tests passed", String(passedTests))}
      ${metric("Tests failed", String(failedTests))}
    </div>`;
  const perEval =
    completed
      .map((run) =>
        evalAccordion(
          run,
          run.agentExecutionApplicable ? run.agentExecutionScore : 0,
          run.agentExecutionApplicable ? "exec score" : "n/a",
          run.agentExecutionApplicable ? agentExecutionInspectHtml(run) : executionPhaseCard(run)
        )
      )
      .join("") || `<div class="empty compact">No completed evals.</div>`;
  return `
    ${rgSection("Agent execution summary", "task tests executed against the demo company", stats)}
    ${rgSection("Per-eval inspection", `${completed.length} completed eval${completed.length === 1 ? "" : "s"}`, perEval)}`;
}

function groupRawTab(runs) {
  return rgSection(
    "Raw evaluation data",
    `${runs.length} eval record${runs.length === 1 ? "" : "s"} · summarized API payload`,
    `<pre class="raw-json">${escapeHtml(JSON.stringify(runs, null, 2))}</pre>`
  );
}

function runGroupTabContent(group, tab) {
  const runs = group.items;
  switch (tab) {
    case "companies":
      return groupCompaniesTab(runs);
    case "harvesters":
      return groupHarvestersTab(runs);
    case "task":
      return groupTaskTab(runs);
    case "solution":
      return groupSolutionTab(runs);
    case "execution":
      return groupExecutionTab(runs);
    case "raw":
      return groupRawTab(runs);
    default:
      return groupOverviewTab(runs);
  }
}

function renderRunGroupDetail(group) {
  const harvesters = new Set(group.items.map((run) => run.harvesterName));
  const companies = new Set(group.items.map((run) => run.projectId));
  const modes = new Set(group.items.map((run) => modeLabel(run.mode)));
  const summary = summarizeRuns(group.items);
  const active = resolveDetailTab(RUN_GROUP_TABS);
  const node = el("runDetailView");
  node.innerHTML = `
    ${breadcrumbHtml([{ label: "Runs", route: { tab: "runs" } }, { label: shortId(group.runGroupId) }])}
    <section class="panel rg-detail">
      <div class="rg-hero">
        <div class="rg-hero-id">
          <div class="eyebrow">Run</div>
          <h2>${escapeHtml(runGroupLabel(group))}</h2>
          <p class="mono crumb-id">${escapeHtml(group.runGroupId)}</p>
          <p class="rg-hero-date">${escapeHtml(new Date(group.createdAt).toLocaleString())}</p>
        </div>
        <div class="rg-hero-rings">
          ${scoreRing(group.avgScore, { label: "overall", size: 112 })}
          ${donut(summary.passed, summary.completed || group.total, { size: 112 })}
        </div>
        <div class="rg-hero-stats">
          ${statTile("Evaluations", group.total)}
          ${statTile("Harvesters", harvesters.size)}
          ${statTile("Companies", companies.size)}
          ${statTile("Modes", modes.size, { info: GLOSSARY.sourceMode })}
          ${statTile("Agent exec", summary.executionApplicable ? pct(summary.executionScore) : "n/a", { info: GLOSSARY.agentExec })}
          ${statTile("Failed", summary.failed, summary.failed ? { tone: "bad" } : {})}
        </div>
      </div>
      ${detailSubtabs(RUN_GROUP_TABS, active)}
      <div class="rg-body">${runGroupTabContent(group, active)}</div>
    </section>`;

  bindDetailNav();
  bindDetailSubtabs();
  bindOpenRun(node, (runId) => go({ tab: "runs", group: group.runGroupId, run: runId }));
}

function renderSingleRunDetail(run) {
  const node = el("runDetailView");
  const group = run.runGroupId ? { tab: "runs", group: run.runGroupId } : { tab: "runs" };
  const trail = [{ label: "Runs", route: { tab: "runs" } }];
  if (run.runGroupId) trail.push({ label: shortId(run.runGroupId), route: group });
  trail.push({ label: `${run.projectName || run.projectId} · ${harvesterLabel(run.harvesterName)}` });
  const active = resolveDetailTab(SINGLE_RUN_TABS);
  node.innerHTML = `
    ${breadcrumbHtml(trail)}
    <section class="panel">
      ${detailSubtabs(SINGLE_RUN_TABS, active)}
      <div class="panel-body run-detail-body">
        ${singleRunTabContent(run, active)}
      </div>
    </section>`;
  bindDetailNav();
  bindDetailSubtabs();
}

function bindDetailSubtabs() {
  document.querySelectorAll("[data-detail-tab]").forEach((node) => {
    node.addEventListener("click", () => {
      state.detailTab = node.getAttribute("data-detail-tab") || "overview";
      renderResults();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function bindOpenRun(node, open) {
  node.querySelectorAll("[data-open-run]").forEach((row) => {
    const fire = () => open(row.getAttribute("data-open-run"));
    row.addEventListener("click", fire);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fire();
      }
    });
  });
}

function bindDetailNav() {
  document.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      try {
        go(JSON.parse(node.getAttribute("data-go")));
      } catch {
        go({ tab: "runs" });
      }
    });
  });
}

// Router for the Runs tab: list -> group detail -> single run detail.
function renderResults() {
  const listView = el("runsListView");
  const detailView = el("runDetailView");

  const run = state.openRunId ? findRun(state.openRunId) : null;
  const group = state.openGroupId ? findGroup(state.openGroupId) : null;

  if (run) {
    listView.hidden = true;
    detailView.hidden = false;
    renderSingleRunDetail(run);
    return;
  }
  if (group) {
    listView.hidden = true;
    detailView.hidden = false;
    renderRunGroupDetail(group);
    return;
  }

  // fall back to the list (also clears a stale deep-link that no longer resolves)
  detailView.hidden = true;
  detailView.innerHTML = "";
  listView.hidden = false;
  renderRunsListView();
}

function metric(label, value, mono = false) {
  return `<div class="metric"><small>${escapeHtml(label)}</small><strong class="${mono ? "mono" : ""}">${escapeHtml(value)}</strong></div>`;
}

function miniMetric(label, value) {
  return `<span class="mini-metric"><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b></span>`;
}

function phaseDetailCard(title, passed, score, rows) {
  return `
    <div class="phase-detail-card ${passed ? "pass" : "fail"}">
      <div class="phase-detail-top">
        <strong>${escapeHtml(title)}</strong>
        <span>${pct(score)}</span>
      </div>
      <div class="phase-detail-bar"><i style="width:${Math.round(clamp01(score) * 100)}%"></i></div>
      <div class="phase-detail-metrics">
        ${rows.map(([label, value]) => miniMetric(label, value)).join("")}
      </div>
    </div>`;
}

function taskDiscoveryInspectHtml(run) {
  const tasks = run.projectTasks || [];
  const matches = run.taskDiscoveryMatches || [];
  const byTask = new Map(matches.map((match) => [match.expectedTaskId, match]));
  const extra = run.taskExtraTaskNames || [];
  return `
    <div class="task-inspect">
      <div class="task-inspect-head">
        <div>
          <h4>Demo company tasks</h4>
          <p>Expected benchmark tasks and how task discovery matched them.</p>
        </div>
        <span class="surface">${Number(run.matchedTasks || 0)}/${Number(run.expectedTasks || 0)} matched</span>
      </div>
      <div class="task-inspect-list">
        ${
          tasks.length
            ? tasks
                .map((task) => {
                  const match = byTask.get(task.taskId) || {};
                  const matched = Boolean(match.matched);
                  return `
                    <div class="task-inspect-card ${matched ? "pass" : "fail"}">
                      <div class="task-inspect-title">
                        <strong>${escapeHtml(task.name || task.taskId)}</strong>
                        <span class="${matched ? "status pass" : "status"}">${matched ? "matched" : "missing"}</span>
                      </div>
                      <p>${escapeHtml(task.prompt || "")}</p>
                      <div class="task-meta-row">
                        <span>${escapeHtml((task.expectedSurfaces || []).join(" + ") || "surface")}</span>
                        <span>${escapeHtml(task.riskClass || "read")}</span>
                        <span>${escapeHtml(task.taskId || "")}</span>
                      </div>
                      <div class="match-row">
                        <small>Discovered as</small>
                        <b>${escapeHtml(match.matchedName || "No matching discovered task")}</b>
                        <span class="mono">${pct(match.score || 0)}</span>
                      </div>
                      <div class="success-criteria">${escapeHtml(task.successCriteria || "")}</div>
                    </div>`;
                })
                .join("")
            : `<div class="empty compact">No task metadata was included for this eval.</div>`
        }
      </div>
      ${
        extra.length
          ? `<div class="extra-discovery">
              <h4>Extra discovered tasks</h4>
              <div class="extra-tags">${extra.map((item) => `<span class="surface">${escapeHtml(item)}</span>`).join("")}</div>
            </div>`
          : ""
      }
    </div>`;
}

function listBlock(label, items) {
  const values = items || [];
  const body = values.length
    ? `<div class="list-chips">${values
        .map((v) => `<span class="list-chip" title="${escapeHtml(v)}">${escapeHtml(v)}</span>`)
        .join("")}</div>`
    : `<strong>None</strong>`;
  return `
    <div class="list-block ${values.length ? "has-items" : ""}">
      <small>${escapeHtml(label)}<em class="list-count">${values.length}</em></small>
      ${body}
    </div>`;
}

function solBlock(label, body) {
  return `<div class="sol-block"><small>${escapeHtml(label)}</small><div class="sol-block-body">${body}</div></div>`;
}

function chipList(items) {
  const values = items || [];
  if (!values.length) return `<span class="sol-none">—</span>`;
  return values.map((v) => `<span class="mini-chip" title="${escapeHtml(v)}">${escapeHtml(v)}</span>`).join("");
}

function trajectoriesHtml(trajs) {
  const list = trajs || [];
  if (!list.length) return "";
  return `<div class="sol-sub"><span class="cc-sub">Trajectories</span>${list
    .map(
      (t) => `
      <div class="traj">
        <div class="traj-top">
          <strong>${escapeHtml(t.description || t.trajectoryId || "trajectory")}</strong>
          ${t.source ? `<span class="mini-chip">${escapeHtml(t.source)}</span>` : ""}
        </div>
        <div class="traj-calls">${
          (t.toolCalls || []).length
            ? (t.toolCalls || []).map((tc) => `<span class="mono">${escapeHtml(tc.toolName || "tool")}()</span>`).join(`<span class="traj-arrow">→</span>`)
            : `<span class="sol-none">no tool calls</span>`
        }</div>
      </div>`
    )
    .join("")}</div>`;
}

function skillsHtml(skills) {
  const list = skills || [];
  if (!list.length) return "";
  return `<div class="sol-sub"><span class="cc-sub">Skills</span>${list
    .map(
      (s) => `
      <div class="skill">
        <div class="traj-top">
          <strong>${escapeHtml(s.name || s.skillId || "skill")}</strong>
          ${s.source ? `<span class="mini-chip">${escapeHtml(s.source)}</span>` : ""}
        </div>
        ${s.instructions ? `<p>${escapeHtml(s.instructions)}</p>` : ""}
      </div>`
    )
    .join("")}</div>`;
}

function solutionDiscoveryInspectHtml(run) {
  const solutions = run.solutionDiscoverySolutions || [];
  const missing = new Set(run.solutionMissingTaskIds || []);
  const incomplete = new Set(run.solutionIncompleteTaskIds || []);
  if (!solutions.length && !missing.size && !incomplete.size) {
    return `<div class="empty compact">No solution discovery output for this eval.</div>`;
  }

  const cards = solutions
    .map((sol) => {
      const ap = sol.agentProvider || {};
      const status = missing.has(sol.taskId) ? "missing" : incomplete.has(sol.taskId) ? "incomplete" : "complete";
      const statusCls = status === "complete" ? "status pass" : "status";
      return `
        <div class="sol-card ${status}">
          <div class="sol-top">
            <strong class="mono">${escapeHtml(sol.taskId || "task")}</strong>
            <span class="${statusCls}">${status}</span>
          </div>
          <div class="sol-grid">
            ${solBlock("Connectors", chipList(sol.connectors))}
            ${solBlock("Tools", chipList(sol.tools))}
            ${solBlock("Trajectories", `<b class="sol-count">${(sol.trajectories || []).length}</b>`)}
            ${solBlock("Skills", `<b class="sol-count">${(sol.skills || []).length}</b>`)}
          </div>
          ${trajectoriesHtml(sol.trajectories)}
          ${skillsHtml(sol.skills)}
          <div class="sol-agent">
            <span class="cc-sub">Agent provider</span>
            <div class="sol-agent-row">
              <span class="mini-chip">runtime: ${escapeHtml(ap.runtimeKind || "—")}</span>
              <span class="mini-chip">provider: ${escapeHtml(ap.provider || "—")}</span>
              <span class="mini-chip">model: ${escapeHtml(ap.model || "default")}</span>
            </div>
            ${ap.systemPrompt ? `<div class="success-criteria">${escapeHtml(ap.systemPrompt)}</div>` : ""}
          </div>
        </div>`;
    })
    .join("");

  const solTaskIds = new Set(solutions.map((s) => s.taskId));
  const orphanMissing = [...missing].filter((id) => !solTaskIds.has(id));
  const orphanIncomplete = [...incomplete].filter((id) => !solTaskIds.has(id));

  return `
    <div class="sol-list">
      ${cards}
      ${
        orphanMissing.length
          ? `<div class="sol-flags"><span class="cc-sub">Missing solutions</span><div class="sol-block-body">${orphanMissing
              .map((id) => `<span class="mini-chip warn">${escapeHtml(id)}</span>`)
              .join("")}</div></div>`
          : ""
      }
      ${
        orphanIncomplete.length
          ? `<div class="sol-flags"><span class="cc-sub">Incomplete solutions</span><div class="sol-block-body">${orphanIncomplete
              .map((id) => `<span class="mini-chip warn">${escapeHtml(id)}</span>`)
              .join("")}</div></div>`
          : ""
      }
    </div>`;
}

/* ---------- source coverage ---------- */

function heatClass(value) {
  const n = clamp01(value);
  if (n >= 0.7) return "heat-good";
  if (n >= 0.4) return "heat-warn";
  return "heat-bad";
}

function heatCell(items) {
  if (!items.length) return `<td class="heat heat-empty" title="no evaluations">—</td>`;
  const score = avg(items, (r) => r.score);
  const passed = items.filter((r) => r.passed).length;
  return `<td class="heat ${heatClass(score)}" title="${items.length} eval${items.length === 1 ? "" : "s"} · ${passed} passed">
    <b>${pct(score)}</b><i>${items.length}×</i>
  </td>`;
}

function renderSourceSummary(completed) {
  const node = el("sourceSummary");
  if (!node) return;
  if (!completed.length) {
    node.innerHTML = "";
    return;
  }

  // Per individual source: isolated single-source capability (mode = `${source}_only`),
  // falling back to "source involved anywhere" only if it is never benchmarked alone.
  const SOURCE_NAMES = { web: "Web UI", api: "API", documents: "Documents", code: "Code" };
  const perSource = SOURCES.map((s) => {
    const solo = completed.filter((r) => String(r.mode) === `${s.key}_only`);
    const items = solo.length ? solo : completed.filter((r) => modeSources(r.mode).includes(s.key));
    return {
      ...s,
      name: SOURCE_NAMES[s.key] || s.short,
      items,
      isolated: solo.length > 0,
      score: avg(items, (r) => r.score),
      passed: items.filter((r) => r.passed).length,
    };
  });
  const ranked = [...perSource].filter((s) => s.items.length).sort((a, b) => b.score - a.score);
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];

  // Does combining sources help? Average score per source-count group.
  const groupStats = MODE_GROUPS.map((g) => {
    const items = completed.filter((r) => modeGroupKey(r.mode) === g.key);
    return { ...g, items, score: avg(items, (r) => r.score) };
  }).filter((g) => g.items.length);

  const cards = perSource
    .map((s) => {
      const has = s.items.length > 0;
      const w = Math.round(clamp01(s.score) * 100);
      const scope = !has ? "no evals" : s.isolated ? "solo source" : "in combination";
      return `
        <div class="src-card${has ? "" : " is-empty"}">
          <div class="src-card-head">
            <span class="src-chip src-${s.token} on">${s.short}</span>
            <span class="src-card-name">${escapeHtml(s.name)}</span>
          </div>
          <strong class="src-card-score ${has ? gradeClass(s.score) : ""}">${has ? pct(s.score) : "—"}</strong>
          <span class="src-card-track"><i class="${gradeClass(s.score)}" style="width:${has ? w : 0}%"></i></span>
          <span class="src-card-sub">${has ? `${s.items.length} eval${s.items.length === 1 ? "" : "s"} · ${scope}` : "no evals"}</span>
        </div>`;
    })
    .join("");

  const groupBars = groupStats
    .map(
      (g) => `
      <div class="mini-bar">
        <span class="mb-label">${escapeHtml(g.label)}</span>
        <span class="mb-track"><i class="mb-fill ${gradeClass(g.score)}" style="width:${Math.round(clamp01(g.score) * 100)}%"></i></span>
        <span class="mb-val">${pct(g.score)}</span>
      </div>`
    )
    .join("");

  const insight =
    best && worst && best.key !== worst.key
      ? `Strongest source: <b>${escapeHtml(best.short)}</b> (${pct(best.score)}) · weakest: <b>${escapeHtml(worst.short)}</b> (${pct(worst.score)}).`
      : "Average score by how many input sources are combined.";

  node.innerHTML = `
    <div class="src-cards">${cards}</div>
    <div class="src-progression">
      <div class="src-prog-head">
        <h3>Does combining sources help?</h3>
        <p>${insight}</p>
      </div>
      <div class="src-prog-bars">${groupBars}</div>
    </div>`;
}

function renderSourceCoverage() {
  const legend = el("sourceLegend");
  if (legend) {
    legend.innerHTML = SOURCES.map(
      (s) => `<span class="legend-item"><span class="src-chip src-${s.token} on">${s.short}</span></span>`
    ).join("");
  }
  const scale = el("heatScale");
  if (scale) {
    scale.innerHTML = `
      <span class="heat-scale-title">Score</span>
      <span class="hs-item"><i class="hs-sw heat-bad"></i>&lt;40 weak</span>
      <span class="hs-item"><i class="hs-sw heat-warn"></i>40–69 mixed</span>
      <span class="hs-item"><i class="hs-sw heat-good"></i>≥70 strong</span>`;
  }
  const node = el("sourceMatrix");
  if (!node) return;

  document.querySelectorAll("#sourceDim .seg-btn").forEach((b) => b.classList.toggle("is-active", b.getAttribute("data-dim") === state.sourceDim));

  const completed = completedRuns();
  renderSourceSummary(completed);
  if (!completed.length) {
    node.innerHTML = `<div class="empty">${state.loading ? "Loading…" : "No completed evaluations yet. Run the matrix to populate the source-coverage grid."}</div>`;
    return;
  }

  const dim = state.sourceDim === "project" ? "projectId" : "harvesterName";
  const labelFor = (id, items) =>
    dim === "projectId" ? items[0]?.projectName || id : harvesterLabel(id);
  const cols = dimensionStats(completed, dim, labelFor); // sorted by score
  const modesPresent = [...new Set(completed.map((r) => String(r.mode || "")))];

  const byCell = new Map(); // `${mode}|${dimValue}` -> runs
  for (const run of completed) {
    const key = `${run.mode}|${run[dim]}`;
    if (!byCell.has(key)) byCell.set(key, []);
    byCell.get(key).push(run);
  }

  const headerCols = cols
    .map((c) => `<th class="hc-col" title="${escapeHtml(c.label)}"><span>${escapeHtml(c.label)}</span><i>${pct(c.score)}</i></th>`)
    .join("");

  let bodyRows = "";
  for (const grp of MODE_GROUPS) {
    const groupModes = modesPresent
      .filter((m) => modeGroupKey(m) === grp.key)
      .sort((a, b) => modeSources(a).length - modeSources(b).length || a.localeCompare(b));
    if (!groupModes.length) continue;
    bodyRows += `<tr class="hc-group"><td colspan="${cols.length + 2}"><span>${escapeHtml(grp.label)}</span><small>${escapeHtml(grp.hint)}</small></td></tr>`;
    for (const mode of groupModes) {
      const rowRuns = completed.filter((r) => String(r.mode) === mode);
      const cells = cols.map((c) => heatCell(byCell.get(`${mode}|${c.id}`) || [])).join("");
      bodyRows += `
        <tr>
          <td class="hc-mode">
            <strong>${escapeHtml(modeLabel(mode))}</strong>
            ${sourceChips(mode)}
          </td>
          ${cells}
          ${heatCell(rowRuns)}
        </tr>`;
    }
  }

  node.innerHTML = `
    <div class="table-wrap">
      <table class="heat-table">
        <thead>
          <tr>
            <th class="hc-corner">Source mode</th>
            ${headerCols}
            <th class="hc-col hc-total"><span>All</span></th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>`;
}

function render() {
  el("apiUrlInput").value = state.apiUrl;
  const apiToggle = el("apiToggle");
  if (apiToggle) {
    const isLocal = state.apiUrl.includes("127.0.0.1") || state.apiUrl.includes("localhost");
    const label = apiToggle.querySelector(".api-status-label");
    if (label) label.textContent = isLocal ? "local API" : "remote API";
    apiToggle.classList.toggle("remote", !isLocal);
  }
  const runDisabled =
    state.running || state.loading || !state.selectedHarvesters.size || !state.selectedProjects.size || !state.selectedModes.size;
  for (const id of ["runButtonRuns"]) {
    const button = el(id);
    if (!button) continue;
    button.disabled = runDisabled;
    const label = button.querySelector(".run-label");
    if (label) label.textContent = state.running ? "Running…" : "Run matrix";
  }
  for (const id of ["runTopAllProjects", "runAllAllProjects"]) {
    const button = el(id);
    if (button) button.disabled = state.running || state.loading || !state.harvesters.length || !state.companies.length;
  }
  for (const id of ["runState", "runStateRuns"]) {
    const node = el(id);
    if (node) {
      node.textContent = state.running ? "running" : state.loading ? "loading" : "idle";
      node.classList.toggle("is-running", state.running || state.loading);
    }
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
  renderCharts();
  renderLeaderboard();
  renderSourceCoverage();
}

async function loadData() {
  state.loading = true;
  setError("");
  render();
  try {
    await resolveApiUrl();
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
    // Default to the single-source modes only — a clear, representative baseline.
    // Combinations (two / three / all sources) are opt-in so the matrix stays sane.
    state.selectedModes = new Set(allModeIds().filter((m) => modeGroupKey(m) === "single"));
  } catch (error) {
    setError(error.message || "Failed to load ICA data");
  } finally {
    state.loading = false;
    render();
  }
}

async function runMatrix() {
  await runMatrixWith({
    harvesterNames: Array.from(state.selectedHarvesters),
    projectIds: Array.from(state.selectedProjects),
    modeIds: Array.from(state.selectedModes),
  });
}

async function runMatrixWith({ harvesterNames, projectIds, modeIds, canonicalModeOnly = false }) {
  // Estimate the matrix size for the confirm + progress views. Canonical presets
  // run one mode per company; manual runs use the selected modes.
  const modesPerCompany = canonicalModeOnly ? 1 : Math.max(modeIds.length, 1);
  const cells = harvesterNames.length * projectIds.length * modesPerCompany;
  const exprText = `${harvesterNames.length} × ${projectIds.length} × ${modesPerCompany}`;

  const proceed = await confirmRun(cells, exprText);
  if (!proceed) return;

  state.running = true;
  closeRunModal();
  startRunProgress(cells);
  setError("");
  render();
  try {
    const response = await fetch(api("/ica/runs"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        harvesterNames,
        projectIds,
        modeIds,
        canonicalModeOnly,
        email: "ica-owner@example.com",
      }),
    });
    if (!response.ok) throw new Error((await response.text()) || `Run failed: ${response.status}`);
    const data = await response.json();
    state.lastRunGroupId = data.runGroupId || "";
    state.runs = [...(data.runs || []), ...state.runs];
    // jump straight into the new run group's detail section (with its own URL)
    state.activeTab = "runs";
    state.openGroupId = state.lastRunGroupId;
    state.openRunId = "";
    syncUrl(false);
  } catch (error) {
    setError(error.message || "ICA run failed");
  } finally {
    state.running = false;
    stopRunProgress();
    render();
  }
}

async function runPreset(kind) {
  const projectIds = state.companies.map((company) => company.projectId);
  const modeIds = [];
  if (kind === "top") {
    const top = topHarvesterName();
    if (!top) {
      setError("No harvester available for top-harvester run.");
      return;
    }
    await runMatrixWith({ harvesterNames: [top], projectIds, modeIds, canonicalModeOnly: true });
    return;
  }
  await runMatrixWith({ harvesterNames: state.harvesters.map((item) => item.name), projectIds, modeIds, canonicalModeOnly: true });
}

/* ---------- run progress + confirmation overlay ---------- */

const RUN_CONFIRM_THRESHOLD = 24; // ask before launching a big matrix
let runProgressTimer = null;

function fmtElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// Resolves true when the user confirms (or immediately for small runs / when
// the confirm elements are missing). Rejects nothing — always resolves.
function confirmRun(cells, exprText) {
  return new Promise((resolve) => {
    const overlay = el("runProgress");
    const confirm = el("rpConfirm");
    const running = el("rpRunning");
    if (!overlay || !confirm || cells <= RUN_CONFIRM_THRESHOLD) {
      resolve(true);
      return;
    }
    if (running) running.hidden = true;
    confirm.hidden = false;
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    const cellsNode = el("rpcCells");
    if (cellsNode) cellsNode.textContent = String(cells);
    const exprNode = el("rpcExpr");
    if (exprNode) exprNode.textContent = exprText || "";
    const hintNode = el("rpcHint");
    if (hintNode) hintNode.textContent = runSizeHint(cells);

    const cleanup = () => {
      el("rpConfirmBtn")?.removeEventListener("click", onYes);
      el("rpCancel")?.removeEventListener("click", onNo);
    };
    const onYes = () => {
      cleanup();
      resolve(true);
    };
    const onNo = () => {
      cleanup();
      confirm.hidden = true;
      overlay.hidden = true;
      document.body.style.overflow = "";
      resolve(false);
    };
    el("rpConfirmBtn")?.addEventListener("click", onYes);
    el("rpCancel")?.addEventListener("click", onNo);
  });
}

function startRunProgress(cells) {
  const overlay = el("runProgress");
  if (!overlay) return;
  const confirm = el("rpConfirm");
  if (confirm) confirm.hidden = true;
  const running = el("rpRunning");
  if (running) running.hidden = false;
  overlay.hidden = false;
  document.body.style.overflow = "hidden";
  const cellsNode = el("rpCells");
  if (cellsNode) cellsNode.textContent = String(cells);
  const hintNode = el("rpHint");
  if (hintNode) hintNode.textContent = `This ${runSizeHint(cells)}.`;
  const start = Date.now();
  const elapsedNode = el("rpElapsed");
  if (elapsedNode) elapsedNode.textContent = "0:00";
  clearInterval(runProgressTimer);
  runProgressTimer = setInterval(() => {
    if (elapsedNode) elapsedNode.textContent = fmtElapsed(Date.now() - start);
  }, 1000);
}

function stopRunProgress() {
  clearInterval(runProgressTimer);
  runProgressTimer = null;
  const overlay = el("runProgress");
  if (overlay) overlay.hidden = true;
  document.body.style.overflow = "";
}

function openRunModal() {
  const modal = el("runModal");
  if (!modal) return;
  modal.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeRunModal() {
  const modal = el("runModal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.style.overflow = "";
}

function bindControls() {
  el("apiToggle").addEventListener("click", (event) => {
    event.stopPropagation();
    const panel = el("apiPanel");
    panel.hidden = !panel.hidden;
    el("apiToggle").classList.toggle("is-open", !panel.hidden);
  });
  document.addEventListener("click", (event) => {
    const panel = el("apiPanel");
    if (panel.hidden) return;
    if (!panel.contains(event.target) && event.target !== el("apiToggle")) {
      panel.hidden = true;
      el("apiToggle").classList.remove("is-open");
    }
  });
  el("apiUrlInput").addEventListener("change", (event) => {
    state.apiUrl = event.target.value.trim() || DEFAULT_API_URL;
    localStorage.setItem("ica_api_url", state.apiUrl);
    loadData();
  });
  const collapseBtn = el("sidebarCollapse");
  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      const appNode = el("app");
      const collapsed = appNode.classList.toggle("is-collapsed");
      localStorage.setItem("ica_sidebar_collapsed", collapsed ? "1" : "0");
    });
  }
  const companySearch = el("companySearch");
  if (companySearch) {
    companySearch.addEventListener("input", (event) => {
      state.companyFilter.search = event.target.value;
      renderCompanies();
    });
  }
  const companySort = el("companySort");
  if (companySort) {
    companySort.addEventListener("change", (event) => {
      state.companyFilter.sort = event.target.value;
      renderCompanies();
    });
  }
  const runModal = el("runModal");
  el("openRunModal")?.addEventListener("click", openRunModal);
  el("runModalClose")?.addEventListener("click", closeRunModal);
  if (runModal) {
    runModal.addEventListener("click", (event) => {
      if (event.target === runModal) closeRunModal();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeRunModal();
  });
  el("reloadButton").addEventListener("click", loadData);
  el("runButtonRuns").addEventListener("click", runMatrix);
  el("runTopAllProjects").addEventListener("click", () => runPreset("top"));
  el("runAllAllProjects").addEventListener("click", () => runPreset("all"));
  const sourceDim = el("sourceDim");
  if (sourceDim) {
    sourceDim.addEventListener("click", (event) => {
      const btn = event.target.closest(".seg-btn");
      if (!btn) return;
      state.sourceDim = btn.getAttribute("data-dim") || "harvester";
      renderSourceCoverage();
    });
  }
  document.querySelectorAll("[data-tab]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      go({ tab: node.getAttribute("data-tab") || "overview" });
    });
  });
  window.addEventListener("popstate", () => {
    const route = routeFromUrl();
    state.activeTab = route.activeTab;
    state.openGroupId = route.openGroupId;
    state.openRunId = route.openRunId;
    render();
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
    ["filterPhase", "phase"],
    ["filterStatus", "status"],
  ].forEach(([id, key]) => {
    const node = el(id);
    if (!node) return;
    node.addEventListener("change", (event) => {
      state.filters[key] = event.target.value;
      render();
    });
  });
  el("clearFilters").addEventListener("click", () => {
    state.filters = { group: "", harvester: "", project: "", mode: "", status: "", phase: "" };
    render();
  });
}

if (localStorage.getItem("ica_sidebar_collapsed") === "1") {
  el("app")?.classList.add("is-collapsed");
}
bindControls();
syncUrl(true);
loadData();
