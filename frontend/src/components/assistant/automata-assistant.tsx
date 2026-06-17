import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useSelector } from "react-redux";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faXmark,
  faPaperPlane,
  faPenToSquare,
  faExpand,
  faCompress,
  faArrowRight,
  faClock,
  faWandMagicSparkles,
  faPlug,
  faRobot,
  faListCheck,
  faLayerGroup,
  faToolbox,
  faChevronDown,
  faChevronRight,
  faUpRightFromSquare,
  faBrain,
  faGear,
} from "@fortawesome/free-solid-svg-icons";
import { faCircleCheck } from "@fortawesome/free-regular-svg-icons";
import { getApiUrl } from "../../utils/api-url";

const API_URL = getApiUrl();

type AssistantMode =
  | "studio_global"
  | "onboarding"
  | "agent_detail"
  | "connectors"
  | "capabilities"
  | "evals"
  | "work";

interface AssistantMessage {
  role: string;
  content: string;
  type: string;
  toolName: string;
  status: string;
  createdAt: string;
  metadata?: Record<string, any>;
}

interface AssistantConversation {
  conversationId: string;
  mode?: AssistantMode;
  companyId?: string;
  title?: string;
  lastMessage?: string;
  messageCount?: number;
  updatedAt?: string;
  createdAt?: string;
  messages: AssistantMessage[];
}

interface AssistantConversationSummary {
  conversationId: string;
  mode: AssistantMode;
  companyId: string;
  title: string;
  lastMessage: string;
  messageCount: number;
  updatedAt?: string;
  createdAt?: string;
}

interface AssistantModelOption {
  value: string;
  label: string;
}

/** Conservatively infer the assistant mode from the current Studio route. */
function inferMode(pathname: string): AssistantMode {
  if (pathname.startsWith("/connectors")) return "connectors";
  if (pathname.startsWith("/capabilities")) return "capabilities";
  if (pathname.startsWith("/evals")) return "evals";
  if (pathname.startsWith("/work")) return "work";
  // /agents/:id (a detail page), but not the /agents list itself.
  if (/^\/agents\/[^/]+/.test(pathname)) return "agent_detail";
  return "studio_global";
}

const SUGGESTIONS: Record<AssistantMode, string[]> = {
  studio_global: [
    "What can Automata Studio do?",
    "Help me get started",
    "How do I create an agent?",
  ],
  connectors: [
    "What connectors do I have?",
    "How do I add a new connector?",
    "Explain custom connectors",
  ],
  capabilities: [
    "What capabilities are available?",
    "How do skills and tools work?",
    "Help me organise capabilities",
  ],
  evals: [
    "How do evals work?",
    "Help me build an eval",
    "What should I measure?",
  ],
  work: [
    "What's running right now?",
    "How do I schedule work?",
    "Explain the work queue",
  ],
  agent_detail: [
    "Explain this agent's setup",
    "How do I improve this agent?",
    "What can this agent do?",
  ],
  onboarding: [
    "Help me onboard my company",
    "What information do you need?",
  ],
};

function isToolEvent(message: AssistantMessage): boolean {
  return message.role === "tool" || message.type === "tool_call" || message.type === "tool_result";
}

function isThinking(message: AssistantMessage): boolean {
  return message.type === "thinking";
}

// ---------------------------------------------------------------------------
// Presentational widgets (tool cards, link previews, images, timing).
// ---------------------------------------------------------------------------

const URL_RE = /https?:\/\/[^\s<>()]+/g;
const IMG_EXT_RE = /\.(png|jpe?g|gif|webp|svg|avif)(\?[^\s]*)?$/i;

/** Strip trailing punctuation that commonly clings to URLs in prose. */
function cleanUrl(url: string): string {
  return url.replace(/[.,;:!?)\]]+$/, "");
}

