import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import {
  faArrowRight,
  faBook,
  faBuilding,
  faCheck,
  faCheckCircle,
  faCircle,
  faCode,
  faCopy,
  faGlobe,
  faKey,
  faPaperPlane,
  faPlug,
  faRobot,
  faRotateRight,
  faSpinner,
  faTriangleExclamation,
  faWandMagicSparkles,
} from "@fortawesome/free-solid-svg-icons";
import SectionTitle from "../components/layout/section-title";
import { Company } from "../utils/types";
import { getApiUrl } from "../utils/api-url";
import { apiErrorMessage } from "../utils/api-error";
import { useToast } from "../components/common/toast";
import { useStudioMode } from "../utils/studio-mode";

const apiUrl = getApiUrl();
const RUNTIME_KINDS = ["model_agent", "codex", "claude_code"];

type Sender = "automata" | "user" | "system";
type MaterialKind = "website" | "document_url" | "api_docs" | "openapi" | "auth_note" | "knowledge_note" | "task_list";

interface MaterialType {
  kind: MaterialKind;
  label: string;
  icon: IconDefinition;
  hint: string;
}

const MATERIAL_TYPES: MaterialType[] = [
  { kind: "website", label: "Website / app", icon: faGlobe, hint: "Websites or apps Automata should learn to use." },
  { kind: "document_url", label: "Docs / PDF", icon: faBook, hint: "Policies, handbooks, help centers and PDFs." },
  { kind: "api_docs", label: "API docs", icon: faPlug, hint: "Human-readable API documentation." },
  { kind: "openapi", label: "OpenAPI", icon: faPlug, hint: "Swagger/OpenAPI specs." },
  { kind: "auth_note", label: "Auth note", icon: faKey, hint: "Login instructions or credential references. Do not paste raw secrets." },
  { kind: "knowledge_note", label: "Knowledge", icon: faBook, hint: "Free-form company context." },
  { kind: "task_list", label: "Tasks", icon: faCheckCircle, hint: "Workflows or jobs the agents should learn." },
];

interface ChatMessage {
  id: string;
  sender: Sender;
  text: string;
  timestamp: string;
  action?: "start" | "answer" | "refresh";
}

interface DraftMaterial {
  id: string;
  kind: MaterialKind;
  value: string;
  name: string;
}

interface NormalStatus {
  runId: string;
  intakeId: string;
  companyId: string;
  status: string;
  currentStep: string;
  steps: Array<{ key: string; label: string; status: string; message?: string; visibility?: string }>;
  summary: Record<string, any>;
  delivery: Record<string, any>;
  questions: Array<{ questionId: string; code: string; prompt: string; severity: string; expectedAnswerType: string }>;
  nextAction: Record<string, any>;
  errors: string[];
}

function newId(prefix: string): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return `${prefix}_${crypto.randomUUID()}`;
  } catch {
    /* ignore */
  }
  return `${prefix}_${Math.random().toString(36).slice(2)}`;
}

function nowStamp(): string {
  return new Date().toISOString();
}

function runKey(companyId: string): string {
  return `automata_harvest_run_${companyId}`;
}

function materialType(kind: string): MaterialType {
  return MATERIAL_TYPES.find((item) => item.kind === kind) || MATERIAL_TYPES[0];
}

function stepTone(status: string): { icon: IconDefinition; spin?: boolean; cls: string } {
  if (status === "done") return { icon: faCheckCircle, cls: "text-emerald-500" };
  if (status === "in_progress") return { icon: faSpinner, spin: true, cls: "text-primary" };
  if (status === "blocked") return { icon: faTriangleExclamation, cls: "text-amber-500" };
  return { icon: faCircle, cls: "text-gray-300 dark:text-zinc-600" };
}

