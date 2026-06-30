import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import {
  faArrowRight,
  faGlobe,
  faBook,
  faPlug,
  faKey,
  faClipboardCheck,
  faPaperPlane,
  faPaperclip,
  faRobot,
  faSpinner,
  faXmark,
  faTriangleExclamation,
  faCircleCheck,
  faBolt,
  faCloudArrowUp,
} from "@fortawesome/free-solid-svg-icons";
import { faCircle } from "@fortawesome/free-regular-svg-icons";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

const DEMO_PROMPT = `Celeris es una asesoria laboral en Andorra.
Usamos SMTP para enviar emails, Holded para facturas, Telegram para mensajes, documentos internos y la web https://www.bopa.ad/ para leer el BOPA.
Tareas:
1. Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.
2. Buscar una peticion de un cliente en email y clasificarla como nomina, contrato, factura o consulta laboral.
3. Encontrar la ultima factura de un cliente en Holded y preparar una respuesta por email.`;

interface OnboardingMessage {
  role: "assistant" | "user" | "event";
  content: string;
  createdAt?: string;
  kind?: "thinking" | "tool_call" | "tool_result" | "assistant_summary" | string;
  toolName?: string;
  status?: string;
}

interface OnboardingDraft {
  company: { name: string; industry?: string; description?: string };
  agent: { name: string; websiteUrl?: string; successCriteria?: string; customInstructions?: string };
  connectors: Array<{
    name: string;
    type: string;
    category: string;
    surface?: string;
    authRequired?: boolean;
    [key: string]: any;
  }>;
  tasks: Array<{ name: string; prompt: string; [key: string]: any }>;
  [key: string]: any;
}

interface OnboardingSession {
  sessionId: string;
  messages: OnboardingMessage[];
  draft: OnboardingDraft;
  status: string;
}

interface PendingFile {
  name: string;
  size: number;
  status: "uploading" | "done" | "error";
}

interface ChecklistItem {
  key: string;
  label: string;
  hint: string;
  icon: IconDefinition;
  done: boolean;
}

interface OnboardingWindowProps {
  companyId?: string;
  companyName?: string;
  companyDescription?: string;
  onClose: () => void;
  onComplete?: () => void;
}

