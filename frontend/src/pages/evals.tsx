import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faClipboardCheck,
  faMagnifyingGlass,
  faPlay,
  faSpinner,
  faCheck,
  faXmark,
  faGlobe,
  faListCheck,
  faClockRotateLeft,
  faPlus,
} from "@fortawesome/free-solid-svg-icons";
import { AgentConfig, EvalItem, EvalRun } from "../utils/types";
import useStartSession from "../hooks/useStartSession";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type TabKey = "benchmarks" | "runs";

interface Benchmark {
  benchmarkId: string;
  name: string;
  description?: string;
  websiteUrl: string;
  agentId: string;
  agentName?: string;
  tasks: EvalItem[];
  persisted?: boolean;
}

interface PendingRun {
  type: "task" | "benchmark";
  evalItem?: EvalItem;
  benchmark?: Benchmark;
}

function formatDate(iso?: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function labelClass(label: string) {
  if (label === "pass") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (label === "fail") return "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30";
  return "bg-yellow-50 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/30";
}

function statusClass(status?: string) {
  const s = (status || "").toLowerCase();
  if (["approved", "ready", "completed"].includes(s)) return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (["harvest_failed", "failed", "error"].includes(s)) return "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30";
  if (["needs_harvest", "harvesting", "harvested", "pending"].includes(s)) return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function judgeClass(judgeType?: string) {
  return (judgeType || "manual") === "llm"
    ? "bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-300 border-purple-200 dark:border-purple-500/30"
    : "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

export default function Evals() {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const startSession = useStartSession();

  const [activeTab, setActiveTab] = useState<TabKey>("benchmarks");
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [runningEvalId, setRunningEvalId] = useState<string | null>(null);
  const [runningBenchmarkId, setRunningBenchmarkId] = useState<string | null>(null);
  const [savingRunId, setSavingRunId] = useState<string | null>(null);
  const [pendingRun, setPendingRun] = useState<PendingRun | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [fetchedBenchmarks, setFetchedBenchmarks] = useState<Benchmark[]>([]);

  const [showCreateBenchmark, setShowCreateBenchmark] = useState(false);
  const [creatingBenchmark, setCreatingBenchmark] = useState(false);
  const [newBenchmark, setNewBenchmark] = useState({ name: "", description: "", websiteUrl: "", agentId: "" });

  const [addTaskBenchmark, setAddTaskBenchmark] = useState<Benchmark | null>(null);
  const [addingTask, setAddingTask] = useState(false);
  const [newTask, setNewTask] = useState({ name: "", prompt: "", successCriteria: "", initialUrl: "", judgeType: "manual" });
  const [judgingRunId, setJudgingRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!user.email) return;
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, user.email]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const scoped = new URLSearchParams({ email: user.email });
      if (companyId) scoped.set("companyId", companyId);
      const agentParams = new URLSearchParams({ email: user.email });
      if (companyId) agentParams.set("companyId", companyId);
      const [evalsRes, runsRes, agentsRes, benchmarksRes] = await Promise.all([
        fetch(`${apiUrl}/evals?${scoped.toString()}`),
        fetch(`${apiUrl}/eval-runs?${scoped.toString()}`),
        fetch(`${apiUrl}/agents?${agentParams.toString()}`),
        fetch(`${apiUrl}/benchmarks?${scoped.toString()}`),
      ]);
      if (!evalsRes.ok) throw new Error(await evalsRes.text());
      const evalsData = await evalsRes.json();
      setEvals(evalsData.evals || []);
      if (runsRes.ok) {
        const runsData = await runsRes.json();
        setRuns(runsData.runs || []);
      }
      if (agentsRes.ok) {
        const agentsData = await agentsRes.json();
        setAgents(agentsData.agents || []);
      }
      if (benchmarksRes.ok) {
        const benchmarksData = await benchmarksRes.json();
        setFetchedBenchmarks(benchmarksData.benchmarks || []);
      }
    } catch (err) {
      console.error("Failed to fetch benchmark data:", err);
    } finally {
      setLoading(false);
    }
  };

  const benchmarks = useMemo<Benchmark[]>(() => {
    const grouped = new Map<string, Benchmark>();
    for (const bench of fetchedBenchmarks) {
      grouped.set(bench.benchmarkId, {
        benchmarkId: bench.benchmarkId,
        name: bench.name || "Benchmark",
        description: bench.description || "",
        websiteUrl: bench.websiteUrl || "",
        agentId: bench.agentId || "",
        agentName: bench.agentName || "",
        tasks: bench.tasks || [],
        persisted: true,
      });
    }
    for (const item of evals) {
      const key = item.benchmarkId || item.agentId || `manual:${item.initialUrl || "default"}`;
      const existing = grouped.get(key);
      if (existing) {
        if (!existing.tasks.some((task) => task.evalId === item.evalId)) {
          existing.tasks.push(item);
        }
        continue;
      }
      grouped.set(key, {
        benchmarkId: key,
        name: item.benchmarkName || item.agentName || "Manual Benchmark",
        websiteUrl: item.initialUrl || "",
        agentId: item.agentId || "",
        tasks: [item],
        persisted: false,
      });
    }
    return Array.from(grouped.values());
  }, [evals, fetchedBenchmarks]);

  const filteredBenchmarks = benchmarks.filter((benchmark) => {
    const q = search.toLowerCase();
    return (
      benchmark.name.toLowerCase().includes(q) ||
      benchmark.websiteUrl.toLowerCase().includes(q) ||
      benchmark.tasks.some((task) => task.prompt.toLowerCase().includes(q))
    );
  });

  const filteredRuns = runs.filter((run) => {
    const q = search.toLowerCase();
    return (
      (run.agentName || "").toLowerCase().includes(q) ||
      (run.prompt || "").toLowerCase().includes(q) ||
      (run.label || "").toLowerCase().includes(q)
    );
  });

  const openRunSelector = (next: PendingRun) => {
    setPendingRun(next);
    const currentAgent = next.evalItem?.agentId || next.benchmark?.agentId || "";
    setSelectedAgentId(currentAgent);
  };

  const selectedAgent = agents.find((agent) => agent.agentId === selectedAgentId) || null;
  const selectedAgentName = selectedAgent?.name || (selectedAgentId ? "Custom Agent" : "Generalist Agent");

  const runEval = async (evalItem: EvalItem, agentId = selectedAgentId) => {
    if (runningEvalId) return;
    setRunningEvalId(evalItem.evalId);
    try {
      const res = await fetch(`${apiUrl}/evals/${evalItem.evalId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "", agentId, agentName: agentId ? selectedAgentName : "Generalist Agent" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        "",
        { evalMode: true, evalId: evalItem.evalId, runId: data.runId },
        `/evals/${evalItem.evalId}/run`,
        agentId ? { agentId, agentName: selectedAgentName } : undefined,
      );
    } catch (err) {
      console.error("Failed to run benchmark task:", err);
      setRunningEvalId(null);
    }
  };

  const runBenchmark = async (benchmark: Benchmark, agentId = selectedAgentId) => {
    if (runningBenchmarkId || runningEvalId || benchmark.tasks.length === 0) return;
    setRunningBenchmarkId(benchmark.benchmarkId);
    try {
      const res = await fetch(`${apiUrl}/benchmarks/${encodeURIComponent(benchmark.benchmarkId)}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "", agentId, agentName: agentId ? selectedAgentName : "Generalist Agent" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const firstRun = data.runs?.[0];
      if (!firstRun) throw new Error("Benchmark has no runnable tasks");
      const firstTask = benchmark.tasks.find((task) => task.evalId === firstRun.evalId) || benchmark.tasks[0];
      await startSession(
        firstTask.prompt,
        firstTask.initialUrl || "",
        "",
        {
          evalMode: true,
          evalId: firstTask.evalId,
          runId: firstRun.runId,
          benchmarkMode: true,
          benchmarkId: benchmark.benchmarkId,
          benchmarkRunId: data.benchmarkRunId,
        },
        `/evals/${firstTask.evalId}/run`,
        agentId ? { agentId, agentName: selectedAgentName } : undefined,
      );
    } catch (err) {
      console.error("Failed to run benchmark:", err);
      setRunningBenchmarkId(null);
    }
  };

  const confirmRun = async () => {
    const next = pendingRun;
    setPendingRun(null);
    if (!next) return;
    if (next.type === "task" && next.evalItem) {
      await runEval(next.evalItem, selectedAgentId);
    } else if (next.type === "benchmark" && next.benchmark) {
      await runBenchmark(next.benchmark, selectedAgentId);
    }
  };

  const createBenchmark = async () => {
    if (creatingBenchmark || !newBenchmark.name.trim()) return;
    setCreatingBenchmark(true);
    try {
      const agent = agents.find((a) => a.agentId === newBenchmark.agentId) || null;
      const res = await fetch(`${apiUrl}/benchmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: newBenchmark.name.trim(),
          description: newBenchmark.description.trim(),
          websiteUrl: newBenchmark.websiteUrl.trim(),
          agentId: newBenchmark.agentId,
          agentName: agent?.name || "",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setShowCreateBenchmark(false);
      setNewBenchmark({ name: "", description: "", websiteUrl: "", agentId: "" });
      await fetchData();
    } catch (err) {
      console.error("Failed to create benchmark:", err);
    } finally {
      setCreatingBenchmark(false);
    }
  };

  const addTask = async () => {
    if (addingTask || !addTaskBenchmark || !newTask.prompt.trim()) return;
    setAddingTask(true);
    try {
      const res = await fetch(`${apiUrl}/benchmarks/${encodeURIComponent(addTaskBenchmark.benchmarkId)}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          agentId: addTaskBenchmark.agentId,
          name: newTask.name.trim(),
          prompt: newTask.prompt.trim(),
          successCriteria: newTask.successCriteria.trim(),
          initialUrl: newTask.initialUrl.trim(),
          judgeType: newTask.judgeType,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setAddTaskBenchmark(null);
      setNewTask({ name: "", prompt: "", successCriteria: "", initialUrl: "", judgeType: "manual" });
      await fetchData();
    } catch (err) {
      console.error("Failed to add benchmark task:", err);
    } finally {
      setAddingTask(false);
    }
  };

  const updateRunLabel = async (run: EvalRun, label: "pass" | "fail") => {
    if (savingRunId) return;
    setSavingRunId(run.runId);
    try {
      const res = await fetch(`${apiUrl}/evals/${run.evalId}/runs/${run.runId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
      if (!res.ok) throw new Error(await res.text());
      setRuns((prev) => prev.map((r) => (r.runId === run.runId ? { ...r, label, labelSource: "manual_override", manualOverride: true } : r)));
    } catch (err) {
      console.error("Failed to update run label:", err);
    } finally {
      setSavingRunId(null);
    }
  };

  const runLlmJudge = async (run: EvalRun) => {
    if (judgingRunId) return;
    setJudgingRunId(run.runId);
    try {
      const res = await fetch(`${apiUrl}/evals/${run.evalId}/runs/${run.runId}/judge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apply: true }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const judgement = data.judgement || {};
      setRuns((prev) =>
        prev.map((r) =>
          r.runId === run.runId
            ? { ...r, label: judgement.label || r.label, judge: judgement, judgeType: "llm", labelSource: "llm_judge" }
            : r,
        ),
      );
    } catch (err) {
      console.error("Failed to run LLM judge:", err);
    } finally {
      setJudgingRunId(null);
    }
  };

  const passCount = runs.filter((run) => run.label === "pass").length;
  const failCount = runs.filter((run) => run.label === "fail").length;
  const pendingCount = runs.filter((run) => run.label === "pending").length;

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-glow">
              <FontAwesomeIcon icon={faClipboardCheck} className="text-sm" />
            </span>
            <div>
              <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">Benchmarks</h1>
              <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">Evaluation tasks and runs</p>
            </div>
          </div>
          <button
            onClick={() => setShowCreateBenchmark(true)}
            className="flex items-center justify-center gap-1.5 h-9 px-3 rounded-lg text-xs font-semibold
              bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg transition-all"
          >
            <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
            New Benchmark
          </button>
        </div>

        <div className="flex-1 overflow-auto px-8 lg:px-16 xl:px-28 py-8">
          <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-6">
            <div className="flex items-center gap-1 p-1 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border">
              {[
                { key: "benchmarks" as TabKey, label: "Benchmarks", icon: faClipboardCheck },
                { key: "runs" as TabKey, label: "Runs", icon: faClockRotateLeft },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 h-8 px-3 rounded-lg text-sm font-medium transition-colors
                    ${activeTab === tab.key
                      ? "bg-gradient-primary text-white shadow-glow"
                      : "text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border"
                    }`}
                >
                  <FontAwesomeIcon icon={tab.icon} className="text-xs" />
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-white dark:bg-dark-surface flex-1
              border border-gray-200 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-200">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder={activeTab === "benchmarks" ? "Search benchmarks..." : "Search runs..."}
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
              <span className="px-2 py-1 rounded-md bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border">
                {benchmarks.length} benchmarks
              </span>
              <span className="px-2 py-1 rounded-md bg-yellow-50 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400">
                {pendingCount} pending
              </span>
              <span className="px-2 py-1 rounded-md bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400">
                {passCount} pass
              </span>
              <span className="px-2 py-1 rounded-md bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400">
                {failCount} fail
              </span>
            </div>

          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading evals...</p>
            </div>
          ) : activeTab === "benchmarks" ? (
            filteredBenchmarks.length === 0 ? (
              <EmptyState text={companyId ? "No benchmarks for this company yet." : "Select a company to see its benchmarks."} />
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {filteredBenchmarks.map((benchmark) => (
                  <div
                    key={benchmark.benchmarkId}
                    className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border shadow-soft p-5"
                  >
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="min-w-0">
                        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{benchmark.name}</h2>
                        {benchmark.description && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{benchmark.description}</p>
                        )}
                        {benchmark.websiteUrl && (
                          <p className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 font-mono truncate mt-1">
                            <FontAwesomeIcon icon={faGlobe} className="text-[10px]" />
                            {benchmark.websiteUrl}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="flex items-center gap-1.5 px-2.5 h-8 rounded-lg text-xs font-medium
                          bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300">
                          <FontAwesomeIcon icon={faListCheck} className="text-[10px]" />
                          {benchmark.tasks.length} {benchmark.tasks.length === 1 ? "task" : "tasks"}
                        </div>
                        {benchmark.persisted && (
                          <button
                            onClick={() => setAddTaskBenchmark(benchmark)}
                            className="flex items-center justify-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                              border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300
                              hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
                          >
                            <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
                            Add Task
                          </button>
                        )}
                        <button
                          onClick={() => openRunSelector({ type: "benchmark", benchmark })}
                          disabled={runningBenchmarkId === benchmark.benchmarkId || !!runningEvalId || benchmark.tasks.length === 0}
                          className="flex items-center justify-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                            bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg disabled:opacity-60 transition-all"
                        >
                          <FontAwesomeIcon icon={runningBenchmarkId === benchmark.benchmarkId ? faSpinner : faPlay} className={`text-[10px] ${runningBenchmarkId === benchmark.benchmarkId ? "animate-spin" : ""}`} />
                          Run Benchmark
                        </button>
                      </div>
                    </div>

                    <div className="space-y-2">
                      {benchmark.tasks.length === 0 && (
                        <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border px-3 py-6 text-center">
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            No tasks yet.{benchmark.persisted ? " Use “Add Task” to create one." : ""}
                          </p>
                        </div>
                      )}
                      {benchmark.tasks.map((task) => (
                        <div
                          key={task.evalId}
                          className="flex items-center gap-3 rounded-lg border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                                {task.agentTaskName || "Task"}
                              </p>
                              {task.status && (
                                <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold ${statusClass(task.status)}`}>
                                  {task.status.replace(/_/g, " ")}
                                </span>
                              )}
                              <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold ${judgeClass(task.judgeType)}`}>
                                {(task.judgeType || "manual") === "llm" ? "LLMJudge" : "Manual"}
                              </span>
                            </div>
                            <p className="text-sm text-gray-900 dark:text-white truncate">{task.prompt}</p>
                          </div>
                          <button
                            onClick={() => openRunSelector({ type: "task", evalItem: task })}
                            disabled={runningEvalId === task.evalId}
                            className="flex items-center justify-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                              bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg disabled:opacity-60 transition-all"
                          >
                            <FontAwesomeIcon icon={runningEvalId === task.evalId ? faSpinner : faPlay} className={`text-[10px] ${runningEvalId === task.evalId ? "animate-spin" : ""}`} />
                            Run
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : filteredRuns.length === 0 ? (
            <EmptyState text="No runs yet. Run a benchmark task, then confirm pass or fail here." />
          ) : (
            <div className="flex flex-col gap-3">
              {filteredRuns.map((run) => (
                <div
                  key={run.runId}
                  className="flex items-center gap-4 bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border shadow-soft px-5 py-4"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-2 py-0.5 rounded-md border text-[11px] font-semibold ${labelClass(run.label)}`}>
                        {run.label}
                      </span>
                      <span className={`px-2 py-0.5 rounded-md border text-[11px] font-semibold ${judgeClass(run.judgeType)}`}>
                        {(run.judgeType || "manual") === "llm" ? "LLMJudge" : "Manual"}
                      </span>
                      {run.manualOverride && (
                        <span className="px-2 py-0.5 rounded-md border text-[11px] font-semibold bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">
                          override
                        </span>
                      )}
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {formatDate(run.createdAt)}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {run.prompt || run.evalId}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                      {(run.agentName || "Benchmark")} {run.agentTaskName ? ` / ${run.agentTaskName}` : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {(run.judgeType || "manual") === "llm" && (
                      <button
                        onClick={() => runLlmJudge(run)}
                        disabled={judgingRunId === run.runId}
                        className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                          bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-300
                          border border-purple-200 dark:border-purple-500/30 hover:bg-purple-100 dark:hover:bg-purple-500/20 disabled:opacity-60 transition-colors"
                      >
                        <FontAwesomeIcon icon={judgingRunId === run.runId ? faSpinner : faClipboardCheck} className={`text-[10px] ${judgingRunId === run.runId ? "animate-spin" : ""}`} />
                        LLM Judge
                      </button>
                    )}
                    <button
                      onClick={() => navigate(`/evals/${run.evalId}/run/${run.sessionId || run.runId}`, { state: { evalMode: true, evalId: run.evalId, runId: run.runId } })}
                      className="px-3 h-8 rounded-lg text-xs font-medium border border-gray-200 dark:border-dark-border
                        text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
                    >
                      View
                    </button>
                    <button
                      onClick={() => updateRunLabel(run, "pass")}
                      disabled={savingRunId === run.runId}
                      className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                        bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400
                        border border-green-200 dark:border-green-500/30 hover:bg-green-100 dark:hover:bg-green-500/20 disabled:opacity-60 transition-colors"
                    >
                      <FontAwesomeIcon icon={faCheck} className="text-[10px]" />
                      Pass
                    </button>
                    <button
                      onClick={() => updateRunLabel(run, "fail")}
                      disabled={savingRunId === run.runId}
                      className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                        bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400
                        border border-red-200 dark:border-red-500/30 hover:bg-red-100 dark:hover:bg-red-500/20 disabled:opacity-60 transition-colors"
                    >
                      <FontAwesomeIcon icon={faXmark} className="text-[10px]" />
                      Fail
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {pendingRun && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setPendingRun(null)} />
          <div className="relative w-full max-w-md mx-4 bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">Select Agent</h3>
              <button
                onClick={() => setPendingRun(null)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border"
              >
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>
            <div className="space-y-2">
              <button
                onClick={() => setSelectedAgentId("")}
                className={`w-full text-left rounded-xl border px-3 py-3 transition-colors ${
                  selectedAgentId === ""
                    ? "border-primary bg-primary/5 text-gray-900 dark:text-white"
                    : "border-gray-200 dark:border-dark-border text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"
                }`}
              >
                <span className="block text-sm font-semibold">Generalist Agent</span>
                <span className="block text-xs text-gray-400 dark:text-gray-500">Default generalist agent</span>
              </button>
              {agents.map((agent) => (
                <button
                  key={agent.agentId}
                  onClick={() => setSelectedAgentId(agent.agentId)}
                  className={`w-full text-left rounded-xl border px-3 py-3 transition-colors ${
                    selectedAgentId === agent.agentId
                      ? "border-primary bg-primary/5 text-gray-900 dark:text-white"
                      : "border-gray-200 dark:border-dark-border text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"
                  }`}
                >
                  <span className="block text-sm font-semibold">{agent.name}</span>
                  <span className="block text-xs text-gray-400 dark:text-gray-500 truncate">{agent.websiteUrl || agent.runtimeType}</span>
                </button>
              ))}
            </div>
            <button
              onClick={confirmRun}
              className="mt-5 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow"
            >
              Run with {selectedAgentName}
            </button>
          </div>
        </div>
      )}

      {showCreateBenchmark && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => !creatingBenchmark && setShowCreateBenchmark(false)} />
          <div className="relative w-full max-w-md mx-4 bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">New Benchmark</h3>
              <button
                onClick={() => setShowCreateBenchmark(false)}
                disabled={creatingBenchmark}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60"
              >
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>
            <div className="space-y-3">
              <FormField label="Name" required>
                <input
                  type="text"
                  autoFocus
                  value={newBenchmark.name}
                  onChange={(e) => setNewBenchmark((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Checkout flow benchmark"
                  className={fieldClass}
                />
              </FormField>
              <FormField label="Description">
                <textarea
                  value={newBenchmark.description}
                  onChange={(e) => setNewBenchmark((p) => ({ ...p, description: e.target.value }))}
                  placeholder="Optional summary of what this benchmark covers"
                  rows={2}
                  className={`${fieldBase} resize-none`}
                />
              </FormField>
              <FormField label="Website URL">
                <input
                  type="text"
                  value={newBenchmark.websiteUrl}
                  onChange={(e) => setNewBenchmark((p) => ({ ...p, websiteUrl: e.target.value }))}
                  placeholder="https://example.com"
                  className={fieldClass}
                />
              </FormField>
              <FormField label="Agent">
                <select
                  value={newBenchmark.agentId}
                  onChange={(e) => setNewBenchmark((p) => ({ ...p, agentId: e.target.value }))}
                  className={fieldClass}
                >
                  <option value="">Generalist Agent</option>
                  {agents.map((agent) => (
                    <option key={agent.agentId} value={agent.agentId}>{agent.name}</option>
                  ))}
                </select>
              </FormField>
            </div>
            <button
              onClick={createBenchmark}
              disabled={creatingBenchmark || !newBenchmark.name.trim()}
              className="mt-5 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow
                disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {creatingBenchmark && <FontAwesomeIcon icon={faSpinner} className="text-xs animate-spin" />}
              {creatingBenchmark ? "Creating..." : "Create Benchmark"}
            </button>
          </div>
        </div>
      )}

      {addTaskBenchmark && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => !addingTask && setAddTaskBenchmark(null)} />
          <div className="relative w-full max-w-md mx-4 bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">Add Task</h3>
                <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{addTaskBenchmark.name}</p>
              </div>
              <button
                onClick={() => setAddTaskBenchmark(null)}
                disabled={addingTask}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60"
              >
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>
            <div className="space-y-3">
              <FormField label="Task name">
                <input
                  type="text"
                  value={newTask.name}
                  onChange={(e) => setNewTask((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Add item to cart"
                  className={fieldClass}
                />
              </FormField>
              <FormField label="Prompt" required>
                <textarea
                  autoFocus
                  value={newTask.prompt}
                  onChange={(e) => setNewTask((p) => ({ ...p, prompt: e.target.value }))}
                  placeholder="Describe what the agent should accomplish"
                  rows={3}
                  className={`${fieldBase} resize-none`}
                />
              </FormField>
              <FormField label="Success criteria">
                <textarea
                  value={newTask.successCriteria}
                  onChange={(e) => setNewTask((p) => ({ ...p, successCriteria: e.target.value }))}
                  placeholder="How to determine the task succeeded"
                  rows={2}
                  className={`${fieldBase} resize-none`}
                />
              </FormField>
              <FormField label="Judge">
                <select
                  value={newTask.judgeType}
                  onChange={(e) => setNewTask((p) => ({ ...p, judgeType: e.target.value }))}
                  className={fieldClass}
                >
                  <option value="manual">Manual review</option>
                  <option value="llm">LLMJudge</option>
                </select>
              </FormField>
              <FormField label="Initial URL">
                <input
                  type="text"
                  value={newTask.initialUrl}
                  onChange={(e) => setNewTask((p) => ({ ...p, initialUrl: e.target.value }))}
                  placeholder={addTaskBenchmark.websiteUrl || "https://example.com"}
                  className={fieldClass}
                />
              </FormField>
            </div>
            <button
              onClick={addTask}
              disabled={addingTask || !newTask.prompt.trim()}
              className="mt-5 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow
                disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {addingTask && <FontAwesomeIcon icon={faSpinner} className="text-xs animate-spin" />}
              {addingTask ? "Adding..." : "Add Task"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const fieldBase =
  "w-full px-3 py-2 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border " +
  "text-sm text-gray-800 dark:text-gray-100 placeholder:text-gray-400 outline-none " +
  "focus:border-primary dark:focus:border-primary transition-colors";
const fieldClass = `${fieldBase} h-10`;

function FormField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      {children}
    </label>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-primary shadow-glow mb-4">
        <FontAwesomeIcon icon={faClipboardCheck} className="text-white text-xl" />
      </div>
      <p className="text-gray-500 dark:text-gray-400 text-sm">{text}</p>
    </div>
  );
}
