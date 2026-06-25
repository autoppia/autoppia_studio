import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faBoxesStacked,
  faBolt,
  faCircleCheck,
  faClockRotateLeft,
  faFileLines,
  faGlobe,
  faMagnifyingGlass,
  faShieldHalved,
  faRobot,
  faShapes,
  faTriangleExclamation,
  faWandMagicSparkles,
} from "@fortawesome/free-solid-svg-icons";
import SectionTitle from "../components/layout/section-title";
import { SessionItem } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function formatDate(value?: string | Date) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function hostLabel(value?: string) {
  if (!value) return "";
  try {
    return new URL(value).hostname;
  } catch {
    return value.replace(/^https?:\/\//, "").split("/")[0];
  }
}

function formatCredits(value?: number) {
  const amount = Number(value || 0);
  if (amount <= 0) return "";
  return `${amount.toFixed(2)} cr`;
}

function metricTone(kind: "neutral" | "good" | "accent") {
  if (kind === "good") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30";
  if (kind === "accent") return "bg-primary/10 text-primary border-primary/20";
  return "bg-gray-50 text-gray-600 border-gray-200 dark:bg-dark-bg dark:text-gray-300 dark:border-dark-border";
}

function runtimeKind(session: SessionItem): "browser" | "api" | "hybrid" {
  if (session.hasBrowserActivity && session.hasConnectorActivity) return "hybrid";
  if (session.hasBrowserActivity) return "browser";
  return "api";
}

function runtimeKindLabel(kind: "browser" | "api" | "hybrid") {
  if (kind === "hybrid") return "Hybrid runtime";
  if (kind === "browser") return "Browser runtime";
  return "API runtime";
}

function runtimeKindTone(kind: "browser" | "api" | "hybrid") {
  if (kind === "hybrid") return "bg-primary/10 text-primary border-primary/20";
  if (kind === "browser") return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/30";
  return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30";
}

function SummaryCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  );
}

