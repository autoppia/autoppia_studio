import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faCheck,
  faCircleNodes,
  faClipboardCheck,
  faCode,
  faGlobe,
  faListCheck,
  faPlay,
  faPlus,
  faRobot,
  faRoute,
  faSpinner,
  faWrench,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import {
  EvalItem,
  EvalRun,
  Operator,
  OperatorCapability,
  OperatorTrajectory,
  OperatorWeb,
} from "../utils/types";
import useStartSession from "../hooks/useStartSession";

const apiUrl = process.env.REACT_APP_API_URL;

type TabKey = "overview" | "webs" | "capabilities" | "trajectories" | "benchmarks" | "runs";

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
  if (["draft", "needs_review", "needs_trajectories", "pending"].includes(value)) return "amber";
  if (value === "fail") return "red";
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

export default function OperatorDetail() {
  const { operatorId = "" } = useParams();
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const startSession = useStartSession();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [operator, setOperator] = useState<Operator | null>(null);
  const [webs, setWebs] = useState<OperatorWeb[]>([]);
  const [trajectories, setTrajectories] = useState<OperatorTrajectory[]>([]);
  const [capabilities, setCapabilities] = useState<OperatorCapability[]>([]);
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState("");
  const [webName, setWebName] = useState("");
  const [webUrl, setWebUrl] = useState("");
  const [taskName, setTaskName] = useState("");
  const [taskPrompt, setTaskPrompt] = useState("");
  const [taskCriteria, setTaskCriteria] = useState("");

  const loadData = async () => {
    if (!operatorId || !user.email) return;
    setLoading(true);
    try {
      const [opRes, websRes, trRes, capRes, evalRes, runsRes] = await Promise.all([
        fetch(`${apiUrl}/operators/${operatorId}`),
        fetch(`${apiUrl}/operators/${operatorId}/webs`),
        fetch(`${apiUrl}/operators/${operatorId}/trajectories`),
        fetch(`${apiUrl}/operators/${operatorId}/capabilities`),
        fetch(`${apiUrl}/evals?email=${encodeURIComponent(user.email)}`),
        fetch(`${apiUrl}/eval-runs?email=${encodeURIComponent(user.email)}`),
      ]);
      if (!opRes.ok) throw new Error(await opRes.text());
      const opData = await opRes.json();
      setOperator(opData.operator);
      setWebs(websRes.ok ? (await websRes.json()).webs || [] : []);
      setTrajectories(trRes.ok ? (await trRes.json()).trajectories || [] : []);
      setCapabilities(capRes.ok ? (await capRes.json()).capabilities || [] : []);
      setEvals(evalRes.ok ? ((await evalRes.json()).evals || []).filter((item: EvalItem) => item.operatorId === operatorId) : []);
      setRuns(runsRes.ok ? ((await runsRes.json()).runs || []).filter((run: EvalRun) => run.operatorId === operatorId) : []);
    } catch (err) {
      console.error("Failed to load operator:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatorId, user.email]);

  const benchmark = useMemo(() => ({
    name: operator?.name || "Operator",
    operatorId,
    tasks: evals,
  }), [evals, operator?.name, operatorId]);

  const addWeb = async () => {
    if (!webName.trim() || !webUrl.trim() || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/operators/${operatorId}/webs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, name: webName.trim(), baseUrl: webUrl.trim(), authRequired: false }),
      });
      if (!res.ok) throw new Error(await res.text());
      setWebName("");
      setWebUrl("");
      await loadData();
    } catch (err) {
      console.error("Failed to add web:", err);
    } finally {
      setSaving(false);
    }
  };

  const addTrajectory = async () => {
    if (!taskName.trim() || !taskPrompt.trim() || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/operators/${operatorId}/trajectories`, {
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
      if (!res.ok) throw new Error(await res.text());
      setTaskName("");
      setTaskPrompt("");
      setTaskCriteria("");
      await loadData();
    } catch (err) {
      console.error("Failed to add trajectory:", err);
    } finally {
      setSaving(false);
    }
  };

  const approveTrajectory = async (trajectoryId?: string) => {
    if (!trajectoryId || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/trajectories/${trajectoryId}/approve`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      await loadData();
    } catch (err) {
      console.error("Failed to approve trajectory:", err);
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
        body: JSON.stringify({ sessionId: "" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        "",
        { evalMode: true, evalId: evalItem.evalId, runId: data.runId },
        `/evals/${evalItem.evalId}/run`,
        { operatorId, operatorName: operator?.name || "" },
      );
    } catch (err) {
      console.error("Failed to run task:", err);
      setRunningId("");
    }
  };

  const runBenchmark = async () => {
    if (runningId || !benchmark.tasks.length) return;
    setRunningId(operatorId);
    try {
      const res = await fetch(`${apiUrl}/benchmarks/${operatorId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "" }),
      });
      if (!res.ok) throw new Error(await res.text());
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
          benchmarkId: operatorId,
          benchmarkRunId: data.benchmarkRunId,
        },
        `/evals/${firstTask.evalId}/run`,
        { operatorId, operatorName: operator?.name || "" },
      );
    } catch (err) {
      console.error("Failed to run benchmark:", err);
      setRunningId("");
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
      if (!res.ok) throw new Error(await res.text());
      setRuns((prev) => prev.map((item) => (item.runId === run.runId ? { ...item, label } : item)));
    } catch (err) {
      console.error("Failed to label run:", err);
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

  if (!operator) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-dark-bg text-sm text-gray-500">
        Operator not found
      </div>
    );
  }

  const tabs: { key: TabKey; label: string; icon: any }[] = [
    { key: "overview", label: "Overview", icon: faRobot },
    { key: "webs", label: "Webs", icon: faGlobe },
    { key: "capabilities", label: "Capabilities", icon: faCode },
    { key: "trajectories", label: "Trajectories", icon: faRoute },
    { key: "benchmarks", label: "Benchmarks", icon: faClipboardCheck },
    { key: "runs", label: "Runs", icon: faCircleNodes },
  ];

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => navigate("/operators")}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
            >
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <div className="min-w-0">
              <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100 truncate">{operator.name}</h1>
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{operator.websiteUrl}</p>
            </div>
          </div>
          <button
            onClick={runBenchmark}
            disabled={runningId !== "" || benchmark.tasks.length === 0}
            className="flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-medium bg-gradient-primary text-white shadow-glow disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <FontAwesomeIcon icon={runningId === operatorId ? faSpinner : faPlay} className={`text-xs ${runningId === operatorId ? "animate-spin" : ""}`} />
            Run Benchmark
          </button>
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
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {[
                  { label: "Tasks", value: operator.tasks?.length || 0, icon: faListCheck },
                  { label: "Webs", value: webs.length, icon: faGlobe },
                  { label: "Trajectories", value: trajectories.length, icon: faRoute },
                  { label: "Capabilities", value: capabilities.length, icon: faWrench },
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

              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                <div className="flex flex-wrap gap-2 mb-4">
                  <StatusBadge label={normalizeName(operator.status)} tone={toneForStatus(operator.status)} />
                  <StatusBadge label={normalizeName(operator.trainingStatus)} tone={toneForStatus(operator.trainingStatus)} />
                  <StatusBadge label={normalizeName(operator.runtimeType)} tone="blue" />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Runtime endpoint</p>
                    <p className="font-mono text-gray-700 dark:text-gray-200 break-all">{operator.runtimeEndpoint || "Not deployed yet"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Harvester</p>
                    <p className="text-gray-700 dark:text-gray-200">{operator.harvester || "Automata Operator"}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "webs" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_auto] gap-3 bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                <input className={inputClass} placeholder="Web name" value={webName} onChange={(e) => setWebName(e.target.value)} />
                <input className={inputClass} placeholder="https://example.com" value={webUrl} onChange={(e) => setWebUrl(e.target.value)} />
                <button onClick={addWeb} disabled={saving || !webName.trim() || !webUrl.trim()} className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
                  <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                  Add Web
                </button>
              </div>
              {webs.map((web) => (
                <div key={web.webId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{web.name}</p>
                      <p className="text-xs font-mono text-gray-500 dark:text-gray-400 truncate">{web.baseUrl}</p>
                    </div>
                    <StatusBadge label={web.authRequired ? "auth" : "public"} tone={web.authRequired ? "amber" : "gray"} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "capabilities" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {capabilities.map((capability) => (
                <div key={capability.capabilityId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">{capability.name}()</p>
                    <StatusBadge label={normalizeName(capability.runtime)} tone="blue" />
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">{capability.description || "No description"}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">{capability.trajectoryIds?.length || 0} linked trajectories</p>
                </div>
              ))}
              {capabilities.length === 0 && <Empty text="No capabilities yet. Approve a trajectory to generate the first function." />}
            </div>
          )}

          {activeTab === "trajectories" && (
            <div className="space-y-4">
              <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 space-y-3">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <input className={inputClass} placeholder="Task name" value={taskName} onChange={(e) => setTaskName(e.target.value)} />
                  <input className={inputClass} placeholder="Success criteria" value={taskCriteria} onChange={(e) => setTaskCriteria(e.target.value)} />
                </div>
                <textarea
                  className={`${inputClass} h-auto py-2 resize-none`}
                  rows={2}
                  placeholder="Task prompt for Automata Operator to harvest"
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
                        Approve
                      </button>
                    )}
                  </div>
                </div>
              ))}
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
                  <FontAwesomeIcon icon={runningId === operatorId ? faSpinner : faPlay} className={`mr-2 text-xs ${runningId === operatorId ? "animate-spin" : ""}`} />
                  Run Benchmark
                </button>
              </div>
              <div className="space-y-2">
                {benchmark.tasks.map((task) => (
                  <div key={task.evalId} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 dark:border-dark-border p-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{task.operatorTaskName || task.prompt}</p>
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
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{run.operatorTaskName || run.prompt}</p>
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
        </div>
      </div>
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
