import React, { useCallback, useEffect, useRef, useState } from "react";
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
  faComments,
  faCopy,
  faGlobe,
  faKey,
  faPaperPlane,
  faPlug,
  faPlus,
  faRobot,
  faRotateRight,
  faSpinner,
  faTrash,
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

interface MaterialType {
  kind: string;
  label: string;
  icon: IconDefinition;
  input: "url" | "text";
  placeholder: string;
  hint: string;
}

/** Material kinds a normal (non-technical) user can attach during onboarding. */
const MATERIAL_TYPES: MaterialType[] = [
  { kind: "website", label: "Website / web app", icon: faGlobe, input: "url", placeholder: "https://app.yourcompany.com", hint: "The product or internal app Automata should learn to operate." },
  { kind: "document_url", label: "Docs or PDF", icon: faBook, input: "url", placeholder: "https://yourcompany.com/handbook.pdf", hint: "Handbooks, policies or process docs to ground answers." },
  { kind: "api_docs", label: "API documentation", icon: faPlug, input: "url", placeholder: "https://api.yourcompany.com/docs", hint: "Where your API is documented." },
  { kind: "openapi", label: "OpenAPI spec", icon: faPlug, input: "url", placeholder: "https://api.yourcompany.com/openapi.json", hint: "A machine-readable OpenAPI / Swagger spec URL." },
  { kind: "auth_note", label: "Auth notes", icon: faKey, input: "text", placeholder: "How to log in, or a credential reference name…", hint: "How Automata should authenticate (never paste raw passwords)." },
  { kind: "knowledge_note", label: "Knowledge note", icon: faBook, input: "text", placeholder: "Anything Automata should know about your company…", hint: "Free-form context that doesn't fit a document." },
];

function materialType(kind: string): MaterialType {
  return MATERIAL_TYPES.find((item) => item.kind === kind) || MATERIAL_TYPES[0];
}

interface DraftMaterial {
  id: string;
  kind: string;
  value: string;
  name: string;
}

interface NormalStatus {
  runId: string;
  intakeId: string;
  companyId: string;
  status: string;
  currentStep: string;
  steps: Array<{ key: string; label: string; status: string; message?: string }>;
  summary: Record<string, any>;
  delivery: Record<string, any>;
  questions: Array<{ questionId: string; code: string; prompt: string; severity: string; expectedAnswerType: string }>;
  nextAction: Record<string, any>;
  errors: string[];
}

function newId(prefix: string): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `${prefix}_${crypto.randomUUID()}`;
    }
  } catch {
    /* fall through */
  }
  return `${prefix}_${Math.random().toString(36).slice(2)}`;
}

function runKey(companyId: string): string {
  return `automata_harvest_run_${companyId}`;
}

function STEP_TONE(status: string): { icon: IconDefinition; spin?: boolean; cls: string } {
  if (status === "done") return { icon: faCheckCircle, cls: "text-emerald-500" };
  if (status === "in_progress") return { icon: faSpinner, spin: true, cls: "text-primary" };
  if (status === "blocked") return { icon: faTriangleExclamation, cls: "text-amber-500" };
  if (status === "skipped") return { icon: faCircle, cls: "text-gray-300 dark:text-zinc-700" };
  return { icon: faCircle, cls: "text-gray-300 dark:text-zinc-600" };
}

/* ------------------------------- presentational ------------------------------- */

function StatCard({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      {hint ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p> : null}
    </div>
  );
}

function CopyField({ label, value, showToast }: { label: string; value: string; showToast: (m: string, t?: any) => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      showToast("Could not copy to clipboard.", "error");
    }
  };
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200">
          {value}
        </code>
        <button
          type="button"
          onClick={copy}
          className="flex h-9 flex-shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
        >
          <FontAwesomeIcon icon={copied ? faCheck : faCopy} className="text-[10px]" />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

/* --------------------------------- page --------------------------------- */

