import React, { useRef, useState, useEffect, useCallback } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faCompressAlt,
  faSave,
  faUser,
} from "@fortawesome/free-solid-svg-icons";
import { faShareFromSquare } from "@fortawesome/free-regular-svg-icons";

import ChatSidebar from "../components/operator/chat-sidebar";
import BrowserLoading from "../components/operator/browser-loading";
import ScreenshotStrip from "../components/operator/screenshot-strip";
import ProfileSidebar from "../components/home/profile-sidebar";
import IconButton from "../components/common/icon-button";
import { setChats, resetChat } from "../redux/chatSlice";
import { resetSocket, disconnectBrowser, setLastUrl, setActionHistory } from "../redux/socketSlice";
import { AppDispatch } from "../redux/store";
import { ChatItem } from "../utils/types";

const IDLE_TIMEOUT_MS = 2 * 60 * 1000; // 2 minutes

const apiUrl = process.env.REACT_APP_API_URL;

function Session(): React.ReactElement {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const { id: sessionId } = useParams<{ id: string }>();

  const [showChatSidebar, setShowChatSidebar] = useState(window.screen.width >= 1024);
  const [profileSidebarOpen, setProfileSidebarOpen] = useState(false);
  const [historySaved, setHistorySaved] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState<number | null>(null);

  const chats = useSelector((state: any) => state.chat.chats);
  const completed = useSelector((state: any) => state.chat.completed);
  const socketIds = useSelector((state: any) => state.socket.socketIds);
  const liveUrls = useSelector((state: any) => state.socket.liveUrls);
  const reduxSessionId = useSelector((state: any) => state.socket.sessionId);
  const lastUrl = useSelector((state: any) => state.socket.lastUrl);
  const actionHistory = useSelector((state: any) => state.socket.actionHistory);

  // Track which session we've already loaded to avoid re-fetching
  const loadedSessionRef = useRef<string | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load old session chat history when navigating to a session
  useEffect(() => {
    if (!sessionId) return;
    // This is the active session we just created — don't overwrite live chats
    if (reduxSessionId === sessionId) return;
    // Already loaded this session's history
    if (loadedSessionRef.current === sessionId) return;

    // Navigating to a different session — clear old state and load
    dispatch(resetChat());
    dispatch(resetSocket());
    setHistorySaved(false);
    setProfileSidebarOpen(false);
    loadedSessionRef.current = sessionId;

    const loadSession = async () => {
      try {
        const res = await fetch(`${apiUrl}/sessions/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        const history = data.session?.chatHistory;
        if (history && history.length > 0) {
          dispatch(setChats(history));
          setHistorySaved(true);
        }
        if (data.session?.lastUrl) {
          dispatch(setLastUrl(data.session.lastUrl));
        }
        if (data.session?.actionHistory) {
          dispatch(setActionHistory(data.session.actionHistory));
        }
      } catch (err) {
        console.error("Failed to load session:", err);
      }
    };
    loadSession();
  }, [sessionId, reduxSessionId, dispatch]);

  // Save chat history to backend when all agents complete
  const saveChatHistory = useCallback(async () => {
    const sid = reduxSessionId || sessionId;
    if (!sid || chats.length === 0 || historySaved) return;

    try {
      await fetch(`${apiUrl}/sessions/${sid}/history`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chatHistory: chats,
          lastUrl: lastUrl || "",
          actionHistory: actionHistory || [],
        }),
      });
      setHistorySaved(true);
    } catch (err) {
      console.error("Failed to save chat history:", err);
    }
  }, [reduxSessionId, sessionId, chats, historySaved, lastUrl, actionHistory]);

  // Reset historySaved when a new task is submitted (addTask sets completed to 0)
  useEffect(() => {
    if (socketIds.length > 0 && completed === 0) {
      setHistorySaved(false);
    }
  }, [completed, socketIds.length]);

  useEffect(() => {
    // Save when all sockets have completed
    if (socketIds.length > 0 && completed >= socketIds.length && !historySaved) {
      saveChatHistory();
    }
  }, [completed, socketIds.length, historySaved, saveChatHistory]);

  // Idle timer: disconnect browser after 2 min of no new task
  useEffect(() => {
    if (socketIds.length > 0 && completed >= socketIds.length) {
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
  }, [completed, socketIds.length, dispatch]);

  // Collect all screenshots from chat messages for the strip
  const allScreenshots = chats
    .filter((c: ChatItem) => c.role === "assistant" && c.screenshots)
    .flatMap((c: ChatItem) => c.screenshots || []);
  const lastScreenshot = allScreenshots.length > 0
    ? allScreenshots[allScreenshots.length - 1]
    : null;
  const displayedScreenshot = selectedScreenshot !== null && allScreenshots[selectedScreenshot]
    ? allScreenshots[selectedScreenshot]
    : lastScreenshot;

  const handleFullScreen = () => {
    if (iframeRef.current) {
      iframeRef.current.requestFullscreen?.();
    }
  };

  const toggleChatSidebar = () => {
    setShowChatSidebar(!showChatSidebar);
  };

  const generateClassName = (parent: boolean) => {
    if (parent) {
      if (socketIds.length > 1) {
        return "flex flex-col xl:grid xl:grid-cols-2 gap-4 w-full flex-grow min-h-0 relative overflow-hidden mt-2";
      } else {
        return "flex w-full flex-grow min-h-0 relative overflow-hidden mt-2";
      }
    }

    let className =
      "flex relative bg-white dark:bg-dark-surface rounded-xl w-full shadow-soft flex-grow overflow-hidden border border-gray-200 dark:border-dark-border";

    if (socketIds.length > 1) {
      return className + " h-auto xl:h-full";
    } else {
      return className + " h-full";
    }
  };

  return (
    <div className="w-full h-screen flex relative bg-gray-100 dark:bg-dark-bg">
      <div className="fixed w-full h-full hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full object-cover"
        />
      </div>

      {/* Chat sidebar — left side */}
      <ChatSidebar
        open={showChatSidebar}
        toggleSideBar={toggleChatSidebar}
      />

      {/* Browser view area — right, fills remaining space */}
      <div className="hidden lg:flex flex-col flex-1 min-w-0 min-h-0 px-5 py-5 h-full relative overflow-hidden">
        {/* Top toolbar */}
        <div className="flex justify-between w-full animate-fade-in">
          <div className="flex items-center gap-1">
            {!showChatSidebar && (
              <IconButton icon={faBars} onClick={toggleChatSidebar} className="dark:text-white dark:border-dark-border" />
            )}
            <div
              className="flex items-center justify-center w-10 h-10 rounded-full cursor-pointer
                transition-all duration-300 text-gray-500 dark:text-gray-400
                hover:bg-gray-100 dark:hover:bg-dark-surface hover:text-gray-700 dark:hover:text-white"
              onClick={handleFullScreen}
            >
              <FontAwesomeIcon icon={faCompressAlt} className="text-sm" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl cursor-not-allowed
              text-gray-400 dark:text-gray-500 text-sm font-medium transition-all duration-300">
              <FontAwesomeIcon icon={faShareFromSquare} />
              <span>Share</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl cursor-not-allowed
              border border-gray-200 dark:border-dark-border text-gray-400 dark:text-gray-500 text-sm font-medium transition-all duration-300">
              <FontAwesomeIcon icon={faSave} />
              <span>Save Task</span>
            </div>
            <div
              className="flex justify-center items-center p-2 sm:p-3 rounded-full
                transition-all duration-200 cursor-pointer text-white
                bg-gradient-primary"
              onClick={() => setProfileSidebarOpen(true)}
            >
              <FontAwesomeIcon icon={faUser} />
            </div>
          </div>
        </div>

        {/* Browser view */}
        <div className={generateClassName(true)}>
          {socketIds.length > 0 ? (
            socketIds.map((socketId: string, index: number) => {
              const liveUrl = liveUrls[socketId];
              return (
                <div
                  key={`${index}_live_main`}
                  className={generateClassName(false)}
                >
                  {liveUrl ? (
                    <iframe
                      ref={index === 0 ? iframeRef : undefined}
                      src={liveUrl}
                      title={`Live browser session ${index + 1}`}
                      sandbox="allow-same-origin allow-scripts"
                      allow="clipboard-read; clipboard-write"
                      className="w-full h-full border-0"
                      style={{ pointerEvents: "none" }}
                    />
                  ) : (
                    <BrowserLoading minHeight="600px" />
                  )}
                </div>
              );
            })
          ) : displayedScreenshot ? (
            <div className={generateClassName(false)}>
              <img
                src={`data:image/png;base64,${displayedScreenshot}`}
                alt="Last browser state"
                className="w-full h-full object-contain bg-white dark:bg-dark-surface"
              />
            </div>
          ) : null}
        </div>

        {/* Screenshot strip — only when no task is actively running */}
        {allScreenshots.length > 0 &&
          (socketIds.length === 0 || completed >= socketIds.length) && (
          <div className="w-full px-5 mt-2 flex-shrink-0">
            <ScreenshotStrip
              screenshots={allScreenshots}
              selectedIndex={selectedScreenshot}
              onSelect={setSelectedScreenshot}
            />
          </div>
        )}
      </div>

      <ProfileSidebar
        sidebarOpen={profileSidebarOpen}
        setSidebarOpen={setProfileSidebarOpen}
      />
    </div>
  );
}

export default Session;