/** Non-image links found in a block of text, de-duplicated. */
function extractLinks(text: string): string[] {
  const found = (text.match(URL_RE) || []).map(cleanUrl);
  return Array.from(new Set(found)).filter((u) => !IMG_EXT_RE.test(u));
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Friendly label + icon for each studio tool the assistant can call. */
const TOOL_META: Record<string, { label: string; icon: any }> = {
  "studio.list_connectors": { label: "Connectors", icon: faPlug },
  "studio.list_capabilities": { label: "Capabilities", icon: faWandMagicSparkles },
  "studio.list_agents": { label: "Agents", icon: faRobot },
  "studio.list_work_items": { label: "Work items", icon: faListCheck },
  "studio_create_work_item": { label: "Create work item", icon: faListCheck },
  "studio_update_work_item": { label: "Update work item", icon: faListCheck },
  "studio_run_work_item": { label: "Run work item", icon: faListCheck },
  "studio_delete_work_item": { label: "Delete work item", icon: faListCheck },
  "studio_rejudge_work_item": { label: "Rejudge work item", icon: faListCheck },
  "studio_list_work_boards": { label: "Work boards", icon: faListCheck },
  "studio_create_work_board": { label: "Create work board", icon: faListCheck },
  "studio_list_work_items": { label: "Work items", icon: faListCheck },
  "studio_create_connector": { label: "Create connector", icon: faPlug },
  "studio_update_connector": { label: "Update connector", icon: faPlug },
  "studio_test_connector": { label: "Test connector", icon: faPlug },
  "studio_delete_connector": { label: "Delete connector", icon: faPlug },
  "studio_publish_connector_tools": { label: "Publish tools", icon: faWandMagicSparkles },
  "studio_list_credentials": { label: "Credentials", icon: faToolbox },
  "studio_create_credential": { label: "Create credential", icon: faToolbox },
  "studio_update_credential": { label: "Update credential", icon: faToolbox },
  "studio_delete_credential": { label: "Delete credential", icon: faToolbox },
  "studio_list_api_keys": { label: "API keys", icon: faToolbox },
  "studio_create_api_key": { label: "Create API key", icon: faToolbox },
  "studio_rename_api_key": { label: "Rename API key", icon: faToolbox },
  "studio_delete_api_key": { label: "Delete API key", icon: faToolbox },
  "studio_list_browser_profiles": { label: "Browser profiles", icon: faToolbox },
  "studio_create_browser_profile": { label: "Create profile", icon: faToolbox },
  "studio_rename_browser_profile": { label: "Rename profile", icon: faToolbox },
  "studio_delete_browser_profile": { label: "Delete profile", icon: faToolbox },
  "studio_create_agent": { label: "Create agent", icon: faRobot },
  "studio_update_agent_runtime_settings": { label: "Agent settings", icon: faRobot },
  "studio_run_agent_task": { label: "Run agent", icon: faRobot },
  "studio_approve_approval": { label: "Approve", icon: faListCheck },
  "studio_reject_approval": { label: "Reject", icon: faListCheck },
  "studio_create_vector_database": { label: "Create vector DB", icon: faLayerGroup },
  "studio_save_knowledge_document_from_url": { label: "Save knowledge", icon: faLayerGroup },
  "studio_delete_knowledge_document": { label: "Delete knowledge", icon: faLayerGroup },
  "studio_update_tool_approval": { label: "Tool approval", icon: faWandMagicSparkles },
  "studio_update_skill_approval": { label: "Skill approval", icon: faWandMagicSparkles },
  "studio_test_tool": { label: "Test tool", icon: faToolbox },
  "studio_promote_trajectory_to_skill": { label: "Promote skill", icon: faWandMagicSparkles },
  "studio_get_account_info": { label: "Account", icon: faToolbox },
  "studio_update_account_instructions": { label: "Account instructions", icon: faToolbox },
  "studio_get_analytics_summary": { label: "Analytics", icon: faLayerGroup },
  "studio_list_usage_events": { label: "Usage events", icon: faLayerGroup },
  "studio_get_billing_plan_status": { label: "Plan status", icon: faLayerGroup },
  "studio_list_assistant_conversations": { label: "Conversations", icon: faLayerGroup },
  "studio_get_assistant_memory": { label: "Memory", icon: faLayerGroup },
  "studio_rebuild_assistant_memory": { label: "Rebuild memory", icon: faLayerGroup },
  "studio_delete_assistant_conversations": { label: "Delete chats", icon: faLayerGroup },
  "studio.snapshot": { label: "Workspace", icon: faLayerGroup },
};

function toolMeta(name: string): { label: string; icon: any } {
  return TOOL_META[name] || { label: name || "Tool", icon: faToolbox };
}

function nameOf(item: any): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    return item.name || item.label || item.title || item.id || item.slug || JSON.stringify(item);
  }
  return String(item);
}

