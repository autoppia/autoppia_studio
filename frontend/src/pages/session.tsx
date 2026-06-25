import React, { useRef, useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { useSelector, useDispatch } from "react-redux";
import { useParams, useNavigate, useOutletContext, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faBolt,
  faBuilding,
  faClipboardCheck,
  faCloudArrowUp,
  faDownload,
  faExpand,
  faFileLines,
  faGlobe,
  faPlay,
  faRobot,
  faShieldHalved,
  faShapes,
  faSpinner,
  faWandMagicSparkles,
} from "@fortawesome/free-solid-svg-icons";

import ChatSidebar from "../components/session/chat-sidebar";
import RuntimeCanvas, {
  RecentActivityStrip,
  RuntimeRunState,
  RuntimeActivity,
  RuntimeTimelineStep,
} from "../components/session/runtime-canvas";
import BrowserTabs from "../components/session/browser-tabs";
import BrowserLoading from "../components/session/browser-loading";
import ScreenshotStrip from "../components/session/screenshot-strip";
import IconButton from "../components/common/icon-button";
import { setChats, resetChat } from "../redux/chatSlice";
import {
  resetSocket,
  disconnectBrowser,
  setSessionInfo,
  setLastUrl,
  setActionHistory,
  setRuntimeState,
  setContextId,
  setAgentInfo,
  setActiveTabIndex,
  setLiveUrl,
} from "../redux/socketSlice";
import { AppDispatch } from "../redux/store";
import { ChatItem, HistoryItem, KnowledgeDocument, SessionArtifact, SessionDocument, SessionItem } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const IDLE_TIMEOUT_MS = 2 * 60 * 1000; // 2 minutes

const apiUrl = getApiUrl();
const DOCUMENT_ACCEPT = ".pdf,.md,.markdown,.txt,.csv,.json,.doc,.docx,.html,.xml,.yml,.yaml";

/** Map a raw action name to a runtime activity surface. */
function activityForAction(action?: string): RuntimeActivity {
  if (!action) return "tool";
  if (action === "skill.use") return "skill";
  if (action === "browser.done") return "done";
  if (action.startsWith("browser.")) return "browser";
  return "tool";
}

function prettyAction(action: string): string {
  if (action === "skill.use") return "Using skill";
  if (action.startsWith("browser.") || action.startsWith("user.")) {
    return action
      .replace("browser.", "")
      .replace("user.", "")
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }
  return action;
}

function formatDocumentSize(size: number) {
  if (!size) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDocumentDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function formatRuntimeDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatCredits(value?: number) {
  const amount = Number(value || 0);
  if (amount <= 0) return "";
  return `${amount.toFixed(2)} credits`;
}

function artifactRows(content: string) {
  return content
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(0, 16)
    .map((line) => line.split(",").map((cell) => cell.trim()));
}

function mergeApprovalRuntimeState(current: Record<string, any>, patch: Record<string, any>) {
  const merged = { ...(current || {}), ...(patch || {}) };
  const currentApproved = Array.isArray(current?.approvedConnectorToolCalls) ? current.approvedConnectorToolCalls : [];
  const patchApproved = Array.isArray(patch?.approvedConnectorToolCalls) ? patch.approvedConnectorToolCalls : [];
  if (currentApproved.length || patchApproved.length) {
    merged.approvedConnectorToolCalls = Array.from(new Set([...currentApproved, ...patchApproved]));
  }
  return merged;
}

function takeApprovalRuntimePatch(sessionId?: string): Record<string, any> {
  if (!sessionId) return {};
  const key = `approval-session-resume:${sessionId}`;
  const raw = sessionStorage.getItem(key);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    sessionStorage.removeItem(key);
    return parsed?.runtimeStatePatch && typeof parsed.runtimeStatePatch === "object" ? parsed.runtimeStatePatch : {};
  } catch {
    sessionStorage.removeItem(key);
    return {};
  }
}

function ArtifactPreview({ artifact }: { artifact: SessionArtifact }) {
  const type = artifact.artifactType || artifact.kind || "text";
  const content = artifact.content || "";
  if (artifact.url && !content) {
    return (
      <iframe
        title={artifact.name || "Artifact preview"}
        src={artifact.url}
        className="h-full min-h-[420px] w-full rounded-xl border border-gray-200 bg-white dark:border-dark-border"
      />
    );
  }
  if (type === "markdown") {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert rounded-xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <ReactMarkdown>{content || "Nothing to preview yet."}</ReactMarkdown>
      </div>
    );
  }
  if (type === "html" || type === "svg") {
    return <iframe title={artifact.name || "Artifact preview"} sandbox="" srcDoc={content} className="h-full min-h-[420px] w-full rounded-xl border border-gray-200 bg-white dark:border-dark-border" />;
  }
  if (type === "csv") {
    const rows = artifactRows(content);
    return (
      <div className="overflow-auto rounded-xl border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <table className="min-w-full text-left text-xs">
          <tbody>
            {rows.length ? rows.map((row, rowIndex) => (
              <tr key={`${rowIndex}-${row.join("-")}`} className={rowIndex === 0 ? "bg-gray-50 dark:bg-white/5" : ""}>
                {row.map((cell, cellIndex) => (
                  <td key={`${rowIndex}-${cellIndex}`} className="border-b border-r border-gray-100 px-3 py-2 text-gray-700 dark:border-dark-border dark:text-gray-200">
                    {cell}
                  </td>
                ))}
              </tr>
            )) : (
              <tr><td className="px-3 py-2 text-gray-400">Nothing to preview yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <pre className="min-h-[420px] overflow-auto rounded-xl border border-gray-200 bg-gray-950 p-4 text-xs leading-relaxed text-gray-100 dark:border-dark-border">
      <code>{content || "Nothing to preview yet."}</code>
    </pre>
  );
}

function RuntimeMetricCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  hint: string;
  tone?: "neutral" | "accent" | "good";
}) {
  const toneClass = tone === "good"
    ? "border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10"
    : tone === "accent"
      ? "border-primary/20 bg-primary/5 dark:border-primary/20 dark:bg-primary/10"
      : "border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface";
  return (
    <div className={`rounded-xl border p-3 ${toneClass}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</p>
      <p className="mt-1 text-base font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  );
}

function Session(): React.ReactElement {
  const browserContainerRef = useRef<HTMLDivElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { id: sessionId, evalId: evalIdFromParam } = useParams<{ id: string; evalId: string }>();
  const location = useLocation();
  const locationState = location.state as {
    activeSessionId?: string;
    skillMode?: boolean;
    skillId?: string;
    skillName?: string;
    skillGoal?: string;
    skillInstructions?: string;
    evalMode?: boolean;
    evalId?: string;
    runId?: string;
    benchmarkMode?: boolean;
    benchmarkId?: string;
    benchmarkRunId?: string;
    agentId?: string;
    agentName?: string;
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
  // Runtime tabs — only one is visible at a time.
  const [activeView, setActiveView] = useState<"canvas" | "browser" | "documents" | "artifacts">("artifacts");
  const manualViewRef = useRef(false);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [sessionDocuments, setSessionDocuments] = useState<SessionDocument[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([]);
  const [persistedArtifacts, setPersistedArtifacts] = useState<SessionArtifact[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsUploading, setDocumentsUploading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const [loadedSession, setLoadedSession] = useState<SessionItem | null>(null);

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
  const runtimeState = useSelector((state: any) => state.socket.runtimeState);
  const contextId = useSelector((state: any) => state.socket.contextId);
  const agentId = useSelector((state: any) => state.socket.agentId);
  const agentName = useSelector((state: any) => state.socket.agentName);
  const tabs = useSelector((state: any) => state.socket.tabs);
  const activeTabIndex = useSelector((state: any) => state.socket.activeTabIndex);
  const user = useSelector((state: any) => state.user);

  const loadDocuments = useCallback(async () => {
    if (!user.email) {
      setSessionDocuments([]);
      setKnowledgeDocuments([]);
      return;
    }
    setDocumentsLoading(true);
    setDocumentsError("");
    try {
      const sid = reduxSessionId || sessionId || "";
      const requests: Promise<Response>[] = [];
      const sessionParams = new URLSearchParams({ email: user.email });
      if (sid) requests.push(fetch(`${apiUrl}/sessions/${sid}/documents?${sessionParams.toString()}`));
      if (companyId) {
        const knowledgeParams = new URLSearchParams({ email: user.email, companyId });
        requests.push(fetch(`${apiUrl}/knowledge/documents?${knowledgeParams.toString()}`));
      }
      const responses = await Promise.all(requests);
      for (const res of responses) {
        if (!res.ok) throw new Error(await res.text());
      }
      let cursor = 0;
      if (sid) {
        const data = await responses[cursor++].json();
        setSessionDocuments(data.documents || []);
      } else {
        setSessionDocuments([]);
      }
      if (companyId) {
        const data = await responses[cursor]?.json();
        setKnowledgeDocuments(data?.documents || []);
      } else {
        setKnowledgeDocuments([]);
      }
    } catch (err: any) {
      console.error("Failed to load session documents:", err);
      setDocumentsError(err?.message || "Could not load documents.");
    } finally {
      setDocumentsLoading(false);
    }
  }, [companyId, reduxSessionId, sessionId, user.email]);

  const loadArtifacts = useCallback(async () => {
    const sid = reduxSessionId || sessionId || "";
    if (!user.email || !sid) {
      setPersistedArtifacts([]);
      setSelectedArtifactId("");
      return;
    }
    setDocumentsLoading(true);
    setDocumentsError("");
    try {
      const params = new URLSearchParams({ email: user.email });
      const res = await fetch(`${apiUrl}/sessions/${sid}/artifacts?${params.toString()}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const items = data.artifacts || [];
      setPersistedArtifacts(items);
      setSelectedArtifactId((current) => current || items[0]?.artifactId || "");
    } catch (err: any) {
      console.error("Failed to load session artifacts:", err);
      setDocumentsError(err?.message || "Could not load artifacts.");
    } finally {
      setDocumentsLoading(false);
    }
  }, [reduxSessionId, sessionId, user.email]);

  const uploadDocuments = async (files: FileList | File[] | null) => {
    const list = files ? Array.from(files) : [];
    const sid = reduxSessionId || sessionId || "";
    if (!list.length || !user.email || !sid || documentsUploading) return;
    setDocumentsUploading(true);
    setDocumentsError("");
    try {
      for (const file of list) {
        const body = new FormData();
        body.append("email", user.email);
        body.append("companyId", companyId || "");
        body.append("source", "session_upload");
        body.append("file", file);
        const res = await fetch(`${apiUrl}/sessions/${sid}/documents`, { method: "POST", body });
        if (!res.ok) throw new Error(await res.text());
      }
      await loadDocuments();
    } catch (err: any) {
      console.error("Failed to upload session document:", err);
      setDocumentsError(err?.message || "Could not upload document.");
    } finally {
      setDocumentsUploading(false);
      if (documentInputRef.current) documentInputRef.current.value = "";
    }
  };

  const saveArtifactToKnowledge = async (artifact: SessionArtifact) => {
    if (!user.email || !companyId || !artifact.url) return;
    setDocumentsUploading(true);
    setDocumentsError("");
    try {
      const res = await fetch(`${apiUrl}/knowledge/documents/from-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          url: artifact.url,
          filename: artifact.name,
          contentType: artifact.contentType || "",
          source: "session_artifact",
          metadata: {
            artifactId: artifact.artifactId,
            sourceTool: artifact.sourceTool,
            sessionId,
            ...(artifact.metadata || {}),
          },
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadDocuments();
    } catch (err: any) {
      console.error("Failed to save artifact to Knowledge:", err);
      setDocumentsError(err?.message || "Could not save artifact to Knowledge.");
    } finally {
      setDocumentsUploading(false);
    }
  };

  const openDocument = (documentId: string) => {
    if (!user.email || !companyId) return;
    const params = new URLSearchParams({ email: user.email, companyId });
    window.open(`${apiUrl}/knowledge/documents/${documentId}/download?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const openSessionDocument = (documentId: string) => {
    const sid = reduxSessionId || sessionId || "";
    if (!user.email || !sid) return;
    const params = new URLSearchParams({ email: user.email });
    window.open(`${apiUrl}/sessions/${sid}/documents/${documentId}/download?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const promoteSessionDocument = async (documentId: string) => {
    const sid = reduxSessionId || sessionId || "";
    if (!user.email || !companyId || !sid) return;
    setDocumentsUploading(true);
    setDocumentsError("");
    try {
      const res = await fetch(`${apiUrl}/sessions/${sid}/documents/${documentId}/promote-to-knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, companyId, source: "session_document" }),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadDocuments();
    } catch (err: any) {
      console.error("Failed to save session document to Knowledge:", err);
      setDocumentsError(err?.message || "Could not save session document to Knowledge.");
    } finally {
      setDocumentsUploading(false);
    }
  };

  const openSessionArtifact = (artifact: SessionArtifact) => {
    if (artifact.url) {
      window.open(artifact.url, "_blank", "noopener,noreferrer");
      return;
    }
    const sid = reduxSessionId || sessionId || "";
    if (!user.email || !sid || !artifact.artifactId) return;
    const params = new URLSearchParams({ email: user.email });
    window.open(`${apiUrl}/sessions/${sid}/artifacts/${artifact.artifactId}/download?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  useEffect(() => {
    if (activeView === "documents") loadDocuments();
    if (activeView === "artifacts") loadArtifacts();
  }, [activeView, loadDocuments, loadArtifacts]);

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
    setLoadedSession(null);
    loadedSessionRef.current = sessionId;

    const loadSession = async () => {
      try {
        const params = new URLSearchParams();
        if (user.email) params.set("email", user.email);
        if (companyId) params.set("companyId", companyId);
        const res = await fetch(`${apiUrl}/sessions/${sessionId}${params.toString() ? `?${params.toString()}` : ""}`);
        if (!res.ok) {
          if (res.status === 404) {
            setNotFound(true);
          }
          return;
        }
        const data = await res.json();
        const session = data.session;
        if (!session) return;
        setLoadedSession(session);

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
        const approvalPatch = takeApprovalRuntimePatch(sessionId);
        dispatch(setRuntimeState(mergeApprovalRuntimeState(session.runtimeState || {}, approvalPatch)));
        if (session.contextId) {
          dispatch(setContextId(session.contextId));
        }
        if (session.agentId) {
          dispatch(setAgentInfo({ agentId: session.agentId, agentName: session.agentName || "" }));
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
          companyId: companyId || "",
          prompt: sessionPrompt,
          initialUrl: initialUrl || "",
          chatHistory: chats,
          lastUrl: lastUrl || "",
          actionHistory: actionHistory || [],
          runtimeState: runtimeState || {},
          contextId: contextId || "",
          agentId: agentId || locationState?.agentId || "",
          agentName: agentName || locationState?.agentName || "",
        }),
      });
      setHistorySaved(true);

      // Add the new session to the sidebar history list
      const data = await res.json();
      if (data.created) {
        addHistoryItem({
          sessionId: sid,
          email: user.email || "",
          companyId: companyId || "",
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
    runtimeState,
    user.email,
    companyId,
    prompt,
    initialUrl,
    contextId,
    agentId,
    agentName,
    locationState?.agentId,
    locationState?.agentName,
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
  const chatArtifacts: SessionArtifact[] = chats
    .filter((c: ChatItem) => c.role === "assistant" && c.artifacts?.length)
    .flatMap((c: ChatItem) => c.artifacts || []);
  const sessionArtifacts: SessionArtifact[] = [
    ...persistedArtifacts,
    ...chatArtifacts.filter((artifact) => !persistedArtifacts.some((stored) => stored.artifactId === artifact.artifactId)),
  ];
  const selectedArtifact = sessionArtifacts.find((artifact) => artifact.artifactId === selectedArtifactId) || sessionArtifacts[0] || null;
  const assistantMessages = chats.filter((c: ChatItem) => c.role === "assistant");
  const latestAssistant = assistantMessages.length > 0 ? assistantMessages[assistantMessages.length - 1] : null;
  const latestAssistantTiming = latestAssistant?.actionTimings?.filter(Boolean).slice(-1)[0];
  const latestActions = latestAssistant?.actions || [];
  const runtimeRunState: RuntimeRunState = completed
    ? latestAssistant?.state === "error"
      ? "failed"
      : "done"
    : socketId
      ? "running"
      : "idle";
  const runtimeTimeline: RuntimeTimelineStep[] = assistantMessages.flatMap((message: ChatItem) =>
    (message.actions || []).map((action, index) => ({
      label: prettyAction(action),
      activity: activityForAction(action),
      status:
        message.actionResults?.[index] === false
          ? "failed"
          : message.actionResults?.[index] === true || action === "browser.done"
            ? "ok"
            : completed
              ? "ok"
              : "pending",
    })),
  );
  const latestBrowserStep = [...assistantMessages].reverse().flatMap((message: ChatItem) => {
    const actions = message.actions || [];
    return [...actions].reverse().map((action, reverseIndex) => {
      const index = actions.length - reverseIndex - 1;
      return { action, metadata: message.actionMetadata?.[index] };
    });
  }).find((step) => activityForAction(step.action) === "browser");
  const latestBrowserArgs = latestBrowserStep?.metadata?.tool?.arguments;
  const latestBrowserUrl = typeof latestBrowserArgs?.url === "string" ? latestBrowserArgs.url : "";
  // Browser is a runtime surface, not a default panel. Tool/API agents such as
  // email agents should not show an empty browser just because a socket is live.
  const hasBrowserContent = Boolean(liveUrl) || Boolean(displayedScreenshot);
  const hasBrowserActions = runtimeTimeline.some((step) => step.activity === "browser");
  const browserAvailable = Boolean(initialUrl || lastUrl || hasBrowserContent || hasBrowserActions);
  const connectorActionCount = runtimeTimeline.filter((step) => step.activity === "tool").length;
  const browserActionCount = runtimeTimeline.filter((step) => step.activity === "browser").length;
  const matchedSkillName = String(loadedSession?.matchedSkillName || runtimeState?.matchedSkillName || runtimeState?.matchedSkill || locationState?.skillName || "");
  const matchedSkillId = String(loadedSession?.matchedSkillId || runtimeState?.matchedSkillId || locationState?.skillId || "");
  const benchmarkId = String(locationState?.benchmarkId || "");
  const benchmarkRunId = String(locationState?.benchmarkRunId || "");
  const pendingConnectorApproval = String(loadedSession?.pendingConnectorApproval || runtimeState?.pendingConnectorApproval || "");
  const approvedConnectorToolCalls = Array.isArray(runtimeState?.approvedConnectorToolCalls) ? runtimeState.approvedConnectorToolCalls : [];
  const sourceKind = String(loadedSession?.sourceKind || runtimeState?.sourceKind || "");
  const workItemId = String(loadedSession?.workItemId || runtimeState?.workItemId || "");
  const runId = String(loadedSession?.runId || runtimeState?.runId || "");
  const creditsLabel = formatCredits(loadedSession?.creditsSpent ?? runtimeState?.creditsSpent);
  const runtimeKind = browserActionCount > 0 && connectorActionCount > 0
    ? "Hybrid runtime"
    : browserActionCount > 0
      ? "Browser runtime"
      : "API runtime";
  const latestActivityLabel = runtimeTimeline.length > 0 ? runtimeTimeline[runtimeTimeline.length - 1].label : "Waiting for task";
  const runtimeTimestamp = String(latestAssistantTiming?.emittedAt || "");
  const runtimeOverview = (
    <div className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1.8fr)]">
      <div className="rounded-xl border border-gray-200 bg-white/80 p-4 backdrop-blur-sm dark:border-dark-border dark:bg-dark-surface/80">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Runtime overview</p>
            <p className="mt-1 truncate text-sm font-semibold text-gray-900 dark:text-white">{prompt || "No task loaded"}</p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {runtimeKind} · {runtimeRunState}{runtimeTimestamp ? ` · ${formatRuntimeDate(runtimeTimestamp)}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
              <FontAwesomeIcon icon={browserActionCount > 0 && connectorActionCount > 0 ? faRobot : browserActionCount > 0 ? faGlobe : faBolt} className="text-[10px]" />
              {runtimeKind}
            </span>
            {matchedSkillName && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
                <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
                {matchedSkillName}
              </span>
            )}
            {pendingConnectorApproval && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                <FontAwesomeIcon icon={faShieldHalved} className="text-[10px]" />
                Approval pending
              </span>
            )}
            {sourceKind === "work" && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-primary/20 bg-primary/10 px-2 py-1 text-[11px] text-primary">
                <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
                Work orchestration
              </span>
            )}
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
          Latest activity: <span className="font-semibold text-gray-800 dark:text-gray-100">{latestActivityLabel}</span>
          {agentName ? <span> · AgentRuntime: {agentName}</span> : null}
          {lastUrl ? <span> · Last URL recorded</span> : null}
          {workItemId ? <span> · Work item {workItemId}</span> : null}
          {runId ? <span> · Run {runId}</span> : null}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {pendingConnectorApproval && (
            <button
              type="button"
              onClick={() => navigate(`/approvals?status=pending&sessionId=${encodeURIComponent(reduxSessionId || sessionId || "")}`)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 text-xs font-semibold text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/20"
            >
              <FontAwesomeIcon icon={faShieldHalved} className="text-[10px]" />
              Open approvals
            </button>
          )}
          {sessionArtifacts.length > 0 && (
            <button
              type="button"
              onClick={() => navigate(`/artifacts?sessionId=${encodeURIComponent(reduxSessionId || sessionId || "")}`)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
            >
              <FontAwesomeIcon icon={faShapes} className="text-[10px]" />
              View persisted artifacts
            </button>
          )}
          {workItemId && (
            <button
              type="button"
              onClick={() => navigate(`/work?item=${encodeURIComponent(workItemId)}`)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
            >
              <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
              Open job
            </button>
          )}
          {matchedSkillId && (
            <button
              type="button"
              onClick={() => navigate(`/capabilities/skill/${encodeURIComponent(matchedSkillId)}`)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
            >
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
              Open skill
            </button>
          )}
          {benchmarkId && (
            <>
              <button
                type="button"
                onClick={() => navigate(`/evals?benchmark=${encodeURIComponent(benchmarkId)}`)}
                className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
              >
                <FontAwesomeIcon icon={faClipboardCheck} className="text-[10px]" />
                Open benchmark
              </button>
              <button
                type="button"
                onClick={() => {
                  const params = new URLSearchParams();
                  params.set("benchmark", benchmarkId);
                  if (benchmarkRunId) params.set("runGroup", benchmarkRunId);
                  navigate(`/eval-runs?${params.toString()}`);
                }}
                className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
              >
                <FontAwesomeIcon icon={faPlay} className="text-[10px]" />
                Open recent runs
              </button>
            </>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <RuntimeMetricCard label="Tool Calls" value={connectorActionCount} hint="Typed connector actions executed in this session." />
        <RuntimeMetricCard label="Browser Steps" value={browserActionCount} hint="UI actions executed through browser runtime." tone={browserActionCount > 0 ? "accent" : "neutral"} />
        <RuntimeMetricCard label="Artifacts" value={sessionArtifacts.length} hint="Business outputs separated from the trace." tone={sessionArtifacts.length > 0 ? "good" : "neutral"} />
        <RuntimeMetricCard
          label={creditsLabel ? "Credits" : "Approvals"}
          value={creditsLabel || (pendingConnectorApproval ? "Pending" : approvedConnectorToolCalls.length)}
          hint={
            creditsLabel
              ? `Source: ${sourceKind === "work" ? "Work Orchestration" : "runtime session"}${runId ? ` · ${runId}` : ""}`
              : pendingConnectorApproval
                ? "Waiting for human approval before write/send."
                : `${approvedConnectorToolCalls.length} approved connector calls recorded.`
          }
          tone={creditsLabel ? "good" : pendingConnectorApproval ? "accent" : approvedConnectorToolCalls.length > 0 ? "good" : "neutral"}
        />
      </div>
    </div>
  );

  const runtimeAgents = [
    {
      id: agentId || "active-agent",
      name: agentName || "Automata Agent",
      state: runtimeRunState,
      activity: activityForAction(latestActions[latestActions.length - 1]),
      detail: latestActions.length > 0 ? prettyAction(latestActions[latestActions.length - 1]) : prompt || "Waiting for task",
      browserEnabled: browserAvailable,
    },
  ];
  const runtimeCanvas = (
    <RuntimeCanvas
      agents={runtimeAgents}
      timeline={runtimeTimeline}
      title="AgentRuntime"
      subtitle={prompt || "No task is running"}
      minHeight="100%"
      showActivityDock={false}
    />
  );

  // A run is live (socket connected and task not finished) — the browser is initializing or running.
  const browserActive = Boolean(socketId) && !completed && browserAvailable;

  // Auto-focus the Browser tab the moment a run starts (so the user sees it initialize),
  // unless they manually picked a tab. Fall back to Canvas when idle with nothing to show.
  useEffect(() => {
    if (manualViewRef.current) return;
    if (browserActive || hasBrowserContent) {
      setActiveView("browser");
    } else if (activeView === "browser" && !browserAvailable) {
      setActiveView("artifacts");
    }
  }, [activeView, browserActive, browserAvailable, hasBrowserContent]);

  useEffect(() => {
    if (activeView === "browser" && !browserAvailable) {
      setActiveView("artifacts");
      manualViewRef.current = false;
    }
  }, [activeView, browserAvailable]);

  // Reset the manual override once a run fully ends, so the next run can auto-focus the browser again.
  useEffect(() => {
    if (!socketId && !completed) manualViewRef.current = false;
  }, [socketId, completed]);

  const selectView = (view: "canvas" | "browser" | "documents" | "artifacts") => {
    manualViewRef.current = true;
    setActiveView(view);
  };

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
    "flex relative bg-white dark:bg-dark-surface rounded-xl w-full shadow-soft flex-grow overflow-hidden border border-gray-200 dark:border-dark-border h-full min-h-[320px]";

  const documentsWorkspace = (
    <div className="flex h-full w-full flex-col rounded-xl border border-gray-200 bg-white shadow-soft dark:border-dark-border dark:bg-dark-surface">
      <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-dark-border">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">Session documents</p>
          <p className="mt-0.5 text-xs text-gray-400">
            Session files stay temporary until you save them to Company Knowledge.
          </p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <button
            onClick={() => documentInputRef.current?.click()}
            disabled={documentsUploading || !(reduxSessionId || sessionId)}
            className="flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white transition-opacity disabled:opacity-60"
          >
            <FontAwesomeIcon icon={documentsUploading ? faSpinner : faCloudArrowUp} className={`text-[10px] ${documentsUploading ? "animate-spin" : ""}`} />
            Upload
          </button>
          <input
            ref={documentInputRef}
            type="file"
            accept={DOCUMENT_ACCEPT}
            multiple
            className="hidden"
            onChange={(event) => uploadDocuments(event.target.files)}
          />
        </div>
      </div>

      <div
        className="flex-1 overflow-auto p-4"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          uploadDocuments(event.dataTransfer.files);
        }}
      >
        {documentsError && (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {documentsError}
          </div>
        )}

        {documentsLoading ? (
          <div className="flex h-full min-h-[320px] items-center justify-center">
            <FontAwesomeIcon icon={faSpinner} className="text-2xl text-primary animate-spin" />
          </div>
        ) : (
          <div className="space-y-4">
            <section>
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">This Session</p>
                  <p className="mt-0.5 text-xs text-gray-400">Temporary files available to this session. Promote them only when they should become reusable Knowledge.</p>
                </div>
              </div>
              {sessionDocuments.length === 0 ? (
                <button
                  onClick={() => documentInputRef.current?.click()}
                  className="flex min-h-[220px] w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 px-6 text-center transition-colors hover:border-primary/60 hover:bg-gray-50 dark:border-dark-border dark:hover:bg-white/5"
                >
                  <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <FontAwesomeIcon icon={faCloudArrowUp} />
                  </span>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Drop files here or click to upload</p>
                  <p className="mt-1 text-xs text-gray-400">Uploads stay in this session until you save them to Knowledge.</p>
                </button>
              ) : (
                <div className="grid grid-cols-1 gap-3 xl:grid-cols-2 2xl:grid-cols-3">
                  {sessionDocuments.map((document) => (
                    <div
                      key={document.documentId}
                      className="group rounded-lg border border-gray-200 bg-gray-50 p-3 transition-colors hover:border-primary/40 dark:border-dark-border dark:bg-zinc-900/50"
                    >
                      <div className="flex items-start gap-3">
                        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <FontAwesomeIcon icon={faFileLines} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-gray-900 dark:text-white" title={document.filename}>
                            {document.filename}
                          </p>
                          <p className="mt-0.5 text-[11px] text-gray-400">
                            {formatDocumentSize(document.size)} · {formatDocumentDate(document.createdAt)}
                          </p>
                          <p className="mt-1 truncate text-[10px] text-gray-400">
                            {document.source?.replace(/_/g, " ") || "session upload"} · {document.status || "stored"}
                          </p>
                        </div>
                        <div className="flex flex-shrink-0 items-center gap-1">
                          <button
                            onClick={() => openSessionDocument(document.documentId)}
                            className="h-8 rounded-lg px-2 text-xs font-semibold text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/5 dark:hover:text-white"
                          >
                            View
                          </button>
                          <button
                            onClick={() => promoteSessionDocument(document.documentId)}
                            disabled={!companyId || documentsUploading || Boolean(document.knowledgeDocumentId)}
                            className="h-8 rounded-lg bg-gradient-primary px-2 text-xs font-semibold text-white transition-opacity disabled:opacity-60"
                            title={companyId ? "Save to Company Knowledge" : "Select a company first"}
                          >
                            {document.knowledgeDocumentId ? "Saved" : "Save"}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Company Knowledge</p>
                  <p className="mt-0.5 text-xs text-gray-400">Persistent documents available across agents and sessions for the selected company.</p>
                </div>
              </div>
              {!companyId ? (
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-6 text-center dark:border-dark-border dark:bg-zinc-900/50">
                  <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-white text-gray-400 dark:border-dark-border dark:bg-zinc-950">
                    <FontAwesomeIcon icon={faBuilding} />
                  </span>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">No company selected</p>
                  <p className="mt-1 text-xs text-gray-400">Select a company from the top bar to see persistent Knowledge.</p>
                </div>
              ) : knowledgeDocuments.length === 0 ? (
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-400 dark:border-dark-border dark:bg-zinc-900/50">
                  No Company Knowledge documents yet.
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3 xl:grid-cols-2 2xl:grid-cols-3">
                  {knowledgeDocuments.map((document) => (
                    <div
                      key={document.documentId}
                      className="group rounded-lg border border-gray-200 bg-gray-50 p-3 transition-colors hover:border-primary/40 dark:border-dark-border dark:bg-zinc-900/50"
                    >
                      <div className="flex items-start gap-3">
                        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
                          <FontAwesomeIcon icon={faFileLines} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-gray-900 dark:text-white" title={document.filename}>
                            {document.filename}
                          </p>
                          <p className="mt-0.5 text-[11px] text-gray-400">
                            {formatDocumentSize(document.size)} · {formatDocumentDate(document.createdAt)}
                          </p>
                          <p className="mt-1 truncate text-[10px] text-gray-400">
                            {document.source?.replace(/_/g, " ") || "upload"} · {document.status || "stored"}
                          </p>
                        </div>
                        <button
                          onClick={() => openDocument(document.documentId)}
                          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-primary/10 hover:text-primary"
                          title="Open document"
                        >
                          <FontAwesomeIcon icon={faDownload} className="text-xs" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );

  const artifactsWorkspace = (
    <div className="flex h-full w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-soft dark:border-dark-border dark:bg-dark-surface">
      <aside className="flex w-[280px] flex-shrink-0 flex-col border-r border-gray-200 dark:border-dark-border">
        <div className="border-b border-gray-200 px-4 py-3 dark:border-dark-border">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Session artifacts</p>
              <p className="mt-0.5 text-xs text-gray-400">Outputs created by this agent run.</p>
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-2">
          {sessionArtifacts.length === 0 ? (
            <div className="flex min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 px-4 text-center dark:border-dark-border">
              <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <FontAwesomeIcon icon={faShapes} />
              </span>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">No artifacts yet</p>
              <p className="mt-1 text-xs text-gray-400">Ask the agent to create a report, diagram, HTML page, table, or code artifact.</p>
            </div>
          ) : sessionArtifacts.map((artifact) => {
            const active = selectedArtifact?.artifactId === artifact.artifactId;
            return (
              <button
                key={artifact.artifactId || artifact.url || artifact.name}
                onClick={() => setSelectedArtifactId(artifact.artifactId)}
                className={`mb-2 flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors ${
                  active
                    ? "border-primary/50 bg-primary/5 dark:bg-primary/10"
                    : "border-gray-200 bg-gray-50 hover:border-primary/30 dark:border-dark-border dark:bg-zinc-900/50"
                }`}
              >
                <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FontAwesomeIcon icon={faShapes} className="text-sm" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-gray-900 dark:text-white" title={artifact.name || artifact.title}>
                    {artifact.name || artifact.title || "Artifact"}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-gray-400">
                    {artifact.artifactType || artifact.kind || "artifact"}{artifact.sourceTool ? ` · ${artifact.sourceTool}` : ""}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-dark-border">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">
              {selectedArtifact?.name || selectedArtifact?.title || "Artifact preview"}
            </p>
            <p className="mt-0.5 truncate text-xs text-gray-400">
              {selectedArtifact ? `${selectedArtifact.artifactType || selectedArtifact.kind || "artifact"}${selectedArtifact.fileName ? ` · ${selectedArtifact.fileName}` : ""}` : "Select an artifact"}
            </p>
          </div>
          {selectedArtifact && (
            <div className="flex flex-shrink-0 items-center gap-2">
              <button
                onClick={() => openSessionArtifact(selectedArtifact)}
                className="flex h-8 items-center gap-2 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
              >
                <FontAwesomeIcon icon={faDownload} className="text-[10px]" />
                Download
              </button>
              {selectedArtifact.url && (
                <button
                  onClick={() => saveArtifactToKnowledge(selectedArtifact)}
                  disabled={!companyId || documentsUploading}
                  className="h-8 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white transition-opacity disabled:opacity-60"
                >
                  Save to Knowledge
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex-1 overflow-auto p-4">
          {documentsError && activeView === "artifacts" && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {documentsError}
            </div>
          )}
          {selectedArtifact ? (
            <ArtifactPreview artifact={selectedArtifact} />
          ) : (
            <div className="flex h-full min-h-[320px] items-center justify-center text-sm text-gray-400">
              Select an artifact to preview it.
            </div>
          )}
        </div>
      </main>
    </div>
  );

  return (
    <div className="w-full h-full flex flex-col relative bg-gray-100 dark:bg-dark-bg">
      {/* Shared section backdrop — same dark-bg image used across the app. */}
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      {/* Top header bar — full width, h-14 matches sidebar logo row */}
      <div
        className="flex items-center justify-between w-full h-14 px-5 border-b border-gray-200 dark:border-zinc-800/80
        bg-transparent backdrop-blur-sm relative z-10 flex-shrink-0"
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
        <div className="flex items-center gap-3 min-w-0">
          {/* Recent activity — last few tools/actions, right-aligned on the header row */}
          <div className="hidden md:flex min-w-0 max-w-[46vw] overflow-x-auto scrollbar-thin">
            <RecentActivityStrip timeline={runtimeTimeline} limit={5} />
          </div>
          {!showChatSidebar && (
            <IconButton
              icon={faBars}
              onClick={toggleChatSidebar}
              className="dark:text-white dark:border-dark-border"
            />
          )}
        </div>
      </div>

      {/* Content area — chat sidebar + browser */}
      <div className="flex flex-1 min-h-0 relative">
        {/* Chat sidebar — left side, right after the history rail */}
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

        {/* Browser view area */}
        <div className="hidden lg:flex flex-col flex-1 min-w-0 min-h-0 px-5 py-4 h-full relative overflow-hidden">
          {runtimeOverview}
          {/* Tab switcher — Canvas and Browser are mutually exclusive */}
          <div className="mb-3 flex items-center gap-1 flex-shrink-0 w-fit rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-white/70 dark:bg-zinc-900/60 p-1 backdrop-blur-sm">
            {([
              { key: "canvas" as const, label: "Trace", icon: faRobot },
              { key: "artifacts", label: "Artifacts", icon: faShapes },
              ...(browserAvailable ? [{ key: "browser" as const, label: "Browser", icon: faGlobe }] : []),
              { key: "documents", label: "Documents", icon: faFileLines },
            ] as const).map((tab) => {
              const isActive = activeView === tab.key;
              const showLiveDot = tab.key === "browser" && Boolean(socketId && liveUrl && !completed);
              return (
                <button
                  key={tab.key}
                  onClick={() => selectView(tab.key)}
                  className={`flex items-center gap-2 rounded-lg px-3.5 h-8 text-xs font-semibold transition-all duration-200 ${
                    isActive
                      ? "bg-gradient-primary text-white shadow-glow"
                      : "text-gray-500 dark:text-zinc-400 hover:bg-gray-100 dark:hover:bg-white/5"
                  }`}
                >
                  <FontAwesomeIcon icon={tab.icon} className="text-[11px]" />
                  {tab.label}
                  {showLiveDot && (
                    <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Active panel */}
          <div className="flex w-full flex-grow min-h-0 relative overflow-hidden">
            {activeView === "canvas" ? (
              <div className="w-full h-full min-h-[320px]">
                {runtimeCanvas}
              </div>
            ) : activeView === "documents" ? (
              <div className="w-full h-full min-h-[320px]">
                {documentsWorkspace}
              </div>
            ) : activeView === "artifacts" ? (
              <div className="w-full h-full min-h-[320px]">
                {artifactsWorkspace}
              </div>
            ) : socketId && liveUrl && !completed ? (
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
            ) : displayedScreenshot ? (
              <div ref={browserContainerRef} className={browserContainerClass}>
                <img
                  src={`data:image/png;base64,${displayedScreenshot}`}
                  alt="Browser state"
                  className="w-full h-full object-contain bg-white dark:bg-dark-surface"
                />
                <button
                  className="absolute top-3 right-3 z-10 flex items-center justify-center w-8 h-8 rounded-lg
                    bg-black/40 hover:bg-black/60 text-white/80 hover:text-white
                    transition-all duration-200 backdrop-blur-sm"
                  onClick={handleFullScreen}
                  title="Fullscreen"
                >
                  <FontAwesomeIcon icon={faExpand} className="text-xs" />
                </button>
              </div>
            ) : browserActive ? (
              // Run is live but the live URL / first screenshot has not arrived yet — show the init animation.
              <div className={browserContainerClass}>
                <BrowserLoading minHeight="320px" />
              </div>
            ) : latestBrowserStep ? (
              <div className={browserContainerClass + " items-center justify-center"}>
                <div className="w-full max-w-xl px-6 text-center">
                  <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-300">
                    <FontAwesomeIcon icon={faGlobe} />
                  </span>
                  <p className="text-sm font-semibold text-gray-700 dark:text-zinc-200">
                    Browser action planned
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-zinc-400">
                    {prettyAction(latestBrowserStep.action)}
                  </p>
                  {latestBrowserUrl && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-gray-200 bg-white px-3 py-2 text-left font-mono text-[11px] text-gray-500 dark:border-zinc-800 dark:bg-black/20 dark:text-zinc-400">
                      <span className="block truncate">{latestBrowserUrl}</span>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className={browserContainerClass + " items-center justify-center"}>
                <div className="text-center px-6">
                  <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-gray-200 dark:border-zinc-800/80 bg-gray-50 dark:bg-zinc-900/70 text-gray-400 dark:text-zinc-500">
                    <FontAwesomeIcon icon={faGlobe} />
                  </span>
                  <p className="text-sm font-semibold text-gray-700 dark:text-zinc-200">No browser activity yet</p>
                  <p className="mt-1 text-xs text-gray-400 dark:text-zinc-500">Start a task to see the live browser here.</p>
                </div>
              </div>
            )}
          </div>

          {/* Screenshot strip — browser tab, only when no task is actively running */}
          {activeView === "browser" && allScreenshots.length > 0 && (!socketId || completed) && (
            <div className="w-full px-5 mt-2 flex-shrink-0">
              <ScreenshotStrip
                screenshots={allScreenshots}
                selectedIndex={selectedScreenshot}
                onSelect={setSelectedScreenshot}
              />
            </div>
          )}
        </div>
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
