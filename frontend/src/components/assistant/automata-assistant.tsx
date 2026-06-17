import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useSelector } from "react-redux";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faWandMagicSparkles,
  faXmark,
  faPaperPlane,
  faPenToSquare,
  faExpand,
  faCompress,
  faCircleNotch,
  faGear,
  faArrowRight,
} from "@fortawesome/free-solid-svg-icons";
import { faCircleCheck } from "@fortawesome/free-regular-svg-icons";

const API_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8080";

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
  messages: AssistantMessage[];
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
      return conversation.conversationId;
    } catch (err) {
      console.error("Failed to start Automata conversation:", err);
      setError("Couldn't reach Automata. Please try again.");
      return "";
    } finally {
      setStarting(false);
    }
  }, [email, baseBody]);

  const handleOpen = useCallback(() => {
    setOpen(true);
    void ensureConversation();
  }, [ensureConversation]);

  const newConversation = useCallback(() => {
    conversationIdRef.current = "";
    setMessages([]);
    setInput("");
    setError(null);
    void ensureConversation();
  }, [ensureConversation]);

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
      } catch (err) {
        console.error("Failed to send Automata message:", err);
        setError("Couldn't send your message. Please try again.");
      } finally {
        setSending(false);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    },
    [sending, email, ensureConversation, baseBody]
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

  if (!open) {
    return (
      <button
        onClick={handleOpen}
        aria-label="Open Automata assistant"
        className="fixed bottom-4 right-4 z-[120] flex items-center gap-2 h-12 pl-3.5 pr-4 rounded-full
          bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg
          transition-all duration-300 active:scale-95"
      >
        <FontAwesomeIcon icon={faWandMagicSparkles} className="text-sm" />
        <span className="text-sm font-semibold">Automata</span>
      </button>
    );
  }

  return (
    <div
      className={`fixed z-[120]
        flex flex-col overflow-hidden
        border border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-bg shadow-2xl dark:shadow-black/60
        animate-slide-up transition-all duration-200
        ${expanded
          ? "inset-0 w-screen h-screen max-h-screen rounded-none"
          : "bottom-3 right-3 left-3 sm:left-auto max-h-[calc(100vh-1.5rem)] rounded-2xl sm:w-[400px] h-[70vh] sm:h-[560px]"}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 h-12 flex-shrink-0 border-b border-gray-200 dark:border-dark-border">
        <span className="w-7 h-7 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
          <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold text-gray-900 dark:text-white leading-4">Automata</span>
            <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-px rounded-full bg-primary/10 text-primary">
              Beta
            </span>
          </div>
          <button
            onClick={newConversation}
            className="text-[11px] text-gray-400 hover:text-primary dark:text-gray-500 dark:hover:text-primary leading-3 transition-colors"
          >
            <FontAwesomeIcon icon={faPenToSquare} className="text-[9px] mr-1" />
            New conversation
          </button>
        </div>
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

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-3 py-3 space-y-3">
        {!hasConversation && (
          <div className="h-full flex flex-col items-center justify-center text-center px-2">
            <span className="w-12 h-12 rounded-2xl bg-gradient-primary text-white flex items-center justify-center mb-3 shadow-glow">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-lg" />
            </span>
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
          if (isToolEvent(m)) {
            return (
              <div
                key={i}
                className="flex items-center gap-2 text-[11px] text-gray-400 dark:text-gray-500 px-1"
              >
                <FontAwesomeIcon
                  icon={m.status === "completed" ? faCircleCheck : faGear}
                  className="text-[10px] flex-shrink-0"
                />
                <span className="truncate">{m.content || m.toolName || "Working..."}</span>
              </div>
            );
          }
          const isUser = m.role === "user";
          return (
            <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed break-words ${
                  isUser
                    ? "bg-gradient-primary text-white rounded-br-md"
                    : "bg-gray-100 dark:bg-dark-surface text-gray-800 dark:text-gray-100 rounded-bl-md"
                }`}
              >
                {isUser ? (
                  <span className="whitespace-pre-wrap">{m.content}</span>
                ) : (
                  <div className="assistant-markdown space-y-2">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {(sending || starting) && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-gray-100 dark:bg-dark-surface px-3 py-2">
              <FontAwesomeIcon icon={faCircleNotch} spin className="text-gray-400 text-sm" />
            </div>
          </div>
        )}

        {error && (
          <div className="text-[11px] text-red-500 bg-red-50 dark:bg-red-500/10 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={onSubmit}
        className="flex-shrink-0 border-t border-gray-200 dark:border-dark-border p-2.5"
      >
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
      </form>
    </div>
  );
}
