import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faBuilding,
  faCheck,
  faDatabase,
  faFileLines,
  faPaperPlane,
  faRobot,
  faSpinner,
  faWrench,
} from "@fortawesome/free-solid-svg-icons";

const apiUrl = process.env.REACT_APP_API_URL;

const CELERIS_PROMPT = `Celeris es una asesoria laboral en Andorra.
Usamos SMTP para enviar emails, Holded para facturas, Telegram para mensajes, documentos internos y la web https://www.bopa.ad/ para leer el BOPA.
Tareas:
1. Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.
2. Buscar una peticion de un cliente en email y clasificarla como nomina, contrato, factura o consulta laboral.
3. Encontrar la ultima factura de un cliente en Holded y preparar una respuesta por email.
4. Revisar documentos internos y responder una consulta laboral basica con fuentes.
5. Enviar por Telegram un resumen breve de una novedad laboral importante para el equipo.`;

interface OnboardingMessage {
  role: "assistant" | "user";
  content: string;
  createdAt?: string;
}

interface OnboardingDraft {
  company: {
    name: string;
    industry?: string;
    description?: string;
  };
  agent: {
    name: string;
    websiteUrl?: string;
    successCriteria?: string;
    customInstructions?: string;
  };
  connectors: Array<{
    name: string;
    type: string;
    category: string;
    description?: string;
    status?: string;
    config?: Record<string, any>;
  }>;
  tasks: Array<{
    name: string;
    prompt: string;
    successCriteria?: string;
    status?: string;
  }>;
  questions?: string[];
}

interface OnboardingSession {
  sessionId: string;
  messages: OnboardingMessage[];
  draft: OnboardingDraft;
  status: string;
}

function connectorLogo(type: string) {
  if (type === "gmail" || type === "smtp") return "/assets/images/connectors/mail.png";
  if (type === "telegram") return "/assets/images/connectors/telegram.png";
  return "";
}

