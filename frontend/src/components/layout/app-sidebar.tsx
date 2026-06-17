import { useState, useCallback, useEffect, useRef, forwardRef, useImperativeHandle, FormEvent } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useNavigate, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faHome,
  faPenToSquare,
  faClock,
  faUser,
  faCircleHalfStroke,
  faRightFromBracket,
  faGear,
  faClipboardCheck,
  faClipboardList,
  faRobot,
  faCircleNodes,
  faDiagramProject,
  faFileLines,
  faLock,
  faTrash,
  faXmark,
  faEye,
  faEyeSlash,
  faWallet,
  faSpinner,
} from "@fortawesome/free-solid-svg-icons";

import { logout } from "../../redux/userSlice";
import ConfirmModal from "../common/confirm-modal";
import { useToast } from "../common/toast";

import { HistoryItem } from "../../utils/types";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

const COLLAPSED_WIDTH = 56;
const EXPANDED_WIDTH = 232;

export interface AppSidebarHandle {
  addHistoryItem: (item: HistoryItem) => void;
}

interface AppSidebarProps {
  onExpandChange?: (expanded: boolean) => void;
}

/** Typewriter text — reveals characters one by one, then calls onComplete. */
function TypewriterText({ text, speed = 30, onComplete }: { text: string; speed?: number; onComplete?: () => void }) {
  const [displayed, setDisplayed] = useState("");
  const indexRef = useRef(0);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    indexRef.current = 0;
    setDisplayed("");
    const interval = setInterval(() => {
      indexRef.current++;
      if (indexRef.current >= text.length) {
        setDisplayed(text);
        clearInterval(interval);
        onCompleteRef.current?.();
      } else {
        setDisplayed(text.slice(0, indexRef.current));
      }
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed]);

  return <>{displayed}<span className="animate-pulse">|</span></>;
}

