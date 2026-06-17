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
  faBrain,
  faCheckCircle,
  faClock,
  faPaperclip,
  faMagnifyingGlass,
  faCircleNodes,
  faClipboardCheck,
  faCloudArrowUp,
  faWandMagicSparkles,
  faXmark,
  faTriangleExclamation,
  faBolt,
} from "@fortawesome/free-solid-svg-icons";
import InfoIcon from "../common/info-icon";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

const CELERIS_PROMPT = `Celeris es una asesoria laboral en Andorra.
Usamos SMTP para enviar emails, Holded para facturas, Telegram para mensajes, documentos internos y la web https://www.bopa.ad/ para leer el BOPA.
Tareas:
1. Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.
2. Buscar una peticion de un cliente en email y clasificarla como nomina, contrato, factura o consulta laboral.
3. Encontrar la ultima factura de un cliente en Holded y preparar una respuesta por email.
4. Revisar documentos internos y responder una consulta laboral basica con fuentes.
5. Enviar por Telegram un resumen breve de una novedad laboral importante para el equipo.`;

/** Staged "live" activity the agent appears to perform while the request is in flight. */
const WORKING_STEPS = [
  { icon: faBrain, label: "Reading your description" },
  { icon: faMagnifyingGlass, label: "Identifying systems & auth" },
  { icon: faCircleNodes, label: "Drafting connectors & toolkits" },
  { icon: faClipboardCheck, label: "Generating benchmark tasks" },
  { icon: faRobot, label: "Assembling the company agent" },
];

interface OnboardingMessage {
  role: "assistant" | "user" | "event";
  content: string;
  createdAt?: string;
  kind?: "thinking" | "tool_call" | "tool_result" | "assistant_summary" | string;
  toolName?: string;
  status?: string;
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
    provider?: string;
    generationStatus?: string;
    surface?: string;
    authRequired?: boolean;
    discoveryStatus?: string;
    runtimeRequirements?: string[];
    config?: Record<string, any>;
  }>;
  tasks: Array<{
    name: string;
    prompt: string;
    successCriteria?: string;
    status?: string;
    metadata?: {
      hints?: string[];
      startUrl?: string;
      expectedArtifacts?: string[];
      [key: string]: any;
    };
  }>;
  automationPlan?: Array<{
    connectorName?: string;
    strategy?: string;
    toolName?: string;
    runtimeRequirements?: string[];
    message?: string;
  }>;
  capabilityDiscovery?: {
    mode?: "task_scoped" | "broad_autodiscovery" | string;
    label?: string;
    description?: string;
  };
  questions?: string[];
}

interface OnboardingSession {
  sessionId: string;
  messages: OnboardingMessage[];
  draft: OnboardingDraft;
  status: string;
}

function connectorLogo(type: string) {
  const logos: Record<string, string> = {
    gmail: "/assets/images/connectors/mail.png",
    smtp: "/assets/images/connectors/mail.png",
    holded: "/assets/images/connectors/holded.png",
    telegram: "/assets/images/connectors/telegram.png",
    slack: "/assets/images/connectors/slack.png",
    discord: "/assets/images/connectors/discord.png",
    whatsapp: "/assets/images/connectors/whatsapp.png",
    teams: "/assets/images/connectors/teams.png",
    matrix: "/assets/images/connectors/matrix.svg",
    signal: "/assets/images/connectors/signal.svg",
    github: "/assets/images/connectors/github.svg",
    gitlab: "/assets/images/connectors/gitlab.svg",
    jira: "/assets/images/connectors/jira.svg",
    linear: "/assets/images/connectors/linear.svg",
    notion: "/assets/images/connectors/notion.svg",
    trello: "/assets/images/connectors/trello.svg",
    asana: "/assets/images/connectors/asana.svg",
    confluence: "/assets/images/connectors/confluence.svg",
    google_calendar: "/assets/images/connectors/google-calendar.svg",
    google_drive: "/assets/images/connectors/google-drive.svg",
    aws: "/assets/images/connectors/aws.png",
    runpod: "/assets/images/connectors/runpod.png",
    contabo: "/assets/images/connectors/contabo.svg",
    cloudflare: "/assets/images/connectors/cloudflare.svg",
    kubernetes: "/assets/images/connectors/kubernetes.svg",
    postgres: "/assets/images/connectors/postgres.svg",
    mongodb: "/assets/images/connectors/mongodb.svg",
    openai: "/assets/images/connectors/openai.png",
    google: "/assets/images/connectors/google.svg",
    taostats: "/assets/images/connectors/taostats.png",
    twitter: "/assets/images/connectors/x.svg",
    twitterapi: "/assets/images/connectors/twitterapi.png",
    bittensor_directory: "/assets/images/connectors/bittensor.png",
    bittensor_subnet_vendor: "/assets/images/connectors/bittensor.png",
    bittensor_desearch: "/assets/images/connectors/bittensor-desearch.png",
    bittensor_datauniverse: "/assets/images/connectors/bittensor-datauniverse.png",
    bittensor_chutes: "/assets/images/connectors/bittensor-chutes.png",
    bittensor_computehorde: "/assets/images/connectors/bittensor.png",
  };
  return logos[type] || "";
}