function SessionCard({
  session,
  onOpen,
  onOpenApprovals,
  onOpenArtifacts,
  onOpenWorkItem,
  onOpenSkill,
}: {
  session: SessionItem;
  onOpen: (sessionId: string) => void;
  onOpenApprovals: (sessionId: string) => void;
  onOpenArtifacts: (sessionId: string) => void;
  onOpenWorkItem: (workItemId: string) => void;
  onOpenSkill: (skillId: string) => void;
}) {
  const initialHost = hostLabel(session.initialUrl);
  const lastHost = hostLabel(session.lastUrl);
  const matchedSkillId = String(session.matchedSkillId || "");
  const matchedSkillName = String(session.matchedSkillName || "");
  const kind = runtimeKind(session);
  const workItemId = String(session.workItemId || "");
  const runId = String(session.runId || "");
  const sourceKind = String(session.sourceKind || "");
  const creditsLabel = formatCredits(session.creditsSpent);

  return (
    <div className="w-full rounded-2xl border border-gray-200 bg-white p-4 text-left transition-colors hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:bg-dark-surface dark:hover:border-primary/30 dark:hover:bg-primary/5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FontAwesomeIcon icon={faBolt} className="text-sm" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">
                {session.prompt || "Untitled runtime session"}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {formatDate(session.createdAt)}
                {session.agentName ? ` · ${session.agentName}` : ""}
              </p>
            </div>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
          Open
          <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${runtimeKindTone(kind)}`}>
          <FontAwesomeIcon icon={kind === "hybrid" ? faBoxesStacked : kind === "browser" ? faGlobe : faBolt} className="text-[10px]" />
          {runtimeKindLabel(kind)}
        </span>
        <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("neutral")}`}>
          <FontAwesomeIcon icon={faClockRotateLeft} className="text-[10px]" />
          {session.actionCount || 0} actions
        </span>
        <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("neutral")}`}>
          <FontAwesomeIcon icon={faShapes} className="text-[10px]" />
          {session.chatCount || 0} messages
        </span>
        {matchedSkillId && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("good")}`}>
            <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
            {matchedSkillName || "Matched skill"}
          </span>
        )}
        {session.hasBrowserActivity && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("accent")}`}>
            <FontAwesomeIcon icon={faGlobe} className="text-[10px]" />
            Browser trace
          </span>
        )}
        {(session.approvedConnectorToolCallCount || 0) > 0 && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("good")}`}>
            <FontAwesomeIcon icon={faCircleCheck} className="text-[10px]" />
            {session.approvedConnectorToolCallCount} approved calls
          </span>
        )}
        {(session.pendingApprovalCount || 0) > 0 && (
          <span className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
            <FontAwesomeIcon icon={faShieldHalved} className="text-[10px]" />
            {session.pendingApprovalCount} pending approvals
          </span>
        )}
        {(session.artifactCount || 0) > 0 && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("neutral")}`}>
            <FontAwesomeIcon icon={faFileLines} className="text-[10px]" />
            {session.artifactCount} artifacts
          </span>
        )}
        {sourceKind === "work" && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("accent")}`}>
            <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
            Work orchestration
          </span>
        )}
        {creditsLabel && (
          <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${metricTone("neutral")}`}>
            <FontAwesomeIcon icon={faShapes} className="text-[10px]" />
            {creditsLabel} spent
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-3 text-xs text-gray-500 dark:text-gray-400 sm:grid-cols-3">
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-dark-border dark:bg-dark-bg">
          <p className="font-semibold uppercase tracking-wide text-[10px] text-gray-400">Initial system</p>
          <p className="mt-1 truncate text-gray-700 dark:text-gray-200">{initialHost || "Not recorded"}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-dark-border dark:bg-dark-bg">
          <p className="font-semibold uppercase tracking-wide text-[10px] text-gray-400">Last location</p>
          <p className="mt-1 truncate text-gray-700 dark:text-gray-200">{lastHost || "Not recorded"}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-dark-border dark:bg-dark-bg">
          <p className="font-semibold uppercase tracking-wide text-[10px] text-gray-400">Provider</p>
          <p className="mt-1 truncate text-gray-700 dark:text-gray-200">
            {sourceKind === "work" ? "Work Orchestration" : session.provider || "autoppia"}
          </p>
          {workItemId ? (
            <p className="mt-1 truncate text-[11px] text-gray-400 dark:text-gray-500">
              {workItemId}{runId ? ` · ${runId}` : ""}
            </p>
          ) : null}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 dark:border-dark-border">
        <span className="text-[11px] text-gray-400">Session {session.sessionId.slice(0, 8)}</span>
        <div className="flex flex-wrap items-center gap-2">
          {(session.pendingApprovalCount || 0) > 0 && (
            <button
              type="button"
              onClick={() => onOpenApprovals(session.sessionId)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 text-xs font-semibold text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/20"
            >
              <FontAwesomeIcon icon={faShieldHalved} className="text-[10px]" />
              Approvals
            </button>
          )}
          {(session.artifactCount || 0) > 0 && (
            <button
              type="button"
              onClick={() => onOpenArtifacts(session.sessionId)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-surface"
            >
              <FontAwesomeIcon icon={faFileLines} className="text-[10px]" />
              Artifacts
            </button>
          )}
          {matchedSkillId && (
            <button
              type="button"
              onClick={() => onOpenSkill(matchedSkillId)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
            >
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
              Open skill
            </button>
          )}
          {workItemId && (
            <button
              type="button"
              onClick={() => onOpenWorkItem(workItemId)}
              className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-surface"
            >
              <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
              Open job
            </button>
          )}
          <button
            type="button"
            onClick={() => onOpen(session.sessionId)}
            className="inline-flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
          >
            Open session
            <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Runtime(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<"all" | "browser" | "api" | "hybrid">("all");
  const skillFilter = searchParams.get("skillId") || "";
  const workItemFilter = searchParams.get("workItemId") || "";
  const sessionIdsFilter = useMemo(
    () => new Set((searchParams.get("sessionIds") || "").split(",").map((value) => value.trim()).filter(Boolean)),
    [searchParams],
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  useEffect(() => {
    const loadSessions = async () => {
      if (!user.email) return;
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ email: user.email });
        if (companyId) params.set("companyId", companyId);
        const res = await fetch(`${apiUrl}/sessions?${params.toString()}`);
        if (!res.ok) throw new Error("Could not load runtime sessions.");
        const data = await res.json();
        setSessions(data.sessions || []);
      } catch (err: any) {
        console.error("Failed to load runtime sessions:", err);
        setError(err?.message || "Could not load runtime sessions.");
      } finally {
        setLoading(false);
      }
    };
    loadSessions();
  }, [companyId, user.email]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sessions.filter((session) => {
      const matchedSkillId = String(session.matchedSkillId || "");
      if (skillFilter && matchedSkillId !== skillFilter) return false;
      if (workItemFilter) {
        const sessionWorkItemId = String(session.workItemId || "");
        if (sessionWorkItemId !== workItemFilter) return false;
      }
      if (sessionIdsFilter.size > 0 && !sessionIdsFilter.has(session.sessionId)) return false;
      const kindMatches = kindFilter === "all" || runtimeKind(session) === kindFilter;
      if (!kindMatches) return false;
      if (!q) return true;
      return (
      [
        session.prompt,
        session.agentName || "",
        session.initialUrl || "",
        session.lastUrl || "",
        session.provider || "",
        session.matchedSkillName || "",
        session.workItemId || "",
      ].join(" ").toLowerCase().includes(q)
      );
    });
  }, [kindFilter, search, sessionIdsFilter, sessions, skillFilter, workItemFilter]);

  const metrics = useMemo(() => ({
    total: filtered.length,
    browser: filtered.filter((session) => session.hasBrowserActivity).length,
    skillReplay: filtered.filter((session) => !!session.matchedSkillId).length,
    approvals: filtered.reduce((sum, session) => sum + (session.approvedConnectorToolCallCount || 0), 0),
    pendingApprovals: filtered.reduce((sum, session) => sum + (session.pendingApprovalCount || 0), 0),
    artifacts: filtered.reduce((sum, session) => sum + (session.artifactCount || 0), 0),
  }), [filtered]);

  return (
    <div className="h-full overflow-auto bg-gray-50/70 px-6 py-6 dark:bg-dark-bg">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <div className="flex flex-col gap-4 rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
          <SectionTitle
            icon={faBolt}
            title="Runtime Lab"
            subtitle="Inspect live sessions, skill routing, approvals and operational traces."
          />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <SummaryCard label="Sessions" value={metrics.total} hint="Durable runtime executions in scope" />
            <SummaryCard label="Browser Traces" value={metrics.browser} hint="Sessions that touched browser automation" />
            <SummaryCard label="Skill Replays" value={metrics.skillReplay} hint="Sessions with a matched approved skill" />
            <SummaryCard label="Approved Calls" value={metrics.approvals} hint="Connector calls already unblocked in runtime" />
            <SummaryCard label="Pending Approvals" value={metrics.pendingApprovals} hint="Runtime actions waiting for human approval" />
            <SummaryCard label="Artifacts" value={metrics.artifacts} hint="Business outputs created across runtime sessions" />
          </div>
        </div>

        <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Sessions</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Recent runtime activity for the selected company.
              </p>
            </div>
            <label className="relative block w-full lg:w-96">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search prompt, agent, URL or provider"
                className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50 pl-9 pr-3 text-sm text-gray-800 outline-none transition focus:border-primary focus:bg-white dark:border-dark-border dark:bg-dark-bg dark:text-gray-100"
              />
            </label>
          </div>

          {(skillFilter || workItemFilter || sessionIdsFilter.size > 0) && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-dark-border dark:bg-dark-bg">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime scope active</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {skillFilter
                    ? `Showing sessions for skill ${skillFilter}.`
                    : workItemFilter
                      ? `Showing sessions for job ${workItemFilter}.`
                    : `Showing ${sessionIdsFilter.size} linked runtime ${sessionIdsFilter.size === 1 ? "session" : "sessions"}.`}
                </p>
              </div>
              <button
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.delete("skillId");
                  next.delete("workItemId");
                  next.delete("sessionIds");
                  setSearchParams(next, { replace: true });
                }}
                className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-surface"
              >
                Clear scope
              </button>
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {([
              { key: "all", label: "All runtimes" },
              { key: "api", label: "API" },
              { key: "browser", label: "Browser" },
              { key: "hybrid", label: "Hybrid" },
            ] as const).map((item) => (
              <button
                key={item.key}
                onClick={() => setKindFilter(item.key)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                  kindFilter === item.key
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300 dark:hover:bg-dark-surface"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              <FontAwesomeIcon icon={faTriangleExclamation} />
              {error}
            </div>
          )}

          <div className="mt-5 space-y-3">
            {loading ? (
              <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-6 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                Loading runtime sessions...
              </div>
            ) : filtered.length ? filtered.map((session) => (
              <SessionCard
                key={session.sessionId}
                session={session}
                onOpen={(sessionId) => navigate(`/session/${sessionId}`)}
                onOpenApprovals={(sessionId) => navigate(`/approvals?status=pending&sessionId=${encodeURIComponent(sessionId)}`)}
                onOpenArtifacts={(sessionId) => navigate(`/artifacts?sessionId=${encodeURIComponent(sessionId)}`)}
                onOpenWorkItem={(workItemId) => navigate(`/work?item=${encodeURIComponent(workItemId)}`)}
                onOpenSkill={(skillId) => navigate(`/capabilities/skill/${encodeURIComponent(skillId)}`)}
              />
            )) : (
              <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-6 py-10 text-center dark:border-dark-border dark:bg-dark-bg">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <FontAwesomeIcon icon={faRobot} className="text-lg" />
                </div>
                <p className="mt-4 text-sm font-semibold text-gray-900 dark:text-white">No runtime sessions yet</p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Start an agent run, benchmark replay or connector smoke to populate the runtime lab.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