function inferMaterialKind(text: string, url: string): MaterialKind {
  const lower = `${text} ${url}`.toLowerCase();
  if (lower.includes("web app") || lower.includes("app is") || lower.includes("website")) return "website";
  if (lower.includes("openapi") || lower.includes("swagger") || lower.endsWith(".json") || lower.includes("openapi.json")) return "openapi";
  if (lower.includes("api")) return "api_docs";
  if (lower.includes(".pdf") || lower.includes("docs") || lower.includes("documentation") || lower.includes("handbook") || lower.includes("policy")) return "document_url";
  return "website";
}

function extractUrls(text: string): string[] {
  const matches = text.match(/https?:\/\/[^\s),]+/gi) || [];
  return Array.from(new Set(matches.map((item) => item.replace(/[.。]$/, ""))));
}

function extractTaskLines(text: string): string[] {
  const lines = text
    .split(/\n|;/)
    .map((line) => line.trim().replace(/^[-*]\s*/, ""))
    .filter(Boolean);
  const taskHints = ["task", "tarea", "workflow", "automat", "agent", "need", "quiero", "necesito", "answer", "responder", "actualizar", "buscar", "draft", "crear"];
  return lines.filter((line) => {
    const lower = line.toLowerCase();
    if (/^(tasks?|tareas?|workflows?)\s*:?\s*$/.test(lower)) return false;
    return taskHints.some((hint) => lower.includes(hint)) && !extractUrls(line).length;
  });
}

function buildParsedMaterials(text: string): { materials: DraftMaterial[]; tasks: string[] } {
  const urls = extractUrls(text);
  const materials = urls.map((url) => {
    const kind = inferMaterialKind(text, url);
    return { id: newId("mat"), kind, value: url, name: url };
  });
  const lower = text.toLowerCase();
  if ((lower.includes("auth") || lower.includes("login") || lower.includes("credential") || lower.includes("credencial")) && !urls.length) {
    materials.push({ id: newId("mat"), kind: "auth_note", value: text.trim(), name: "Auth note" });
  } else if (!urls.length && text.trim().length > 20 && !extractTaskLines(text).length) {
    materials.push({ id: newId("mat"), kind: "knowledge_note", value: text.trim(), name: "Knowledge note" });
  }
  return { materials, tasks: extractTaskLines(text) };
}

function dedupeMaterials(prev: DraftMaterial[], next: DraftMaterial[]): DraftMaterial[] {
  const seen = new Set(prev.map((item) => `${item.kind}:${item.value}`));
  const merged = [...prev];
  next.forEach((item) => {
    const key = `${item.kind}:${item.value}`;
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(item);
    }
  });
  return merged;
}

function initialMessages(companyName: string): ChatMessage[] {
  return [
    {
      id: newId("msg"),
      sender: "automata",
      text: `Hi, I'm Automata. Tell me about ${companyName || "your company"} and send me the website, docs, API docs, auth notes, or tasks you want automated. I'll collect the context and start the company onboarding when you're ready.`,
      timestamp: nowStamp(),
    },
  ];
}

function statusMessage(status: NormalStatus): string {
  const summary = status.summary || {};
  if (status.status === "needs_user_input") return "I need a little more information before I can continue.";
  if (status.nextAction?.kind === "implement_connectors") {
    return "I found integrations that need a developer implementation step before I can complete those tasks.";
  }
  if (status.status === "ready" || status.delivery?.state === "ready") {
    return `Your agents are ready. I prepared ${summary.agentsReady || status.delivery?.readyAgentCount || 0} ready agent(s).`;
  }
  if (summary.recommendedNextAction) return String(summary.recommendedNextAction);
  return "I'm analyzing your company and preparing agents.";
}

