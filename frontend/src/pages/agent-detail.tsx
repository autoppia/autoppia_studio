import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faBook,
  faCheck,
  faCircleNodes,
  faCode,
  faListCheck,
  faPlug,
  faPlay,
  faPlus,
  faRobot,
  faRoute,
  faSliders,
  faSpinner,
  faTriangleExclamation,
  faWaveSquare,
  faWrench,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import {
  EvalItem,
  EvalRun,
  AgentToolkit,
  AgentCreationJob,
  AgentConfig,
  AgentCapability,
  AgentTrajectory,
  AgentWeb,
  RuntimeEvent,
} from "../utils/types";
import useStartSession from "../hooks/useStartSession";
import InfoIcon from "../components/common/info-icon";
import { useToast } from "../components/common/toast";
import { apiErrorMessage } from "../utils/api-error";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type TabKey = "overview" | "skills" | "runtime" | "benchmarks" | "runs" | "connect";
type SkillAssetTab = "skills" | "traces";
type SnippetTab = "curl" | "javascript" | "python";
type RunTarget = "selected" | "all";

interface AgentTaskRunResult {
  agentId: string;
  agentName: string;
  status: "ok" | "failed";
  result?: Record<string, any>;
  error?: string;
}

function StatusBadge({ label, tone = "gray" }: { label: string; tone?: "green" | "amber" | "blue" | "gray" | "red" }) {
  const tones = {
    green: "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30",
    amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30",
    blue: "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/30",
    red: "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30",
    gray: "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border",
  };
  return <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${tones[tone]}`}>{label}</span>;
}

function toneForStatus(status?: string): "green" | "amber" | "blue" | "gray" | "red" {
  const value = (status || "").toLowerCase();
  if (["ready", "verified", "approved", "pass"].includes(value)) return "green";
  if (["draft", "needs_review", "needs_trajectories", "pending", "needs_credentials", "ready_for_harvest"].includes(value)) return "amber";
  if (["fail", "blocked", "failed"].includes(value)) return "red";
  if (value) return "blue";
  return "gray";
}

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function normalizeName(value: string) {
  return value.replace(/_/g, " ");
}

function eventStatusTone(event: RuntimeEvent): "green" | "amber" | "blue" | "gray" | "red" {
  if (event.error) return "red";
  return toneForStatus(event.status || (event.eventType.includes("request") ? "pending" : "ok"));
}

function RuntimeJsonDetails({ label, value }: { label: string; value?: Record<string, any> | string }) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <details className="group rounded-lg border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 group-open:border-b group-open:border-gray-100 group-open:dark:border-dark-border">
        {label}
      </summary>
      <pre className="max-h-56 overflow-auto px-3 py-2 text-[11px] leading-5 text-gray-700 dark:text-gray-200 whitespace-pre-wrap break-words">
        {text}
      </pre>
    </details>
  );
}

export default function AgentDetail() {
  const { agentId = "" } = useParams();
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const startSession = useStartSession();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [webs, setWebs] = useState<AgentWeb[]>([]);
  const [trajectories, setTrajectories] = useState<AgentTrajectory[]>([]);
  const [skills, setSkills] = useState<AgentCapability[]>([]);
  const [toolkits, setToolkits] = useState<AgentToolkit[]>([]);
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [creationJob, setCreationJob] = useState<AgentCreationJob | null>(null);
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [skillAssetTab, setSkillAssetTab] = useState<SkillAssetTab>("skills");
  const [snippetTab, setSnippetTab] = useState<SnippetTab>("curl");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [runningId, setRunningId] = useState("");
  const [taskName, setTaskName] = useState("");
  const [taskPrompt, setTaskPrompt] = useState("");
  const [taskCriteria, setTaskCriteria] = useState("");
  const [runtimeBrowserEnabled, setRuntimeBrowserEnabled] = useState(true);
  const [runtimeBrowserMode, setRuntimeBrowserMode] = useState<"visible" | "headless">("visible");
  const [runtimeMaxCredits, setRuntimeMaxCredits] = useState(5);
  const [runtimeSaving, setRuntimeSaving] = useState(false);
  const [showRunTask, setShowRunTask] = useState(false);
  const [runPrompt, setRunPrompt] = useState("");
  const [runTarget, setRunTarget] = useState<RunTarget>("selected");
  const [runBrowserEnabled, setRunBrowserEnabled] = useState(true);
  const [runBrowserMode, setRunBrowserMode] = useState<"visible" | "headless">("visible");
  const [runMaxCredits, setRunMaxCredits] = useState(5);
  const [runResults, setRunResults] = useState<AgentTaskRunResult[]>([]);

  const responseMessage = (res: Response, fallback: string) => apiErrorMessage(res, fallback, "this agent");

  const loadData = async () => {
    if (!agentId || !user.email) return;
    setLoading(true);
    try {
      const [opRes, websRes, trRes, capRes, toolkitsRes, evalRes, runsRes, jobRes] = await Promise.all([
        fetch(`${apiUrl}/agents/${agentId}`),
        fetch(`${apiUrl}/agents/${agentId}/webs`),
        fetch(`${apiUrl}/agents/${agentId}/trajectories`),
        fetch(`${apiUrl}/agents/${agentId}/skills`),
        fetch(`${apiUrl}/agents/${agentId}/toolkits`),
        fetch(`${apiUrl}/evals?email=${encodeURIComponent(user.email)}`),
        fetch(`${apiUrl}/eval-runs?email=${encodeURIComponent(user.email)}`),
        fetch(`${apiUrl}/agents/${agentId}/creation-job`),
      ]);
      if (!opRes.ok) throw new Error(await opRes.text());
      const opData = await opRes.json();
      setAgent(opData.agent);
      setWebs(websRes.ok ? (await websRes.json()).webs || [] : []);
      setTrajectories(trRes.ok ? (await trRes.json()).trajectories || [] : []);
      setSkills(capRes.ok ? (await capRes.json()).skills || [] : []);
      setToolkits(toolkitsRes.ok ? (await toolkitsRes.json()).toolkits || [] : []);
      setEvals(evalRes.ok ? ((await evalRes.json()).evals || []).filter((item: EvalItem) => item.agentId === agentId) : []);
      setRuns(runsRes.ok ? ((await runsRes.json()).runs || []).filter((run: EvalRun) => run.agentId === agentId) : []);
      setCreationJob(jobRes.ok ? (await jobRes.json()).job || null : null);
    } catch (err) {
      console.error("Failed to load agent:", err);
      showToast("Could not load agent details.", "error");
    } finally {
      setLoading(false);
    }
  };

  const loadRuntimeEvents = async () => {
    if (!agentId) return;
    setEventsLoading(true);
    setEventsError("");
    try {
      const res = await fetch(`${apiUrl}/agents/${agentId}/runtime-events?limit=200`);
      if (!res.ok) throw new Error(await responseMessage(res, "Could not load runtime events."));
      const data = await res.json();
      setRuntimeEvents(data.events || []);
    } catch (err) {
      console.error("Failed to load runtime events:", err);
      setEventsError(err instanceof Error ? err.message : "Could not load runtime events.");
    } finally {
      setEventsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, user.email]);

  useEffect(() => {
    if (activeTab === "runtime") loadRuntimeEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, agentId]);

  useEffect(() => {
    if (!agent) return;
    const spec = agent.runtimeSpec || {};
    const browserEnabled = spec.browserEnabled ?? agent.runtimeCapabilities?.browser ?? true;
    const browserMode = spec.browserMode === "headless" ? "headless" : "visible";
    const maxCredits = Number(spec.maxCreditsPerRun ?? 5);
    setRuntimeBrowserEnabled(browserEnabled);
    setRuntimeBrowserMode(browserMode);
    setRuntimeMaxCredits(Number.isFinite(maxCredits) ? maxCredits : 5);
    setRunBrowserEnabled(browserEnabled);
    setRunBrowserMode(browserMode);
    setRunMaxCredits(Number.isFinite(maxCredits) ? maxCredits : 5);
  }, [agent]);

  const benchmark = useMemo(() => ({
    name: agent?.name || "Agent",
    id: evals[0]?.benchmarkId || `agent-${agentId}`,
    tasks: evals,
  }), [evals, agent?.name, agentId]);

  // Connectors powering this agent, derived from its enabled toolkits.
  const connectors = useMemo(() => {
    const map = new Map<string, { name: string; category: string; toolCount: number }>();
    for (const toolkit of toolkits) {
      const key = toolkit.connectorId || toolkit.connectorName || toolkit.name;
      if (!key) continue;
      const existing = map.get(key);
      if (existing) {
        existing.toolCount += toolkit.tools.length;
      } else {
        map.set(key, {
          name: toolkit.connectorName || toolkit.name,
          category: toolkit.category,
          toolCount: toolkit.tools.length,
        });
      }
    }
    return Array.from(map.values());
  }, [toolkits]);

  // Every tool the agent can call, flattened across its toolkits.
  const allTools = useMemo(
    () => toolkits.flatMap((toolkit) => toolkit.tools.map((tool) => ({ ...tool, toolkit: toolkit.name }))),
    [toolkits],
  );

  // Knowledge: vectorstore-backed toolkits + the runtime knowledge capability.
  const knowledgeToolkits = useMemo(
    () =>
      toolkits.filter((toolkit) =>
        (toolkit.runtimeRequirements || []).some(
          (req) => req.toLowerCase().includes("vector") || req.toLowerCase().includes("knowledge"),
        ),
      ),
    [toolkits],
  );

  const addTrajectory = async () => {
    if (!taskName.trim() || !taskPrompt.trim() || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/agents/${agentId}/trajectories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          webId: webs[0]?.webId || "",
          taskName: taskName.trim(),
          prompt: taskPrompt.trim(),
          successCriteria: taskCriteria.trim(),
          source: "user_prompt",
          status: "draft",
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not add trajectory."));
      setTaskName("");
      setTaskPrompt("");
      setTaskCriteria("");
      await loadData();
      showToast("Trajectory added.", "success");
    } catch (err) {
      console.error("Failed to add trajectory:", err);
      showToast(err instanceof Error ? err.message : "Could not add trajectory.", "error");
    } finally {
      setSaving(false);
    }
  };

  const approveTrajectory = async (trajectoryId?: string) => {
    if (!trajectoryId || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/trajectories/${trajectoryId}/convert-to-skill`, { method: "POST" });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not convert trajectory to skill."));
      await loadData();
      showToast("Trajectory converted to skill.", "success");
    } catch (err) {
      console.error("Failed to approve trajectory:", err);
      showToast(err instanceof Error ? err.message : "Could not convert trajectory to skill.", "error");
    } finally {
      setSaving(false);
    }
  };

  const runEval = async (evalItem: EvalItem) => {
    if (runningId) return;
    setRunningId(evalItem.evalId);
    try {
      const res = await fetch(`${apiUrl}/evals/${evalItem.evalId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "", agentId, agentName: agent?.name || "" }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not create eval run."));
      const data = await res.json();
      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        "",
        { evalMode: true, evalId: evalItem.evalId, runId: data.runId },
        `/evals/${evalItem.evalId}/run`,
        { agentId, agentName: agent?.name || "" },
      );
    } catch (err) {
      console.error("Failed to run task:", err);
      showToast(err instanceof Error ? err.message : "Could not run task.", "error");
      setRunningId("");
    }
  };

  const runBenchmark = async () => {
    if (runningId || !benchmark.tasks.length) return;
    setRunningId(agentId);
    try {
      const res = await fetch(`${apiUrl}/benchmarks/${benchmark.id}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "", agentId, agentName: agent?.name || "" }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not start benchmark."));
      const data = await res.json();
      const firstRun = data.runs?.[0];
      const firstTask = benchmark.tasks.find((task) => task.evalId === firstRun?.evalId) || benchmark.tasks[0];
      await startSession(
        firstTask.prompt,
        firstTask.initialUrl || "",
        "",
        {
          evalMode: true,
          evalId: firstTask.evalId,
          runId: firstRun.runId,
          benchmarkMode: true,
          benchmarkId: benchmark.id,
          benchmarkRunId: data.benchmarkRunId,
        },
        `/evals/${firstTask.evalId}/run`,
        { agentId, agentName: agent?.name || "" },
      );
    } catch (err) {
      console.error("Failed to run benchmark:", err);
      showToast(err instanceof Error ? err.message : "Could not start benchmark.", "error");
      setRunningId("");
    }
  };

  const saveRuntimeSettings = async (options?: { silent?: boolean }) => {
    if (!agent || runtimeSaving) return false;
    setRuntimeSaving(true);
    try {
      const res = await fetch(`${apiUrl}/agents/${agentId}/runtime-settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          browserEnabled: runtimeBrowserEnabled,
          browserMode: runtimeBrowserMode,
          maxCreditsPerRun: runtimeMaxCredits,
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not update runtime settings."));
      const data = await res.json();
      setAgent(data.agent || agent);
      if (!options?.silent) showToast("Runtime settings saved.", "success");
      return true;
    } catch (err) {
      console.error("Failed to save runtime settings:", err);
      showToast(err instanceof Error ? err.message : "Could not update runtime settings.", "error");
      return false;
    } finally {
      setRuntimeSaving(false);
    }
  };

  const runAdHocTask = async () => {
    const prompt = runPrompt.trim();
    if (!prompt || runningId) return;
    setRunningId(runTarget);
    setRunResults([]);
    try {
      if (runTarget === "selected") {
        setRuntimeBrowserEnabled(runBrowserEnabled);
        setRuntimeBrowserMode(runBrowserMode);
        setRuntimeMaxCredits(runMaxCredits);
        const res = await fetch(`${apiUrl}/agents/${agentId}/runtime-settings`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            browserEnabled: runBrowserEnabled,
            browserMode: runBrowserMode,
            maxCreditsPerRun: runMaxCredits,
          }),
        });
        if (!res.ok) throw new Error(await responseMessage(res, "Could not update runtime settings."));
        const data = await res.json();
        setAgent(data.agent || agent);
        await startSession(
          prompt,
          agent?.websiteUrl || "",
          "",
          { agentId, agentName: agent?.name || "" },
          "/session",
          { agentId, agentName: agent?.name || "" },
        );
        return;
      }

      const res = await fetch(`${apiUrl}/agents/run-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId: agent?.companyId || "",
          prompt,
          target: "all",
          browserEnabled: runBrowserEnabled,
          browserMode: runBrowserMode,
          maxCreditsPerRun: runMaxCredits,
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not run task."));
      const data = await res.json();
      setRunResults(data.results || []);
      showToast(`Task ran against ${data.count || 0} agents.`, "success");
    } catch (err) {
      console.error("Failed to run ad hoc task:", err);
      showToast(err instanceof Error ? err.message : "Could not run task.", "error");
    } finally {
      setRunningId("");
    }
  };

  const runCreationAction = async (action: "validate" | "harvest") => {
    if (saving) return;
    setSaving(true);
    setSetupError("");
    try {
      const res = await fetch(`${apiUrl}/agents/${agentId}/creation-job/${action}`, { method: "POST" });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not update setup job."));
      const data = await res.json();
      setCreationJob(data.job || null);
      await loadData();
      showToast(action === "validate" ? "Setup validation updated." : "Harvester started.", "success");
    } catch (err) {
      console.error("Failed to run creation action:", err);
      const message = err instanceof Error ? err.message : action === "validate" ? "Could not validate the agent setup. Check connector credentials and try again." : "Could not start the harvester. Check the setup status and try again.";
      setSetupError(message);
      showToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const updateRunLabel = async (run: EvalRun, label: "pass" | "fail") => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/evals/${run.evalId}/runs/${run.runId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not label run."));
      setRuns((prev) => prev.map((item) => (item.runId === run.runId ? { ...item, label } : item)));
      showToast(`Run marked ${label}.`, "success");
    } catch (err) {
      console.error("Failed to label run:", err);
      showToast(err instanceof Error ? err.message : "Could not label run.", "error");
    } finally {
      setSaving(false);
    }
  };

  const inputClass = `w-full px-3 h-10 rounded-xl border border-gray-200 dark:border-dark-border
    bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
    placeholder:text-gray-400 outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors`;

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-dark-bg">
        <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-dark-bg text-sm text-gray-500">
        Agent not found
      </div>
    );
  }

  const tabs: { key: TabKey; label: string; icon: any }[] = [
    { key: "overview", label: "Overview", icon: faRobot },
    { key: "skills", label: "Skills", icon: faCode },
    { key: "connect", label: "Connect", icon: faPlug },
  ];

  const knowledgeEnabled = agent.runtimeCapabilities?.knowledge ?? false;

  const apiBase = (apiUrl || "").replace(/\/$/, "");
  const agentStepUrl = `${apiBase}/api/v1/agents/${agentId}/step`;
  const agentSkillsUrl = `${apiBase}/api/v1/agents/${agentId}/skills`;
  const docsUrl = `${apiBase}/docs`;
  const curlSnippet = `curl -X POST "${agentStepUrl}" \\
  -H "x-api-key: $AUTOMATA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"task":"Log in to Autocinema","url":"${agent.websiteUrl || "https://example.com"}"}'`;
  const jsSnippet = `const response = await fetch("${agentStepUrl}", {
  method: "POST",
  headers: {
    "x-api-key": process.env.AUTOMATA_API_KEY,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ task: "Your task prompt", url: "${agent.websiteUrl || "https://example.com"}" })
});
const { result } = await response.json();`;
  const pythonSnippet = `import os, requests

response = requests.post(
    "${agentStepUrl}",
    headers={"x-api-key": os.environ["AUTOMATA_API_KEY"]},
    json={"task": "Your task prompt", "url": "${agent.websiteUrl || "https://example.com"}"},
    timeout=60,
)
print(response.json()["result"])`;
  const snippets: Record<SnippetTab, { title: string; code: string }> = {
    curl: { title: "cURL", code: curlSnippet },
    javascript: { title: "JavaScript", code: jsSnippet },
    python: { title: "Python", code: pythonSnippet },
  };

  const blockedStep = creationJob?.steps.find((step) => step.status === "blocked");
  const harvestedCount = trajectories.filter((trajectory) => trajectory.status === "harvested").length;
  const approvedCount = trajectories.filter((trajectory) => trajectory.status === "approved").length;
  const setupGuidance = (() => {
    if (!creationJob) return null;
    if (creationJob.status === "needs_credentials" || blockedStep?.key === "validate_connectors") {
      return {
        tone: "amber" as const,
        title: "Add connector credentials",
        description: blockedStep?.message || "Some connectors need credentials or a successful test before this agent can learn useful workflows.",
        action: "Open connectors",
        onClick: () => navigate("/connectors"),
      };
    }
    if (["draft", "ready_for_harvest"].includes(creationJob.status)) {
      return {
        tone: "blue" as const,
        title: creationJob.status === "draft" ? "Validate the setup" : "Run the harvester",
        description: creationJob.status === "draft"
          ? "Check connector readiness before collecting trajectories."
          : "Connector validation passed. Harvest trajectories from the benchmark tasks so the agent can become reusable.",
        action: creationJob.status === "draft" ? "Validate setup" : "Run harvester",
        onClick: () => runCreationAction(creationJob.status === "draft" ? "validate" : "harvest"),
      };
    }
    if (creationJob.status === "harvesting") {
      return {
        tone: "blue" as const,
        title: "Harvester is running",
        description: "Trajectories are being collected in the background. The latest status loads automatically when you open this page.",
      };
    }
    if (creationJob.status === "awaiting_review" || harvestedCount > 0) {
      return {
        tone: "amber" as const,
        title: "Review harvested trajectories",
        description: "Approve successful trajectories to turn them into reusable skills for this agent.",
        action: "Review trajectories",
        onClick: () => {
          setActiveTab("skills");
          setSkillAssetTab("traces");
        },
      };
    }
    if (creationJob.status === "harvest_failed") {
      return {
        tone: "red" as const,
        title: "Harvesting needs attention",
        description: blockedStep?.message || "The harvester did not produce successful trajectories. Adjust tasks or credentials, then run it again.",
        action: "Run harvester again",
        onClick: () => runCreationAction("harvest"),
      };
    }
    if (approvedCount > 0 || skills.length > 0 || agent.trainingStatus === "verified") {
      return {
        tone: "green" as const,
        title: "Agent is ready to test",
        description: "Run the benchmark or try one task from the home screen with this agent selected.",
        action: "Run benchmark",
        onClick: runBenchmark,
      };
    }
    return null;
  })();

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => navigate("/agents")}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
            >
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <div className="min-w-0">
              <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100 truncate">{agent.name}</h1>
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{agent.websiteUrl}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
            Configure the agent here. Run tasks and benchmarks from Sessions and Benchmarks.
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="flex flex-wrap items-center gap-2 mb-5">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-medium border transition-colors
                  ${activeTab === tab.key
                    ? "bg-gradient-primary text-white border-transparent shadow-glow"
                    : "bg-white dark:bg-dark-surface text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-gray-600"
                  }`}
              >
                <FontAwesomeIcon icon={tab.icon} className="text-xs" />
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === "overview" && (
            <div className="space-y-5">
              {setupError && (
                <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-4 flex items-start gap-3">
                  <FontAwesomeIcon icon={faTriangleExclamation} className="text-red-500 text-sm mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-red-600 dark:text-red-400">Setup action failed</p>
                    <p className="text-xs text-red-500 dark:text-red-300 mt-1">{setupError}</p>
                  </div>
                  <button onClick={() => setSetupError("")} className="w-7 h-7 rounded-lg flex items-center justify-center text-red-400 hover:bg-red-100 dark:hover:bg-red-500/10">
                    <FontAwesomeIcon icon={faXmark} className="text-xs" />
                  </button>
                </div>
              )}

              {setupGuidance && (
                <div className={`rounded-xl border p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 ${
                  setupGuidance.tone === "green"
                    ? "bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/30"
                    : setupGuidance.tone === "red"
                      ? "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/30"
                      : setupGuidance.tone === "amber"
                        ? "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30"
                        : "bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/30"
                }`}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <FontAwesomeIcon
                        icon={setupGuidance.tone === "red" ? faTriangleExclamation : setupGuidance.tone === "green" ? faCheck : faListCheck}
                        className={`text-sm ${
                          setupGuidance.tone === "green"
                            ? "text-green-600 dark:text-green-400"
                            : setupGuidance.tone === "red"
                              ? "text-red-500 dark:text-red-400"
                              : setupGuidance.tone === "amber"
                                ? "text-amber-600 dark:text-amber-400"
                                : "text-blue-600 dark:text-blue-400"
                        }`}
                      />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{setupGuidance.title}</p>
                    </div>
                    <p className="text-xs leading-5 text-gray-600 dark:text-gray-300">{setupGuidance.description}</p>
                  </div>
                  {"action" in setupGuidance && setupGuidance.action && "onClick" in setupGuidance && setupGuidance.onClick && (
                    <button
                      onClick={setupGuidance.onClick}
                      disabled={saving || runningId !== ""}
                      className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow disabled:opacity-60 flex items-center justify-center gap-2 flex-shrink-0"
                    >
                      {(saving || runningId === agentId) && <FontAwesomeIcon icon={faSpinner} className="text-xs animate-spin" />}
                      {setupGuidance.action}
                    </button>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
                {[
                  { label: "Connectors", value: connectors.length, icon: faPlug },
                  { label: "Tools", value: allTools.length, icon: faWrench },
                  { label: "Skills", value: skills.length, icon: faCode },
                  { label: "Knowledge", value: knowledgeToolkits.length, icon: faBook },
                  { label: "Trajectories", value: trajectories.length, icon: faRoute },
                  { label: "Runs", value: runs.length, icon: faCircleNodes },
                ].map((item) => (
                  <div key={item.label} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-gray-500 dark:text-gray-400">{item.label}</span>
                      <FontAwesomeIcon icon={item.icon} className="text-xs text-primary" />
                    </div>
                    <p className="text-2xl font-semibold text-gray-900 dark:text-white">{item.value}</p>
                  </div>
                ))}
              </div>

              {/* What this agent is made of — connectors, tools, skills, knowledge. */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Connectors */}
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <FontAwesomeIcon icon={faPlug} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Connectors</p>
                      <StatusBadge label={`${connectors.length}`} tone={connectors.length ? "blue" : "gray"} />
                    </div>
                    <button onClick={() => navigate("/connectors")} className="text-xs font-medium text-primary hover:underline">
                      Manage
                    </button>
                  </div>
                  {connectors.length === 0 ? (
                    <Empty text="No connectors enabled. Connect a tool from the Connectors page." />
                  ) : (
                    <div className="space-y-2">
                      {connectors.map((connector) => (
                        <div key={connector.name} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-dark-border px-3 py-2.5">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{connector.name}</p>
                            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{normalizeName(connector.category || "connector")}</p>
                          </div>
                          <StatusBadge label={`${connector.toolCount} tool${connector.toolCount === 1 ? "" : "s"}`} tone="gray" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Skills */}
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <FontAwesomeIcon icon={faCode} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Skills</p>
                      <StatusBadge label={`${skills.length}`} tone={skills.length ? "blue" : "gray"} />
                    </div>
                    <button onClick={() => setActiveTab("skills")} className="text-xs font-medium text-primary hover:underline">
                      View all
                    </button>
                  </div>
                  {skills.length === 0 ? (
                    <Empty text="No skills yet. Approve a trajectory to build a reusable workflow." />
                  ) : (
                    <div className="space-y-2">
                      {skills.slice(0, 5).map((skill) => (
                        <div key={skill.capabilityId} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-dark-border px-3 py-2.5">
                          <p className="font-mono text-sm font-medium text-gray-900 dark:text-white truncate">{skill.name}()</p>
                          <StatusBadge label={skill.type || "web"} tone={skill.type === "api" ? "green" : "gray"} />
                        </div>
                      ))}
                      {skills.length > 5 && (
                        <p className="text-xs text-gray-400 dark:text-gray-500 pt-1">+{skills.length - 5} more</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Tools */}
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <FontAwesomeIcon icon={faWrench} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Tools</p>
                      <StatusBadge label={`${allTools.length}`} tone={allTools.length ? "blue" : "gray"} />
                    </div>
                  </div>
                  {allTools.length === 0 ? (
                    <Empty text="No tools available yet. Enable a connector to expose tools." />
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {allTools.slice(0, 14).map((tool, index) => (
                        <span
                          key={`${tool.name}-${index}`}
                          title={`${tool.toolkit} · ${tool.sideEffects || "no side effects"}`}
                          className="font-mono text-[11px] px-2 py-1 rounded-lg bg-gray-100 dark:bg-dark-bg text-gray-700 dark:text-gray-200 border border-gray-200/70 dark:border-dark-border"
                        >
                          {tool.name}
                        </span>
                      ))}
                      {allTools.length > 14 && (
                        <span className="text-[11px] px-2 py-1 text-gray-400 dark:text-gray-500">+{allTools.length - 14} more</span>
                      )}
                    </div>
                  )}
                </div>

                {/* Knowledge */}
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <FontAwesomeIcon icon={faBook} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Knowledge</p>
                      <StatusBadge label={knowledgeEnabled ? "enabled" : "disabled"} tone={knowledgeEnabled ? "green" : "gray"} />
                    </div>
                    <button onClick={() => navigate("/knowledge")} className="text-xs font-medium text-primary hover:underline">
                      Manage
                    </button>
                  </div>
                  {knowledgeToolkits.length === 0 ? (
                    <p className="text-xs leading-5 text-gray-500 dark:text-gray-400">
                      {knowledgeEnabled
                        ? "Knowledge search is enabled for this runtime. Attach a vectorstore from the Knowledge page to ground answers in your documents."
                        : "Knowledge search is off. Enable it in Runtime settings and attach a vectorstore to let this agent read your documents."}
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {knowledgeToolkits.map((toolkit) => (
                        <div key={toolkit.toolkitId} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-dark-border px-3 py-2.5">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{toolkit.name}</p>
                            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{toolkit.connectorName || "Knowledge"}</p>
                          </div>
                          <StatusBadge label="vectorstore" tone="blue" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex flex-wrap gap-2 mb-4">
                  <StatusBadge label={normalizeName(agent.status)} tone={toneForStatus(agent.status)} />
                  <StatusBadge label={normalizeName(agent.trainingStatus)} tone={toneForStatus(agent.trainingStatus)} />
                  <StatusBadge label={normalizeName(agent.runtimeType)} tone="blue" />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Runtime endpoint</p>
                    <p className="font-mono text-gray-700 dark:text-gray-200 break-all">{agent.runtimeEndpoint || "Not deployed yet"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Automata</p>
                    <p className="text-gray-700 dark:text-gray-200">{agent.harvester || "Automata Agent"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">OpenAPI / Swagger</p>
                    <p className="font-mono text-gray-700 dark:text-gray-200 break-all">{agent.apiSpecUrl || "Not configured"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">API auth</p>
                    <p className="text-gray-700 dark:text-gray-200">{agent.apiAuthConfigured ? "Configured" : "Not configured"}</p>
                  </div>
                </div>
              </div>

              {creationJob && (
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Agent creation pipeline</p>
                        <StatusBadge label={normalizeName(creationJob.status)} tone={toneForStatus(creationJob.status)} />
                      </div>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                        Creation is not finished until connectors are validated, trajectories are reviewed, skills are built, and the benchmark runs.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => runCreationAction("validate")} disabled={saving} className="h-9 px-3 rounded-xl border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
                        <FontAwesomeIcon icon={saving ? faSpinner : faCheck} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                        Validate
                      </button>
                      <button onClick={() => runCreationAction("harvest")} disabled={saving} className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
                        <FontAwesomeIcon icon={saving ? faSpinner : faPlay} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                        Run Harvester
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {creationJob.steps.map((step) => (
                      <div key={step.key} className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">{step.label}</p>
                          <StatusBadge label={normalizeName(step.status)} tone={toneForStatus(step.status)} />
                        </div>
                        {step.message && <p className="text-xs leading-5 text-gray-500 dark:text-gray-400 mt-2">{step.message}</p>}
                      </div>
                    ))}
                  </div>
                  {creationJob.events?.length > 0 && (
                    <div className="mt-4 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border p-3 space-y-2">
                      {creationJob.events.slice(-3).map((event, index) => (
                        <p key={`${event.createdAt}-${index}`} className="text-xs text-gray-500 dark:text-gray-400">
                          {event.createdAt ? `${formatDate(event.createdAt)} · ` : ""}{event.message}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {activeTab === "skills" && (
            <div className="space-y-4">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Skills & Trajectories</h2>
                  <InfoIcon title="Tools, Skills, and Trajectories">
                    <div className="space-y-3">
                      <p><strong>Tool</strong> means an atomic capability connected to a system, such as sending email, calling an API, reading a document, or clicking in a browser.</p>
                      <p><strong>Toolkit</strong> means a bundle of tools from one connector or runtime, such as Gmail Toolkit, Browser Toolkit, or Knowledge Toolkit.</p>
                      <p><strong>Skill</strong> means a learned reusable workflow that can call multiple tools, such as sending a client their latest invoice from Gmail and Holded.</p>
                      <p><strong>Trajectory</strong> means an approved or recorded execution attempt. A successful trajectory can be promoted into a Skill.</p>
                    </div>
                  </InfoIcon>
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface p-1">
                  {[
                    { key: "skills" as SkillAssetTab, label: "Skills" },
                    { key: "traces" as SkillAssetTab, label: "Trajectories" },
                  ].map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setSkillAssetTab(tab.key)}
                      className={`h-8 px-3 rounded-lg text-xs font-medium transition-colors ${skillAssetTab === tab.key ? "bg-gradient-primary text-white" : "text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border"}`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {skillAssetTab === "skills" && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {skills.map((skill) => (
                    <div key={skill.capabilityId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                      <div className="flex items-center justify-between gap-3 mb-3">
                        <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">{skill.name}()</p>
                        <div className="flex items-center gap-2">
                          <StatusBadge label={skill.type || "web"} tone={skill.type === "api" ? "green" : "gray"} />
                          <StatusBadge label={normalizeName(skill.runtime)} tone="blue" />
                        </div>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">{skill.description || "No description"}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500">{skill.trajectoryIds?.length || 0} linked trajectories</p>
                    </div>
                  ))}
                  {skills.length === 0 && <Empty text="No skills yet. Approve a trajectory to generate the first reusable workflow." />}
                </div>
              )}

              {skillAssetTab === "traces" && (
                <>
              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 space-y-3">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <input className={inputClass} placeholder="Task name" value={taskName} onChange={(e) => setTaskName(e.target.value)} />
                  <input className={inputClass} placeholder="Success criteria" value={taskCriteria} onChange={(e) => setTaskCriteria(e.target.value)} />
                </div>
                <textarea
                  className={`${inputClass} h-auto py-2 resize-none`}
                  rows={2}
                  placeholder="Task prompt for Automata Agent to harvest"
                  value={taskPrompt}
                  onChange={(e) => setTaskPrompt(e.target.value)}
                />
                <button onClick={addTrajectory} disabled={saving || !taskName.trim() || !taskPrompt.trim()} className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
                  <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                  Add Trajectory
                </button>
              </div>
              {trajectories.map((trajectory) => (
                <div key={trajectory.trajectoryId || `${trajectory.taskName}-${trajectory.createdAt}`} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">{trajectory.taskName || trajectory.name}</p>
                        <StatusBadge label={trajectory.status || "draft"} tone={toneForStatus(trajectory.status)} />
                        {trajectory.source && <StatusBadge label={normalizeName(trajectory.source)} tone="gray" />}
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-300">{trajectory.prompt || "Bundled trajectory"}</p>
                      {trajectory.successCriteria && <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{trajectory.successCriteria}</p>}
                    </div>
                    {trajectory.status !== "approved" && (
                      <button onClick={() => approveTrajectory(trajectory.trajectoryId)} className="h-9 px-3 rounded-xl text-sm font-medium bg-green-600 text-white">
                        <FontAwesomeIcon icon={faCheck} className="mr-2 text-xs" />
                        Convert to Skill
                      </button>
                    )}
                  </div>
                </div>
              ))}
                </>
              )}
            </div>
          )}

          {activeTab === "runtime" && (
            <div className="space-y-4">
              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <FontAwesomeIcon icon={faSliders} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime Settings</p>
                    </div>
                    <p className="text-xs leading-5 text-gray-500 dark:text-gray-400">
                      Browser is an optional runtime surface. Disable it for API-only or connector-only tasks.
                    </p>
                  </div>
                  <button
                    onClick={() => saveRuntimeSettings()}
                    disabled={runtimeSaving}
                    className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow disabled:opacity-60 flex items-center gap-2"
                  >
                    <FontAwesomeIcon icon={runtimeSaving ? faSpinner : faCheck} className={`text-xs ${runtimeSaving ? "animate-spin" : ""}`} />
                    Save
                  </button>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
                  <label className="rounded-xl border border-gray-100 dark:border-dark-border p-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">Browser toolkit</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Expose browser actions to this runtime.</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={runtimeBrowserEnabled}
                      onChange={(event) => setRuntimeBrowserEnabled(event.target.checked)}
                      className="w-4 h-4 accent-primary"
                    />
                  </label>
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">Browser mode</p>
                    <div className="flex items-center gap-1 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-1">
                      {(["visible", "headless"] as const).map((mode) => (
                        <button
                          key={mode}
                          onClick={() => setRuntimeBrowserMode(mode)}
                          className={`flex-1 h-8 rounded-lg text-xs font-medium capitalize ${runtimeBrowserMode === mode ? "bg-gradient-primary text-white" : "text-gray-500 dark:text-gray-300 hover:bg-white dark:hover:bg-dark-surface"}`}
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">Max credits per run</p>
                    <input
                      type="number"
                      min="0"
                      step="0.25"
                      value={runtimeMaxCredits}
                      onChange={(event) => setRuntimeMaxCredits(Number(event.target.value))}
                      className={inputClass}
                    />
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex items-center gap-2 mb-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Enterprise runtime contract</p>
                  <InfoIcon title="Enterprise Runtime Contract">
                    <p>Runtime policy sent with AgentConfig: browser allowlists, explicit read/write approval boundaries, and available runtime classes.</p>
                  </InfoIcon>
                </div>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Browser default</p>
                    <StatusBadge label={agent.runtimeSpec?.browserDefaultUse || "exception"} tone={agent.runtimeSpec?.browserEnabled ? "amber" : "gray"} />
                  </div>
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Domain restriction</p>
                    <StatusBadge label={agent.runtimeSpec?.browserRestrictedByDomain ? "restricted" : "open"} tone={agent.runtimeSpec?.browserRestrictedByDomain ? "green" : "amber"} />
                  </div>
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Approval boundaries</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{(agent.runtimeSpec?.approvalRequiredFor || ["write", "send"]).join(", ")}</p>
                  </div>
                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Runtime classes</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{(agent.runtimeSpec?.runtimeClasses || ["api_runtime"]).length}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(agent.runtimeSpec?.allowedDomains || []).length === 0 ? (
                    <span className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                      No domain allowlist
                    </span>
                  ) : (agent.runtimeSpec?.allowedDomains || []).map((domain) => (
                    <span key={domain} className="rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                      {domain}
                    </span>
                  ))}
                  {(agent.runtimeSpec?.runtimeClasses || []).map((runtimeClass) => (
                    <span key={runtimeClass} className="rounded-lg border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                      {runtimeClass.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex items-center gap-2 mb-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime Capabilities</p>
                  <InfoIcon title="Runtime Capabilities">
                    <p>The browser is no longer the center of the agent. It is one runtime capability among others. An agent may have browser access, API calls, knowledge search, Python execution, or human approval depending on the company workflow.</p>
                  </InfoIcon>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                  {[
                    { label: "Browser", enabled: agent.runtimeCapabilities?.browser ?? true },
                    { label: "API Calls", enabled: agent.runtimeCapabilities?.apiCalls ?? true },
                    { label: "Knowledge", enabled: agent.runtimeCapabilities?.knowledge ?? false },
                    { label: "Python", enabled: agent.runtimeCapabilities?.python ?? false },
                    { label: "Human Approval", enabled: agent.runtimeCapabilities?.humanApprovalForWrites ?? true },
                  ].map((capability) => (
                    <div key={capability.label} className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{capability.label}</p>
                      <StatusBadge label={capability.enabled ? "enabled" : "disabled"} tone={capability.enabled ? "green" : "gray"} />
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <FontAwesomeIcon icon={faWaveSquare} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime Events</p>
                      <StatusBadge label={`${runtimeEvents.length} events`} tone={runtimeEvents.length ? "blue" : "gray"} />
                    </div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      Step requests, step results, and connector calls recorded by this agent.
                    </p>
                  </div>
                </div>

                {eventsError && (
                  <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-3 mb-4">
                    <p className="text-xs font-medium text-red-600 dark:text-red-400">{eventsError}</p>
                  </div>
                )}

                {eventsLoading && runtimeEvents.length === 0 ? (
                  <div className="h-32 rounded-xl border border-dashed border-gray-200 dark:border-dark-border flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
                    <FontAwesomeIcon icon={faSpinner} className="mr-2 text-xs animate-spin" />
                    Loading runtime events
                  </div>
                ) : runtimeEvents.length === 0 ? (
                  <Empty text="No runtime events yet. Run a task through /step to populate this timeline." />
                ) : (
                  <div className="space-y-3">
                    {runtimeEvents.map((event) => (
                      <div key={event.runId || `${event.eventType}-${event.createdAt}`} className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">{event.eventType}</p>
                              <StatusBadge label={event.error ? "failed" : event.status || "recorded"} tone={eventStatusTone(event)} />
                              {event.toolName && <StatusBadge label={event.toolName} tone="blue" />}
                              {event.stepIndex !== undefined && event.stepIndex !== null && <StatusBadge label={`step ${event.stepIndex}`} tone="gray" />}
                            </div>
                            <p className="text-xs text-gray-400 dark:text-gray-500">{formatDate(event.createdAt)}</p>
                          </div>
                          {event.runId && <p className="font-mono text-[11px] text-gray-400 dark:text-gray-500 truncate max-w-full lg:max-w-xs">{event.runId}</p>}
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
                          <RuntimeJsonDetails label="Payload" value={event.payload} />
                          <RuntimeJsonDetails label="Result" value={event.result} />
                          <RuntimeJsonDetails label="Error" value={event.error} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex items-center gap-2 mb-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Toolkits</p>
                  <InfoIcon title="Toolkits">
                    <p>A Toolkit is a group of tools from one connector or runtime. Connectors belong to the Company and can be reused by multiple agents. Some toolkits require runtime resources such as browser sessions, vectorstores, network access, API credentials, or a Python sandbox.</p>
                  </InfoIcon>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {toolkits.map((toolkit) => (
                    <div key={toolkit.toolkitId} className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                      <div className="flex items-center justify-between gap-3 mb-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white">{toolkit.name}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{toolkit.connectorName}</p>
                        </div>
                        <StatusBadge label={toolkit.category} tone="blue" />
                      </div>
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {toolkit.runtimeRequirements.map((requirement) => (
                          <StatusBadge key={requirement} label={normalizeName(requirement)} tone="gray" />
                        ))}
                      </div>
                      <div className="space-y-2">
                        {toolkit.tools.map((tool) => (
                          <div key={tool.name} className="flex items-center justify-between gap-3 text-xs">
                            <span className="font-mono text-gray-700 dark:text-gray-200">{tool.name}</span>
                            <span className="text-gray-400 dark:text-gray-500">{tool.sideEffects}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                  {toolkits.length === 0 && <Empty text="No toolkits are enabled for this agent yet." />}
                </div>
              </div>
            </div>
          )}

          {activeTab === "benchmarks" && (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
              <div className="flex items-center justify-between gap-3 mb-4">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{benchmark.name} Benchmark</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">{benchmark.tasks.length} tasks</p>
                </div>
                <button onClick={runBenchmark} disabled={runningId !== "" || benchmark.tasks.length === 0} className="h-9 px-3 rounded-xl text-sm font-medium bg-gradient-primary text-white disabled:opacity-60">
                  <FontAwesomeIcon icon={runningId === agentId ? faSpinner : faPlay} className={`mr-2 text-xs ${runningId === agentId ? "animate-spin" : ""}`} />
                  Run Benchmark
                </button>
              </div>
              <div className="space-y-2">
                {benchmark.tasks.map((task) => (
                  <div key={task.evalId} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-dark-border p-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{task.agentTaskName || task.prompt}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{task.prompt}</p>
                    </div>
                    <button onClick={() => runEval(task)} disabled={runningId !== ""} className="w-9 h-9 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
                      <FontAwesomeIcon icon={runningId === task.evalId ? faSpinner : faPlay} className={`text-xs ${runningId === task.evalId ? "animate-spin" : ""}`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "runs" && (
            <div className="space-y-3">
              {runs.map((run) => (
                <div key={run.runId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <StatusBadge label={run.label} tone={toneForStatus(run.label)} />
                        <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(run.createdAt)}</span>
                      </div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{run.agentTaskName || run.prompt}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateRunLabel(run, "pass")} className="w-9 h-9 rounded-lg flex items-center justify-center text-green-600 hover:bg-green-50 dark:hover:bg-green-500/10">
                        <FontAwesomeIcon icon={faCheck} className="text-xs" />
                      </button>
                      <button onClick={() => updateRunLabel(run, "fail")} className="w-9 h-9 rounded-lg flex items-center justify-center text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10">
                        <FontAwesomeIcon icon={faXmark} className="text-xs" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {runs.length === 0 && <Empty text="No runs yet. Run the benchmark or a single task." />}
            </div>
          )}

          {activeTab === "connect" && (
            <div className="space-y-4">
              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Agent API</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">Use this custom agent from your backend, product, or evaluation harness.</p>
                    <div className="space-y-2 text-sm">
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Step endpoint</p>
                        <p className="font-mono text-gray-700 dark:text-gray-200 break-all">{agentStepUrl}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Skills endpoint</p>
                        <p className="font-mono text-gray-700 dark:text-gray-200 break-all">{agentSkillsUrl}</p>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => navigate("/settings?tab=api-keys")}
                    className="h-9 px-3 rounded-xl text-sm font-medium bg-gradient-primary text-white shadow-glow"
                  >
                    API Keys
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Docs</p>
                  <div className="space-y-3 text-sm">
                    <a href={docsUrl} target="_blank" rel="noreferrer" className="block text-primary hover:opacity-80">OpenAPI Swagger UI</a>
                    <a href={`${apiBase}/openapi.json`} target="_blank" rel="noreferrer" className="block text-primary hover:opacity-80">OpenAPI JSON schema</a>
                    {agent.apiSpecUrl && (
                      <a href={agent.apiSpecUrl} target="_blank" rel="noreferrer" className="block text-primary hover:opacity-80">Customer API spec</a>
                    )}
                  </div>
                </div>

                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Agent Context</p>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-500 dark:text-gray-400">Agent ID</span>
                      <span className="font-mono text-xs text-gray-700 dark:text-gray-200 truncate">{agentId}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-500 dark:text-gray-400">Skills</span>
                      <span className="text-gray-700 dark:text-gray-200">{skills.length}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-gray-500 dark:text-gray-400">API spec</span>
                      <span className="text-gray-700 dark:text-gray-200">{agent.apiSpecUrl ? "Configured" : "Missing"}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border overflow-hidden">
                <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-gray-100 dark:border-dark-border">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Code Snippet</p>
                  <div className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-1">
                    {[
                      { key: "curl" as SnippetTab, label: "cURL" },
                      { key: "javascript" as SnippetTab, label: "JavaScript" },
                      { key: "python" as SnippetTab, label: "Python" },
                    ].map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setSnippetTab(tab.key)}
                        className={`h-7 px-2.5 rounded-md text-xs font-medium transition-colors ${snippetTab === tab.key ? "bg-gradient-primary text-white shadow-glow" : "text-gray-500 dark:text-gray-300 hover:bg-white dark:hover:bg-dark-surface"}`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>
                <pre className="p-5 overflow-auto text-xs leading-5 text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-dark-bg font-mono whitespace-pre-wrap">
                  {snippets[snippetTab].code}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>

      {showRunTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-auto rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-soft-lg">
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Run Task</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Run this prompt with one agent or race it against all agents.</p>
              </div>
              <button
                onClick={() => setShowRunTask(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-border"
              >
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <textarea
                value={runPrompt}
                onChange={(event) => setRunPrompt(event.target.value)}
                placeholder="Describe the task..."
                className="w-full min-h-28 p-3 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100 outline-none resize-y"
              />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {[
                  { key: "selected" as RunTarget, title: agent.name, desc: "Open a live session with this agent." },
                  { key: "all" as RunTarget, title: "All agents", desc: "Run one race step and compare outputs." },
                ].map((option) => (
                  <button
                    key={option.key}
                    onClick={() => setRunTarget(option.key)}
                    className={`text-left rounded-xl border p-4 transition-colors ${runTarget === option.key ? "border-primary bg-primary/5 dark:bg-primary/10" : "border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <FontAwesomeIcon icon={option.key === "all" ? faCircleNodes : faRobot} className="text-xs text-primary" />
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{option.title}</p>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{option.desc}</p>
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <label className="rounded-xl border border-gray-100 dark:border-dark-border p-4 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">Browser</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Expose browser tools.</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={runBrowserEnabled}
                    onChange={(event) => setRunBrowserEnabled(event.target.checked)}
                    className="w-4 h-4 accent-primary"
                  />
                </label>
                <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                  <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">Mode</p>
                  <select
                    value={runBrowserMode}
                    onChange={(event) => setRunBrowserMode(event.target.value === "headless" ? "headless" : "visible")}
                    className={inputClass}
                  >
                    <option value="visible">Visible</option>
                    <option value="headless">Headless</option>
                  </select>
                </div>
                <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                  <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">Max credits</p>
                  <input
                    type="number"
                    min="0"
                    step="0.25"
                    value={runMaxCredits}
                    onChange={(event) => setRunMaxCredits(Number(event.target.value))}
                    className={inputClass}
                  />
                </div>
              </div>

              {runResults.length > 0 && (
                <div className="space-y-2">
                  {runResults.map((item) => {
                    const result = item.result || {};
                    const calls: any[] = Array.isArray(result.tool_calls) ? result.tool_calls : [];
                    return (
                      <div key={item.agentId} className="rounded-xl border border-gray-100 dark:border-dark-border p-3">
                        <div className="flex items-center justify-between gap-3 mb-2">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{item.agentName || item.agentId}</p>
                          <StatusBadge label={item.status} tone={item.status === "ok" ? "green" : "red"} />
                        </div>
                        {item.error ? (
                          <p className="text-xs text-red-500 break-words">{item.error}</p>
                        ) : (
                          <p className="text-xs text-gray-500 dark:text-gray-400 break-words">
                            {calls.length > 0
                              ? calls.map((call: any) => call.name || call.action || "tool").join(", ")
                              : result.content || result.reasoning || "No tool call returned"}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowRunTask(false)}
                  className="h-9 px-3 rounded-xl border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border"
                >
                  Close
                </button>
                <button
                  onClick={runAdHocTask}
                  disabled={!runPrompt.trim() || runningId !== ""}
                  className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow disabled:opacity-60 flex items-center gap-2"
                >
                  <FontAwesomeIcon icon={runningId ? faSpinner : faPlay} className={`text-xs ${runningId ? "animate-spin" : ""}`} />
                  {runTarget === "all" ? "Run All" : "Open Session"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center text-sm text-gray-500 dark:text-gray-400">
      {text}
    </div>
  );
}