function formatSize(size: number) {
  if (!size) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/** Derive a short "what have we got so far" checklist from the live draft. */
function buildChecklist(draft?: OnboardingDraft): ChecklistItem[] {
  const connectors = draft?.connectors || [];
  const hasWebsite =
    !!draft?.agent?.websiteUrl ||
    connectors.some((c) => /web|site|browser/i.test(`${c.type} ${c.surface || ""} ${c.category}`));
  const hasDocs = connectors.some((c) => c.type === "knowledge" || c.category === "knowledge");
  const hasApi = connectors.some((c) => c.type === "api" || c.category === "api");
  const hasAuth = connectors.some((c) => !!c.authRequired);
  const hasTasks = (draft?.tasks || []).length > 0;
  return [
    { key: "website", label: "Website / app", hint: "A site or app the agent should use", icon: faGlobe, done: hasWebsite },
    { key: "docs", label: "Docs", hint: "Policies, handbooks or PDFs", icon: faBook, done: hasDocs },
    { key: "api", label: "API docs", hint: "API or OpenAPI references", icon: faPlug, done: hasApi },
    { key: "auth", label: "Access", hint: "How the agent logs in", icon: faKey, done: hasAuth },
    { key: "tasks", label: "Tasks", hint: "Workflows you want automated", icon: faClipboardCheck, done: hasTasks },
  ];
}

/**
 * Full-window company onboarding — a conversation with Automata that quietly
 * tracks the key context provided (website, docs, API, access, tasks). Styled to
 * match the Automata assistant; the heavy "live draft" surface is intentionally
 * out of scope here — this is a chat plus a checklist, nothing more.
 */
export default function OnboardingWindow({
  companyId = "",
  companyName = "",
  companyDescription = "",
  onClose,
  onComplete,
}: OnboardingWindowProps) {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [session, setSession] = useState<OnboardingSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const draft = session?.draft;
  const checklist = useMemo(() => buildChecklist(draft), [draft]);
  const ready = !!draft?.company?.name && (draft?.connectors?.length || 0) > 0 && (draft?.tasks?.length || 0) > 0;
  const busy = sending || uploading;
  const hasConversation = !!session && session.messages.length > 0;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.messages.length, sending, uploading, pendingFiles.length]);

  // Esc closes the window.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    const start = async () => {
      if (!user.email) return;
      setLoading(true);
      setError("");
      try {
        const seedPrompt = companyName ? `Company name: ${companyName}. ${companyDescription}` : "";
        const res = await fetch(`${apiUrl}/onboarding/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: user.email, companyId, seedPrompt }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setSession(data.session);
      } catch (err: any) {
        setError(err?.message || "Could not start onboarding.");
      } finally {
        setLoading(false);
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    };
    start();
  }, [user.email, companyId, companyName, companyDescription]);

  const sendMessage = async (message?: string) => {
    const content = (message || input).trim();
    if (!user.email || !session || !content || sending) return;
    setSending(true);
    setError("");
    setInput("");
    const previousSession = session;
    const now = new Date().toISOString();
    setSession((prev) => (prev ? { ...prev, messages: [...prev.messages, { role: "user", content, createdAt: now }] } : prev));
    try {
      const res = await fetch(`${apiUrl}/onboarding/sessions/${session.sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, message: content }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSession(data.session);
    } catch (err: any) {
      setError(err?.message || "Could not update onboarding.");
      setInput(content);
      setSession(previousSession);
    } finally {
      setSending(false);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  const uploadDocuments = async (files: FileList | File[] | null) => {
    const list = files ? Array.from(files) : [];
    if (!list.length || !user.email || !companyId || uploading) return;
    setUploading(true);
    setError("");
    setPendingFiles(list.map((file) => ({ name: file.name, size: file.size, status: "uploading" as const })));
    try {
      const uploaded: string[] = [];
      for (let i = 0; i < list.length; i++) {
        const file = list[i];
        const body = new FormData();
        body.append("email", user.email);
        body.append("companyId", companyId);
        body.append("source", "onboarding_chat");
        body.append("file", file);
        const res = await fetch(`${apiUrl}/knowledge/documents`, { method: "POST", body });
        if (!res.ok) {
          setPendingFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "error" } : f)));
          throw new Error(await res.text());
        }
        const data = await res.json();
        uploaded.push(data.document?.filename || file.name);
        setPendingFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "done" } : f)));
      }
      const completedAt = new Date().toISOString();
      setSession((prev) =>
        prev
          ? {
              ...prev,
              messages: [
                ...prev.messages,
                {
                  role: "user",
                  content: `📎 Added ${uploaded.length} document${uploaded.length === 1 ? "" : "s"} to company Knowledge.`,
                  createdAt: completedAt,
                },
              ],
              draft: {
                ...prev.draft,
                connectors: prev.draft.connectors.some((connector) => connector.type === "knowledge")
                  ? prev.draft.connectors
                  : [
                      ...prev.draft.connectors,
                      {
                        name: "Documents",
                        type: "knowledge",
                        category: "knowledge",
                      },
                    ],
              },
            }
          : prev,
      );
      setTimeout(() => setPendingFiles([]), 1800);
    } catch (err: any) {
      setError(err?.message || "Could not upload document.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const finalize = async () => {
    if (!user.email || !session || !ready || finalizing) return;
    setFinalizing(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/onboarding/sessions/${session.sessionId}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, draft: session.draft }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data.company?.companyId) {
        localStorage.setItem("automata_company_id", data.company.companyId);
        window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: data.company.companyId } }));
      }
      onComplete?.();
      navigate(`/agents/${data.agentId}`);
    } catch (err: any) {
      setError(err?.message || "Could not create company agent.");
    } finally {
      setFinalizing(false);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[120] flex flex-col overflow-hidden border border-gray-200 bg-white shadow-2xl animate-slide-up dark:border-dark-border dark:bg-dark-bg dark:shadow-black/60">
      {/* Header */}
      <div className="flex h-16 flex-shrink-0 items-center gap-2 border-b border-gray-200 px-5 dark:border-dark-border sm:px-8">
        <div className="flex min-w-0 flex-1 items-center gap-2 pl-1">
          <img src="/assets/images/logos/automata.webp" alt="Automata" className="h-4 w-auto dark:hidden" />
          <img src="/assets/images/logos/automata_dark.webp" alt="Automata" className="hidden h-4 w-auto dark:block" />
          <span className="rounded-full bg-primary/10 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-primary">
            Onboarding
          </span>
          {companyName && (
            <span className="ml-1 hidden truncate text-xs text-gray-400 sm:inline">· {companyName}</span>
          )}
          <span className="ml-2 inline-flex items-center gap-1.5 text-[11px] text-gray-400">
            <span className={`h-1.5 w-1.5 rounded-full ${busy ? "animate-pulse bg-amber-400" : "bg-green-400"}`} />
            {busy ? (uploading ? "Adding to Knowledge…" : "Thinking…") : "Online"}
          </span>
        </div>
        <button
          onClick={() => sendMessage(DEMO_PROMPT)}
          disabled={busy || loading}
          className="hidden h-8 items-center gap-1.5 rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:opacity-60 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5 sm:flex"
        >
          <FontAwesomeIcon icon={faBolt} className="text-[10px] text-primary" />
          Try demo
        </button>
        <button
          onClick={onClose}
          title="Close"
          aria-label="Close onboarding"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-white/5 dark:hover:text-white"
        >
          <FontAwesomeIcon icon={faXmark} className="text-sm" />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-row">
        {/* Conversation column */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
            <div className={`mx-auto w-full max-w-3xl px-4 py-4 sm:px-6 ${hasConversation ? "space-y-3" : "flex min-h-full flex-col justify-end"}`}>
              {loading ? (
                <div className="flex flex-col items-center gap-3 py-10 text-gray-400">
                  <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xl text-primary" />
                  <p className="text-xs">Starting the onboarding agent…</p>
                </div>
              ) : !hasConversation ? (
                <div className="px-2 pb-1">
                  <h3 className="text-3xl font-semibold tracking-tight text-gray-900 dark:text-white">Hey, I'm Automata</h3>
                  <p className="mt-1.5 max-w-md text-[15px] text-gray-500 dark:text-gray-400">
                    Tell me about {companyName || "your company"} — the tools you use, how you log in, the docs you rely on,
                    and the tasks you want automated. I'll keep track on the right.
                  </p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {["We use Gmail and Telegram", "Our app is https://app.example.com", "Read invoices from Holded"].map((chip) => (
                      <button
                        key={chip}
                        onClick={() => setInput(chip)}
                        className="group inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50/80 px-3.5 py-2 text-left text-[13px] text-gray-600 transition-colors hover:border-primary/40 hover:bg-primary/5 dark:border-white/10 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10"
                      >
                        <span className="truncate">{chip}</span>
                        <FontAwesomeIcon icon={faArrowRight} className="flex-shrink-0 text-[9px] text-gray-300 transition-colors group-hover:text-primary" />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                session?.messages.map((message, index) => {
                  const isUser = message.role === "user";
                  if (isUser) {
                    return (
                      <div key={index} className="flex justify-end">
                        <div className="max-w-[85%] break-words rounded-2xl rounded-br-md bg-gradient-primary px-3 py-2 text-sm leading-relaxed text-white">
                          <span className="whitespace-pre-wrap">{message.content}</span>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={index} className="flex flex-col items-start gap-1.5">
                      <div className="w-full break-words text-sm leading-relaxed text-gray-800 dark:text-gray-100">
                        <span className="whitespace-pre-wrap">{message.content}</span>
                      </div>
                    </div>
                  );
                })
              )}

              {/* Working indicator */}
              {sending && (
                <div className="flex items-center gap-2.5 py-1">
                  <img src="/assets/images/logos/main.webp" alt="" className="h-4 w-4" />
                  <span className="flex gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s] dark:bg-gray-500" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s] dark:bg-gray-500" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" />
                  </span>
                </div>
              )}

              {/* Upload chips */}
              {pendingFiles.length > 0 && (
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-md border border-primary/25 bg-primary/[0.04] px-3.5 py-3 dark:bg-primary/[0.06]">
                    <div className="mb-2 flex items-center gap-2">
                      <FontAwesomeIcon icon={faCloudArrowUp} className="text-xs text-primary" />
                      <span className="text-[11px] font-semibold text-gray-700 dark:text-gray-200">Uploading to Knowledge</span>
                    </div>
                    <div className="space-y-1.5">
                      {pendingFiles.map((file, idx) => (
                        <div key={`${file.name}-${idx}`} className="flex items-center gap-2 text-xs">
                          <FontAwesomeIcon
                            icon={file.status === "done" ? faCircleCheck : file.status === "error" ? faTriangleExclamation : faSpinner}
                            className={`flex-shrink-0 text-[11px] ${
                              file.status === "done" ? "text-green-500" : file.status === "error" ? "text-red-500" : "animate-spin text-primary"
                            }`}
                          />
                          <span className="max-w-[180px] truncate text-gray-700 dark:text-gray-200">{file.name}</span>
                          <span className="ml-auto flex-shrink-0 text-[10px] text-gray-400">{formatSize(file.size)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-lg bg-red-50 px-3 py-2 text-[11px] text-red-500 dark:bg-red-500/10">{error}</div>
              )}
            </div>
          </div>

          {/* Composer */}
          <div className="flex-shrink-0">
            <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-2 sm:px-6">
              <div className="flex items-end gap-2 rounded-[26px] border border-gray-200 bg-gray-50 px-2 py-2 shadow-sm transition-all focus-within:border-primary/50 focus-within:shadow-md dark:border-white/10 dark:bg-dark-surface">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || !companyId}
                  title={companyId ? "Attach Knowledge documents" : "Save the company first to attach documents"}
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-white/5"
                >
                  <FontAwesomeIcon icon={uploading ? faSpinner : faPaperclip} className={`text-sm ${uploading ? "animate-spin" : ""}`} />
                </button>
                <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(event) => uploadDocuments(event.target.files)} />
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  disabled={loading}
                  placeholder="Describe your systems, paste API docs, or list tasks…"
                  className="max-h-40 flex-1 resize-none bg-transparent px-2.5 py-1.5 text-[15px] leading-6 text-gray-900 outline-none placeholder:text-gray-400 disabled:opacity-60 dark:text-white"
                />
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || sending}
                  aria-label="Send"
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-primary text-white transition-all hover:shadow-glow disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <FontAwesomeIcon icon={sending ? faSpinner : faPaperPlane} className={`text-sm ${sending ? "animate-spin" : ""}`} />
                </button>
              </div>
              <p className="mt-2 text-center text-[10px] text-gray-400 dark:text-gray-500">
                Attached files become company Knowledge · Enter to send, Shift+Enter for a new line.
              </p>
            </div>
          </div>
        </div>

        {/* Checklist rail */}
        <aside className="hidden w-72 flex-shrink-0 flex-col border-l border-gray-200 bg-gray-50/60 dark:border-dark-border dark:bg-dark-surface/40 sm:flex">
          <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
            <div className="mb-3 flex items-center gap-2">
              <FontAwesomeIcon icon={faClipboardCheck} className="text-xs text-primary" />
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">What I've got so far</span>
            </div>
            <div className="space-y-2">
              {checklist.map((item) => (
                <div
                  key={item.key}
                  className={`flex items-start gap-3 rounded-xl border p-2.5 transition-colors ${
                    item.done
                      ? "border-primary/30 bg-primary/[0.05]"
                      : "border-gray-200 bg-white dark:border-dark-border dark:bg-dark-bg"
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg ${
                      item.done ? "bg-primary/10 text-primary" : "bg-gray-100 text-gray-400 dark:bg-white/5"
                    }`}
                  >
                    <FontAwesomeIcon icon={item.icon} className="text-[10px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="text-xs font-semibold text-gray-800 dark:text-gray-100">{item.label}</p>
                      <FontAwesomeIcon
                        icon={item.done ? faCircleCheck : faCircle}
                        className={`ml-auto text-[12px] ${item.done ? "text-primary" : "text-gray-300 dark:text-zinc-600"}`}
                      />
                    </div>
                    <p className="mt-0.5 text-[11px] leading-4 text-gray-400">{item.hint}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-gray-200 p-4 dark:border-dark-border">
            <button
              onClick={finalize}
              disabled={!ready || finalizing}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gradient-primary text-sm font-semibold text-white shadow-glow transition-all hover:shadow-glow-lg disabled:opacity-50"
            >
              <FontAwesomeIcon icon={finalizing ? faSpinner : faRobot} className={`text-xs ${finalizing ? "animate-spin" : ""}`} />
              {finalizing ? "Creating agent…" : "Create agent"}
            </button>
            <p className="mt-2 text-center text-[11px] leading-4 text-gray-400">
              {ready ? "Ready when you are." : "Add a website or docs and a task to enable."}
            </p>
          </div>
        </aside>
      </div>
    </div>,
    document.body,
  );
}