export default function Onboarding(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const mode = useStudioMode();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const pollRef = useRef<number | null>(null);

  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [company, setCompany] = useState<Company | null>(null);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companyName, setCompanyName] = useState("");
  const [companyDescription, setCompanyDescription] = useState("");
  const [materials, setMaterials] = useState<DraftMaterial[]>([]);
  const [tasks, setTasks] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState<NormalStatus | null>(null);
  const [devRun, setDevRun] = useState<Record<string, any> | null>(null);
  const [pendingQuestionId, setPendingQuestionId] = useState("");
  const [starting, setStarting] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [error, setError] = useState("");

  const addMessage = useCallback((message: Omit<ChatMessage, "id" | "timestamp">) => {
    setMessages((prev) => [...prev, { ...message, id: newId("msg"), timestamp: nowStamp() }]);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId ?? localStorage.getItem("automata_company_id") ?? "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const loadCompany = useCallback(async () => {
    if (!user.email) {
      setCompany(null);
      setCompaniesLoading(false);
      return;
    }
    setCompaniesLoading(true);
    try {
      const res = await fetch(`${apiUrl}/companies?email=${encodeURIComponent(user.email)}`);
      const data = res.ok ? await res.json() : { companies: [] };
      const companies = (data.companies || []) as Company[];
      const selected = companies.find((item) => item.companyId === companyId) || companies[0] || null;
      setCompany(selected);
      if (selected && selected.companyId !== companyId) setCompanyId(selected.companyId);
    } catch (err) {
      console.error("Failed to load company:", err);
      setCompany(null);
    } finally {
      setCompaniesLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadCompany();
  }, [loadCompany]);

  useEffect(() => {
    const name = company?.name && company.name !== "Default Company" ? company.name : "";
    setCompanyName(name);
    setCompanyDescription(company?.description || "");
    setMaterials([]);
    setTasks([]);
    setMessages(initialMessages(name));
    setInput("");
    setError("");
    setPendingQuestionId("");
    setStatus(null);
    setDevRun(null);
    const savedRun = company ? localStorage.getItem(runKey(company.companyId)) || "" : "";
    setRunId(savedRun);
  }, [company]);

  useEffect(() => {
    const target = messagesEndRef.current;
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length, status?.status]);

  const fetchStatus = useCallback(
    async (id: string, withDev: boolean, announce = false) => {
      if (!id) return;
      const headers = user.email ? { "X-User-Email": user.email } : undefined;
      try {
        const res = await fetch(`${apiUrl}/company-harvest-runs/${id}/status?mode=normal`, { headers });
        if (res.status === 404) {
          if (company) localStorage.removeItem(runKey(company.companyId));
          setRunId("");
          setStatus(null);
          return;
        }
        if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not load onboarding status."));
        const data = await res.json();
        const nextStatus = data.status as NormalStatus;
        setStatus(nextStatus);
        setError("");
        if (announce) addMessage({ sender: "automata", text: statusMessage(nextStatus) });
        if ((nextStatus.questions || []).length > 0) {
          const first = nextStatus.questions[0];
          setPendingQuestionId(first.questionId);
          addMessage({ sender: "automata", text: first.prompt, action: "answer" });
        }
        if (withDev) {
          const devRes = await fetch(`${apiUrl}/company-harvest-runs/${id}/status?mode=dev`, { headers });
          if (devRes.ok) {
            const devData = await devRes.json();
            setDevRun(devData.status || null);
          }
        } else {
          setDevRun(null);
        }
      } catch (err: any) {
        console.error("Failed to load harvest status:", err);
        setError(err?.message || "Could not load onboarding status.");
      }
    },
    [addMessage, company, user.email],
  );

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!runId) {
      setStatus(null);
      return;
    }
    fetchStatus(runId, mode === "dev", true);
    pollRef.current = window.setInterval(() => fetchStatus(runId, mode === "dev"), 5000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [fetchStatus, mode, runId]);

  useEffect(() => {
    const s = status?.status || "";
    if ((s === "ready" || s === "failed" || s === "needs_user_input") && pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [status?.status]);

  const buildMaterialsPayload = useCallback(() =>
    materials.map((m) => {
      if (m.kind === "auth_note" || m.kind === "knowledge_note" || m.kind === "task_list") return { kind: m.kind, name: materialType(m.kind).label, content: m.value };
      return { kind: m.kind, name: m.name || m.value, url: m.value };
    }), [materials]);

  const buildUserTasks = useCallback(() => tasks.map((task) => ({ name: task.slice(0, 60), prompt: task })), [tasks]);

  const addParsedContext = useCallback(
    (text: string) => {
      const parsed = buildParsedMaterials(text);
      if (parsed.materials.length) setMaterials((prev) => dedupeMaterials(prev, parsed.materials));
      if (parsed.tasks.length) {
        setTasks((prev) => Array.from(new Set([...prev, ...parsed.tasks])));
      }
      const notes = [];
      if (parsed.materials.length) notes.push(`${parsed.materials.length} source${parsed.materials.length === 1 ? "" : "s"}`);
      if (parsed.tasks.length) notes.push(`${parsed.tasks.length} task${parsed.tasks.length === 1 ? "" : "s"}`);
      if (notes.length) addMessage({ sender: "automata", text: `Got it. I added ${notes.join(" and ")} to the onboarding context.` });
      else addMessage({ sender: "automata", text: "Got it. I saved that as company context. Send more material, or start onboarding when ready.", action: "start" });
    },
    [addMessage],
  );

  const startHarvest = useCallback(async () => {
    if (!company || starting) return;
    if (!companyName.trim()) {
      setError("Add a company name before starting onboarding.");
      addMessage({ sender: "automata", text: "What is the company name? I need that before I can start onboarding." });
      return;
    }
    setStarting(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/company-intakes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId: company.companyId,
          companyName: companyName.trim(),
          description: companyDescription.trim(),
          materials: buildMaterialsPayload(),
          userTasks: buildUserTasks(),
          mode,
          startHarvest: true,
          autoSolveTasks: true,
          autoPromoteSkills: true,
          buildAgents: true,
          runtimeKinds: RUNTIME_KINDS,
        }),
      });
      if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not start onboarding."));
      const data = await res.json();
      const nextRunId = data.harvestRun?.runId || "";
      if (!nextRunId) throw new Error("Onboarding started but no run id was returned.");
      localStorage.setItem(runKey(company.companyId), nextRunId);
      setRunId(nextRunId);
      addMessage({ sender: "automata", text: "I've started onboarding. I'll analyze the company material, infer tasks, test what I can, and prepare agents." });
      showToast("Automata is analyzing your company.", "success");
    } catch (err: any) {
      console.error("Failed to start onboarding:", err);
      setError(err?.message || "Could not start onboarding.");
    } finally {
      setStarting(false);
    }
  }, [addMessage, buildMaterialsPayload, buildUserTasks, company, companyDescription, companyName, mode, showToast, starting, user.email]);

  const submitAnswer = useCallback(
    async (text: string) => {
      if (!status || !pendingQuestionId || answering) return;
      const question = (status.questions || []).find((item) => item.questionId === pendingQuestionId) || status.questions?.[0];
      if (!question) return;
      setAnswering(true);
      setError("");
      try {
        const answer: Record<string, any> = { questionId: question.questionId, code: question.code, value: text };
        if (question.expectedAnswerType === "credentials") answer.credentialRef = text;
        if (question.expectedAnswerType === "task_list") {
          answer.tasks = text
            .split(/\n|;/)
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => ({ name: line.slice(0, 60), prompt: line }));
        }
        const res = await fetch(`${apiUrl}/company-harvest-runs/${status.runId}/answers`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(user.email ? { "X-User-Email": user.email } : {}) },
          body: JSON.stringify({
            answers: [answer],
            continueHarvest: true,
            autoSolveTasks: true,
            autoPromoteSkills: true,
            buildAgents: true,
            runtimeKinds: RUNTIME_KINDS,
          }),
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not submit your answer."));
        setPendingQuestionId("");
        addMessage({ sender: "automata", text: "Thanks. I'm continuing the onboarding run now." });
        showToast("Automata is continuing.", "success");
        await fetchStatus(status.runId, mode === "dev", true);
      } catch (err: any) {
        console.error("Failed to submit answer:", err);
        setError(err?.message || "Could not submit your answer.");
      } finally {
        setAnswering(false);
      }
    },
    [addMessage, answering, fetchStatus, mode, pendingQuestionId, showToast, status, user.email],
  );

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    addMessage({ sender: "user", text });
    if (pendingQuestionId && status) {
      await submitAnswer(text);
      return;
    }
    const lower = text.toLowerCase();
    if (lower.includes("start") || lower.includes("empez") || lower.includes("comienza") || lower.includes("go ahead") || lower.includes("onboard")) {
      await startHarvest();
      return;
    }
    if (lower.includes("company name") || lower.includes("empresa:") || lower.includes("company:")) {
      const clean = text.replace(/company name|company:|empresa:/gi, "").trim();
      if (clean) setCompanyName(clean);
    }
    addParsedContext(text);
  }, [addMessage, addParsedContext, input, pendingQuestionId, startHarvest, status, submitAnswer]);

  const resetRun = () => {
    if (company) localStorage.removeItem(runKey(company.companyId));
    setRunId("");
    setStatus(null);
    setDevRun(null);
    setPendingQuestionId("");
    setMessages(initialMessages(companyName || company?.name || ""));
  };

  if (companiesLoading) {
    return (
      <Shell>
        <div className="rounded-2xl border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">Loading onboarding...</div>
      </Shell>
    );
  }

  if (!company) {
    return (
      <Shell>
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center dark:border-dark-border dark:bg-dark-surface">
          <FontAwesomeIcon icon={faBuilding} className="text-2xl text-gray-300 dark:text-zinc-600" />
          <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">Pick a company to onboard</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">Use the company selector in the top bar, then Automata will help you set it up.</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <Header company={company} mode={mode} hasRun={Boolean(runId)} onReset={resetRun} />
      {error ? (
        <div className="flex items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          <FontAwesomeIcon icon={faTriangleExclamation} />
          {error}
        </div>
      ) : null}
      <div className="grid min-h-[680px] gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <ChatSurface
          messages={messages}
          input={input}
          setInput={setInput}
          onSend={sendMessage}
          onStart={startHarvest}
          onRefresh={() => runId && fetchStatus(runId, mode === "dev", true)}
          starting={starting}
          answering={answering}
          canStart={!runId}
          pendingQuestion={Boolean(pendingQuestionId)}
          status={status}
          messagesEndRef={messagesEndRef}
        />
        <ContextPanel
          companyName={companyName}
          setCompanyName={setCompanyName}
          companyDescription={companyDescription}
          setCompanyDescription={setCompanyDescription}
          materials={materials}
          setMaterials={setMaterials}
          tasks={tasks}
          setTasks={setTasks}
          status={status}
          navigate={navigate}
          showToast={showToast}
        />
      </div>
      {mode === "dev" ? <DevPanel status={status} devRun={devRun} /> : null}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full overflow-auto bg-gray-50/70 px-4 py-6 dark:bg-dark-bg sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-5">{children}</div>
    </div>
  );
}