function eventIcon(kind?: string, status?: string) {
  if (status === "running") return faSpinner;
  if (kind === "thinking") return faBrain;
  if (kind === "tool_call") return faWrench;
  if (kind === "tool_result") return faCheckCircle;
  return faRobot;
}

function eventLabel(message: OnboardingMessage) {
  if (message.kind === "thinking") return "Thinking";
  if (message.kind === "tool_call") return message.toolName ? `Tool call · ${message.toolName}` : "Tool call";
  if (message.kind === "tool_result") return message.toolName ? `Done · ${message.toolName}` : "Done";
  if (message.kind === "assistant_summary") return "Summary";
  return "Agent";
}

function formatTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatSize(size: number) {
  if (!size) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

interface PendingFile {
  name: string;
  size: number;
  status: "uploading" | "done" | "error";
}

interface CelerisOnboardingProps {
  companyId?: string;
  companyName?: string;
  companyDescription?: string;
  onComplete?: () => void;
}

export default function CelerisOnboarding({ companyId = "", companyName = "", companyDescription = "", onComplete }: CelerisOnboardingProps) {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [session, setSession] = useState<OnboardingSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState("");
  const [workStep, setWorkStep] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Highlight items that were just added by the agent so the panel feels alive.
  const prevConnLen = useRef(0);
  const prevTaskLen = useRef(0);
  const [newConnFrom, setNewConnFrom] = useState<number | null>(null);
  const [newTaskFrom, setNewTaskFrom] = useState<number | null>(null);

  const draft = session?.draft;
  const ready = !!draft?.company?.name && (draft?.connectors?.length || 0) > 0 && (draft?.tasks?.length || 0) > 0;
  const busy = sending || uploading;

  const summary = useMemo(() => {
    if (!draft) return [];
    return [
      { label: "Company", value: draft.company.name || "—", icon: faBuilding },
      { label: "Connectors", value: String(draft.connectors.length), icon: faCircleNodes },
      { label: "Benchmarks", value: String(draft.tasks.length), icon: faClipboardCheck },
    ];
  }, [draft]);

  const setDiscoveryMode = (mode: "task_scoped" | "broad_autodiscovery") => {
    setSession((prev) => {
      if (!prev) return prev;
      const discovery = {
        mode,
        label: mode === "broad_autodiscovery" ? "Auto-discover additional tools and skills" : "Only what is needed for the requested tasks",
        description: mode === "broad_autodiscovery"
          ? "After solving the requested tasks, explore connected systems for additional reusable tools, trajectories and skills."
          : "Harvest only the tools, trajectories and skills needed to solve the benchmark tasks in this onboarding draft.",
      };
      const filteredPlan = (prev.draft.automationPlan || []).filter((item) => item.connectorName !== "All connectors");
      return {
        ...prev,
        draft: {
          ...prev.draft,
          capabilityDiscovery: discovery,
          automationPlan: [
            {
              connectorName: "All connectors",
              strategy: mode,
              runtimeRequirements: [],
              message: discovery.description,
            },
            ...filteredPlan,
          ],
        },
      };
    });
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.messages.length, sending, uploading, workStep, pendingFiles.length]);

  // Advance the simulated working steps while a request is in flight.
  useEffect(() => {
    if (!sending) {
      setWorkStep(0);
      return;
    }
    setWorkStep(0);
    const interval = setInterval(() => {
      setWorkStep((prev) => (prev < WORKING_STEPS.length - 1 ? prev + 1 : prev));
    }, 1100);
    return () => clearInterval(interval);
  }, [sending]);

  // Detect newly added connectors / tasks and flag them as "new" briefly.
  useEffect(() => {
    if (!draft) return;
    if (draft.connectors.length > prevConnLen.current && prevConnLen.current >= 0) {
      setNewConnFrom(prevConnLen.current);
      const t = setTimeout(() => setNewConnFrom(null), 2600);
      prevConnLen.current = draft.connectors.length;
      return () => clearTimeout(t);
    }
    prevConnLen.current = draft.connectors.length;
  }, [draft?.connectors.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!draft) return;
    if (draft.tasks.length > prevTaskLen.current && prevTaskLen.current >= 0) {
      setNewTaskFrom(prevTaskLen.current);
      const t = setTimeout(() => setNewTaskFrom(null), 2600);
      prevTaskLen.current = draft.tasks.length;
      return () => clearTimeout(t);
    }
    prevTaskLen.current = draft.tasks.length;
  }, [draft?.tasks.length]); // eslint-disable-line react-hooks/exhaustive-deps

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
        // Seed the "previous" counts so the initial draft does not flash as "new".
        prevConnLen.current = data.session?.draft?.connectors?.length || 0;
        prevTaskLen.current = data.session?.draft?.tasks?.length || 0;
        setSession(data.session);
      } catch (err: any) {
        setError(err?.message || "Could not start onboarding.");
      } finally {
        setLoading(false);
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
    // Optimistically show the user's message; the live working strip handles the rest.
    setSession((prev) => prev ? { ...prev, messages: [...prev.messages, { role: "user", content, createdAt: now }] } : prev);
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
          setPendingFiles((prev) => prev.map((f, idx) => idx === i ? { ...f, status: "error" } : f));
          throw new Error(await res.text());
        }
        const data = await res.json();
        uploaded.push(data.document?.filename || file.name);
        setPendingFiles((prev) => prev.map((f, idx) => idx === i ? { ...f, status: "done" } : f));
      }
      const completedAt = new Date().toISOString();
      setSession((prev) => prev ? {
        ...prev,
        messages: [
          ...prev.messages,
          {
            role: "user",
            content: `📎 Added ${uploaded.length} document${uploaded.length === 1 ? "" : "s"} to company Knowledge.`,
            createdAt: completedAt,
          },
          {
            role: "event",
            kind: "tool_result",
            toolName: "knowledge_upload",
            status: "completed",
            content: `Indexed into the company Knowledge connector: ${uploaded.join(", ")}.`,
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
                description: "Company knowledge connector for uploaded documents and internal sources.",
                status: "connected",
                provider: "official",
                generationStatus: "autoppia_supported",
              },
            ],
        },
      } : prev);
      // Let the success chips linger briefly, then clear.
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

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (!companyId) {
      setError("Save the company first to attach Knowledge documents.");
      return;
    }
    uploadDocuments(event.dataTransfer.files);
  };

  const showEmptyConversation = !loading && (!session || session.messages.length === 0) && !busy;

  return (
    <div className="w-full max-w-6xl animate-slide-up">
      <div className="mb-5">
        <div className="inline-flex items-center gap-2 px-3 h-8 rounded-full bg-gradient-primary text-white text-xs font-semibold mb-3 shadow-glow">
          <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[11px]" />
          Onboarding agent
          <span className="inline-flex items-center gap-1 ml-1 pl-2 border-l border-white/25">
            <span className="w-1.5 h-1.5 rounded-full bg-green-300 animate-pulse" />
            <span className="text-[10px] font-medium text-white/90">{busy ? "Working" : "Online"}</span>
          </span>
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold text-gray-900 dark:text-white mb-2 tracking-tight">Create a company agent by chatting</h1>
        <p className="text-sm md:text-base text-gray-500 dark:text-gray-400 max-w-3xl">
          Describe your company once. Automata reads it live, wires up connectors, drafts benchmark tasks, and assembles a specialized agent — you watch it happen.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_390px] gap-4">
        <div
          onDragOver={(e) => { e.preventDefault(); if (!dragging) setDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); if (e.currentTarget === e.target) setDragging(false); }}
          onDrop={handleDrop}
          className={`relative bg-white dark:bg-dark-surface rounded-2xl border shadow-soft overflow-hidden flex flex-col h-[min(720px,calc(100vh-170px))] min-h-[560px] transition-colors duration-200 ${
            dragging ? "border-primary ring-2 ring-primary/30" : "border-gray-200 dark:border-dark-border"
          }`}
        >
          {/* Drag overlay */}
          {dragging && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-primary/5 dark:bg-primary/10 backdrop-blur-sm pointer-events-none">
              <FontAwesomeIcon icon={faCloudArrowUp} className="text-primary text-3xl" />
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Drop files to add to company Knowledge</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">PDF, DOCX, Markdown, CSV, JSON…</p>
            </div>
          )}

          {/* Header */}
          <div className="px-5 py-4 border-b border-gray-100 dark:border-dark-border flex items-center justify-between bg-gradient-to-b from-gray-50/60 to-transparent dark:from-white/[0.02]">
            <div className="flex items-center gap-3 min-w-0">
              <span className="relative w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-glow flex-shrink-0">
                <FontAwesomeIcon icon={faRobot} className="text-sm" />
                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-green-400 border-2 border-white dark:border-dark-surface" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Automata</p>
                  <InfoIcon title="Example company setup">
                    <div className="space-y-3">
                      <p>Describe what the company does, what software it uses, and the workflows you want automated.</p>
                      <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs leading-5">
                        Celeris is a labor advisory firm in Andorra. We use SMTP for email, Holded for invoices, Telegram for team messages, internal documents for knowledge, and https://www.bopa.ad/ to read official updates.
                      </div>
                    </div>
                  </InfoIcon>
                </div>
                <p className="text-xs text-gray-400 flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${busy ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
                  {busy ? (uploading ? "Adding to Knowledge…" : "Thinking…") : "Ready · ask anything about your setup"}
                </p>
              </div>
            </div>
            <button
              onClick={() => sendMessage(CELERIS_PROMPT)}
              disabled={busy}
              className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border hover:border-gray-300 disabled:opacity-60 transition-colors flex items-center gap-1.5 flex-shrink-0"
            >
              <FontAwesomeIcon icon={faBolt} className="text-[10px] text-primary" />
              {sending ? "Running…" : "Try Celeris demo"}
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto scrollbar-thin px-5 py-5 space-y-3.5">
            {loading ? (
              <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-400">
                <FontAwesomeIcon icon={faSpinner} className="text-primary text-xl animate-spin" />
                <p className="text-xs">Starting the onboarding agent…</p>
              </div>
            ) : showEmptyConversation ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-6">
                <span className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
                  <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xl" />
                </span>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">Tell Automata about your company</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 max-w-sm mb-5">
                  Mention the tools you use, how you log in, the documents you rely on, and the daily tasks you want automated.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {["We use Gmail and Telegram", "Read invoices from Holded", "Summarize a weekly report"].map((chip) => (
                    <button
                      key={chip}
                      onClick={() => setInput(chip)}
                      className="px-3 h-8 rounded-full border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-xs text-gray-600 dark:text-gray-300 hover:border-primary/50 hover:text-primary transition-colors"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              session?.messages.map((message, index) => {
                if (message.role === "event") {
                  const icon = eventIcon(message.kind, message.status);
                  return (
                    <div key={`${message.role}-${message.kind}-${index}`} className="flex justify-start gap-2.5 float-up">
                      <span className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 mt-0.5">
                        <FontAwesomeIcon icon={icon} className={`text-[11px] ${message.status === "running" ? "animate-spin" : ""}`} />
                      </span>
                      <div className={`max-w-[84%] rounded-2xl rounded-tl-md px-4 py-2.5 text-sm leading-6 border ${
                        message.kind === "assistant_summary"
                          ? "bg-primary/5 border-primary/20 text-gray-800 dark:text-gray-100"
                          : "bg-gray-50 dark:bg-dark-bg border-gray-100 dark:border-dark-border text-gray-700 dark:text-gray-200"
                      }`}>
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{eventLabel(message)}</span>
                          {formatTime(message.createdAt) && (
                            <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-gray-400">
                              <FontAwesomeIcon icon={faClock} className="text-[9px]" />
                              {formatTime(message.createdAt)}
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      </div>
                    </div>
                  );
                }
                const isUser = message.role === "user";
                return (
                  <div key={`${message.role}-${index}`} className={`flex items-end gap-2.5 float-up ${isUser ? "justify-end" : "justify-start"}`}>
                    {!isUser && (
                      <span className="w-7 h-7 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
                        <FontAwesomeIcon icon={faRobot} className="text-[11px]" />
                      </span>
                    )}
                    <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-6 shadow-sm ${
                      isUser
                        ? "bg-gradient-primary text-white rounded-br-md"
                        : "bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200 border border-gray-100 dark:border-dark-border rounded-bl-md"
                    }`}>
                      <span className="whitespace-pre-wrap">{message.content}</span>
                    </div>
                  </div>
                );
              })
            )}

            {/* Live working strip — the agent "doing stuff" */}
            {sending && (
              <div className="flex justify-start gap-2.5 float-up">
                <span className="w-7 h-7 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
                  <FontAwesomeIcon icon={faRobot} className="text-[11px]" />
                </span>
                <div className="max-w-[88%] w-full rounded-2xl rounded-tl-md border border-primary/20 bg-primary/[0.04] dark:bg-primary/[0.06] px-4 py-3">
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className="flex items-center gap-1">
                      <span className="loading-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
                      <span className="loading-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
                      <span className="loading-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
                    </span>
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-primary">Working on your setup</span>
                  </div>
                  <div className="space-y-1.5">
                    {WORKING_STEPS.map((step, idx) => {
                      const state = idx < workStep ? "done" : idx === workStep ? "active" : "pending";
                      return (
                        <div key={step.label} className={`flex items-center gap-2.5 text-xs transition-all duration-300 ${
                          state === "pending" ? "opacity-35" : "opacity-100"
                        }`}>
                          <span className={`w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 ${
                            state === "done" ? "bg-green-500/15 text-green-500" : state === "active" ? "bg-primary/15 text-primary" : "bg-gray-200/60 dark:bg-dark-border text-gray-400"
                          }`}>
                            <FontAwesomeIcon
                              icon={state === "done" ? faCheck : state === "active" ? faSpinner : step.icon}
                              className={`text-[9px] ${state === "active" ? "animate-spin" : ""}`}
                            />
                          </span>
                          <span className={`${state === "active" ? "font-medium text-gray-800 dark:text-gray-100" : "text-gray-500 dark:text-gray-400"}`}>
                            {step.label}
                          </span>
                          {state === "active" && (
                            <span className="ml-auto flex-1 max-w-[80px] h-1 rounded-full bg-primary/15 overflow-hidden shimmer" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Upload progress chips */}
            {pendingFiles.length > 0 && (
              <div className="flex justify-end gap-2.5 float-up">
                <div className="max-w-[80%] rounded-2xl rounded-br-md border border-primary/25 bg-primary/[0.04] dark:bg-primary/[0.06] px-3.5 py-3">
                  <div className="flex items-center gap-2 mb-2">
                    <FontAwesomeIcon icon={faCloudArrowUp} className="text-primary text-xs" />
                    <span className="text-[11px] font-semibold text-gray-700 dark:text-gray-200">Uploading to Knowledge</span>
                  </div>
                  <div className="space-y-1.5">
                    {pendingFiles.map((file, idx) => (
                      <div key={`${file.name}-${idx}`} className="flex items-center gap-2 text-xs">
                        <FontAwesomeIcon
                          icon={file.status === "done" ? faCheckCircle : file.status === "error" ? faTriangleExclamation : faSpinner}
                          className={`text-[11px] flex-shrink-0 ${
                            file.status === "done" ? "text-green-500" : file.status === "error" ? "text-red-500" : "text-primary animate-spin"
                          }`}
                        />
                        <span className="text-gray-700 dark:text-gray-200 truncate max-w-[180px]">{file.name}</span>
                        <span className="ml-auto text-[10px] text-gray-400 flex-shrink-0">{formatSize(file.size)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="p-4 border-t border-gray-100 dark:border-dark-border bg-gray-50/40 dark:bg-white/[0.015]">
            {error && (
              <div className="mb-2 flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-[11px]" />
                <span className="flex-1">{error}</span>
                <button onClick={() => setError("")} className="text-red-400 hover:text-red-600"><FontAwesomeIcon icon={faXmark} className="text-[11px]" /></button>
              </div>
            )}
            <div className={`flex items-end gap-2 rounded-2xl border bg-white dark:bg-dark-bg px-2 py-1.5 transition-colors ${
              busy ? "border-gray-200 dark:border-dark-border" : "border-gray-200 dark:border-dark-border focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/15"
            }`}>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || !companyId}
                className="w-9 h-9 rounded-xl text-gray-500 dark:text-gray-300 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-50 transition-colors flex-shrink-0"
                title={companyId ? "Attach Knowledge documents" : "Save the company first to attach documents"}
              >
                <FontAwesomeIcon icon={uploading ? faSpinner : faPaperclip} className={`text-sm ${uploading ? "animate-spin" : ""}`} />
              </button>
              <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(event) => uploadDocuments(event.target.files)} />
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                  }
                }}
                rows={1}
                disabled={sending}
                placeholder="Describe your systems, paste API docs, or list more tasks…"
                className="flex-1 bg-transparent px-1 py-1.5 text-sm text-gray-900 dark:text-white outline-none resize-none max-h-32 scrollbar-thin disabled:opacity-60"
                style={{ minHeight: "36px" }}
              />
              <button
                onClick={() => sendMessage()}
                disabled={!input.trim() || sending}
                className="w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center disabled:opacity-40 hover:shadow-glow transition-all flex-shrink-0"
                title="Send"
              >
                <FontAwesomeIcon icon={sending ? faSpinner : faPaperPlane} className={`text-sm ${sending ? "animate-spin" : ""}`} />
              </button>
            </div>
            <p className="mt-2 px-1 text-[11px] text-gray-400 flex items-center gap-1.5">
              <FontAwesomeIcon icon={faPaperclip} className="text-[10px]" />
              Attached files become company <span className="font-medium text-gray-500 dark:text-gray-400">Knowledge</span>
              <span className="mx-1 text-gray-300 dark:text-gray-600">·</span>
              <span className="hidden sm:inline">Enter to send, Shift+Enter for a new line</span>
            </p>
          </div>
        </div>

        {/* Right column — live draft */}
        <div className="space-y-3">
          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FontAwesomeIcon icon={faBuilding} className="text-primary text-xs" />
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Live draft</p>
              </div>
              {busy && <span className="inline-flex items-center gap-1 text-[10px] font-medium text-primary"><span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />updating</span>}
            </div>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {summary.map((item) => (
                <div key={item.label} className="rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border p-2.5">
                  <div className="flex items-center gap-1 mb-1">
                    <FontAwesomeIcon icon={item.icon} className="text-[9px] text-gray-400" />
                    <p className="text-[10px] text-gray-400">{item.label}</p>
                  </div>
                  <p className="text-base font-semibold text-gray-900 dark:text-white truncate leading-none">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-gray-100 dark:border-dark-border bg-gradient-to-br from-primary/[0.04] to-transparent p-3">
              <p className="text-[10px] font-medium uppercase tracking-wide text-gray-400 mb-1">Agent</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{draft?.agent?.name || "Not set yet"}</p>
              <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{draft?.company?.industry || draft?.company?.description || "Waiting for company context…"}</p>
            </div>
          </div>

          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center gap-2 mb-3">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="text-primary text-xs" />
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Discovery scope</p>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {[
                {
                  mode: "task_scoped" as const,
                  title: "Only requested tasks",
                  body: "Create the minimum tools, trajectories and skills needed for the tasks listed here.",
                },
                {
                  mode: "broad_autodiscovery" as const,
                  title: "Auto-discover more",
                  body: "After task coverage, explore connected systems for additional reusable tools and skills.",
                },
              ].map((option) => {
                const active = (draft?.capabilityDiscovery?.mode || "task_scoped") === option.mode;
                return (
                  <button
                    key={option.mode}
                    type="button"
                    onClick={() => setDiscoveryMode(option.mode)}
                    className={`text-left rounded-xl border p-2.5 transition-colors ${
                      active
                        ? "border-primary/40 bg-primary/[0.06]"
                        : "border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg hover:border-primary/25"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-gray-900 dark:text-white">{option.title}</p>
                      {active && <FontAwesomeIcon icon={faCheck} className="text-primary text-[10px]" />}
                    </div>
                    <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1 leading-4">{option.body}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {(draft?.automationPlan || []).length > 0 && (
            <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
              <div className="flex items-center gap-2 mb-3">
                <FontAwesomeIcon icon={faWandMagicSparkles} className="text-primary text-xs" />
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Automation plan</p>
              </div>
              <div className="space-y-2 max-h-[150px] overflow-auto scrollbar-thin">
                {(draft?.automationPlan || []).map((item, index) => (
                  <div key={`${item.connectorName}-${item.strategy}-${index}`} className="rounded-xl border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-gray-900 dark:text-white truncate">{item.connectorName || "Connector"}</p>
                      <span className="px-1.5 py-0.5 rounded-md border border-gray-200 dark:border-dark-border text-[10px] text-gray-500 dark:text-gray-300 whitespace-nowrap">
                        {(item.strategy || "strategy").replace(/_/g, " ")}
                      </span>
                    </div>
                    {item.toolName && <p className="mt-1 font-mono text-[11px] text-primary truncate">{item.toolName}</p>}
                    {item.message && <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 line-clamp-2">{item.message}</p>}
                    {(item.runtimeRequirements || []).length > 0 && (
                      <p className="mt-1 text-[10px] text-gray-400">requires {(item.runtimeRequirements || []).join(", ")}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FontAwesomeIcon icon={faCircleNodes} className="text-primary text-xs" />
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Connectors & toolkits</p>
              </div>
              <span className="px-1.5 h-5 inline-flex items-center rounded-md bg-gray-100 dark:bg-dark-border text-[11px] font-semibold text-gray-500 dark:text-gray-300">{draft?.connectors?.length || 0}</span>
            </div>
            <div className="space-y-2 max-h-[190px] overflow-auto scrollbar-thin">
              {(draft?.connectors || []).map((connector, index) => {
                const logo = connectorLogo(connector.type);
                const isNew = newConnFrom !== null && index >= newConnFrom;
                return (
                  <div key={`${connector.name}-${index}`} className={`flex items-center gap-3 rounded-xl border p-2.5 transition-colors ${
                    isNew ? "border-primary/40 bg-primary/[0.05] float-up" : "border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg"
                  }`}>
                    {logo ? (
                      <span className="w-8 h-8 rounded-lg bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border flex items-center justify-center overflow-hidden flex-shrink-0">
                        <img src={logo} alt="" className="w-full h-full object-contain p-1.5" />
                      </span>
                    ) : (
                      <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                        <FontAwesomeIcon icon={connector.type === "knowledge" ? faFileLines : connector.type === "api" ? faDatabase : faWrench} className="text-xs" />
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{connector.name}</p>
                        {isNew && <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-primary text-white flex-shrink-0">New</span>}
                      </div>
                      <p className="text-[11px] text-gray-400 truncate">
                        {(connector.provider === "custom" ? "Custom generated" : "Autoppia official")} · {connector.surface || connector.type}
                      </p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {connector.discoveryStatus && (
                          <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-border text-[9px] font-semibold uppercase text-gray-500 dark:text-gray-300">
                            discovery {connector.discoveryStatus}
                          </span>
                        )}
                        {connector.authRequired && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-500/10 text-[9px] font-semibold uppercase text-amber-600 dark:text-amber-300">
                            auth required
                          </span>
                        )}
                        {(connector.runtimeRequirements || []).slice(0, 2).map((requirement) => (
                          <span key={requirement} className="px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-500/10 text-[9px] font-semibold uppercase text-blue-600 dark:text-blue-300">
                            {requirement}
                          </span>
                        ))}
                      </div>
                    </div>
                    <span className={`text-[10px] font-medium whitespace-nowrap flex-shrink-0 ${connector.status === "connected" ? "text-green-500" : "text-gray-400"}`}>
                      {connector.status === "connected" ? "connected" : connector.status || "pending"}
                    </span>
                  </div>
                );
              })}
              {(draft?.connectors || []).length === 0 && (
                <div className="rounded-xl border border-dashed border-gray-200 dark:border-dark-border py-5 text-center">
                  <p className="text-xs text-gray-400">Connectors appear here as you describe your tools.</p>
                </div>
              )}
            </div>
          </div>

          <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FontAwesomeIcon icon={faClipboardCheck} className="text-primary text-xs" />
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Benchmark tasks</p>
              </div>
              <span className="px-1.5 h-5 inline-flex items-center rounded-md bg-gray-100 dark:bg-dark-border text-[11px] font-semibold text-gray-500 dark:text-gray-300">{draft?.tasks?.length || 0}</span>
            </div>
            <div className="space-y-2 max-h-[210px] overflow-auto scrollbar-thin">
              {(draft?.tasks || []).map((task, index) => {
                const isNew = newTaskFrom !== null && index >= newTaskFrom;
                return (
                  <div key={`${task.name}-${index}`} className={`rounded-xl border p-2.5 transition-colors ${
                    isNew ? "border-primary/40 bg-primary/[0.05] float-up" : "border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg"
                  }`}>
                    <div className="flex items-center gap-1.5">
                      <span className="w-4 h-4 rounded bg-primary/10 text-primary text-[9px] font-bold flex items-center justify-center flex-shrink-0">{index + 1}</span>
                      <p className="text-xs font-semibold text-gray-900 dark:text-white truncate flex-1">{task.name || `Task ${index + 1}`}</p>
                      {isNew && <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-primary text-white flex-shrink-0">New</span>}
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2 pl-6">{task.prompt}</p>
                    {task.successCriteria && (
                      <p className="text-[11px] text-gray-400 mt-1 line-clamp-2 pl-6">Success: {task.successCriteria}</p>
                    )}
                    {(task.metadata?.hints || []).length > 0 && (
                      <p className="text-[11px] text-gray-400 mt-1 line-clamp-2 pl-6">Hints: {(task.metadata?.hints || []).join(" · ")}</p>
                    )}
                    {task.metadata?.startUrl && (
                      <p className="font-mono text-[10px] text-gray-400 mt-1 truncate pl-6">{task.metadata.startUrl}</p>
                    )}
                  </div>
                );
              })}
              {(draft?.tasks || []).length === 0 && (
                <div className="rounded-xl border border-dashed border-gray-200 dark:border-dark-border py-5 text-center">
                  <p className="text-xs text-gray-400">Benchmark tasks are drafted from the workflows you mention.</p>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={finalize}
            disabled={!ready || finalizing}
            className="w-full h-12 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow flex items-center justify-center gap-2 disabled:opacity-50 hover:shadow-glow-lg transition-all"
          >
            <FontAwesomeIcon icon={finalizing ? faSpinner : faArrowRight} className={`text-xs ${finalizing ? "animate-spin" : ""}`} />
            {finalizing ? "Creating draft agent…" : "Create draft agent"}
          </button>
          {!ready && !finalizing && (
            <p className="text-center text-[11px] text-gray-400 -mt-1">
              Add a company, at least one connector and one benchmark task to continue.
            </p>
          )}
          {ready && !finalizing && (
            <p className="text-center text-[11px] text-gray-400 -mt-1">
              Next: validate credentials, harvest traces, and run the benchmark.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
