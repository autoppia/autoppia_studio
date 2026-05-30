import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faClipboardCheck,
  faCoins,
  faMagnifyingGlass,
  faPlay,
  faSpinner,
  faCheck,
  faXmark,
  faGlobe,
  faListCheck,
  faClockRotateLeft,
} from "@fortawesome/free-solid-svg-icons";
import { EvalItem, EvalRun } from "../utils/types";
import useStartSession from "../hooks/useStartSession";

const apiUrl = process.env.REACT_APP_API_URL;

type TabKey = "benchmarks" | "runs";

interface Benchmark {
  benchmarkId: string;
  name: string;
  websiteUrl: string;
  operatorId: string;
  tasks: EvalItem[];
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

export default function Evals() {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const startSession = useStartSession();

  const [activeTab, setActiveTab] = useState<TabKey>("benchmarks");
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [runningEvalId, setRunningEvalId] = useState<string | null>(null);
  const [savingRunId, setSavingRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!user.email) return;
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [evalsRes, runsRes] = await Promise.all([
        fetch(`${apiUrl}/evals?email=${encodeURIComponent(user.email)}`),
        fetch(`${apiUrl}/eval-runs?email=${encodeURIComponent(user.email)}`),
      ]);
      if (!evalsRes.ok) throw new Error(await evalsRes.text());
      const evalsData = await evalsRes.json();
      setEvals(evalsData.evals || []);
      if (runsRes.ok) {
        const runsData = await runsRes.json();
        setRuns(runsData.runs || []);
      }
    } catch (err) {
      console.error("Failed to fetch benchmark data:", err);
    } finally {
      setLoading(false);
    }
  };

  const benchmarks = useMemo<Benchmark[]>(() => {
    const grouped = new Map<string, Benchmark>();
    for (const item of evals) {
      const key = item.operatorId || `manual:${item.initialUrl || "default"}`;
      const existing = grouped.get(key);
      if (existing) {
        existing.tasks.push(item);
        continue;
      }
      grouped.set(key, {
        benchmarkId: key,
        name: item.operatorName || "Manual Benchmark",
        websiteUrl: item.initialUrl || "",
        operatorId: item.operatorId || "",
        tasks: [item],
      });
    }
    return Array.from(grouped.values());
  }, [evals]);

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
      (run.operatorName || "").toLowerCase().includes(q) ||
      (run.prompt || "").toLowerCase().includes(q) ||
      (run.label || "").toLowerCase().includes(q)
    );
  });

  const runEval = async (evalItem: EvalItem) => {
    if (runningEvalId) return;
    setRunningEvalId(evalItem.evalId);
    try {
      const res = await fetch(`${apiUrl}/evals/${evalItem.evalId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        "",
        { evalMode: true, evalId: evalItem.evalId, runId: data.runId },
        `/evals/${evalItem.evalId}/run`
      );
    } catch (err) {
      console.error("Failed to run benchmark task:", err);
      setRunningEvalId(null);
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
      setRuns((prev) => prev.map((r) => (r.runId === run.runId ? { ...r, label } : r)));
    } catch (err) {
      console.error("Failed to update run label:", err);
    } finally {
      setSavingRunId(null);
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
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Evals</h1>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg
            border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium">
            <FontAwesomeIcon icon={faCoins} className="text-xs" />
            <span>0.00 Credits</span>
          </div>
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
              <EmptyState text="No benchmarks yet. Create an operator to generate a benchmark." />
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
                        {benchmark.websiteUrl && (
                          <p className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 font-mono truncate mt-1">
                            <FontAwesomeIcon icon={faGlobe} className="text-[10px]" />
                            {benchmark.websiteUrl}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 px-2.5 h-7 rounded-lg text-xs font-medium
                        bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300">
                        <FontAwesomeIcon icon={faListCheck} className="text-[10px]" />
                        {benchmark.tasks.length} tasks
                      </div>
                    </div>

                    <div className="space-y-2">
                      {benchmark.tasks.map((task) => (
                        <div
                          key={task.evalId}
                          className="flex items-center gap-3 rounded-lg border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                              {task.operatorTaskName || "Task"}
                            </p>
                            <p className="text-sm text-gray-900 dark:text-white truncate">{task.prompt}</p>
                          </div>
                          <button
                            onClick={() => runEval(task)}
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
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {formatDate(run.createdAt)}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {run.prompt || run.evalId}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                      {(run.operatorName || "Benchmark")} {run.operatorTaskName ? ` / ${run.operatorTaskName}` : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
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
    </div>
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