function Header({ company, mode, hasRun, onReset }: { company: Company; mode: string; hasRun: boolean; onReset: () => void }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <SectionTitle
            icon={faWandMagicSparkles}
            title="Automata onboarding"
            subtitle="Chat with Automata. Share company docs, URLs, auth notes and tasks; Automata will discover systems and prepare agents."
          />
          <div className="mt-4 flex flex-wrap gap-2">
            <Chip icon={faBuilding} label={company.name} />
            <Chip icon={mode === "dev" ? faCode : faRobot} label={mode === "dev" ? "Dev mode" : "Normal mode"} />
          </div>
        </div>
        {hasRun ? (
          <button type="button" onClick={onReset} className="inline-flex h-9 flex-shrink-0 items-center gap-2 self-start rounded-xl border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg">
            <FontAwesomeIcon icon={faRotateRight} className="text-[10px]" />
            New onboarding
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Chip({ icon, label }: { icon: IconDefinition; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
      <FontAwesomeIcon icon={icon} className="text-[10px]" />
      {label}
    </span>
  );
}

function ChatSurface(props: {
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  onSend: () => void;
  onStart: () => void;
  onRefresh: () => void;
  starting: boolean;
  answering: boolean;
  canStart: boolean;
  pendingQuestion: boolean;
  status: NormalStatus | null;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <section className="flex min-h-[680px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gray-200 px-5 py-4 dark:border-dark-border">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Onboarding chat</h2>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">Talk naturally. Automata will collect what it needs.</p>
          </div>
          {props.status ? <StatusPill status={props.status.status} /> : null}
        </div>
      </div>
      {props.status ? <ProgressStrip status={props.status} /> : null}
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-5">
        {props.messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={props.messagesEndRef} />
      </div>
      <div className="border-t border-gray-200 p-4 pb-20 pr-16 dark:border-dark-border sm:pb-4 sm:pr-4">
        {props.canStart ? (
          <div className="mb-3 flex flex-wrap gap-2">
            <QuickPrompt label="Add website" text="Our web app is https://app.example.com" setInput={props.setInput} />
            <QuickPrompt label="Add API docs" text="Our OpenAPI docs are at https://api.example.com/openapi.json" setInput={props.setInput} />
            <QuickPrompt label="Add tasks" text={"Tasks:\n- Answer customer questions from our docs\n- Update records in our CRM"} setInput={props.setInput} />
            <button type="button" onClick={props.onStart} disabled={props.starting} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white disabled:opacity-60">
              {props.starting ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={faWandMagicSparkles} />}
              Start onboarding
            </button>
          </div>
        ) : (
          <div className="mb-3 flex flex-wrap gap-2">
            <button type="button" onClick={props.onRefresh} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg">
              <FontAwesomeIcon icon={faRotateRight} className="text-[10px]" />
              Refresh
            </button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={props.input}
            onChange={(e) => props.setInput(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                props.onSend();
              }
            }}
            rows={2}
            placeholder={props.pendingQuestion ? "Answer Automata..." : "Send docs, URLs, API docs, auth notes, or tasks..."}
            className="min-h-[48px] min-w-0 flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
          />
          <button type="button" onClick={props.onSend} disabled={!props.input.trim() || props.starting || props.answering} aria-label="Send onboarding message" className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-primary text-white shadow-glow disabled:opacity-50">
            {props.answering ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={faPaperPlane} />}
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-400">Normal mode hides raw internals. Switch to Dev mode to inspect factory details.</p>
      </div>
    </section>
  );
}

function QuickPrompt({ label, text, setInput }: { label: string; text: string; setInput: (value: string) => void }) {
  return (
    <button type="button" onClick={() => setInput(text)} className="inline-flex h-8 items-center rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg">
      {label}
    </button>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.sender === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm shadow-sm ${isUser ? "bg-primary text-white" : message.sender === "system" ? "bg-gray-100 text-gray-600 dark:bg-dark-bg dark:text-gray-300" : "border border-gray-200 bg-white text-gray-800 dark:border-dark-border dark:bg-dark-bg dark:text-gray-100"}`}>
        {!isUser ? (
          <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
            <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
            Automata
          </div>
        ) : null}
        <p className="whitespace-pre-wrap leading-relaxed">{message.text}</p>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const label = status.replace(/_/g, " ");
  const ready = status === "ready";
  const blocked = status === "needs_user_input" || status === "failed";
  return (
    <span className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${ready ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300" : blocked ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300" : "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300"}`}>
      {label}
    </span>
  );
}

function ProgressStrip({ status }: { status: NormalStatus }) {
  const visibleSteps = (status.steps || []).slice(0, 8);
  return (
    <div className="border-b border-gray-200 bg-gray-50/70 px-5 py-3 dark:border-dark-border dark:bg-dark-bg/60">
      <div className="flex flex-wrap gap-2">
        {visibleSteps.map((step) => {
          const tone = stepTone(step.status);
          return (
            <span key={step.key} title={step.message || step.label} className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
              <FontAwesomeIcon icon={tone.icon} className={`${tone.cls} ${tone.spin ? "animate-spin" : ""}`} />
              <span className="truncate">{step.label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function ContextPanel(props: {
  companyName: string;
  setCompanyName: (value: string) => void;
  companyDescription: string;
  setCompanyDescription: (value: string) => void;
  materials: DraftMaterial[];
  setMaterials: React.Dispatch<React.SetStateAction<DraftMaterial[]>>;
  tasks: string[];
  setTasks: React.Dispatch<React.SetStateAction<string[]>>;
  status: NormalStatus | null;
  navigate: (path: string) => void;
  showToast: (m: string, t?: any) => void;
}) {
  const summary = props.status?.summary || {};
  const delivery = props.status?.delivery || {};
  return (
    <aside className="flex min-h-0 flex-col gap-4">
      <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Onboarding context</h2>
        <label className="mt-3 block">
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">Company name</span>
          <input value={props.companyName} onChange={(e) => props.setCompanyName(e.target.value)} placeholder="Company name" className="mt-1.5 h-9 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white" />
        </label>
        <label className="mt-3 block">
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">Short description</span>
          <textarea value={props.companyDescription} onChange={(e) => props.setCompanyDescription(e.target.value)} rows={3} placeholder="What does this company do?" className="mt-1.5 w-full resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white" />
        </label>
      </section>
      <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Sources</h2>
          <span className="text-xs text-gray-400">{props.materials.length}</span>
        </div>
        <div className="mt-3 space-y-2">
          {props.materials.length ? (
            props.materials.map((material) => {
              const type = materialType(material.kind);
              return (
                <div key={material.id} className="flex gap-2 rounded-xl border border-gray-200 bg-gray-50 p-2 dark:border-dark-border dark:bg-dark-bg">
                  <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FontAwesomeIcon icon={type.icon} className="text-[10px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{type.label}</p>
                    <p className="truncate text-xs text-gray-500 dark:text-gray-400">{material.value}</p>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="rounded-xl border border-dashed border-gray-200 px-3 py-3 text-xs text-gray-400 dark:border-dark-border">Send a URL, doc, API spec or note in chat.</p>
          )}
        </div>
      </section>
      <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Tasks</h2>
          <span className="text-xs text-gray-400">{props.tasks.length || summary.taskCandidatesFound || 0}</span>
        </div>
        <div className="mt-3 space-y-2">
          {props.tasks.length ? (
            props.tasks.map((task) => (
              <p key={task} className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{task}</p>
            ))
          ) : (
            <p className="rounded-xl border border-dashed border-gray-200 px-3 py-3 text-xs text-gray-400 dark:border-dark-border">Optional. Automata can infer tasks for you.</p>
          )}
        </div>
      </section>
      {props.status ? <SummaryAndDelivery status={props.status} delivery={delivery} navigate={props.navigate} showToast={props.showToast} /> : null}
    </aside>
  );
}

function SummaryAndDelivery({ status, delivery, navigate, showToast }: { status: NormalStatus; delivery: Record<string, any>; navigate: (path: string) => void; showToast: (m: string, t?: any) => void }) {
  const summary = status.summary || {};
  const ready = status.status === "ready" || (delivery.state === "ready" && (delivery.readyAgentCount || 0) > 0);
  const needsImplementation = status.nextAction?.kind === "implement_connectors";
  return (
    <>
      <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Progress summary</h2>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <MiniStat label="Systems" value={summary.systemsFound ?? 0} />
          <MiniStat label="Sources" value={summary.materialsReceived ?? 0} />
          <MiniStat label="Tasks" value={summary.tasksSolved ?? summary.taskCandidatesFound ?? 0} />
          <MiniStat label="Agents" value={summary.agentsReady ?? 0} />
        </div>
        {summary.recommendedNextAction ? <p className="mt-3 rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-dark-bg dark:text-gray-300">{summary.recommendedNextAction}</p> : null}
      </section>
      {needsImplementation ? (
        <section className="rounded-2xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-500/30 dark:bg-blue-500/10">
          <h2 className="text-sm font-semibold text-blue-900 dark:text-blue-100">Developer step needed</h2>
          <p className="mt-2 text-xs leading-relaxed text-blue-700 dark:text-blue-200">Some integrations need implementation before agents can complete every task.</p>
        </section>
      ) : null}
      {ready ? <DeliveryView delivery={delivery} navigate={navigate} showToast={showToast} /> : null}
    </>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-dark-border dark:bg-dark-bg">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{value}</p>
    </div>
  );
}

function CopyField({ label, value, showToast }: { label: string; value: string; showToast: (m: string, t?: any) => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-2 text-[11px] text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200">{value}</code>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1400);
            } catch {
              showToast("Could not copy.", "error");
            }
          }}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300"
          aria-label={`Copy ${label}`}
        >
          <FontAwesomeIcon icon={copied ? faCheck : faCopy} className="text-[10px]" />
        </button>
      </div>
    </div>
  );
}

function DeliveryView({ delivery, navigate, showToast }: { delivery: Record<string, any>; navigate: (path: string) => void; showToast: (m: string, t?: any) => void }) {
  const agents = (delivery.agents || []) as any[];
  if (!agents.length) return null;
  return (
    <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-500/30 dark:bg-emerald-500/10">
      <div className="flex items-center gap-2">
        <FontAwesomeIcon icon={faCheckCircle} className="text-emerald-500" />
        <h2 className="text-sm font-semibold text-emerald-900 dark:text-emerald-100">Agents ready</h2>
      </div>
      <div className="mt-3 space-y-3">
        {agents.map((agent) => {
          const endpoint = `${apiUrl}${agent.apiEndpoint || ""}`;
          const snippet = `<script src="${apiUrl}${agent.widgetEmbedScript || "/embed/v1/widget.js"}" data-agent="${agent.agentId}" async></script>`;
          return (
            <div key={agent.agentId} className="rounded-xl border border-emerald-200 bg-white p-3 dark:border-emerald-500/30 dark:bg-dark-surface">
              <div className="flex items-center gap-2">
                <FontAwesomeIcon icon={faRobot} className="text-primary" />
                <p className="min-w-0 flex-1 truncate text-sm font-semibold text-gray-900 dark:text-white">{agent.name || agent.agentId}</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {agent.chatAvailable ? <button type="button" onClick={() => navigate("/home")} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white">Chat <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" /></button> : null}
                {agent.widgetAvailable ? <button type="button" onClick={() => navigator.clipboard.writeText(snippet).then(() => showToast("Widget snippet copied.", "success")).catch(() => showToast("Could not copy snippet.", "error"))} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200"><FontAwesomeIcon icon={faCopy} className="text-[10px]" /> Widget</button> : null}
              </div>
              <div className="mt-3">
                <CopyField label="API endpoint" value={endpoint} showToast={showToast} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DevPanel({ status, devRun }: { status: NormalStatus | null; devRun: Record<string, any> | null }) {
  const artifacts = useMemo(() => (devRun?.artifacts || []) as any[], [devRun]);
  const byKind = useMemo(() => {
    const counts: Record<string, number> = {};
    artifacts.forEach((artifact) => {
      const key = String(artifact.kind || "unknown");
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [artifacts]);
  if (!status && !devRun) return null;
  return (
    <section className="rounded-2xl border border-gray-300 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex items-center gap-2">
        <FontAwesomeIcon icon={faCode} className="text-gray-500" />
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">Dev mode details</h2>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <MiniStat label="Status" value={status?.status || "none"} />
        <MiniStat label="Step" value={status?.currentStep || "none"} />
        <MiniStat label="Artifacts" value={artifacts.length} />
      </div>
      {Object.keys(byKind).length ? (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {Object.entries(byKind).map(([kind, count]) => (
            <span key={kind} className="inline-flex rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
              {kind.replace(/_/g, " ")}: <span className="ml-1 font-semibold text-gray-900 dark:text-white">{count}</span>
            </span>
          ))}
        </div>
      ) : null}
      {devRun?.devSummary ? (
        <pre className="mt-4 max-h-80 overflow-auto rounded-xl border border-gray-200 bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200">
          {JSON.stringify(devRun.devSummary, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}
