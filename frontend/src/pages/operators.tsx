import React, { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faRobot,
  faMagnifyingGlass,
  faSpinner,
  faPlus,
  faTrash,
  faCoins,
  faGlobe,
  faBolt,
  faXmark,
  faCircleCheck,
  faListCheck,
  faRoute,
} from "@fortawesome/free-solid-svg-icons";
import { Operator, OperatorTask } from "../utils/types";

const apiUrl = process.env.REACT_APP_API_URL;

interface TaskDraft {
  name: string;
  prompt: string;
  successCriteria: string;
}

const emptyTask = (): TaskDraft => ({ name: "", prompt: "", successCriteria: "" });

/** Small colored pill used for status / type metadata. */
function StatusBadge({ label, tone }: { label: string; tone: "green" | "amber" | "gray" | "blue" }) {
  const tones: Record<string, string> = {
    green: "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/20",
    amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
    blue: "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
    gray: "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border",
  };
  return (
    <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${tones[tone]}`}>
      {label}
    </span>
  );
}

function statusTone(status: string): "green" | "amber" | "gray" | "blue" {
  const s = status.toLowerCase();
  if (s === "ready" || s === "verified") return "green";
  if (s === "draft" || s === "not_started" || s === "needs_trajectories") return "amber";
  if (s === "pending") return "gray";
  return "blue";
}

function prettify(value: string) {
  return value.replace(/_/g, " ");
}

export default function Operators() {
  const user = useSelector((state: any) => state.user);

  const [operators, setOperators] = useState<Operator[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [bootstrapping, setBootstrapping] = useState(false);

  // Create modal
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [successCriteria, setSuccessCriteria] = useState("");
  const [tasks, setTasks] = useState<TaskDraft[]>([emptyTask()]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!user.email) return;
    fetchOperators();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email]);

  const fetchOperators = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/operators?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setOperators(data.operators || []);
    } catch (err) {
      console.error("Failed to fetch operators:", err);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setName("");
    setWebsiteUrl("");
    setAuthUsername("");
    setAuthPassword("");
    setSuccessCriteria("");
    setTasks([emptyTask()]);
  };

  const closeModal = () => {
    setShowModal(false);
    resetForm();
  };

  const updateTask = (index: number, field: keyof TaskDraft, value: string) => {
    setTasks((prev) => prev.map((t, i) => (i === index ? { ...t, [field]: value } : t)));
  };

  const addTaskRow = () => setTasks((prev) => [...prev, emptyTask()]);

  const removeTaskRow = (index: number) =>
    setTasks((prev) => (prev.length === 1 ? prev : prev.filter((_, i) => i !== index)));

  const canSubmit = name.trim() !== "" && websiteUrl.trim() !== "" && !submitting;

  const handleCreate = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const cleanTasks: OperatorTask[] = tasks
        .filter((t) => t.name.trim() || t.prompt.trim())
        .map((t) => ({
          name: t.name.trim(),
          prompt: t.prompt.trim(),
          successCriteria: t.successCriteria.trim(),
        }));
      const res = await fetch(`${apiUrl}/operators`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          name: name.trim(),
          websiteUrl: websiteUrl.trim(),
          authUsername: authUsername.trim(),
          authPassword: authPassword,
          successCriteria: successCriteria.trim(),
          tasks: cleanTasks,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      closeModal();
      await fetchOperators();
    } catch (err) {
      console.error("Failed to create operator:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleBootstrapAutocinema = async () => {
    if (bootstrapping) return;
    setBootstrapping(true);
    try {
      const res = await fetch(`${apiUrl}/operators/bootstrap/autocinema`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });
      if (!res.ok) throw new Error(await res.text());
      await fetchOperators();
    } catch (err) {
      console.error("Failed to bootstrap Autocinema operator:", err);
    } finally {
      setBootstrapping(false);
    }
  };

  const filtered = operators.filter(
    (o) =>
      o.name.toLowerCase().includes(search.toLowerCase()) ||
      o.websiteUrl.toLowerCase().includes(search.toLowerCase())
  );

  const inputClass = `w-full px-3 h-10 rounded-xl border border-gray-200 dark:border-dark-border
    bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
    placeholder:text-gray-400 outline-none
    focus:border-gray-300 dark:focus:border-gray-600 transition-colors`;

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Operators</h1>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg
            border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium">
            <FontAwesomeIcon icon={faCoins} className="text-xs" />
            <span>0.00 Credits</span>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-6">
          {/* Search + actions */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mb-6">
            <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-white dark:bg-dark-surface
              border border-gray-200 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-200 flex-1">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder="Search operators..."
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button
              onClick={handleBootstrapAutocinema}
              disabled={bootstrapping}
              className="flex items-center justify-center gap-2 px-4 h-10 rounded-xl text-sm font-medium flex-shrink-0
                text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-surface
                border border-gray-200 dark:border-dark-border
                hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-dark-border/60
                disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200"
            >
              <FontAwesomeIcon icon={bootstrapping ? faSpinner : faBolt} className={`text-xs ${bootstrapping ? "animate-spin" : ""}`} />
              {bootstrapping ? "Bootstrapping..." : "Autocinema Demo"}
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center justify-center gap-2 px-4 h-10 rounded-xl text-sm font-medium flex-shrink-0
                bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-105 transition-all duration-200"
            >
              <FontAwesomeIcon icon={faPlus} className="text-xs" />
              Create Operator
            </button>
          </div>

          {/* List */}
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading operators…</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-primary shadow-glow mb-4">
                <FontAwesomeIcon icon={faRobot} className="text-white text-xl" />
              </div>
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                {search ? "No operators found." : "No operators yet. Create one or bootstrap the Autocinema demo."}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((op) => (
                <div
                  key={op.operatorId}
                  className="group relative flex flex-col bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft
                    hover:shadow-soft-lg hover:border-gray-300 dark:hover:border-gray-600
                    transition-all duration-200 p-5"
                >
                  {/* Icon */}
                  <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-primary shadow-glow mb-4 flex-shrink-0">
                    <FontAwesomeIcon icon={faRobot} className="text-white text-base" />
                  </div>

                  {/* Title */}
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">{op.name}</h3>

                  {/* Website */}
                  {op.websiteUrl && (
                    <a
                      href={op.websiteUrl}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-primary
                        truncate font-mono mb-3"
                    >
                      <FontAwesomeIcon icon={faGlobe} className="text-[10px] flex-shrink-0" />
                      <span className="truncate">{op.websiteUrl}</span>
                    </a>
                  )}

                  {/* Status badges */}
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    <StatusBadge label={prettify(op.status)} tone={statusTone(op.status)} />
                    <StatusBadge label={prettify(op.runtimeType)} tone="blue" />
                    <StatusBadge label={prettify(op.trainingStatus)} tone={statusTone(op.trainingStatus)} />
                  </div>

                  {/* Runtime endpoint */}
                  {op.runtimeEndpoint && (
                    <p className="text-[11px] text-gray-400 dark:text-gray-500 font-mono truncate mb-3" title={op.runtimeEndpoint}>
                      {op.runtimeEndpoint}
                    </p>
                  )}

                  {/* Counts */}
                  <div className="mt-auto flex items-center gap-4 pt-3 border-t border-gray-100 dark:border-dark-border">
                    <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                      <FontAwesomeIcon icon={faListCheck} className="text-[10px]" />
                      <span>{op.tasks?.length || 0} tasks</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                      <FontAwesomeIcon icon={faRoute} className="text-[10px]" />
                      <span>{op.trajectories?.length || 0} trajectories</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create Operator Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeModal} />
          <div className="relative w-full max-w-lg mx-4 max-h-[90vh] overflow-auto scrollbar-thin
            bg-white dark:bg-dark-surface rounded-2xl shadow-xl border border-gray-200 dark:border-dark-border p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">Create Custom Operator</h3>
              <button
                onClick={closeModal}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400
                  hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
              >
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="My Operator"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                />
              </div>

              {/* Website URL */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Website URL <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="https://example.com"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                />
              </div>

              {/* Auth (optional) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    Auth Username <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <input
                    type="text"
                    className={inputClass}
                    placeholder="username"
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    Auth Password <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <input
                    type="password"
                    className={inputClass}
                    placeholder="••••••••"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
              </div>

              {/* Success criteria */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Success Criteria
                </label>
                <textarea
                  className={`${inputClass} h-auto py-2.5 resize-none`}
                  rows={2}
                  placeholder="How is a successful run judged?"
                  value={successCriteria}
                  onChange={(e) => setSuccessCriteria(e.target.value)}
                />
              </div>

              {/* Tasks */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Tasks</label>
                  <button
                    onClick={addTaskRow}
                    className="flex items-center gap-1.5 text-xs font-medium text-primary hover:opacity-80 transition-opacity"
                  >
                    <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
                    Add task
                  </button>
                </div>
                <div className="space-y-3">
                  {tasks.map((task, index) => (
                    <div
                      key={index}
                      className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <input
                          type="text"
                          className="flex-1 px-2.5 h-9 rounded-lg border border-gray-200 dark:border-dark-border
                            bg-white dark:bg-dark-surface text-sm text-gray-800 dark:text-gray-100
                            placeholder:text-gray-400 outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors"
                          placeholder="Task name"
                          value={task.name}
                          onChange={(e) => updateTask(index, "name", e.target.value)}
                        />
                        <button
                          onClick={() => removeTaskRow(index)}
                          disabled={tasks.length === 1}
                          className="flex items-center justify-center w-9 h-9 rounded-lg flex-shrink-0
                            text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10
                            disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-gray-400
                            transition-colors"
                          title="Remove task"
                        >
                          <FontAwesomeIcon icon={faTrash} className="text-xs" />
                        </button>
                      </div>
                      <textarea
                        className="w-full px-2.5 py-2 rounded-lg border border-gray-200 dark:border-dark-border
                          bg-white dark:bg-dark-surface text-sm text-gray-800 dark:text-gray-100
                          placeholder:text-gray-400 outline-none resize-none
                          focus:border-gray-300 dark:focus:border-gray-600 transition-colors mb-2"
                        rows={2}
                        placeholder="Task prompt…"
                        value={task.prompt}
                        onChange={(e) => updateTask(index, "prompt", e.target.value)}
                      />
                      <input
                        type="text"
                        className="w-full px-2.5 h-9 rounded-lg border border-gray-200 dark:border-dark-border
                          bg-white dark:bg-dark-surface text-sm text-gray-800 dark:text-gray-100
                          placeholder:text-gray-400 outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors"
                        placeholder="Success criteria (optional)"
                        value={task.successCriteria}
                        onChange={(e) => updateTask(index, "successCriteria", e.target.value)}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={closeModal}
                className="flex-1 h-10 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-300
                  bg-gray-100 dark:bg-dark-border hover:bg-gray-200 dark:hover:bg-dark-border/80 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!canSubmit}
                className={`flex-1 h-10 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all duration-300
                  ${canSubmit
                    ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg"
                    : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                  }`}
              >
                {submitting ? (
                  <FontAwesomeIcon icon={faSpinner} className="animate-spin" />
                ) : (
                  <FontAwesomeIcon icon={faCircleCheck} className="text-xs" />
                )}
                {submitting ? "Creating..." : "Create Operator"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