export default function Onboarding(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const mode = useStudioMode();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [company, setCompany] = useState<Company | null>(null);
  const [companiesLoading, setCompaniesLoading] = useState(true);

  // Wizard state
  const [companyName, setCompanyName] = useState("");
  const [companyDescription, setCompanyDescription] = useState("");
  const [materials, setMaterials] = useState<DraftMaterial[]>([]);
  const [tasksText, setTasksText] = useState("");
  const [draftKind, setDraftKind] = useState<string>(MATERIAL_TYPES[0].kind);
  const [draftValue, setDraftValue] = useState("");

  // Run state
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState<NormalStatus | null>(null);
  const [devRun, setDevRun] = useState<Record<string, any> | null>(null);
  const [starting, setStarting] = useState(false);
  const [answering, setAnswering] = useState(false);
  const [error, setError] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const pollRef = useRef<number | null>(null);

  // Resolve the active company from the shared selector.
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

  // Prefill the wizard and pick up any saved run for this company.
  useEffect(() => {
    setCompanyName(company?.name && company.name !== "Default Company" ? company.name : "");
    setCompanyDescription(company?.description || "");
    setMaterials([]);
    setTasksText("");
    setDraftValue("");
    setError("");
    setAnswers({});
    setStatus(null);
    setDevRun(null);
    const savedRun = company ? localStorage.getItem(runKey(company.companyId)) || "" : "";
    setRunId(savedRun);
  }, [company]);

  const fetchStatus = useCallback(
    async (id: string, withDev: boolean) => {
      if (!id) return;
      const params = (m: string) => `${apiUrl}/company-harvest-runs/${id}/status?mode=${m}`;
      const headers = user.email ? { "X-User-Email": user.email } : undefined;
      try {
        const res = await fetch(params("normal"), { headers });
        if (res.status === 404) {
          // Run no longer exists — drop the stale pointer and return to the wizard.
          if (company) localStorage.removeItem(runKey(company.companyId));
          setRunId("");
          setStatus(null);
          return;
        }
        if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not load onboarding status."));
        const data = await res.json();
        setStatus(data.status as NormalStatus);
        setError("");
        if (withDev) {
          const devRes = await fetch(params("dev"), { headers });
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
    [company, user.email],
  );

  // Load + poll the run status while it is actively progressing.
  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!runId) {
      setStatus(null);
      return;
    }
    fetchStatus(runId, mode === "dev");
    pollRef.current = window.setInterval(() => {
      fetchStatus(runId, mode === "dev");
    }, 5000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [runId, mode, fetchStatus]);

  // Stop polling once the run reaches a state that only changes on user action.
  useEffect(() => {
    const s = status?.status || "";
    const terminal = s === "ready" || s === "failed" || s === "needs_user_input";
    if (terminal && pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [status?.status]);

  const addMaterial = () => {
    const value = draftValue.trim();
    if (!value) return;
    const type = materialType(draftKind);
    setMaterials((prev) => [
      ...prev,
      { id: newId("mat"), kind: draftKind, value, name: type.input === "url" ? value : `${type.label}` },
    ]);
    setDraftValue("");
  };

  const removeMaterial = (id: string) => setMaterials((prev) => prev.filter((m) => m.id !== id));

  const buildMaterialsPayload = () =>
    materials.map((m) => {
      const type = materialType(m.kind);
      if (type.input === "url") return { kind: m.kind, name: m.value, url: m.value };
      return { kind: m.kind, name: type.label, content: m.value };
    });

  const buildUserTasks = () =>
    tasksText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => ({ name: line.slice(0, 60), prompt: line }));

  const startHarvest = async () => {
    if (!company || starting) return;
    if (!companyName.trim()) {
      setError("Add your company name to continue.");
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
      const newRunId = data.harvestRun?.runId || "";
      if (!newRunId) throw new Error("Onboarding started but no run id was returned.");
      localStorage.setItem(runKey(company.companyId), newRunId);
      setRunId(newRunId);
      showToast("Automata is analyzing your company.", "success");
    } catch (err: any) {
      console.error("Failed to start onboarding:", err);
      setError(err?.message || "Could not start onboarding.");
    } finally {
      setStarting(false);
    }
  };

  const submitAnswers = async () => {
    if (!status || answering) return;
    const pending = status.questions || [];
    const payload = pending
      .map((q) => {
        const value = (answers[q.questionId] || "").trim();
        if (!value) return null;
        const answer: Record<string, any> = { questionId: q.questionId, code: q.code, value };
        if (q.expectedAnswerType === "credentials") answer.credentialRef = value;
        if (q.expectedAnswerType === "task_list") {
          answer.tasks = value
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => ({ name: line.slice(0, 60), prompt: line }));
        }
        return answer;
      })
      .filter(Boolean);
    if (payload.length === 0) {
      setError("Answer at least one question to continue.");
      return;
    }
    setAnswering(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/company-harvest-runs/${status.runId}/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(user.email ? { "X-User-Email": user.email } : {}) },
        body: JSON.stringify({
          answers: payload,
          continueHarvest: true,
          autoSolveTasks: true,
          autoPromoteSkills: true,
          buildAgents: true,
          runtimeKinds: RUNTIME_KINDS,
        }),
      });
      if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not submit your answers."));
      setAnswers({});
      showToast("Thanks — Automata is continuing.", "success");
      await fetchStatus(status.runId, mode === "dev");
    } catch (err: any) {
      console.error("Failed to submit answers:", err);
      setError(err?.message || "Could not submit your answers.");
    } finally {
      setAnswering(false);
    }
  };

  const resetRun = () => {
    if (company) localStorage.removeItem(runKey(company.companyId));
    setRunId("");
    setStatus(null);
    setDevRun(null);
  };

  /* ------------------------------- render ------------------------------- */

  if (companiesLoading) {
    return (
      <Shell>
        <div className="rounded-3xl border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">
          Loading onboarding…
        </div>
      </Shell>
    );
  }

  if (!company) {
    return (
      <Shell>
        <div className="rounded-3xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center dark:border-dark-border dark:bg-dark-surface">
          <FontAwesomeIcon icon={faBuilding} className="text-2xl text-gray-300 dark:text-zinc-600" />
          <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">Pick a company to onboard</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">
            Use the company selector in the top bar to create or choose a company, then Automata will help you set it up.
          </p>
          <button
            type="button"
            onClick={() => window.dispatchEvent(new CustomEvent("automata-open-company-onboarding"))}
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-gradient-primary px-4 text-sm font-semibold text-white"
          >
            <FontAwesomeIcon icon={faPlus} className="text-[11px]" />
            Create a company
          </button>
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

      {!runId ? (
        <Wizard
          companyName={companyName}
          setCompanyName={setCompanyName}
          companyDescription={companyDescription}
          setCompanyDescription={setCompanyDescription}
          materials={materials}
          removeMaterial={removeMaterial}
          draftKind={draftKind}
          setDraftKind={setDraftKind}
          draftValue={draftValue}
          setDraftValue={setDraftValue}
          addMaterial={addMaterial}
          tasksText={tasksText}
          setTasksText={setTasksText}
          starting={starting}
          onStart={startHarvest}
          mode={mode}
        />
      ) : status ? (
        <StatusView
          status={status}
          mode={mode}
          devRun={devRun}
          answers={answers}
          setAnswers={setAnswers}
          answering={answering}
          onSubmitAnswers={submitAnswers}
          onRefresh={() => fetchStatus(runId, mode === "dev")}
          navigate={navigate}
          showToast={showToast}
        />
      ) : (
        <div className="rounded-3xl border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">
          Loading run status…
        </div>
      )}
    </Shell>
  );
}

