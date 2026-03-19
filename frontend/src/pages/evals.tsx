import React, { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faClipboardCheck,
  faMagnifyingGlass,
  faTrash,
  faSpinner,
  faPlus,
  faGlobe,
  faAngleDown,
  faPlay,
  faCoins,
} from "@fortawesome/free-solid-svg-icons";
import { EvalItem } from "../utils/types";
import ConfirmModal from "../components/common/confirm-modal";
import useStartSession from "../hooks/useStartSession";
import { websites } from "../utils/mock/mockDB";

const apiUrl = process.env.REACT_APP_API_URL;

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Evals() {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const startSession = useStartSession();

  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingEvalId, setDeletingEvalId] = useState<string | null>(null);

  // Add task modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [initialUrl, setInitialUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [filteredWebsites, setFilteredWebsites] = useState(websites);
  const [showUrlDropdown, setShowUrlDropdown] = useState(false);

  useEffect(() => {
    if (!user.email) return;
    fetchEvals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email]);

  // Close URL dropdown on outside click
  useEffect(() => {
    if (!showUrlDropdown) return;
    const handler = () => setShowUrlDropdown(false);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [showUrlDropdown]);

  const fetchEvals = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/evals?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setEvals(data.evals || []);
    } catch (err) {
      console.error("Failed to fetch evals:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (evalId: string) => {
    try {
      const res = await fetch(`${apiUrl}/evals/${evalId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setEvals((prev) => prev.filter((e) => e.evalId !== evalId));
    } catch (err) {
      console.error("Failed to delete eval:", err);
    }
  };

  const handleAddTask = async () => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/evals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          prompt: prompt.trim(),
          initialUrl: initialUrl.trim(),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPrompt("");
      setInitialUrl("");
      setShowAddModal(false);
      await fetchEvals();
    } catch (err) {
      console.error("Failed to add task:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handlePromptChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPrompt(event.target.value);
    event.target.style.height = "auto";
    event.target.style.height = `${event.target.scrollHeight}px`;
  };

  const handleUrlChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setInitialUrl(value);
    if (value) {
      setFilteredWebsites(websites.filter((w) => w.url.toLowerCase().includes(value.toLowerCase())));
    } else {
      setFilteredWebsites(websites);
    }
    setShowUrlDropdown(true);
  };

  const handleModalKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleAddTask();
    }
  };

  const handleRunEval = async (evalItem: EvalItem) => {
    try {
      const res = await fetch(`${apiUrl}/evals/${evalItem.evalId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const runId = data.runId;

      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        "",
        { evalMode: true, evalId: evalItem.evalId, runId },
        `/evals/${evalItem.evalId}/run`
      );
    } catch (err) {
      console.error("Failed to run eval:", err);
    }
  };

  const filtered = evals.filter(
    (e) => e.prompt.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Evals</h1>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg
            border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium">
            <FontAwesomeIcon icon={faCoins} className="text-xs" />
            <span>0.00 Credits</span>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-12 lg:px-24 xl:px-40 py-8">
          {/* Search + Add Task row */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-white dark:bg-dark-surface flex-1
              border border-gray-200 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-200">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder="Search tasks..."
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-4 h-10 rounded-xl text-sm font-medium flex-shrink-0
                bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-105 transition-all duration-300"
            >
              <FontAwesomeIcon icon={faPlus} className="text-xs" />
              Add Task
            </button>
          </div>

          {/* Task list */}
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading tasks...</p>
            </div>
          ) : filtered.length === 0 && !search ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-primary shadow-glow mb-4">
                <FontAwesomeIcon icon={faClipboardCheck} className="text-white text-xl" />
              </div>
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                No tasks yet. Click "Add Task" to create one.
              </p>
            </div>
          ) : filtered.length === 0 && search ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-gray-500 dark:text-gray-400 text-sm">No tasks matching "{search}"</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {filtered.map((evalItem) => (
                <div
                  key={evalItem.evalId}
                  onClick={() => navigate(`/evals/${evalItem.evalId}`)}
                  className="group flex items-center gap-4 bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft
                    hover:shadow-soft-lg hover:border-gray-300 dark:hover:border-gray-600
                    transition-all duration-200 px-6 py-4 cursor-pointer"
                >
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white leading-relaxed">
                      {evalItem.prompt}
                    </p>
                    {evalItem.initialUrl && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-1 font-mono">
                        {evalItem.initialUrl}
                      </p>
                    )}
                  </div>

                  {/* Meta + actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {evalItem.createdAt && (
                      <span className="text-xs text-gray-400 dark:text-gray-600 hidden sm:block whitespace-nowrap mr-1">
                        {formatDate(evalItem.createdAt)}
                      </span>
                    )}

                    {/* Run */}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRunEval(evalItem); }}
                      className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                        bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-105 transition-all duration-200"
                      title="Run this task"
                    >
                      <FontAwesomeIcon icon={faPlay} className="text-[10px]" />
                      Run
                    </button>

                    {/* Delete */}
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeletingEvalId(evalItem.evalId); }}
                      className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium
                        text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-dark-border
                        hover:text-red-500 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-500/30
                        hover:bg-red-50 dark:hover:bg-red-500/10 transition-all duration-200"
                      title="Delete"
                    >
                      <FontAwesomeIcon icon={faTrash} className="text-[10px]" />
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation */}
      {deletingEvalId && (
        <ConfirmModal
          title="Delete Task"
          message="Are you sure you want to delete this task and all its runs? This action cannot be undone."
          onConfirm={() => { handleDelete(deletingEvalId); setDeletingEvalId(null); }}
          onCancel={() => setDeletingEvalId(null)}
        />
      )}

      {/* Add Task Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowAddModal(false)} />
          <div className="relative w-full max-w-lg mx-4 bg-white dark:bg-dark-surface rounded-2xl shadow-xl
            border border-gray-200 dark:border-dark-border p-6">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Add Task</h3>

            {/* Prompt */}
            <textarea
              className="border border-gray-200 dark:border-dark-border rounded-xl outline-none w-full resize-none
                text-gray-900 dark:text-white bg-gray-50 dark:bg-dark-bg p-3 text-sm
                placeholder:text-gray-400 scrollbar-thin
                focus:border-gray-300 dark:focus:border-gray-600 transition-colors"
              placeholder="Describe the task to evaluate..."
              rows={3}
              value={prompt}
              onChange={handlePromptChange}
              onKeyDown={handleModalKeyDown}
              autoFocus
              style={{ minHeight: "4rem", maxHeight: "10rem", overflowY: "auto" }}
            />

            {/* URL input */}
            <div className="relative mt-3" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-gray-50 dark:bg-dark-bg
                border border-gray-200 dark:border-dark-border
                focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-colors">
                <FontAwesomeIcon icon={faGlobe} className="text-gray-400 text-sm" />
                <input
                  type="text"
                  placeholder="Website URL (optional)..."
                  className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                  value={initialUrl}
                  onChange={handleUrlChange}
                  onFocus={() => setShowUrlDropdown(true)}
                />
                <button
                  type="button"
                  onClick={() => setShowUrlDropdown(!showUrlDropdown)}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                >
                  <FontAwesomeIcon icon={faAngleDown} className="text-xs" />
                </button>
              </div>
              {showUrlDropdown && (
                <div className="absolute z-20 mt-1 w-full rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg
                  border border-gray-200 dark:border-dark-border overflow-hidden">
                  <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                    {filteredWebsites.map((website) => (
                      <div
                        key={website.url}
                        className="cursor-pointer p-2.5 rounded-lg flex items-center hover:bg-gradient-primary hover:text-white
                          text-gray-700 dark:text-gray-200 transition-colors duration-200"
                        onClick={() => { setInitialUrl(website.url); setShowUrlDropdown(false); }}
                      >
                        <img alt="" src={website.favicon} className="w-5 h-5 rounded me-2.5" />
                        <span className="text-sm font-medium">{website.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => setShowAddModal(false)}
                className="flex-1 h-10 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-300
                  bg-gray-100 dark:bg-dark-border hover:bg-gray-200 dark:hover:bg-dark-border/80 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddTask}
                disabled={!prompt.trim() || submitting}
                className={`flex-1 h-10 rounded-xl text-sm font-medium transition-all duration-300
                  ${prompt.trim() && !submitting
                    ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg"
                    : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                  }`}
              >
                {submitting ? "Adding..." : "Add Task"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