/** Turn a tool's metadata into displayable {label, items} sections. */
function buildSections(md: Record<string, any>): { label: string; items: any[] }[] {
  const out: { label: string; items: any[] }[] = [];
  const arrayKeys: [string, string][] = [
    ["connectors", "Connectors"],
    ["tools", "Tools"],
    ["skills", "Skills"],
    ["agents", "Agents"],
    ["workItems", "Work items"],
    ["companies", "Companies"],
  ];
  for (const [key, label] of arrayKeys) {
    if (Array.isArray(md[key]) && md[key].length) out.push({ label, items: md[key] });
  }
  if (md.counts && typeof md.counts === "object") {
    const items = Object.entries(md.counts).map(([k, v]) => `${k}: ${v}`);
    if (items.length) out.push({ label: "Counts", items });
  }
  return out;
}

function Chips({ items }: { items: any[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span
          key={i}
          className="text-[11px] px-2 py-0.5 rounded-md truncate max-w-[180px]
            bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-300
            border border-gray-200/70 dark:border-dark-border"
        >
          {nameOf(it)}
        </span>
      ))}
    </div>
  );
}

/** Collapsible card shown when the assistant runs a skill / tool. */
function ToolCard({ message }: { message: AssistantMessage }) {
  const [open, setOpen] = useState(false);
  const meta = toolMeta(message.toolName);
  const sections = buildSections(message.metadata || {});
  const hasDetails = sections.length > 0;
  return (
    <div className="w-full max-w-[90%] rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/70 dark:bg-dark-surface/60 overflow-hidden">
      <button
        onClick={() => hasDetails && setOpen((v) => !v)}
        disabled={!hasDetails}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-left disabled:cursor-default hover:bg-gray-100/60 dark:hover:bg-white/5 transition-colors"
      >
        <span className="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
          <FontAwesomeIcon icon={meta.icon} className="text-[11px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-gray-800 dark:text-gray-100">{meta.label}</div>
          <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">
            {message.content || "Done"}
          </div>
        </div>
        <FontAwesomeIcon icon={faCircleCheck} className="text-[11px] text-emerald-500/80 flex-shrink-0" />
        {hasDetails && (
          <FontAwesomeIcon
            icon={open ? faChevronDown : faChevronRight}
            className="text-[10px] text-gray-400 flex-shrink-0"
          />
        )}
      </button>
      {open && hasDetails && (
        <div className="px-3 pb-3 pt-2 space-y-2.5 border-t border-gray-200/70 dark:border-dark-border">
          {sections.map((s) => (
            <div key={s.label} className="space-y-1.5">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                {s.label} · {s.items.length}
              </div>
              <Chips items={s.items} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Rich preview card for a web link the assistant references. */
function LinkPreview({ url }: { url: string }) {
  const host = hostOf(url);
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-center gap-2.5 rounded-xl border border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-surface px-3 py-2 hover:border-primary/40 hover:bg-primary/5 dark:hover:bg-white/5 transition-colors"
    >
      <img
        src={`https://www.google.com/s2/favicons?domain=${host}&sz=64`}
        alt=""
        loading="lazy"
        className="w-6 h-6 rounded flex-shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate">{host}</div>
        <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">{url}</div>
      </div>
      <FontAwesomeIcon
        icon={faUpRightFromSquare}
        className="text-[10px] text-gray-300 group-hover:text-primary transition-colors flex-shrink-0"
      />
    </a>
  );
}

/** Custom renderers so markdown links and images become first-class widgets. */
const MD_COMPONENTS = {
  a: ({ href, children }: any) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  img: ({ src, alt }: any) => (
    <a href={src} target="_blank" rel="noopener noreferrer" className="block my-2">
      <img
        src={src}
        alt={alt || ""}
        loading="lazy"
        className="rounded-xl border border-gray-200 dark:border-dark-border max-h-72 w-auto object-contain"
      />
      {alt ? <span className="block text-[10px] text-gray-400 mt-1">{alt}</span> : null}
    </a>
  ),
};

/** Live elapsed-seconds counter shown while the assistant is responding. */
function ElapsedTimer() {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setSecs((Date.now() - start) / 1000), 100);
    return () => clearInterval(id);
  }, []);
  return <span className="tabular-nums">{secs.toFixed(1)}s</span>;
}

function shortDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function AutomataAssistant() {
  const location = useLocation();
  const email = useSelector((state: any) => state.user?.email as string | undefined);

  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastDurationMs, setLastDurationMs] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<AssistantConversationSummary[]>([]);
  const [assistantModel, setAssistantModel] = useState("gpt-5-mini");
  const [assistantModels, setAssistantModels] = useState<AssistantModelOption[]>([
    { value: "gpt-5-mini", label: "GPT-5 mini" },
    { value: "gpt-5.4", label: "GPT-5.4" },
  ]);
  const [modelSaving, setModelSaving] = useState(false);

  const conversationIdRef = useRef<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const mode = inferMode(location.pathname);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    if (open) window.requestAnimationFrame(scrollToBottom);
  }, [messages, open, scrollToBottom]);

  const baseBody = useCallback(
    () => ({
      email: email || "",
      mode,
      companyId: localStorage.getItem("automata_company_id") || "",
      route: location.pathname,
      visibleState: { path: location.pathname },
    }),
    [email, mode, location.pathname]
  );

  const activeCompanyId = useCallback(() => localStorage.getItem("automata_company_id") || "", []);

  const loadAssistantSettings = useCallback(async () => {
    if (!email) return;
    try {
      const params = new URLSearchParams({
        email,
        companyId: activeCompanyId(),
      });
      const res = await fetch(`${API_URL}/assistant/settings?${params.toString()}`);
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      const settings = data.settings || {};
      if (settings.model) setAssistantModel(settings.model);
      if (Array.isArray(settings.models) && settings.models.length) setAssistantModels(settings.models);
    } catch (err) {
      console.error("Failed to load Automata model settings:", err);
    }
  }, [activeCompanyId, email]);

  const updateAssistantModel = useCallback(async (model: string) => {
    if (!email || modelSaving || model === assistantModel) return;
    const previous = assistantModel;
    setAssistantModel(model);
    setModelSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/assistant/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, companyId: activeCompanyId(), model }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      const settings = data.settings || {};
      if (settings.model) setAssistantModel(settings.model);
      if (Array.isArray(settings.models) && settings.models.length) setAssistantModels(settings.models);
    } catch (err) {
      console.error("Failed to update Automata model:", err);
      setAssistantModel(previous);
      setError("Couldn't update Automata model.");
    } finally {
      setModelSaving(false);
    }
  }, [activeCompanyId, assistantModel, email, modelSaving]);

  useEffect(() => {
    void loadAssistantSettings();
  }, [loadAssistantSettings]);

  useEffect(() => {
    const handler = () => {
      conversationIdRef.current = "";
      setMessages([]);
      void loadAssistantSettings();
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, [loadAssistantSettings]);

  const historyParams = useCallback(() => {
    const params = new URLSearchParams({
      email: email || "",
      companyId: localStorage.getItem("automata_company_id") || "",
      mode,
      limit: "30",
    });
    return params;
  }, [email, mode]);

  const loadHistory = useCallback(async () => {
    if (!email) return;
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_URL}/assistant/conversations?${historyParams().toString()}`);
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      setHistory(data.conversations || []);
    } catch (err) {
      console.error("Failed to load Automata history:", err);
      setError("Couldn't load Automata history.");
    } finally {
      setHistoryLoading(false);
    }
  }, [email, historyParams]);

  // Full window shows the history as a persistent sidebar — keep it populated.
  useEffect(() => {
    if (open && expanded) void loadHistory();
  }, [open, expanded, loadHistory]);

  /** Lazily create the backend conversation; returns its id (or "" on failure). */
  const ensureConversation = useCallback(async (): Promise<string> => {
    if (conversationIdRef.current) return conversationIdRef.current;
    if (!email) return "";
    setStarting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/assistant/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...baseBody(), seedPrompt: "" }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      const conversation: AssistantConversation = data.conversation;
      conversationIdRef.current = conversation.conversationId;
      setMessages(conversation.messages || []);
      void loadHistory();
      return conversation.conversationId;
    } catch (err) {
      console.error("Failed to start Automata conversation:", err);
      setError("Couldn't reach Automata. Please try again.");
      return "";
    } finally {
      setStarting(false);
    }
  }, [email, baseBody, loadHistory]);

  const handleOpen = useCallback(() => {
    setOpen(true);
    void loadAssistantSettings();
    void loadHistory();
    void ensureConversation();
  }, [ensureConversation, loadAssistantSettings, loadHistory]);

  const newConversation = useCallback(() => {
    conversationIdRef.current = "";
    setMessages([]);
    setInput("");
    setError(null);
    setLastDurationMs(null);
    setHistoryOpen(false);
    void ensureConversation();
  }, [ensureConversation]);

  const loadConversation = useCallback(
    async (conversationId: string) => {
      if (!email || !conversationId) return;
      setStarting(true);
      setError(null);
      try {
        const params = historyParams();
        const res = await fetch(`${API_URL}/assistant/conversations/${conversationId}?${params.toString()}`);
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        const conversation: AssistantConversation = data.conversation;
        conversationIdRef.current = conversation.conversationId;
        setMessages(conversation.messages || []);
        setLastDurationMs(null);
        setHistoryOpen(false);
      } catch (err) {
        console.error("Failed to load Automata conversation:", err);
        setError("Couldn't load that Automata conversation.");
      } finally {
        setStarting(false);
      }
    },
    [email, historyParams]
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending || !email) return;
      setInput("");
      setError(null);

      // Optimistically show the user's message while we wait for the server.
      const optimistic: AssistantMessage = {
        role: "user",
        content: trimmed,
        type: "message",
        toolName: "",
        status: "completed",
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      setSending(true);
      setLastDurationMs(null);
      const startedAt = Date.now();

      try {
        const conversationId = await ensureConversation();
        if (!conversationId) throw new Error("No conversation");
        const res = await fetch(
          `${API_URL}/assistant/conversations/${conversationId}/messages`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...baseBody(), message: trimmed }),
          }
        );
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        const conversation: AssistantConversation = data.conversation;
        // Server is the source of truth: replace with its full transcript.
        setMessages(conversation.messages || []);
        void loadHistory();
      } catch (err) {
        console.error("Failed to send Automata message:", err);
        setError("Couldn't send your message. Please try again.");
      } finally {
        setSending(false);
        setLastDurationMs(Date.now() - startedAt);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    },
    [sending, email, ensureConversation, baseBody, loadHistory]
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      void sendMessage(input);
    },
    [input, sendMessage]
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendMessage(input);
      }
    },
    [input, sendMessage]
  );

  // No email: not authenticated enough to use the assistant.
  if (!email) return null;

  // Visible conversation messages (system/empty entries filtered out).
  const visibleMessages = messages.filter((m) => (m.content && m.content.trim()) || isToolEvent(m));
  const hasConversation = visibleMessages.length > 0;

  // Index of the latest assistant reply — used to anchor the response-time chip.
  let lastAssistantIdx = -1;
  for (let i = visibleMessages.length - 1; i >= 0; i--) {
    const m = visibleMessages[i];
    if (!isToolEvent(m) && !isThinking(m) && m.role !== "user") {
      lastAssistantIdx = i;
      break;
    }
  }

  if (!open) {
    return (
      <div className="fixed bottom-4 right-4 z-[120] group">
        <div
          role="tooltip"
          className="pointer-events-none absolute right-full top-1/2 mr-3 -translate-y-1/2 whitespace-nowrap rounded-lg
            bg-gray-900 px-3 py-2 text-sm font-medium text-white shadow-lg opacity-0 transition-opacity duration-150
            group-hover:opacity-100 dark:bg-gray-700"
        >
          Ask Automata
        </div>
        <button
          onClick={handleOpen}
          aria-label="Open Automata assistant"
          className="flex items-center justify-center w-14 h-14 rounded-full
            border border-gray-200 bg-white text-xl font-semibold font-mono text-gray-800 shadow-glow hover:shadow-glow-lg
            transition-all duration-300 active:scale-95 dark:border-dark-border dark:bg-dark-surface dark:text-white"
        >
          <span aria-hidden="true">&gt;_</span>
        </button>
      </div>
    );
  }

  const historyListEl =
    history.length === 0 && !historyLoading ? (
      <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border px-3 py-3 text-xs text-gray-400">
        No previous Automata chats in this company.
      </div>
    ) : (
      history.map((item) => {
        const active = item.conversationId === conversationIdRef.current;
        return (
          <button
            key={item.conversationId}
            onClick={() => void loadConversation(item.conversationId)}
            className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
              active
                ? "border-primary/40 bg-primary/5"
                : "border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-surface hover:border-primary/30"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate">{item.title}</span>
              <span className="text-[10px] text-gray-400 flex-shrink-0">{shortDate(item.updatedAt || item.createdAt)}</span>
            </div>
            <div className="mt-0.5 text-[11px] text-gray-400 truncate">{item.lastMessage || `${item.messageCount} messages`}</div>
          </button>
        );
      })
    );

  return (
    <div
      className={`fixed z-[120]
        flex flex-col overflow-hidden
        border border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-bg shadow-2xl dark:shadow-black/60
        animate-slide-up transition-all duration-200
        ${expanded
          ? "inset-0 w-screen h-screen max-h-screen rounded-none"
          : "bottom-3 right-3 left-3 sm:left-auto max-h-[calc(100vh-1.5rem)] rounded-2xl sm:w-[480px] h-[80vh] sm:h-[672px]"}`}
    >
      {/* Header */}
      <div
        className={`flex items-center gap-2 flex-shrink-0 border-b border-gray-200 dark:border-dark-border ${
          expanded ? "h-16 px-5 sm:px-8" : "h-14 px-4"
        }`}
      >
        <div className="min-w-0 flex-1 flex items-center gap-2 pl-1">
          <img
            src="/assets/images/logos/automata.webp"
            alt="Automata"
            className="h-4 w-auto dark:hidden"
          />
          <img
            src="/assets/images/logos/automata_dark.webp"
            alt="Automata"
            className="h-4 w-auto hidden dark:block"
          />
          <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-px rounded-full bg-primary/10 text-primary">
            Beta
          </span>
        </div>
        <button
          onClick={() => {
            setSettingsOpen((v) => !v);
            setHistoryOpen(false);
          }}
          title="Settings"
          className={`flex w-8 h-8 rounded-lg items-center justify-center transition-colors ${
            settingsOpen
              ? "text-primary bg-primary/10"
              : "text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5"
          }`}
        >
          <FontAwesomeIcon icon={faGear} className={`text-xs ${modelSaving ? "animate-pulse text-primary" : ""}`} />
        </button>
        {!expanded && (
          <button
            onClick={() => {
              setHistoryOpen((v) => !v);
              setSettingsOpen(false);
              void loadHistory();
            }}
            title="Conversation history"
            className="flex w-8 h-8 rounded-lg items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          >
            <FontAwesomeIcon icon={faClock} className="text-xs" />
          </button>
        )}
        <button
          onClick={newConversation}
          title="New conversation"
          className="flex w-8 h-8 rounded-lg items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
        >
          <FontAwesomeIcon icon={faPenToSquare} className="text-xs" />
        </button>
        <button
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "Exit full window" : "Full window"}
          className="flex w-8 h-8 rounded-lg items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
        >
          <FontAwesomeIcon icon={expanded ? faCompress : faExpand} className="text-xs" />
        </button>
        <button
          onClick={() => setOpen(false)}
          title="Close"
          className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
        >
          <FontAwesomeIcon icon={faXmark} className="text-sm" />
        </button>
      </div>

      {settingsOpen && (
        <div className="flex-shrink-0 border-b border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg">
          <div className={`${expanded ? "px-5 sm:px-8" : "px-4"} py-3`}>
            <div className="flex items-center justify-between gap-3 mb-2.5">
              <span className="text-xs font-semibold text-gray-800 dark:text-gray-100">Settings</span>
              {modelSaving && <span className="text-[10px] text-primary animate-pulse">Saving…</span>}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
              <FontAwesomeIcon icon={faBrain} className="text-[10px]" />
              Model
            </div>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {assistantModels.map((model) => {
                const active = model.value === assistantModel;
                return (
                  <button
                    key={model.value}
                    onClick={() => void updateAssistantModel(model.value)}
                    disabled={modelSaving}
                    title={model.label}
                    className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-60 ${
                      active
                        ? "border-primary/50 bg-primary/5 dark:bg-primary/10"
                        : "border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-surface hover:border-primary/30 hover:bg-gray-100 dark:hover:bg-white/5"
                    }`}
                  >
                    <span className={`text-xs font-medium truncate ${active ? "text-primary" : "text-gray-700 dark:text-gray-200"}`}>
                      {model.label}
                    </span>
                    {active && <FontAwesomeIcon icon={faCircleCheck} className="text-[11px] text-primary flex-shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {!expanded && historyOpen && (
        <div className="flex-shrink-0 border-b border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg">
          <div className="px-4 py-3">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs font-semibold text-gray-800 dark:text-gray-100">Recent chats</span>
              {historyLoading && <span className="text-[11px] text-gray-400">Loading...</span>}
            </div>
            <div className="max-h-48 overflow-y-auto scrollbar-thin space-y-1.5">
              {historyListEl}
            </div>
          </div>
        </div>
      )}

      <div className={`flex-1 min-h-0 flex ${expanded ? "flex-row" : "flex-col"}`}>
        {/* Full-window history sidebar (Claude-style) */}
        {expanded && (
          <aside className="hidden sm:flex flex-col w-72 flex-shrink-0 border-r border-gray-200 dark:border-dark-border bg-gray-50/60 dark:bg-dark-surface/40">
            <div className="p-3">
              <button
                onClick={newConversation}
                className="w-full flex items-center justify-center gap-2 h-9 rounded-lg bg-gradient-primary text-white text-xs font-semibold shadow-glow hover:shadow-glow-lg transition-all"
              >
                <FontAwesomeIcon icon={faPenToSquare} className="text-[11px]" />
                New chat
              </button>
            </div>
            <div className="px-3 pb-1.5 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Recent chats</span>
              {historyLoading && <span className="text-[10px] text-gray-400">…</span>}
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-3 space-y-1.5">
              {historyListEl}
            </div>
          </aside>
        )}

        {/* Conversation column */}
        <div className="flex-1 min-w-0 flex flex-col">
      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scrollbar-thin"
      >
        <div className={`mx-auto w-full py-4 space-y-3 ${expanded ? "max-w-3xl px-4 sm:px-6" : "px-4"}`}>
        {!hasConversation && (
          <div className="h-full flex flex-col items-center justify-center text-center px-2">
            <img
              src="/assets/images/logos/automata.webp"
              alt="Automata"
              className="h-7 w-auto mb-3 dark:hidden"
            />
            <img
              src="/assets/images/logos/automata_dark.webp"
              alt="Automata"
              className="h-7 w-auto mb-3 hidden dark:block"
            />
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Hey, I'm Automata</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-[260px]">
              Your Studio helper. Ask me anything about onboarding or getting things done here.
            </p>
            <div className="w-full max-w-md mt-5 space-y-2">
              {SUGGESTIONS[mode].map((s) => (
                <button
                  key={s}
                  onClick={() => void sendMessage(s)}
                  disabled={starting || sending}
                  className="group w-full flex items-center justify-between gap-2 text-left px-3 py-2 rounded-xl
                    border border-gray-200 dark:border-dark-border
                    bg-gray-50 dark:bg-dark-surface
                    hover:border-primary/40 hover:bg-primary/5 dark:hover:bg-white/5
                    text-xs text-gray-700 dark:text-gray-200 transition-colors disabled:opacity-50"
                >
                  <span className="truncate">{s}</span>
                  <FontAwesomeIcon
                    icon={faArrowRight}
                    className="text-[10px] text-gray-300 group-hover:text-primary transition-colors flex-shrink-0"
                  />
                </button>
              ))}
            </div>
          </div>
        )}

        {visibleMessages.map((m, i) => {
          // Tool / skill execution → rich collapsible card.
          if (isToolEvent(m)) {
            return (
              <div key={i} className="flex justify-start">
                <ToolCard message={m} />
              </div>
            );
          }

          // Assistant reasoning → subtle inline note.
          if (isThinking(m)) {
            return (
              <div
                key={i}
                className="flex items-center gap-2 text-[11px] text-gray-400 dark:text-gray-500 px-1 italic"
              >
                <FontAwesomeIcon icon={faBrain} className="text-[10px] flex-shrink-0" />
                <span className="truncate">{m.content}</span>
              </div>
            );
          }

          const isUser = m.role === "user";
          if (isUser) {
            return (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-3 py-2 text-sm leading-relaxed break-words bg-gradient-primary text-white">
                  <span className="whitespace-pre-wrap">{m.content}</span>
                </div>
              </div>
            );
          }

          // Assistant text: plain (bubble-less) markdown, link previews + timing.
          const links = extractLinks(m.content);
          return (
            <div key={i} className="flex flex-col items-start gap-1.5">
              <div className="w-full text-sm leading-relaxed break-words text-gray-800 dark:text-gray-100">
                <div className="assistant-markdown space-y-2">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                    {m.content}
                  </ReactMarkdown>
                </div>
              </div>
              {links.length > 0 && (
                <div className="w-full space-y-1.5">
                  {links.slice(0, 3).map((u) => (
                    <LinkPreview key={u} url={u} />
                  ))}
                </div>
              )}
              {i === lastAssistantIdx && lastDurationMs != null && (
                <span className="flex items-center gap-1 text-[10px] text-gray-400 dark:text-gray-500 pl-1">
                  <FontAwesomeIcon icon={faClock} className="text-[9px]" />
                  Responded in {(lastDurationMs / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          );
        })}

        {(sending || starting) && (
          <div className="flex items-center gap-2.5 py-1">
            <img src="/assets/images/logos/main.webp" alt="" className="w-4 h-4" />
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" />
            </span>
            <span className="text-[10px] text-gray-400 dark:text-gray-500">
              <ElapsedTimer />
            </span>
          </div>
        )}

        {error && (
          <div className="text-[11px] text-red-500 bg-red-50 dark:bg-red-500/10 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
        </div>
      </div>

      {/* Input */}
      <form
        onSubmit={onSubmit}
        className="flex-shrink-0 border-t border-gray-200 dark:border-dark-border"
      >
        <div className={`mx-auto w-full ${expanded ? "max-w-3xl px-4 sm:px-6 py-3" : "p-3"}`}>
          <div className="flex items-end gap-2 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-surface px-2.5 py-1.5 focus-within:border-primary/50 transition-colors">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Ask Automata..."
              className="flex-1 resize-none bg-transparent outline-none text-sm text-gray-900 dark:text-white placeholder:text-gray-400 max-h-28 py-1"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              aria-label="Send"
              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0
                bg-gradient-primary text-white disabled:opacity-40 disabled:cursor-not-allowed
                hover:shadow-glow transition-all"
            >
              <FontAwesomeIcon icon={faPaperPlane} className="text-xs" />
            </button>
          </div>
        </div>
      </form>
        </div>
      </div>
    </div>
  );
}