/* ------------------------------- sub-views ------------------------------- */

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full overflow-auto bg-gray-50/70 px-4 py-6 dark:bg-dark-bg sm:px-6">
      <div className="mx-auto flex max-w-5xl flex-col gap-5">{children}</div>
    </div>
  );
}

function Header({ company, mode, hasRun, onReset }: { company: Company; mode: string; hasRun: boolean; onReset: () => void }) {
  return (
    <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <SectionTitle
            icon={faWandMagicSparkles}
            title="Company onboarding"
            subtitle="Tell Automata about your company and it will discover your systems, build tasks, test them and prepare ready-to-use agents."
          />
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
              <FontAwesomeIcon icon={faBuilding} className="text-[10px]" />
              {company.name}
            </span>
            <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
              <FontAwesomeIcon icon={mode === "dev" ? faCode : faRobot} className="text-[10px]" />
              {mode === "dev" ? "Dev mode" : "Guided mode"}
            </span>
          </div>
        </div>
        {hasRun ? (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex h-9 flex-shrink-0 items-center gap-2 self-start rounded-xl border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg"
          >
            <FontAwesomeIcon icon={faRotateRight} className="text-[10px]" />
            Start over
          </button>
        ) : null}
      </div>
    </div>
  );
}

interface WizardProps {
  companyName: string;
  setCompanyName: (v: string) => void;
  companyDescription: string;
  setCompanyDescription: (v: string) => void;
  materials: DraftMaterial[];
  removeMaterial: (id: string) => void;
  draftKind: string;
  setDraftKind: (v: string) => void;
  draftValue: string;
  setDraftValue: (v: string) => void;
  addMaterial: () => void;
  tasksText: string;
  setTasksText: (v: string) => void;
  starting: boolean;
  onStart: () => void;
  mode: string;
}

