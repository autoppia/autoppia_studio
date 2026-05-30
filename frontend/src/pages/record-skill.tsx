import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useSelector } from "react-redux";
import { io, Socket } from "socket.io-client";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircle,
  faStop,
  faChevronDown,
  faChevronRight,
  faArrowLeft,
} from "@fortawesome/free-solid-svg-icons";
import BrowserLoading from "../components/session/browser-loading";
import BrowserTabs from "../components/session/browser-tabs";
import ConvertToSkillModal from "../components/session/convert-to-skill-modal";
import type { BrowserTab } from "../redux/socketSlice";

const apiUrl = process.env.REACT_APP_API_URL;

interface RecordedAction {
  action: string;
  args: Record<string, any>;
  index: number;
}

export default function RecordSkill() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useSelector((state: any) => state.user);

  const skillName = (location.state as any)?.skillName || "";
  const skillGoal = (location.state as any)?.skillGoal || "";
  const initialUrl = (location.state as any)?.initialUrl || "";
  const contextId = (location.state as any)?.contextId || "";

  const [liveUrl, setLiveUrl] = useState<string | null>(null);
  const [actions, setActions] = useState<RecordedAction[]>([]);
  const [recording, setRecording] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [finalActions, setFinalActions] = useState<any[]>([]);
  const [expandedActions, setExpandedActions] = useState<Set<number>>(new Set());
  const [elapsed, setElapsed] = useState(0);
  const [tabs, setTabs] = useState<BrowserTab[]>([]);
  const [activeTabIndex, setActiveTabIndex] = useState(0);

  const socketRef = useRef<Socket | null>(null);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const actionsEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to latest action
  useEffect(() => {
    if (actionsEndRef.current) {
      actionsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [actions.length]);

  // Start recording on mount
  useEffect(() => {
    const socket = io(`${apiUrl}`, { timeout: 60000, reconnection: false });
    socketRef.current = socket;

    socket.on("connect", () => {
      setRecording(true);
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);

      socket.emit("start-record", {
        initial_url: initialUrl,
        context_id: contextId,
      });
    });

    socket.on("live_url", ({ url }) => {
      setLiveUrl(url);
    });

    socket.on("tabs", ({ tabs: tabsData, activeIndex }) => {
      setTabs(tabsData || []);
      setActiveTabIndex(activeIndex || 0);
      if (tabsData && tabsData[activeIndex]) {
        setLiveUrl(tabsData[activeIndex].debugger_fullscreen_url);
      }
    });

    socket.on("recorded-action", (data: RecordedAction) => {
      setActions((prev) => [...prev, data]);
    });

    socket.on("record-result", ({ actions: recordedActions }) => {
      setStopping(false);
      setRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
      // Convert to skill action format
      const skillActions = (recordedActions || []).map((a: any) => ({
        action: a.action,
        args: a.args || {},
      }));
      setFinalActions(skillActions);
      setShowSaveModal(true);
    });

    socket.on("error", ({ message }) => {
      console.error("Recording error:", message);
      setStopping(false);
    });

    socket.on("disconnect", () => {
      setRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    });

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      socket.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStop = useCallback(() => {
    if (!socketRef.current) return;
    setStopping(true);
    socketRef.current.emit("stop-record");
  }, []);

  const handleSelectTab = useCallback((index: number) => {
    if (!socketRef.current) return;
    setActiveTabIndex(index);
    if (tabs[index]?.debugger_fullscreen_url) {
      setLiveUrl(tabs[index].debugger_fullscreen_url);
    }
    socketRef.current.emit("switch-tab-record", { index });
  }, [tabs]);

  const handleNewTab = useCallback(() => {
    if (!socketRef.current) return;
    socketRef.current.emit("new-tab-record");
  }, []);

  const toggleAction = (i: number) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="w-full h-full flex relative overflow-hidden bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/skills/create")}
              className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400
                hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
            >
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Record Skill</h1>
          </div>
          <div className="flex items-center gap-4">
            {/* Recording indicator */}
            {recording && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30">
                <FontAwesomeIcon icon={faCircle} className="text-red-500 text-[8px] animate-pulse" />
                <span className="text-xs font-medium text-red-600 dark:text-red-400">
                  Recording {formatTime(elapsed)}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left — Live browser */}
          <div className="flex-1 flex flex-col min-w-0 p-4">
            <div className="flex-1 rounded-xl overflow-hidden border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-soft flex flex-col">
              {/* Browser tabs */}
              {tabs.length > 0 && (
                <BrowserTabs
                  tabs={tabs}
                  activeIndex={activeTabIndex}
                  onSelectTab={handleSelectTab}
                  onNewTab={handleNewTab}
                  compact
                />
              )}
              {/* Browser iframe */}
              <div className="flex-1 min-h-0">
                {liveUrl ? (
                  <iframe
                    src={liveUrl}
                    title="Record browser session"
                    allow="clipboard-read; clipboard-write"
                    className="w-full h-full border-0"
                  />
                ) : (
                  <BrowserLoading minHeight="400px" />
                )}
              </div>
            </div>
          </div>

          {/* Right — Actions sidebar */}
          <div className="w-80 flex-shrink-0 border-l border-gray-200 dark:border-dark-border
            bg-white/80 dark:bg-dark-surface/80 backdrop-blur-sm flex flex-col">

            {/* Sidebar header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-dark-border">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Actions ({actions.length})
              </span>
            </div>

            {/* Actions list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-2 space-y-1.5">
              {actions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center px-4">
                  <p className="text-sm text-gray-400 dark:text-gray-500">
                    Interact with the browser to record actions.
                  </p>
                </div>
              ) : (
                actions.map((a, i) => {
                  const argEntries = Object.entries(a.args || {});
                  const isExpanded = expandedActions.has(i);
                  const argSummary = argEntries.map(([, v]) => String(v)).filter(Boolean).join(", ");

                  return (
                    <div key={i} className="rounded-lg border border-gray-200 dark:border-dark-border
                      bg-gray-50 dark:bg-dark-bg/50 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => toggleAction(i)}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-100 dark:hover:bg-dark-bg/80 transition-colors text-left"
                      >
                        <FontAwesomeIcon
                          icon={isExpanded ? faChevronDown : faChevronRight}
                          className="text-[8px] text-gray-400 flex-shrink-0"
                        />
                        <span className="text-[11px] text-gray-400 font-mono w-4 text-right flex-shrink-0">{i + 1}.</span>
                        <span className="text-xs font-mono font-semibold text-primary truncate">{a.action}</span>
                        {!isExpanded && argSummary && (
                          <span className="text-[10px] text-gray-400 truncate ml-auto max-w-[100px]">{argSummary}</span>
                        )}
                      </button>
                      {isExpanded && argEntries.length > 0 && (
                        <div className="px-3 pb-2 pt-1 border-t border-gray-100 dark:border-dark-border space-y-1">
                          {argEntries.map(([key, val]) => (
                            <div key={key} className="flex items-baseline gap-1.5">
                              <span className="text-[10px] text-gray-400 font-mono whitespace-nowrap flex-shrink-0">{key}:</span>
                              <span className="text-[10px] text-gray-600 dark:text-gray-300 font-mono break-all">{String(val)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
              <div ref={actionsEndRef} />
            </div>

            {/* Finish button */}
            <div className="p-4 border-t border-gray-200 dark:border-dark-border">
              <button
                onClick={handleStop}
                disabled={stopping || !recording}
                className={`w-full flex items-center justify-center gap-2 h-10 rounded-xl text-sm font-semibold transition-all duration-200
                  ${recording && !stopping
                    ? "bg-red-500 hover:bg-red-600 text-white cursor-pointer"
                    : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                  }`}
              >
                <FontAwesomeIcon icon={faStop} className="text-xs" />
                {stopping ? "Stopping..." : "Finish Recording"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Save as skill modal */}
      {showSaveModal && (
        <ConvertToSkillModal
          onClose={() => {
            setShowSaveModal(false);
            navigate("/skills");
          }}
          userEmail={user.email || ""}
          initialActions={finalActions}
          prompt=""
          initialUrl={initialUrl}
          skillName={skillName}
          skillGoal={skillGoal}
          onSaved={() => {
            setShowSaveModal(false);
            navigate("/skills");
          }}
        />
      )}
    </div>
  );
}