export default function CelerisOnboarding() {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [session, setSession] = useState<OnboardingSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const draft = session?.draft;
  const ready = !!draft?.company?.name && (draft?.connectors?.length || 0) > 0 && (draft?.tasks?.length || 0) > 0;

  const summary = useMemo(() => {
    if (!draft) return [];
    return [
      { label: "Company", value: draft.company.name || "Not set" },
      { label: "Connectors", value: String(draft.connectors.length) },
      { label: "Benchmark tasks", value: String(draft.tasks.length) },
    ];
  }, [draft]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.messages.length]);

  useEffect(() => {
    const start = async () => {
      if (!user.email) return;
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${apiUrl}/onboarding/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: user.email, seedPrompt: CELERIS_PROMPT }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setSession(data.session);
      } catch (err: any) {
        setError(err?.message || "Could not start onboarding.");
      } finally {
        setLoading(false);
      }
    };
    start();
  }, [user.email]);

  const sendMessage = async (message?: string) => {
    const content = (message || input).trim();
    if (!user.email || !session || !content || sending) return;
    setSending(true);
    setError("");
    setInput("");
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
    } finally {
      setSending(false);
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
      navigate(`/agents/${data.operatorId}`);
    } catch (err: any) {
      setError(err?.message || "Could not create company agent.");
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <div className="w-full max-w-6xl animate-slide-up">
      <div className="mb-5">
        <div className="inline-flex items-center gap-2 px-3 h-8 rounded-full bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-500 dark:text-gray-400 mb-3">
          <FontAwesomeIcon icon={faRobot} className="text-primary" />
          Onboarding agent
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold text-gray-900 dark:text-white mb-2">Create a company agent by chatting</h1>
        <p className="text-sm md:text-base text-gray-500 dark:text-gray-400 max-w-3xl">
          Automata extracts the company, connectors, toolkits and benchmark tasks, then creates the specialized agent in one step.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_390px] gap-4">
        <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft overflow-hidden flex flex-col min-h-[620px]">
          <div className="px-5 py-4 border-b border-gray-100 dark:border-dark-border flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Conversation</p>
              <p className="text-xs text-gray-400">Describe systems, auth, docs, APIs and daily tasks.</p>
            </div>
            <button
              onClick={() => sendMessage(CELERIS_PROMPT)}
              disabled={sending}
              className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60"
            >
              Load Celeris demo
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-auto p-5 space-y-3">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <FontAwesomeIcon icon={faSpinner} className="text-primary text-xl animate-spin" />
              </div>
            ) : (
              session?.messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-gradient-primary text-white"
                      : "bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200 border border-gray-100 dark:border-dark-border"
                  }`}>
                    {message.content}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="p-4 border-t border-gray-100 dark:border-dark-border">
            {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                  }
                }}
                rows={2}
                placeholder="Tell Automata what systems you use, paste API docs, or list more tasks..."
                className="flex-1 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none"
              />
              <button
                onClick={() => sendMessage()}
                disabled={!input.trim() || sending}
                className="w-10 h-10 rounded-xl bg-gradient-primary text-white flex items-center justify-center disabled:opacity-60"
              >
                <FontAwesomeIcon icon={sending ? faSpinner : faPaperPlane} className={`text-sm ${sending ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center gap-2 mb-3">
              <FontAwesomeIcon icon={faBuilding} className="text-primary text-xs" />
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Draft</p>
            </div>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {summary.map((item) => (
                <div key={item.label} className="rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border p-3">
                  <p className="text-[11px] text-gray-400">{item.label}</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{item.value}</p>
                </div>
              ))}
            </div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Agent</p>
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{draft?.agent?.name || "Not set"}</p>
            <p className="text-xs text-gray-400 mt-1">{draft?.company?.industry || draft?.company?.description || "Waiting for company context."}</p>
          </div>

          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center gap-2 mb-3">
              <FontAwesomeIcon icon={faWrench} className="text-primary text-xs" />
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Connectors and toolkits</p>
            </div>
            <div className="space-y-2 max-h-[190px] overflow-auto scrollbar-thin">
              {(draft?.connectors || []).map((connector, index) => {
                const logo = connectorLogo(connector.type);
                return (
                  <div key={`${connector.name}-${index}`} className="flex items-center gap-3 rounded-xl border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                    {logo ? (
                      <span className="w-8 h-8 rounded-lg bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border flex items-center justify-center overflow-hidden">
                        <img src={logo} alt="" className="w-full h-full object-contain p-1.5" />
                      </span>
                    ) : (
                      <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                        <FontAwesomeIcon icon={connector.type === "knowledge" ? faFileLines : connector.type === "api" ? faDatabase : faWrench} className="text-xs" />
                      </span>
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{connector.name}</p>
                      <p className="text-[11px] text-gray-400 truncate">{connector.type} toolkit</p>
                    </div>
                    <span className="ml-auto text-[11px] text-gray-400">{connector.status || "not_connected"}</span>
                  </div>
                );
              })}
              {(draft?.connectors || []).length === 0 && <p className="text-sm text-gray-400">No connectors captured yet.</p>}
            </div>
          </div>

          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Benchmark tasks</p>
              {ready && <FontAwesomeIcon icon={faCheck} className="text-primary text-xs" />}
            </div>
            <div className="space-y-2 max-h-[210px] overflow-auto scrollbar-thin">
              {(draft?.tasks || []).map((task, index) => (
                <div key={`${task.name}-${index}`} className="rounded-xl border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                  <p className="text-xs font-semibold text-gray-900 dark:text-white">{task.name || `Task ${index + 1}`}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{task.prompt}</p>
                </div>
              ))}
              {(draft?.tasks || []).length === 0 && <p className="text-sm text-gray-400">No tasks captured yet.</p>}
            </div>
          </div>

          <button
            onClick={finalize}
            disabled={!ready || finalizing}
            className="w-full h-11 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <FontAwesomeIcon icon={finalizing ? faSpinner : faArrowRight} className={`text-xs ${finalizing ? "animate-spin" : ""}`} />
            {finalizing ? "Creating agent..." : "Create company agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
