import React, { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSelector, useDispatch } from "react-redux";
import { v4 as uuidv4 } from "uuid";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faWandMagicSparkles,
  faPlay,
  faPen,
  faTrash,
  faChevronDown,
  faChevronRight,
  faArrowLeft,
  faSpinner,
  faCoins,
} from "@fortawesome/free-solid-svg-icons";
import { Skill, SkillParameter } from "../utils/types";
import { useToast } from "../components/common/toast";
import { resetSocket, setSessionInfo, setContextId } from "../redux/socketSlice";
import { resetChat, addTask } from "../redux/chatSlice";
import { initializeSocket } from "../utils/socket";
import { checkBackendHealth } from "../utils/health";
import { AppDispatch } from "../redux/store";
import ConvertToSkillModal from "../components/session/convert-to-skill-modal";
import ConfirmModal from "../components/common/confirm-modal";

const apiUrl = process.env.REACT_APP_API_URL;

interface Profile {
  id: string;
  name: string;
  contextId: string;
  createdAt: string;
}

function applyParams(text: string, overrides: Record<string, string>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (match, name) => overrides[name] || match);
}

export default function SkillDetail() {
  const { skillId } = useParams<{ skillId: string }>();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { showToast } = useToast();
  const user = useSelector((state: any) => state.user);

  const [skill, setSkill] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);

  const [expandedActions, setExpandedActions] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!user.email) return;
    fetchSkill();
    fetchProfiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email, skillId]);

  const fetchSkill = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/skills?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const found = (data.skills || []).find((s: Skill) => s.skillId === skillId);
      if (!found) { navigate("/skills"); return; }
      setSkill(found);
      const defaults: Record<string, string> = {};
      (found.parameters || []).forEach((p: SkillParameter) => {
        defaults[p.name] = p.defaultValue || "";
      });
      setParamValues(defaults);
    } catch (err) {
      console.error("Failed to fetch skill:", err);
      navigate("/skills");
    } finally {
      setLoading(false);
    }
  };

  const fetchProfiles = async () => {
    try {
      const res = await fetch(`${apiUrl}/profiles?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) return;
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch (err) {
      console.error("Failed to fetch profiles:", err);
    }
  };

  const handleDelete = async () => {
    if (!skill) return;
    setDeleting(true);
    try {
      const res = await fetch(`${apiUrl}/skills/${skill.skillId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      showToast("Skill deleted", "success");
      navigate("/skills");
    } catch (err) {
      console.error("Delete failed:", err);
      showToast("Failed to delete skill", "error");
      setDeleting(false);
    }
  };

  const handleRun = async () => {
    if (!skill) return;

    const healthy = await checkBackendHealth();
    if (!healthy) {
      showToast("Unable to reach the server. Please try again later.", "error");
      return;
    }

    const profile = profiles.find((p) => p.id === selectedProfileId);
    const contextId = profile?.contextId || "";

    // Resolve {{params}} in action args
    const resolvedActions = skill.actions.map((a: any) => ({
      action: a.action,
      args: Object.fromEntries(
        Object.entries(a.args || {}).map(([k, v]) => [k, typeof v === "string" ? applyParams(v, paramValues) : v])
      ),
    }));

    // Determine initial URL from first navigate action, or duckduckgo
    const firstNav = resolvedActions.find((a: any) => a.action === "browser.navigate");
    const initialUrl: string = String(firstNav?.args?.url || "https://duckduckgo.com");

    // Set up session (same pattern as useStartSession)
    dispatch(resetSocket());
    dispatch(resetChat());
    dispatch(addTask(`Skill: ${skill.name}`));

    const sessionId = uuidv4();
    dispatch(setSessionInfo({ sessionId, prompt: `Skill: ${skill.name}`, initialUrl }));
    if (contextId) dispatch(setContextId(contextId));

    const socket = initializeSocket(dispatch, false, initialUrl);
    socket.emit("play-actions", {
      actions: resolvedActions,
      initial_url: initialUrl,
      context_id: contextId,
      delay: 1.0,
    });

    navigate(`/session/${sessionId}`, { state: { activeSessionId: sessionId } });
  };

  const toggleAction = (i: number) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-dark-bg">
        <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
      </div>
    );
  }

  if (!skill) return null;

  const allParamsFilled = skill.parameters.every((p) => paramValues[p.name]?.trim());

  return (
    <div className="w-full h-full flex relative overflow-hidden bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">

        {/* Top header — same as skills list */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Skills</h1>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg
            border border-gray-200 dark:border-dark-border text-gray-600 dark:text-gray-300 text-sm font-medium">
            <FontAwesomeIcon icon={faCoins} className="text-xs" />
            <span>0.00 Credits</span>
          </div>
        </div>

        {/* Skill info bar — full width */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-dark-border
          bg-white/60 dark:bg-dark-surface/40 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => navigate("/skills")}
              className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-400 hover:text-gray-600
                dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors flex-shrink-0">
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-primary shadow-glow flex-shrink-0">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-white text-sm" />
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white truncate">{skill.name}</h2>
              {skill.goal && (
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{skill.goal}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={() => setEditing(true)}
              className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium text-gray-500 dark:text-gray-400
                border border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-border transition-colors">
              <FontAwesomeIcon icon={faPen} className="text-[10px]" />
              Edit
            </button>
            <button onClick={() => setConfirmDelete(true)} disabled={deleting}
              className="flex items-center gap-1.5 px-3 h-8 rounded-lg text-xs font-medium text-red-500
                border border-red-200 dark:border-red-500/30 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
              {deleting
                ? <FontAwesomeIcon icon={faSpinner} className="text-[10px] animate-spin" />
                : <FontAwesomeIcon icon={faTrash} className="text-[10px]" />}
              Delete
            </button>
          </div>
        </div>

        {/* Body — equal-width split */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 overflow-auto px-6 py-6 gap-6">

          {/* Left panel — Parameters + Profile + Run */}
          <div className="md:overflow-y-auto scrollbar-thin bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border shadow-soft">
            <div className="p-6 space-y-6">

              {/* Instructions preview */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Instructions
                </label>
                <div className="px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-dark-bg/50 border border-gray-200 dark:border-dark-border">
                  <p className="text-xs font-mono text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
                    {applyParams(skill.instructions, paramValues)}
                  </p>
                </div>
              </div>

              {/* Parameters */}
              {skill.parameters.length > 0 && (
                <div className="space-y-3">
                  <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Parameters
                  </label>
                  <div className="space-y-3">
                    {skill.parameters.map((param) => (
                      <div key={param.name} className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-primary bg-primary/10 px-2 py-0.5 rounded-md border border-primary/20">
                            {"{{"}{param.name}{"}}"}
                          </span>
                          {param.description && (
                            <span className="text-[11px] text-gray-400 dark:text-gray-500">{param.description}</span>
                          )}
                        </div>
                        <input
                          type="text"
                          value={paramValues[param.name] || ""}
                          onChange={(e) => setParamValues((prev) => ({ ...prev, [param.name]: e.target.value }))}
                          placeholder={param.defaultValue || `Enter ${param.name}`}
                          className="w-full h-9 px-3 rounded-lg bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                            text-sm text-gray-900 dark:text-white placeholder:text-gray-400 font-mono
                            outline-none focus:border-primary/50 transition-colors bg-gray-50 dark:bg-dark-bg/50"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Profile selection */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Profile
                </label>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setProfileDropdownOpen((v) => !v)}
                    className="w-full h-9 px-3 rounded-lg bg-gray-50 dark:bg-dark-bg/50 border border-gray-200 dark:border-dark-border
                      text-sm text-left flex items-center justify-between
                      outline-none focus:border-primary/50 transition-colors cursor-pointer"
                  >
                    <span className={selectedProfileId
                      ? "text-gray-900 dark:text-white"
                      : "text-gray-400"}>
                      {selectedProfileId
                        ? profiles.find((p) => p.id === selectedProfileId)?.name || "Unknown"
                        : "No profile (fresh session)"}
                    </span>
                    <FontAwesomeIcon
                      icon={faChevronDown}
                      className={`text-[10px] text-gray-400 transition-transform duration-200 ${profileDropdownOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                  {profileDropdownOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setProfileDropdownOpen(false)} />
                      <div className="absolute top-full left-0 right-0 mt-1 z-20 rounded-lg bg-white dark:bg-dark-surface
                        border border-gray-200 dark:border-dark-border shadow-lg overflow-hidden">
                        <button
                          type="button"
                          onClick={() => { setSelectedProfileId(""); setProfileDropdownOpen(false); }}
                          className={`w-full text-left px-3 py-2 text-sm transition-colors
                            ${!selectedProfileId
                              ? "bg-primary/5 text-primary font-medium"
                              : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                        >
                          No profile (fresh session)
                        </button>
                        {profiles.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => { setSelectedProfileId(p.id); setProfileDropdownOpen(false); }}
                            className={`w-full text-left px-3 py-2 text-sm transition-colors
                              ${selectedProfileId === p.id
                                ? "bg-primary/5 text-primary font-medium"
                                : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                          >
                            {p.name}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">
                  Select a profile to reuse saved browser state (cookies, logins).
                </p>
              </div>

              {/* Run button */}
              <button
                onClick={handleRun}
                disabled={skill.parameters.length > 0 && !allParamsFilled}
                className={`w-full flex items-center justify-center gap-2 h-11 rounded-xl text-sm font-semibold transition-all duration-200
                  ${skill.parameters.length === 0 || allParamsFilled
                    ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-[1.02] cursor-pointer"
                    : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                  }`}
              >
                <FontAwesomeIcon icon={faPlay} className="text-xs" />
                Run Skill
              </button>
            </div>
          </div>

          {/* Right panel — Actions list */}
          <div className="md:overflow-y-auto scrollbar-thin bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border shadow-soft">
            <div className="p-6 space-y-3">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Actions ({skill.actions.length})
              </label>

              {skill.actions.length === 0 ? (
                <div className="flex items-center justify-center py-16">
                  <p className="text-sm text-gray-400 dark:text-gray-500">No actions recorded for this skill.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {skill.actions.map((action: any, ai: number) => {
                    const argEntries = Object.entries(action.args || {});
                    const isExpanded = expandedActions.has(ai);
                    const argSummary = argEntries
                      .map(([, v]) => applyParams(String(v), paramValues))
                      .filter(Boolean)
                      .join(", ");

                    return (
                      <div key={ai} className="rounded-xl border border-gray-200 dark:border-dark-border
                        bg-gray-50 dark:bg-dark-bg/50 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => toggleAction(ai)}
                          className="w-full flex items-center gap-2.5 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-dark-bg/50 transition-colors text-left"
                        >
                          <FontAwesomeIcon
                            icon={isExpanded ? faChevronDown : faChevronRight}
                            className="text-[9px] text-gray-400 flex-shrink-0"
                          />
                          <span className="text-xs text-gray-400 font-mono w-5 text-right flex-shrink-0">{ai + 1}.</span>
                          <span className="text-sm font-mono font-semibold text-primary flex-shrink-0">{action.action}</span>
                          {!isExpanded && argSummary && (
                            <span className="text-xs text-gray-400 dark:text-gray-500 truncate ml-1">{argSummary}</span>
                          )}
                        </button>

                        {isExpanded && argEntries.length > 0 && (
                          <div className="px-4 pb-3 pt-2 border-t border-gray-100 dark:border-dark-border space-y-1.5">
                            {argEntries.map(([key, rawVal]) => {
                              const raw = String(rawVal);
                              const resolved = applyParams(raw, paramValues);
                              const isParameterized = /\{\{\w+\}\}/.test(raw);
                              return (
                                <div key={key} className="flex items-baseline gap-2">
                                  <span className="text-[11px] text-gray-400 font-mono whitespace-nowrap flex-shrink-0">
                                    {key}:
                                  </span>
                                  <div className="min-w-0">
                                    <span className={`text-xs font-mono break-all leading-[18px] ${isParameterized ? "text-primary" : "text-gray-600 dark:text-gray-300"}`}>
                                      {raw}
                                    </span>
                                    {isParameterized && resolved !== raw && (
                                      <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono mt-0.5 break-all">
                                        → {resolved}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {confirmDelete && (
        <ConfirmModal
          title="Delete Skill"
          message={`Are you sure you want to delete "${skill.name}"? This action cannot be undone.`}
          onConfirm={() => { setConfirmDelete(false); handleDelete(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      {/* Edit modal */}
      {editing && (
        <ConvertToSkillModal
          onClose={() => setEditing(false)}
          userEmail={user.email || ""}
          skillId={skill.skillId}
          skillName={skill.name}
          skillGoal={skill.goal}
          skillInstructions={skill.instructions}
          initialActions={skill.actions}
          onSaved={() => { setEditing(false); fetchSkill(); }}
        />
      )}
    </div>
  );
}
