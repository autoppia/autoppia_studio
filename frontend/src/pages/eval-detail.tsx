import React, { useState, useEffect, useCallback } from "react";
import { useSelector } from "react-redux";
import { useParams, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faSpinner,
  faPlay,
  faTrash,
  faCheck,
  faXmark,
  faClipboardCheck,
  faImage,
  faUserCircle,
  faAngleDown,
} from "@fortawesome/free-solid-svg-icons";
import { EvalItem, EvalRun } from "../utils/types";
import ConfirmModal from "../components/common/confirm-modal";
import useStartSession from "../hooks/useStartSession";

const apiUrl = process.env.REACT_APP_API_URL;

interface Profile {
  id: string;
  name: string;
  contextId: string;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function LabelBadge({ label }: { label: string }) {
  if (label === "pass") {
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold
        bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border border-green-200 dark:border-green-500/30">
        <FontAwesomeIcon icon={faCheck} className="text-[10px]" />
        Pass
      </span>
    );
  }
  if (label === "fail") {
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold
        bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border border-red-200 dark:border-red-500/30">
        <FontAwesomeIcon icon={faXmark} className="text-[10px]" />
        Fail
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold
      bg-yellow-50 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-500/30">
      Pending
    </span>
  );
}

export default function EvalDetail() {
  const { evalId } = useParams<{ evalId: string }>();
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const startSession = useStartSession();

  const [evalItem, setEvalItem] = useState<EvalItem | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);

  // Profile selector
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);

  useEffect(() => {
    if (!user.email || !evalId) return;
    fetchData();
    loadProfiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email, evalId]);

  useEffect(() => {
    if (profiles.length > 0 && !selectedProfile) {
      setSelectedProfile(profiles[0]);
    }
  }, [profiles]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchData = async () => {
    setLoading(true);
    try {
      const [evalRes, runsRes] = await Promise.all([
        fetch(`${apiUrl}/evals/${evalId}`),
        fetch(`${apiUrl}/evals/${evalId}/runs`),
      ]);
      if (!evalRes.ok) {
        navigate("/evals");
        return;
      }
      const evalData = await evalRes.json();
      setEvalItem(evalData.eval);

      if (runsRes.ok) {
        const runsData = await runsRes.json();
        setRuns(runsData.runs || []);
      }
    } catch (err) {
      console.error("Failed to load eval:", err);
      navigate("/evals");
    } finally {
      setLoading(false);
    }
  };

  const loadProfiles = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/profiles?email=${user.email}`);
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    }
  }, [user.email]);

  const handleDeleteEval = async () => {
    if (!evalId) return;
    try {
      const res = await fetch(`${apiUrl}/evals/${evalId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      navigate("/evals");
    } catch (err) {
      console.error("Failed to delete eval:", err);
    }
  };

  const handleDeleteRun = async (runId: string) => {
    try {
      const res = await fetch(`${apiUrl}/evals/${evalId}/runs/${runId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setRuns((prev) => prev.filter((r) => r.runId !== runId));
    } catch (err) {
      console.error("Failed to delete run:", err);
    }
  };

  const handleRun = async () => {
    if (!evalItem || !evalId) return;
    const contextId = selectedProfile?.contextId || "";

    // Create a run record first
    try {
      const res = await fetch(`${apiUrl}/evals/${evalId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: "" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const runId = data.runId;

      // Start the session and navigate
      await startSession(
        evalItem.prompt,
        evalItem.initialUrl || "",
        contextId,
        { evalMode: true, evalId, runId },
        `/evals/${evalId}/run`,
        evalItem.operatorId ? { operatorId: evalItem.operatorId, operatorName: evalItem.operatorName || "" } : undefined,
      );
    } catch (err) {
      console.error("Failed to create run:", err);
    }
  };

  const passCount = runs.filter((r) => r.label === "pass").length;
  const failCount = runs.filter((r) => r.label === "fail").length;
  const pendingCount = runs.filter((r) => r.label === "pending").length;

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-dark-bg">
        <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
      </div>
    );
  }

  if (!evalItem) return null;

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Benchmarks</h1>
        </div>

        {/* Task info bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-dark-border
          bg-white/60 dark:bg-dark-surface/40 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <button onClick={() => navigate("/evals")}
              className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-400 hover:text-gray-600
                dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors flex-shrink-0">
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-primary shadow-glow flex-shrink-0">
              <FontAwesomeIcon icon={faClipboardCheck} className="text-white text-sm" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 dark:text-white leading-relaxed truncate">
                {evalItem.prompt}
              </p>
              {evalItem.initialUrl && (
                <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5 font-mono">
                  {evalItem.initialUrl}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 ml-4">
            {/* Profile selector */}
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className="flex items-center gap-2 rounded-xl px-3 h-8 text-xs font-medium transition-all duration-300
                  border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200
                  hover:border-gray-300 dark:hover:border-gray-600"
                onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              >
                <FontAwesomeIcon icon={faUserCircle} className={`text-xs ${selectedProfile ? "text-primary" : "opacity-60"}`} />
                <span className="whitespace-nowrap">{selectedProfile ? selectedProfile.name : "No Profile"}</span>
                <FontAwesomeIcon icon={faAngleDown} className="text-[10px] opacity-60" />
              </button>
              {profileDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setProfileDropdownOpen(false)} />
                  <div className="absolute right-0 z-20 mt-1 w-48 rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg
                    border border-gray-200 dark:border-dark-border overflow-hidden">
                    <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                      {profiles.map((profile) => (
                        <button
                          key={profile.id}
                          className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200
                            hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                          onClick={() => { setSelectedProfile(profile); setProfileDropdownOpen(false); }}
                        >
                          {profile.name}
                        </button>
                      ))}
                      <button
                        className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200
                          hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                        onClick={() => { setSelectedProfile(null); setProfileDropdownOpen(false); }}
                      >
                        No Profile
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>

            <button
              onClick={handleRun}
              className="flex items-center gap-2 px-4 h-8 rounded-xl text-xs font-medium
                bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-105 transition-all duration-200"
            >
              <FontAwesomeIcon icon={faPlay} className="text-[10px]" />
              Run
            </button>
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium text-red-500
                border border-red-200 dark:border-red-500/30 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
            >
              <FontAwesomeIcon icon={faTrash} className="text-[10px]" />
              Delete
            </button>
          </div>
        </div>

        {/* Runs list */}
        <div className="flex-1 overflow-auto px-12 lg:px-24 xl:px-40 py-8">
          {runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gray-100 dark:bg-dark-surface mb-4">
                <FontAwesomeIcon icon={faPlay} className="text-gray-400 text-xl" />
              </div>
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                No runs yet. Click "Run" to start evaluating this task.
              </p>
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-4 mb-4">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Runs ({runs.length})
                </label>
                <div className="flex items-center gap-2 text-xs font-medium">
                  {pendingCount > 0 && (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-yellow-50 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400">
                      {pendingCount} pending
                    </span>
                  )}
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400">
                    <FontAwesomeIcon icon={faCheck} className="text-[10px]" />
                    {passCount}
                  </span>
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400">
                    <FontAwesomeIcon icon={faXmark} className="text-[10px]" />
                    {failCount}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                {runs.map((run, index) => {
                  const screenshots = run.screenshots || [];
                  const lastScreenshot = screenshots.length > 0 ? screenshots[screenshots.length - 1] : null;
                  return (
                    <div
                      key={run.runId}
                      onClick={() => navigate(`/evals/${evalId}/run/${run.sessionId}`, { state: { evalMode: true, evalId, runId: run.runId } })}
                      className="group bg-white dark:bg-dark-surface rounded-xl
                        border border-gray-200 dark:border-dark-border shadow-soft
                        hover:shadow-soft-lg hover:border-gray-300 dark:hover:border-gray-600
                        transition-all duration-200 cursor-pointer overflow-hidden"
                    >
                      {/* Last screenshot as cover */}
                      <div className="w-full aspect-video bg-gray-50 dark:bg-dark-bg overflow-hidden">
                        {lastScreenshot ? (
                          <img
                            src={lastScreenshot.startsWith("data:") ? lastScreenshot : `data:image/png;base64,${lastScreenshot}`}
                            alt="Run screenshot"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <FontAwesomeIcon icon={faImage} className="text-gray-300 dark:text-gray-600 text-2xl" />
                          </div>
                        )}
                      </div>

                      {/* Screenshot thumbnails strip */}
                      {screenshots.length > 1 && (
                        <div className="flex gap-1.5 px-3 pt-2 overflow-x-auto scrollbar-thin">
                          {screenshots.map((src, i) => (
                            <img
                              key={i}
                              src={src.startsWith("data:") ? src : `data:image/png;base64,${src}`}
                              alt={`Step ${i + 1}`}
                              className="h-10 rounded border border-gray-200 dark:border-dark-border flex-shrink-0 object-cover"
                            />
                          ))}
                        </div>
                      )}

                      {/* Info */}
                      <div className="px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-xs text-gray-400 font-mono flex-shrink-0">
                            #{runs.length - index}
                          </span>
                          <LabelBadge label={run.label} />
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {run.createdAt && (
                            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                              {formatDate(run.createdAt)}
                            </span>
                          )}
                          <button
                            onClick={(e) => { e.stopPropagation(); setDeletingRunId(run.runId); }}
                            className="flex items-center justify-center w-7 h-7 rounded-lg
                              text-gray-300 dark:text-gray-600 hover:text-red-500 dark:hover:text-red-400
                              hover:bg-red-50 dark:hover:bg-red-500/10
                              opacity-0 group-hover:opacity-100 transition-all duration-200"
                            title="Delete run"
                          >
                            <FontAwesomeIcon icon={faTrash} className="text-xs" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Delete eval confirmation */}
      {confirmDelete && (
        <ConfirmModal
          title="Delete Task"
          message="Are you sure you want to delete this task and all its runs? This action cannot be undone."
          onConfirm={() => { setConfirmDelete(false); handleDeleteEval(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      {/* Delete run confirmation */}
      {deletingRunId && (
        <ConfirmModal
          title="Delete Run"
          message="Are you sure you want to delete this run? This action cannot be undone."
          onConfirm={() => { handleDeleteRun(deletingRunId); setDeletingRunId(null); }}
          onCancel={() => setDeletingRunId(null)}
        />
      )}
    </div>
  );
}
