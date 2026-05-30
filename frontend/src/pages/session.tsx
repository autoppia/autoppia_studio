import React, { useRef, useState, useEffect, useCallback } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useParams, useNavigate, useOutletContext, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faExpand,
} from "@fortawesome/free-solid-svg-icons";

import ChatSidebar from "../components/session/chat-sidebar";
import BrowserLoading from "../components/session/browser-loading";
import BrowserTabs from "../components/session/browser-tabs";
import ScreenshotStrip from "../components/session/screenshot-strip";
import IconButton from "../components/common/icon-button";
import { setChats, resetChat } from "../redux/chatSlice";
import {
  resetSocket,
  disconnectBrowser,
  setSessionInfo,
  setLastUrl,
  setActionHistory,
  setContextId,
  setOperatorInfo,
  setActiveTabIndex,
  setLiveUrl,
} from "../redux/socketSlice";
import { AppDispatch } from "../redux/store";
import { ChatItem, HistoryItem } from "../utils/types";

const IDLE_TIMEOUT_MS = 2 * 60 * 1000; // 2 minutes

const apiUrl = process.env.REACT_APP_API_URL;

function Session(): React.ReactElement {
  const browserContainerRef = useRef<HTMLDivElement | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { id: sessionId, evalId: evalIdFromParam } = useParams<{ id: string; evalId: string }>();
  const location = useLocation();
  const locationState = location.state as {
    activeSessionId?: string;
    skillMode?: boolean;
    skillName?: string;
    skillGoal?: string;
    skillInstructions?: string;
    evalMode?: boolean;
    evalId?: string;
    runId?: string;
    operatorId?: string;
    operatorName?: string;
  } | null;
  const isEvalMode = locationState?.evalMode || location.pathname.startsWith("/evals/");
  const { addHistoryItem } = useOutletContext<{
    sidebarExpanded: boolean;
    addHistoryItem: (item: HistoryItem) => void;
  }>();

  const [showChatSidebar, setShowChatSidebar] = useState(
    window.screen.width >= 1024,
  );
  const [historySaved, setHistorySaved] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState<number | null>(
    null,
  );
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const chats = useSelector((state: any) => state.chat.chats);
  const completed = useSelector((state: any) => state.chat.completed);
  const socket = useSelector((state: any) => state.socket.socket);
  const socketId = useSelector((state: any) => state.socket.socketId);
  const liveUrl = useSelector((state: any) => state.socket.liveUrl);
  const reduxSessionId = useSelector((state: any) => state.socket.sessionId);
  const prompt = useSelector((state: any) => state.socket.prompt);
  const initialUrl = useSelector((state: any) => state.socket.initialUrl);
  const lastUrl = useSelector((state: any) => state.socket.lastUrl);
  const actionHistory = useSelector((state: any) => state.socket.actionHistory);
  const contextId = useSelector((state: any) => state.socket.contextId);
  const operatorId = useSelector((state: any) => state.socket.operatorId);
  const operatorName = useSelector((state: any) => state.socket.operatorName);
  const tabs = useSelector((state: any) => state.socket.tabs);
  const activeTabIndex = useSelector((state: any) => state.socket.activeTabIndex);
  const user = useSelector((state: any) => state.user);

  const handleSelectTab = (index: number) => {
    dispatch(setActiveTabIndex(index));
    if (tabs[index]?.debugger_fullscreen_url) {
      dispatch(setLiveUrl(tabs[index].debugger_fullscreen_url));
    }
  };

  // Track which session we've already loaded to avoid re-fetching
  const loadedSessionRef = useRef<string | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load old session chat history when navigating to a session
  useEffect(() => {
    if (!sessionId) return;
    // This is the active session we just created — don't overwrite live chats
    if (reduxSessionId === sessionId) return;
    // Session was just launched via useStartSession (activeSessionId in nav state is reliable,
    // unlike reduxSessionId which may not have propagated yet at effect time)
    if (locationState?.activeSessionId === sessionId) {
      loadedSessionRef.current = sessionId;
      return;
    }
    // Already loaded this session's history
    if (loadedSessionRef.current === sessionId) return;

    // Navigating to a different session — clear old state and load
    dispatch(resetChat());
    dispatch(resetSocket());
    setHistorySaved(false);
    loadedSessionRef.current = sessionId;

    const loadSession = async () => {
      try {
        const res = await fetch(`${apiUrl}/sessions/${sessionId}`);
        if (!res.ok) {
          if (res.status === 404) {
            setNotFound(true);
          }
          return;
        }
        const data = await res.json();
        const session = data.session;
        if (!session) return;

        dispatch(
          setSessionInfo({
            sessionId,
            prompt: session.prompt || "",
            initialUrl: session.initialUrl || "",
          }),
        );

        const history = session.chatHistory;
        if (history && history.length > 0) {
          dispatch(setChats(history));
          setHistorySaved(true);
        }
        if (session.lastUrl) {
          dispatch(setLastUrl(session.lastUrl));
        }
        if (session.actionHistory) {
          dispatch(setActionHistory(session.actionHistory));
        }
        if (session.contextId) {
          dispatch(setContextId(session.contextId));
        }
        if (session.operatorId) {
          dispatch(setOperatorInfo({ operatorId: session.operatorId, operatorName: session.operatorName || "" }));
        }
      } catch (err) {
        console.error("Failed to load session:", err);
      }
    };
    loadSession();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, reduxSessionId, dispatch]);

  // Save session to backend when the task completes (upsert — creates on first completion, updates on subsequent)
  const saveSession = useCallback(async () => {
    const sid = reduxSessionId || sessionId;
    if (!sid || chats.length === 0 || historySaved) return;

    const sessionPrompt =
      prompt ||
      chats.find((c: ChatItem) => c.role === "user")?.content ||
      "";

    try {
      const res = await fetch(`${apiUrl}/sessions/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: sid,
          email: user.email || "",
          prompt: sessionPrompt,
          initialUrl: initialUrl || "",
          chatHistory: chats,
          lastUrl: lastUrl || "",
          actionHistory: actionHistory || [],
          contextId: contextId || "",
          operatorId: operatorId || locationState?.operatorId || "",
          operatorName: operatorName || locationState?.operatorName || "",
        }),
      });
      setHistorySaved(true);

      // Add the new session to the sidebar history list
      const data = await res.json();
      if (data.created) {
        addHistoryItem({
          sessionId: sid,
          email: user.email || "",
          prompt: sessionPrompt,
          initialUrl: initialUrl || "",
          createdAt: new Date(),
        } as HistoryItem);
      }
    } catch (err) {
      console.error("Failed to save session:", err);
    }
  }, [
    reduxSessionId,
    sessionId,
    chats,
    historySaved,
    lastUrl,
    actionHistory,
    user.email,
    prompt,
    initialUrl,
    contextId,
    operatorId,
    operatorName,
    locationState?.operatorId,
    locationState?.operatorName,
    addHistoryItem,
  ]);

  // Reset historySaved when a new task is submitted
  useEffect(() => {
    if (socketId && !completed) {
      setHistorySaved(false);
    }
  }, [completed, socketId]);

  useEffect(() => {
    // Save when the task has completed
    if (socketId && completed && !historySaved) {
      saveSession();
    }
  }, [completed, socketId, historySaved, saveSession]);

  // Idle timer: disconnect browser after 2 min of no new task
  useEffect(() => {
    if (socketId && completed) {
      idleTimerRef.current = setTimeout(() => {
        dispatch(disconnectBrowser());
      }, IDLE_TIMEOUT_MS);
    }
    return () => {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
    };
  }, [completed, socketId, dispatch]);

  // Collect all screenshots from chat messages for the strip
  const allScreenshots = chats
    .filter((c: ChatItem) => c.role === "assistant" && c.screenshots)
    .flatMap((c: ChatItem) => c.screenshots || []);
  const lastScreenshot =
    allScreenshots.length > 0
      ? allScreenshots[allScreenshots.length - 1]
      : null;
  const displayedScreenshot =
    selectedScreenshot !== null && allScreenshots[selectedScreenshot]
      ? allScreenshots[selectedScreenshot]
      : lastScreenshot;

  // Disconnect the agent when navigating away from the session page
  const socketRef = useRef<any>(null);
  socketRef.current = socket;

  useEffect(() => {
    return () => {
      if (socketRef.current?.connected) {
        socketRef.current.removeAllListeners();
        socketRef.current.disconnect();
      }
    };
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () =>
      document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  const handleFullScreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else if (browserContainerRef.current) {
      browserContainerRef.current.requestFullscreen?.();
    }
  };

  const toggleChatSidebar = () => {
    setShowChatSidebar(!showChatSidebar);
  };

  const browserContainerClass =
    "flex relative bg-white dark:bg-dark-surface rounded-xl w-full shadow-soft flex-grow overflow-hidden border border-gray-200 dark:border-dark-border h-full";

  return (
    <div className="w-full h-full flex flex-col relative bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full object-cover"
        />
      </div>

      {/* Top header bar — full width, h-14 matches sidebar logo row */}
      <div
        className="flex items-center justify-between w-full h-14 px-5 border-b border-gray-200 dark:border-dark-border
        bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm relative z-10 flex-shrink-0"
      >
        <div className="flex items-center gap-3">
          <span className="text-base font-semibold text-gray-800 dark:text-gray-100">
            Autoppia
            <span className="text-gray-400 dark:text-gray-500 font-normal">
              {" / "}
              <span className="font-mono text-base">{sessionId}</span>
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!showChatSidebar && (
            <IconButton
              icon={faBars}
              onClick={toggleChatSidebar}
              className="dark:text-white dark:border-dark-border"
            />
          )}
        </div>
      </div>

      {/* Content area — browser + chat sidebar */}
      <div className="flex flex-1 min-h-0 relative">
        {/* Browser view area */}
        <div className="hidden lg:flex flex-col flex-1 min-w-0 min-h-0 px-5 py-4 h-full relative overflow-hidden">
          {/* Browser view */}
          <div className="flex w-full flex-grow min-h-0 relative overflow-hidden mt-2">
            {socketId && liveUrl && !completed ? (
              <div ref={browserContainerRef} className={browserContainerClass + " flex-col"}>
                <BrowserTabs
                  tabs={tabs}
                  activeIndex={activeTabIndex}
                  onSelectTab={handleSelectTab}
                  isFullscreen={isFullscreen}
                  onFullscreen={handleFullScreen}
                />
                <iframe
                  src={liveUrl}
                  title="Live browser session"
                  sandbox="allow-same-origin allow-scripts"
                  allow="clipboard-read; clipboard-write"
                  className="w-full flex-1 border-0"
                  style={{ pointerEvents: "none" }}
                />
              </div>
            ) : socketId && !liveUrl && !completed ? (
              <div className={browserContainerClass}>
                <BrowserLoading minHeight="600px" />
              </div>
            ) : displayedScreenshot ? (
              <div ref={browserContainerRef} className={browserContainerClass}>
                <img
                  src={`data:image/png;base64,${displayedScreenshot}`}
                  alt="Last browser state"
                  className="w-full h-full object-contain bg-white dark:bg-dark-surface"
                />
                <button
                  className="absolute top-6 right-3 z-10 flex items-center justify-center w-8 h-8 rounded-lg
                    bg-black/40 hover:bg-black/60 text-white/80 hover:text-white
                    transition-all duration-200 backdrop-blur-sm"
                  onClick={handleFullScreen}
                  title="Fullscreen"
                >
                  <FontAwesomeIcon icon={faExpand} className="text-xs" />
                </button>
              </div>
            ) : (
              <div className={browserContainerClass}>
                <div className="w-full h-full flex items-center justify-center text-gray-400 dark:text-gray-500">
                  <div className="text-center">
                    <p className="text-lg font-medium">No screenshot available</p>
                    <p className="text-sm mt-1">Start a task to see the browser view here</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Screenshot strip — only when no task is actively running */}
          {allScreenshots.length > 0 && (!socketId || completed) && (
            <div className="w-full px-5 mt-2 flex-shrink-0">
              <ScreenshotStrip
                screenshots={allScreenshots}
                selectedIndex={selectedScreenshot}
                onSelect={setSelectedScreenshot}
              />
            </div>
          )}
        </div>

        {/* Chat sidebar — right side */}
        <ChatSidebar
          open={showChatSidebar}
          toggleSideBar={toggleChatSidebar}
          skillMode={locationState?.skillMode}
          skillName={locationState?.skillName}
          skillGoal={locationState?.skillGoal}
          skillInstructions={locationState?.skillInstructions}
          evalMode={isEvalMode}
          evalId={locationState?.evalId || evalIdFromParam}
          runId={locationState?.runId}
        />
      </div>

      {/* Session not found modal */}
      {notFound && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft-lg border border-gray-200 dark:border-dark-border
            px-8 py-7 max-w-sm w-full mx-4 text-center animate-slide-up">
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Session not found
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              This session may have been deleted or the link is invalid.
            </p>
            <button
              onClick={() => navigate("/", { replace: true })}
              className="mt-5 px-5 py-2 rounded-lg text-sm font-medium text-white
                bg-gradient-primary shadow-glow hover:shadow-glow-lg transition-all duration-300"
            >
              New Session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default Session;