function ChangePasswordModal({ email, onClose }: { email: string; onClose: () => void }) {
  const { showToast } = useToast();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword || submitting) return;

    if (newPassword.length < 6) {
      showToast("New password must be at least 6 characters", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("Passwords do not match", "error");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, current_password: currentPassword, new_password: newPassword }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Failed to change password", "error");
        return;
      }
      showToast("Password changed successfully", "success");
      onClose();
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = `w-full px-4 py-2.5 pr-10 rounded-xl border border-gray-200 dark:border-zinc-800/80
    bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
    placeholder-gray-400 dark:placeholder-gray-500 outline-none
    focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm mx-4 bg-white dark:bg-zinc-900/70 rounded-2xl shadow-xl border border-gray-200 dark:border-zinc-800/80 p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">Change Password</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          >
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: "Current Password", value: currentPassword, setValue: setCurrentPassword, show: showCurrent, setShow: setShowCurrent, placeholder: "Enter current password", autoFocus: true },
            { label: "New Password", value: newPassword, setValue: setNewPassword, show: showNew, setShow: setShowNew, placeholder: "At least 6 characters", autoFocus: false },
            { label: "Confirm New Password", value: confirmPassword, setValue: setConfirmPassword, show: showConfirm, setShow: setShowConfirm, placeholder: "Repeat new password", autoFocus: false },
          ].map(({ label, value, setValue, show, setShow, placeholder, autoFocus }) => (
            <div key={label}>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">{label}</label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={placeholder}
                  autoFocus={autoFocus}
                  className={inputClass}
                />
                <button
                  type="button"
                  onClick={() => setShow((v: boolean) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <FontAwesomeIcon icon={show ? faEyeSlash : faEye} className="text-sm" />
                </button>
              </div>
            </div>
          ))}

          <button
            type="submit"
            disabled={!currentPassword || !newPassword || !confirmPassword || submitting}
            className="w-full h-10 rounded-xl text-sm font-medium text-white bg-gradient-primary
              disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
          >
            {submitting ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : "Change Password"}
          </button>
        </form>
      </div>
    </div>
  );
}

const AppSidebar = forwardRef<AppSidebarHandle, AppSidebarProps>(function AppSidebar({ onExpandChange }, ref) {
  const [expanded, setExpanded] = useState(false);
  const [histories, setHistories] = useState<HistoryItem[]>([]);
  const [historiesLoaded, setHistoriesLoaded] = useState(false);
  const [animatingId, setAnimatingId] = useState<string | null>(null);
  const [profilePanelOpen, setProfilePanelOpen] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const [confirmDeleteChats, setConfirmDeleteChats] = useState(false);
  const { showToast } = useToast();

  useImperativeHandle(ref, () => ({
    addHistoryItem: (item: HistoryItem) => {
      setHistories((prev) => {
        if (prev.some((h) => h.sessionId === item.sessionId)) return prev;
        return [item, ...prev];
      });
      setAnimatingId(item.sessionId);
    },
  }), []);

  const handleTypewriterComplete = useCallback(() => {
    setAnimatingId(null);
  }, []);

  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const user = useSelector((state: any) => state.user);

  const updateExpanded = (next: boolean) => {
    setExpanded(next);
    onExpandChange?.(next);
  };

  const toggleExpanded = () => {
    const next = !expanded;
    updateExpanded(next);
    if (next && !historiesLoaded) {
      loadHistories();
    }
  };

  const loadHistories = async () => {
    if (!user.email) return;
    try {
      const response = await fetch(`${apiUrl}/sessions?email=${user.email}`);
      const data = await response.json();
      setHistories(data.sessions || []);
      setHistoriesLoaded(true);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteAllChats = async () => {
    setConfirmDeleteChats(false);
    try {
      const res = await fetch(`${apiUrl}/sessions/all?email=${user.email}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Failed to delete chats", "error");
        return;
      }
      setHistories([]);
      setHistoriesLoaded(false);
      showToast("All chats deleted", "success");
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    }
  };

  const handleNewSession = () => {
    navigate("/");
  };

  const handleGoHome = () => {
    window.location.href = "https://autoppia.com/";
  };

  const darkThemeHandler = () => {
    const isDark = document.documentElement.classList.toggle("dark");
    try {
      localStorage.setItem("theme", isDark ? "dark" : "light");
    } catch {
      /* ignore storage errors */
    }
  };

  const getRelativeDate = (dateString: string | Date) => {
    const now = new Date();
    const past = new Date(dateString);
    const days = (now.getTime() - past.getTime()) / (24 * 60 * 60 * 1000);
    if (days < 1) return "Today";
    if (days < 30) return `${Math.floor(days)}d ago`;
    return "Months ago";
  };

  const isOnHome = location.pathname === "/";
  const isOnSettings = location.pathname === "/settings";
  const isOnEvals = location.pathname.startsWith("/evals");
  const isOnAgents = location.pathname.startsWith("/agents");
  const isOnWork = location.pathname.startsWith("/work");
  const isOnConnectors = location.pathname.startsWith("/connectors");
  const isOnCapabilities = location.pathname.startsWith("/capabilities");
  const isOnKnowledge = location.pathname.startsWith("/knowledge");

  return (
    <>
      {/* Backdrop for mobile when expanded */}
      {expanded && (
        <div
          className="fixed inset-0 bg-black/30 z-20 lg:hidden"
          onClick={() => updateExpanded(false)}
        />
      )}

      <div
        className="fixed left-0 top-0 h-full z-30 flex flex-col
          bg-white dark:bg-dark-bg border-r border-gray-200 dark:border-dark-border
          transition-all duration-300 overflow-hidden"
        style={{ width: expanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH }}
      >
        {/* Top section */}
        <div className="flex flex-col flex-shrink-0">
          {/* Logo / toggle */}
          <div className={`flex items-center h-14 ${expanded ? "px-3" : "px-2 justify-center"}`}>
            {expanded ? (
              // Autoppia Studio wordmark (from studio refactor). Click to collapse.
              <div
                className="flex items-center gap-2 cursor-pointer"
                onClick={toggleExpanded}
                title="Autoppia Studio — click to collapse"
              >
                {/* Dark: the white Autoppia Studio wordmark from the refactor reads well on dark. */}
                <img
                  src="/assets/images/logos/autoppia-studio.webp"
                  alt="Autoppia Studio"
                  className="hidden h-10 w-auto object-contain dark:block"
                />
                {/* Light: the white wordmark is invisible/muddy, so use the colored icon + dark text. */}
                <img
                  src="/assets/images/logos/main.webp"
                  alt="Autoppia"
                  className="block h-8 w-8 flex-shrink-0 rounded-full dark:hidden"
                />
                <span className="block text-[15px] font-semibold tracking-tight text-gray-900 dark:hidden">
                  Autoppia
                </span>
                <span className="flex-shrink-0 self-center rounded-md bg-primary/15 px-1.5 py-0.5 text-[9px] font-bold uppercase leading-none tracking-wider text-primary">
                  Studio
                </span>
              </div>
            ) : (
              <button
                onClick={toggleExpanded}
                className="flex items-center justify-center w-9 h-9 rounded-lg
                  hover:bg-gray-100 dark:hover:bg-white/5
                  transition-colors duration-200"
              >
                <img
                  src="/assets/images/logos/main.webp"
                  alt="Autoppia"
                  className="w-8 h-8 rounded-full"
                />
              </button>
            )}
          </div>

          {/* New session button */}
          <div className={`px-2 mt-3 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={handleNewSession}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-white/5
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}
                ${isOnHome ? "bg-gray-100 dark:bg-zinc-900/70" : ""}`}
              title="New session"
            >
              <FontAwesomeIcon icon={faPenToSquare} className="text-sm" />
              {expanded && <span className="text-sm font-medium">New Session</span>}
            </button>
          </div>

          {/* Connectors button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/connectors")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnConnectors
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Connectors"
            >
              <FontAwesomeIcon icon={faCircleNodes} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Connectors</span>}
            </button>
          </div>

          {/* Capabilities button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/capabilities")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnCapabilities
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Capabilities"
            >
              <FontAwesomeIcon icon={faDiagramProject} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Capabilities</span>}
            </button>
          </div>

          {/* Knowledge button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/knowledge")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnKnowledge
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Knowledge"
            >
              <FontAwesomeIcon icon={faFileLines} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Knowledge</span>}
            </button>
          </div>

          {/* Agents button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/agents")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                  ${isOnAgents
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Agents"
            >
              <FontAwesomeIcon icon={faRobot} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Agents</span>}
            </button>
          </div>

          {/* Benchmarks button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/work")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnWork
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Work"
            >
              <FontAwesomeIcon icon={faClipboardList} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Work</span>}
            </button>
          </div>

          {/* Benchmarks button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/evals")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnEvals
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Benchmarks"
            >
              <FontAwesomeIcon icon={faClipboardCheck} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Benchmarks</span>}
            </button>
          </div>

          {/* Settings button */}
          <div className={`px-2 mb-1 ${expanded ? "" : "flex justify-center"}`}>
            <button
              onClick={() => navigate("/settings")}
              className={`flex items-center gap-2 rounded-lg transition-all duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${isOnSettings
                  ? "text-gray-900 dark:text-white bg-gray-100 dark:bg-zinc-900/70"
                  : "text-gray-700 dark:text-zinc-300"}
                ${expanded ? "w-full px-3 py-2" : "w-9 h-9 justify-center"}`}
              title="Settings"
            >
              <FontAwesomeIcon icon={faGear} className="text-sm" />
              {expanded && <span className="text-sm font-medium">Settings</span>}
            </button>
          </div>

          {/* History label (expanded only) */}
          {expanded && (
            <div className="px-4 pt-3 pb-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-zinc-500">
                History
              </span>
            </div>
          )}
        </div>

        {/* Session history list (expanded only) */}
        {expanded && (
          <div className="flex-grow overflow-y-auto px-2 scrollbar-thin">
            {histories.map((item) => {
              const isActive = location.pathname === `/session/${item.sessionId}`;
              const isAnimating = animatingId === item.sessionId;
              return (
                <div
                  key={`sidebar_history_${item.sessionId}`}
                  className={`flex items-center gap-2 px-3 py-2 mb-0.5 rounded-lg cursor-pointer
                    transition-colors duration-200 group
                    ${isAnimating ? "animate-slide-up" : ""}
                    ${isActive
                      ? "bg-gray-100 dark:bg-zinc-900/70 text-gray-900 dark:text-white"
                      : "text-gray-600 dark:text-zinc-400 hover:bg-gray-50 dark:hover:bg-zinc-900/60"
                    }`}
                  onClick={() => item.sessionId && navigate(`/session/${item.sessionId}`)}
                >
                  <FontAwesomeIcon icon={faClock} className="text-[10px] flex-shrink-0 opacity-50" />
                  <div className="flex-grow min-w-0">
                    <p className="text-xs truncate font-medium">
                      {isAnimating
                        ? <TypewriterText text={item.prompt} onComplete={handleTypewriterComplete} />
                        : item.prompt}
                    </p>
                    <p className="text-[10px] truncate opacity-60">{item.initialUrl}</p>
                  </div>
                  {!isAnimating && (
                    <span className="text-[10px] opacity-40 flex-shrink-0 hidden group-hover:block">
                      {getRelativeDate(item.createdAt!)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Collapsed: icon-only nav */}
        {!expanded && (
          <div className="flex flex-col items-center gap-1 px-2 mt-2 flex-grow">
            <button
              onClick={() => { updateExpanded(true); if (!historiesLoaded) loadHistories(); }}
              className="flex items-center justify-center w-9 h-9 rounded-lg
                text-gray-500 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-white/5
                transition-colors duration-200"
              title="History"
            >
              <FontAwesomeIcon icon={faClock} className="text-sm" />
            </button>
          </div>
        )}

        {/* Bottom section */}
        <div className={`flex flex-col flex-shrink-0 border-t border-gray-200 dark:border-zinc-800/80
          ${expanded ? "px-2 py-2 gap-0.5" : "px-2 py-2 items-center gap-1"}`}>
          <button
            onClick={handleGoHome}
            className={`flex items-center gap-2 rounded-lg transition-colors duration-200
              text-gray-500 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-white/5
              ${expanded ? "px-3 py-2" : "w-9 h-9 justify-center"}`}
            title="Autoppia Home"
          >
            <FontAwesomeIcon icon={faHome} className="text-sm" />
            {expanded && <span className="text-xs">Autoppia Home</span>}
          </button>
          <button
            onClick={darkThemeHandler}
            className={`flex items-center gap-2 rounded-lg transition-colors duration-200
              text-gray-500 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-white/5
              ${expanded ? "px-3 py-2" : "w-9 h-9 justify-center"}`}
            title="Toggle theme"
          >
            <FontAwesomeIcon icon={faCircleHalfStroke} className="text-sm" />
            {expanded && <span className="text-xs">Toggle Theme</span>}
          </button>
          {/* Sign out */}
          <button
            onClick={() => dispatch(logout())}
            className={`flex items-center gap-2 rounded-lg transition-colors duration-200
              text-gray-500 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-white/5
              ${expanded ? "px-3 py-2" : "w-9 h-9 justify-center"}`}
            title="Sign out"
          >
            <FontAwesomeIcon icon={faRightFromBracket} className="text-sm" />
            {expanded && <span className="text-xs">Sign Out</span>}
          </button>
          {/* User avatar — opens profile panel */}
          {user.isAuthenticated && (
            <button
              onClick={() => setProfilePanelOpen((v) => !v)}
              className={`flex items-center gap-2 rounded-lg transition-colors duration-200
                hover:bg-gray-100 dark:hover:bg-white/5
                ${expanded ? "px-3 py-2" : "w-9 h-9 justify-center"}
                ${profilePanelOpen ? "bg-gray-100 dark:bg-zinc-900/70" : ""}`}
              title="My profile"
            >
              <div className="flex items-center justify-center w-7 h-7 rounded-full bg-gradient-primary text-white text-xs flex-shrink-0">
                <FontAwesomeIcon icon={faUser} className="text-[10px]" />
              </div>
              {expanded && (
                <span className="text-xs text-gray-600 dark:text-zinc-400 truncate">
                  {user.email.split("@")[0]}
                </span>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Profile panel */}
      {profilePanelOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setProfilePanelOpen(false)} />
          <div
            className="fixed z-50 w-64 bg-white dark:bg-zinc-900/70 rounded-2xl shadow-xl border border-gray-200 dark:border-zinc-800/80 p-4"
            style={{ bottom: 16, left: (expanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH) + 8 }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-primary text-white text-xs flex-shrink-0">
                  <FontAwesomeIcon icon={faUser} className="text-[10px]" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-gray-800 dark:text-gray-100 truncate">
                    {user.email.split("@")[0]}
                  </p>
                  <p className="text-[10px] text-gray-500 dark:text-zinc-400 truncate">{user.email}</p>
                </div>
              </div>
              <button
                onClick={() => setProfilePanelOpen(false)}
                className="w-6 h-6 flex items-center justify-center rounded-md text-gray-400
                  hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors flex-shrink-0"
              >
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>

            <div className="h-px bg-gray-100 dark:bg-zinc-800/80 mb-3" />

            <div className="px-3 py-2.5 rounded-xl bg-gray-50 dark:bg-zinc-950/60 mb-3">
              <div className="flex items-center gap-1.5 mb-0.5">
                <FontAwesomeIcon icon={faWallet} className="text-[10px] text-gray-400" />
                <span className="text-[10px] font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wide">
                  Available Credit
                </span>
              </div>
              <p className="text-lg font-bold text-gray-800 dark:text-gray-100">$0.00</p>
              <p className="text-[10px] text-gray-400 dark:text-zinc-500">Free Beta</p>
            </div>

            <button
              onClick={() => { setProfilePanelOpen(false); setChangePasswordOpen(true); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm
                text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors mb-1"
            >
              <FontAwesomeIcon icon={faLock} className="text-xs" />
              Change Password
            </button>

            <button
              onClick={() => { setProfilePanelOpen(false); setConfirmDeleteChats(true); }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm
                text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
            >
              <FontAwesomeIcon icon={faTrash} className="text-xs" />
              Delete All Chats
            </button>
          </div>
        </>
      )}

      {changePasswordOpen && (
        <ChangePasswordModal email={user.email} onClose={() => setChangePasswordOpen(false)} />
      )}

      {confirmDeleteChats && (
        <ConfirmModal
          title="Delete All Chats"
          message="Are you sure you want to delete all your chat history? This action cannot be undone."
          confirmLabel="Delete All"
          onConfirm={handleDeleteAllChats}
          onCancel={() => setConfirmDeleteChats(false)}
        />
      )}
    </>
  );
});

export default AppSidebar;
export { COLLAPSED_WIDTH, EXPANDED_WIDTH };