function Wizard(props: WizardProps) {
  const type = materialType(props.draftKind);
  return (
    <>
      {/* Step 1 — Company */}
      <section className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <StepHeading index={1} title="Tell us about your company" />
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">Company name</span>
            <input
              value={props.companyName}
              onChange={(e) => props.setCompanyName(e.target.value)}
              placeholder="Acme Inc."
              className="mt-1.5 h-10 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
            />
          </label>
          <label className="block md:row-span-2">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">What does your company do?</span>
            <textarea
              value={props.companyDescription}
              onChange={(e) => props.setCompanyDescription(e.target.value)}
              rows={4}
              placeholder="A short description of your business and the work you'd like to automate…"
              className="mt-1.5 w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
            />
          </label>
        </div>
      </section>

      {/* Step 2 — Materials */}
      <section className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <StepHeading index={2} title="Add your docs, website, API & knowledge" />
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Add as many as you like. Automata uses these to discover the systems it can operate.
        </p>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <div className="flex flex-wrap gap-1.5 rounded-xl border border-gray-200 bg-gray-50 p-1 dark:border-dark-border dark:bg-dark-bg sm:flex-shrink-0">
            {MATERIAL_TYPES.map((item) => {
              const active = item.kind === props.draftKind;
              return (
                <button
                  key={item.kind}
                  type="button"
                  onClick={() => props.setDraftKind(item.kind)}
                  className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                    active ? "bg-white text-gray-900 shadow-sm dark:bg-dark-surface dark:text-white" : "text-gray-500 hover:text-gray-800 dark:text-zinc-400 dark:hover:text-zinc-200"
                  }`}
                  title={item.hint}
                >
                  <FontAwesomeIcon icon={item.icon} className="text-[10px]" />
                  <span className="hidden md:inline">{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-start">
          {type.input === "url" ? (
            <input
              value={props.draftValue}
              onChange={(e) => props.setDraftValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  props.addMaterial();
                }
              }}
              placeholder={type.placeholder}
              className="h-10 min-w-0 flex-1 rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
            />
          ) : (
            <textarea
              value={props.draftValue}
              onChange={(e) => props.setDraftValue(e.target.value)}
              rows={2}
              placeholder={type.placeholder}
              className="min-w-0 flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
            />
          )}
          <button
            type="button"
            onClick={props.addMaterial}
            disabled={!props.draftValue.trim()}
            className="flex h-10 flex-shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            <FontAwesomeIcon icon={faPlus} className="text-[11px]" />
            Add
          </button>
        </div>
        <p className="mt-1.5 text-xs text-gray-400">{type.hint}</p>

        {props.materials.length > 0 ? (
          <div className="mt-4 space-y-2">
            {props.materials.map((m) => {
              const mType = materialType(m.kind);
              return (
                <div
                  key={m.id}
                  className="flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-dark-border dark:bg-dark-bg"
                >
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FontAwesomeIcon icon={mType.icon} className="text-[11px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{mType.label}</p>
                    <p className="truncate text-xs text-gray-500 dark:text-gray-400">{m.value}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => props.removeMaterial(m.id)}
                    aria-label="Remove material"
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10"
                  >
                    <FontAwesomeIcon icon={faTrash} className="text-[11px]" />
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="mt-4 rounded-xl border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-400 dark:border-dark-border">
            No materials added yet. Add at least one so Automata has something to work with.
          </p>
        )}
      </section>

      {/* Step 3 — Optional tasks */}
      <section className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <StepHeading index={3} title="Optional: tasks you want automated" optional />
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">One task per line. Leave blank to let Automata propose tasks for you.</p>
        <textarea
          value={props.tasksText}
          onChange={(e) => props.setTasksText(e.target.value)}
          rows={4}
          placeholder={"Summarize new support tickets every morning\nDraft a reply to billing questions using our docs"}
          className="mt-3 w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
        />
      </section>

      <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Automata will analyze your systems, create and test tasks, then prepare agents you can use by chat, API or widget.
        </p>
        <button
          type="button"
          onClick={props.onStart}
          disabled={props.starting || !props.companyName.trim()}
          className="flex h-11 flex-shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-primary px-6 text-sm font-semibold text-white shadow-glow disabled:opacity-60"
        >
          {props.starting ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={faWandMagicSparkles} />}
          {props.starting ? "Starting…" : "Start onboarding"}
        </button>
      </div>
    </>
  );
}

function StepHeading({ index, title, optional }: { index: number; title: string; optional?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">{index}</span>
      <h2 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h2>
      {optional ? <span className="rounded-md border border-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:border-dark-border">Optional</span> : null}
    </div>
  );
}

interface StatusViewProps {
  status: NormalStatus;
  mode: string;
  devRun: Record<string, any> | null;
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  answering: boolean;
  onSubmitAnswers: () => void;
  onRefresh: () => void;
  navigate: (path: string) => void;
  showToast: (m: string, t?: any) => void;
}

function StatusView({ status, mode, devRun, answers, setAnswers, answering, onSubmitAnswers, onRefresh, navigate, showToast }: StatusViewProps) {
  const summary = status.summary || {};
  const delivery = status.delivery || {};
  const next = status.nextAction || {};
  const ready = status.status === "ready" || (delivery.state === "ready" && (delivery.readyAgentCount || 0) > 0);
  const needsInput = status.status === "needs_user_input" || (status.questions || []).length > 0;
  const needsImplementation = next.kind === "implement_connectors";

  return (
    <>
      {/* Progress */}
      <section className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">Progress</h2>
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg"
          >
            <FontAwesomeIcon icon={faRotateRight} className="text-[10px]" />
            Refresh
          </button>
        </div>
        <ol className="mt-4 space-y-2.5">
          {(status.steps || []).map((step) => {
            const tone = STEP_TONE(step.status);
            return (
              <li key={step.key} className="flex items-start gap-3">
                <FontAwesomeIcon icon={tone.icon} className={`mt-0.5 text-sm ${tone.cls} ${tone.spin ? "animate-spin" : ""}`} />
                <div className="min-w-0">
                  <p className={`text-sm ${step.status === "done" ? "text-gray-500 line-through dark:text-gray-500" : "font-medium text-gray-800 dark:text-gray-100"}`}>{step.label}</p>
                  {step.message ? <p className="text-xs text-gray-400">{step.message}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
        {summary.recommendedNextAction ? (
          <p className="mt-4 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
            {summary.recommendedNextAction}
          </p>
        ) : null}
      </section>

      {/* At-a-glance counts */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Materials" value={summary.materialsReceived ?? 0} hint="provided" />
        <StatCard label="Systems" value={summary.systemsFound ?? 0} hint="discovered" />
        <StatCard label="Knowledge" value={summary.knowledgeSourcesFound ?? 0} hint="sources" />
        <StatCard label="Tasks" value={summary.tasksSolved ?? summary.taskCandidatesFound ?? 0} hint={summary.tasksSolved != null ? "tested" : "proposed"} />
        <StatCard label="Agents" value={summary.agentsReady ?? 0} hint="ready" />
      </div>

      {/* Questions */}
      {needsInput && (status.questions || []).length > 0 ? (
        <section className="rounded-3xl border border-amber-200 bg-amber-50/60 p-6 dark:border-amber-500/30 dark:bg-amber-500/5">
          <div className="flex items-center gap-2">
            <FontAwesomeIcon icon={faComments} className="text-amber-500" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Automata needs a little more</h2>
          </div>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Answer these to keep going.</p>
          <div className="mt-4 space-y-4">
            {(status.questions || []).map((q) => (
              <div key={q.questionId} className="rounded-2xl border border-amber-200 bg-white p-4 dark:border-amber-500/30 dark:bg-dark-surface">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-100">{q.prompt}</p>
                {q.expectedAnswerType === "task_list" ? (
                  <textarea
                    value={answers[q.questionId] || ""}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.questionId]: e.target.value }))}
                    rows={3}
                    placeholder="One task per line…"
                    className="mt-2.5 w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
                  />
                ) : (
                  <input
                    value={answers[q.questionId] || ""}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.questionId]: e.target.value }))}
                    type={q.expectedAnswerType === "url" ? "url" : "text"}
                    placeholder={
                      q.expectedAnswerType === "url"
                        ? "https://…"
                        : q.expectedAnswerType === "credentials"
                          ? "Credential reference or login instructions…"
                          : "Your answer…"
                    }
                    className="mt-2.5 h-10 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm text-gray-900 outline-none focus:border-primary/40 dark:border-dark-border dark:bg-dark-bg dark:text-white"
                  />
                )}
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={onSubmitAnswers}
            disabled={answering}
            className="mt-4 flex h-10 items-center gap-2 rounded-xl bg-gradient-primary px-5 text-sm font-semibold text-white disabled:opacity-60"
          >
            {answering ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={faPaperPlane} className="text-[11px]" />}
            {answering ? "Sending…" : "Send answers"}
          </button>
        </section>
      ) : null}

      {/* Implementation needed */}
      {needsImplementation ? (
        <section className="rounded-3xl border border-blue-200 bg-blue-50/60 p-6 dark:border-blue-500/30 dark:bg-blue-500/5">
          <div className="flex items-center gap-2">
            <FontAwesomeIcon icon={faPlug} className="text-blue-500" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Some integrations need a developer</h2>
          </div>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            Automata prepared everything it could, but a few of your systems need a developer to connect them before agents are fully ready.
            Your team can finish these connections, then onboarding will continue automatically.
          </p>
          {Array.isArray(next.toolNames) && next.toolNames.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {next.toolNames.slice(0, 12).map((name: string) => (
                <span key={name} className="inline-flex rounded-lg border border-blue-200 bg-white px-2.5 py-1 text-xs text-blue-700 dark:border-blue-500/30 dark:bg-dark-surface dark:text-blue-300">
                  {name}
                </span>
              ))}
            </div>
          ) : null}
          {mode === "dev" ? (
            <button
              type="button"
              onClick={() => navigate("/connectors")}
              className="mt-4 inline-flex h-9 items-center gap-2 rounded-xl border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 dark:border-blue-500/30 dark:bg-dark-surface dark:text-blue-300"
            >
              Open connectors
              <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
            </button>
          ) : null}
        </section>
      ) : null}

      {/* Ready — delivery surfaces */}
      {ready ? <DeliveryView delivery={delivery} navigate={navigate} showToast={showToast} /> : null}

      {/* Dev raw view */}
      {mode === "dev" ? <DevPanel status={status} devRun={devRun} /> : null}
    </>
  );
}

function DeliveryView({ delivery, navigate, showToast }: { delivery: Record<string, any>; navigate: (p: string) => void; showToast: (m: string, t?: any) => void }) {
  const agents = (delivery.agents || []) as any[];
  return (
    <section className="rounded-3xl border border-emerald-200 bg-emerald-50/50 p-6 dark:border-emerald-500/30 dark:bg-emerald-500/5">
      <div className="flex items-center gap-2">
        <FontAwesomeIcon icon={faCheckCircle} className="text-emerald-500" />
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">Your agents are ready</h2>
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Use them through chat, your API or an embeddable widget.</p>
      <div className="mt-4 space-y-3">
        {agents.map((agent) => {
          const fullEndpoint = `${apiUrl}${agent.apiEndpoint || ""}`;
          const widgetSnippet = `<script src="${apiUrl}${agent.widgetEmbedScript || "/embed/v1/widget.js"}" data-agent="${agent.agentId}" async></script>`;
          return (
            <div key={agent.agentId} className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FontAwesomeIcon icon={faRobot} className="text-[11px]" />
                </span>
                <span className="text-sm font-semibold text-gray-900 dark:text-white">{agent.name || agent.agentId}</span>
                <span className="rounded-md border border-gray-200 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:border-dark-border dark:text-gray-400">
                  {String(agent.runtimeKind || "model_agent").replace(/_/g, " ")}
                </span>
                {agent.ready ? (
                  <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">ready</span>
                ) : (
                  <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">preparing</span>
                )}
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {agent.chatAvailable ? (
                  <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-dark-border dark:bg-dark-bg">
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
                      <FontAwesomeIcon icon={faComments} className="text-primary text-[12px]" /> Chat
                    </span>
                    <button
                      type="button"
                      onClick={() => navigate("/home")}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
                    >
                      Open chat
                      <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
                    </button>
                  </div>
                ) : null}
                {agent.widgetAvailable ? (
                  <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-dark-border dark:bg-dark-bg">
                    <span className="inline-flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
                      <FontAwesomeIcon icon={faGlobe} className="text-primary text-[12px]" /> Widget
                    </span>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(widgetSnippet);
                          showToast("Widget snippet copied.", "success");
                        } catch {
                          showToast("Could not copy snippet.", "error");
                        }
                      }}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200"
                    >
                      <FontAwesomeIcon icon={faCopy} className="text-[10px]" /> Copy embed
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="mt-3">
                <CopyField label="API endpoint" value={fullEndpoint} showToast={showToast} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DevPanel({ status, devRun }: { status: NormalStatus; devRun: Record<string, any> | null }) {
  const artifacts = (devRun?.artifacts || []) as any[];
  const devSummary = devRun?.devSummary || {};
  const allSteps = (devRun?.steps || status.steps || []) as any[];
  const byKind: Record<string, number> = {};
  artifacts.forEach((a) => {
    const k = String(a.kind || "unknown");
    byKind[k] = (byKind[k] || 0) + 1;
  });

  return (
    <section className="rounded-3xl border border-gray-300 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex items-center gap-2">
        <FontAwesomeIcon icon={faCode} className="text-gray-500" />
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">Developer view</h2>
        <span className="rounded-md border border-gray-200 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:border-dark-border dark:text-gray-400">raw run</span>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-dark-border dark:bg-dark-bg">
          <span className="text-gray-400">status</span>
          <p className="mt-0.5 font-mono text-gray-800 dark:text-gray-100">{status.status}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-dark-border dark:bg-dark-bg">
          <span className="text-gray-400">currentStep</span>
          <p className="mt-0.5 font-mono text-gray-800 dark:text-gray-100">{status.currentStep}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-dark-border dark:bg-dark-bg">
          <span className="text-gray-400">nextAction</span>
          <p className="mt-0.5 font-mono text-gray-800 dark:text-gray-100">{String(status.nextAction?.kind || "—")}</p>
        </div>
      </div>

      {allSteps.length > 0 ? (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Pipeline (all stages)</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {allSteps.map((s: any) => (
              <span
                key={s.key}
                title={s.message || ""}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"
              >
                <FontAwesomeIcon icon={STEP_TONE(s.status).icon} className={`text-[9px] ${STEP_TONE(s.status).cls}`} />
                {String(s.key).replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {artifacts.length > 0 ? (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Artifacts ({artifacts.length})</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(byKind).map(([kind, count]) => (
              <span key={kind} className="inline-flex rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                {kind.replace(/_/g, " ")}: <span className="ml-1 font-semibold text-gray-800 dark:text-gray-100">{count}</span>
              </span>
            ))}
          </div>
          <div className="mt-3 max-h-72 space-y-1.5 overflow-auto">
            {artifacts.map((a: any) => (
              <div key={a.artifactId} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs dark:border-dark-border dark:bg-dark-bg">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-gray-400">{String(a.kind)}</span>
                  <span className="rounded border border-gray-200 px-1.5 py-0.5 text-[9px] text-gray-500 dark:border-dark-border">{a.status}</span>
                  <span className="rounded border border-gray-200 px-1.5 py-0.5 text-[9px] text-gray-500 dark:border-dark-border">{a.visibility}</span>
                </div>
                <p className="mt-1 font-medium text-gray-800 dark:text-gray-100">{a.title}</p>
                {a.summary ? <p className="text-gray-500 dark:text-gray-400">{a.summary}</p> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {Object.keys(devSummary).length > 0 ? (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Dev summary</p>
          <pre className="mt-2 max-h-72 overflow-auto rounded-xl border border-gray-200 bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200">
            {JSON.stringify(devSummary, null, 2)}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
