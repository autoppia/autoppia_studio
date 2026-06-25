import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate, useSearchParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBuilding,
  faCheck,
  faClipboardCheck,
  faClock,
  faCode,
  faCube,
  faSpinner,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { ApprovalRequest } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type ApprovalTab = "pending" | "approved" | "rejected" | "all";

function formatDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusTone(status: string) {
  const clean = status.toLowerCase();
  if (clean === "approved") return "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30";
  if (clean === "rejected") return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-300 border-red-200 dark:border-red-500/30";
  if (clean === "expired") return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
  return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300 border-amber-200 dark:border-amber-500/30";
}

async function responseErrorMessage(res: Response, fallback: string) {
  const text = await res.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (typeof parsed?.message === "string") return parsed.message;
    return fallback;
  } catch {
    return text.trim().startsWith("{") ? fallback : text;
  }
}

function JsonBlock({ value }: { value: any }) {
  return (
    <pre className="max-h-52 overflow-auto rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-[11px] leading-4 text-gray-700 dark:text-gray-200">
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

function shortId(value?: string) {
  if (!value) return "";
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function InfoPill({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
      <span className="font-medium text-gray-700 dark:text-gray-200">{label}</span>
      <span className="font-mono">{shortId(value)}</span>
    </span>
  );
}

function ApprovalCard({
  approval,
  busy,
  onApprove,
  onReject,
  onOpenSession,
  onOpenCapability,
}: {
  approval: ApprovalRequest;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onOpenSession: (sessionId: string) => void;
  onOpenCapability: (kind: "tool" | "trajectory" | "skill", id: string) => void;
}) {
  const actionName = approval.toolName || approval.proposedAction?.name || "proposed action";
  const args = approval.proposedAction?.arguments || {};
  const diff = approval.proposedAction?.diff || approval.metadata?.diff || approval.metadata?.argumentDiff;
  const entity = approval.entityRef?.entity || approval.entityRef?.name || "";
  const entityId = approval.entityRef?.id || approval.entityRef?.entityId || approval.entityRef?.externalId || "";
  const workItemId = approval.workItemId || approval.metadata?.workItemId || "";
  const sessionId = approval.sessionId || approval.metadata?.sessionId || "";
  const runId = approval.runId || approval.metadata?.runId || "";
  const sourceKind = approval.sourceKind || approval.metadata?.sourceKind || (workItemId ? "work" : sessionId ? "session" : "runtime");
  const auditTrail = approval.auditTrail || [];
  const pending = approval.status === "pending";
  const skillId = String(approval.metadata?.skillId || "");
  const trajectoryId = String(approval.metadata?.trajectoryId || "");
  const toolId = String(approval.metadata?.toolId || "");

  return (
    <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-500 flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={faClipboardCheck} className="text-xs" />
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white truncate">{approval.title || `Approve ${actionName}`}</h2>
              <p className="text-[11px] text-gray-400">{formatDate(approval.createdAt)}</p>
            </div>
          </div>
          {approval.message && <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">{approval.message}</p>}
          <p className="mt-2 text-[11px] text-gray-400">
            Source: {sourceKind === "work" ? "Work item / asynchronous run" : sourceKind === "session" ? "Runtime session" : "Runtime approval gate"}
          </p>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold border ${statusTone(approval.status)}`}>{approval.status}</span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="px-2 py-0.5 rounded-md border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border">
          <FontAwesomeIcon icon={faCode} className="mr-1 text-[9px]" />
          {actionName}
        </span>
        {entity && (
          <span className="px-2 py-0.5 rounded-md border bg-primary/10 text-primary border-primary/30">
            <FontAwesomeIcon icon={faCube} className="mr-1 text-[9px]" />
            {entity}
          </span>
        )}
        {entityId && (
          <span className="px-2 py-0.5 rounded-md border bg-primary/10 text-primary border-primary/30">
            ref {shortId(String(entityId))}
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <InfoPill label="work" value={workItemId} />
        <InfoPill label="session" value={sessionId} />
        <InfoPill label="run" value={runId} />
        <InfoPill label="agent" value={approval.agentId} />
        <InfoPill label="key" value={approval.approvalKey} />
      </div>

      {(sessionId || skillId || trajectoryId || toolId) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {sessionId && (
            <button
              onClick={() => onOpenSession(sessionId)}
              className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg"
            >
              Open session
            </button>
          )}
          {skillId && (
            <button
              onClick={() => onOpenCapability("skill", skillId)}
              className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
            >
              Open skill
            </button>
          )}
          {!skillId && trajectoryId && (
            <button
              onClick={() => onOpenCapability("trajectory", trajectoryId)}
              className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
            >
              Open trajectory
            </button>
          )}
          {!skillId && !trajectoryId && toolId && (
            <button
              onClick={() => onOpenCapability("tool", toolId)}
              className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
            >
              Open tool
            </button>
          )}
        </div>
      )}

      <div className="mt-3">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Proposed arguments</p>
        <JsonBlock value={args} />
      </div>

      {diff && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Proposed diff</p>
          <JsonBlock value={diff} />
        </div>
      )}

      {Object.keys(approval.entityRef || {}).length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Entity refs</p>
          <JsonBlock value={approval.entityRef} />
        </div>
      )}

      {auditTrail.length > 0 && (
        <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-dark-border dark:bg-dark-bg">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Audit trail</p>
          <div className="space-y-1.5">
            {auditTrail.map((event, index) => (
              <div key={`${event.event || "event"}-${index}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                <span className="font-semibold capitalize text-gray-700 dark:text-gray-200">{event.event || "event"}</span>
                {event.at && <span>{formatDate(event.at)}</span>}
                {event.by && <span>by {event.by}</span>}
                {event.reason && <span>Reason: {event.reason}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {(approval.decidedBy || approval.decisionReason) && (
        <div className="mt-3 text-[11px] text-gray-400">
          {approval.decidedBy && <span>Decided by {approval.decidedBy}</span>}
          {approval.decisionReason && <span className="ml-2">Reason: {approval.decisionReason}</span>}
        </div>
      )}

      {pending && (
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onReject}
            disabled={busy}
            className="h-9 px-3 rounded-lg border border-red-200 dark:border-red-500/30 text-sm font-medium text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-60 inline-flex items-center gap-2"
          >
            <FontAwesomeIcon icon={faXmark} className="text-xs" />
            Reject
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="h-9 px-3 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-60 inline-flex items-center gap-2"
          >
            {busy ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={faCheck} className="text-xs" />}
            Approve
          </button>
        </div>
      )}
    </div>
  );
}

export default function Approvals(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [tab, setTab] = useState<ApprovalTab>((searchParams.get("status") as ApprovalTab) || "pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [sessionResumeNotice, setSessionResumeNotice] = useState<{ sessionId: string; approvalId: string } | null>(null);
  const sessionFilter = searchParams.get("sessionId") || "";
  const skillFilter = searchParams.get("skillId") || "";
  const trajectoryFilter = searchParams.get("trajectoryId") || "";
  const toolFilter = searchParams.get("toolId") || "";

  const loadApprovals = useCallback(async () => {
    if (!user.email || !companyId) {
      setApprovals([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ email: user.email, companyId });
      if (tab !== "all") params.set("status", tab);
      else params.set("status", "");
      params.set("includeRuntime", "true");
      if (sessionFilter) params.set("sessionId", sessionFilter);
      if (skillFilter) params.set("skillId", skillFilter);
      if (trajectoryFilter) params.set("trajectoryId", trajectoryFilter);
      if (toolFilter) params.set("toolId", toolFilter);
      const res = await fetch(`${apiUrl}/approvals?${params.toString()}`);
      if (res.status === 404) {
        setApprovals([]);
        return;
      }
      if (!res.ok) throw new Error(await responseErrorMessage(res, "Could not load approvals."));
      const data = await res.json();
      setApprovals(data.approvals || []);
    } catch (err: any) {
      console.error("Failed to load approvals:", err);
      setError(err?.message || "Could not load approvals.");
    } finally {
      setLoading(false);
    }
  }, [companyId, sessionFilter, skillFilter, tab, toolFilter, trajectoryFilter, user.email]);

  useEffect(() => {
    const status = searchParams.get("status");
    if (status === "pending" || status === "approved" || status === "rejected" || status === "all") {
      setTab(status);
    }
  }, [searchParams]);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const decide = async (approvalId: string, decision: "approve" | "reject") => {
    if (!user.email || busyId) return;
    setBusyId(approvalId);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/approvals/${approvalId}/${decision}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });
      if (!res.ok) {
        throw new Error(await responseErrorMessage(res, `Could not ${decision} approval.`));
      }
      const data = await res.json();
      const resume = data?.sessionResume;
      if (decision === "approve" && resume?.required && resume?.sessionId) {
        sessionStorage.setItem(
          `approval-session-resume:${resume.sessionId}`,
          JSON.stringify({
            approvalId,
            runtimeStatePatch: resume.runtimeStatePatch || data?.statePatch || {},
            approvedAt: new Date().toISOString(),
          }),
        );
        setSessionResumeNotice({ sessionId: resume.sessionId, approvalId });
      }
      await loadApprovals();
    } catch (err: any) {
      console.error(`Failed to ${decision} approval:`, err);
      setError(err?.message || `Could not ${decision} approval.`);
    } finally {
      setBusyId("");
    }
  };

  const counts = useMemo(() => {
    return approvals.reduce(
      (acc, approval) => {
        const status = approval.status || "pending";
        acc[status] = (acc[status] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>,
    );
  }, [approvals]);

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-glow">
              <FontAwesomeIcon icon={faClipboardCheck} className="text-sm" />
            </span>
            <div>
              <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">Approvals</h1>
              <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">Review runtime session and asynchronous work approvals before execution</p>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          {(sessionFilter || skillFilter || trajectoryFilter || toolFilter) && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime filter active</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {sessionFilter ? <>Session <span className="font-mono text-gray-700 dark:text-gray-200">{sessionFilter}</span></> : null}
                  {skillFilter ? <> {sessionFilter ? "· " : ""}Skill <span className="font-mono text-gray-700 dark:text-gray-200">{skillFilter}</span></> : null}
                  {trajectoryFilter ? <> {(sessionFilter || skillFilter) ? "· " : ""}Trajectory <span className="font-mono text-gray-700 dark:text-gray-200">{trajectoryFilter}</span></> : null}
                  {toolFilter ? <> {(sessionFilter || skillFilter || trajectoryFilter) ? "· " : ""}Tool <span className="font-mono text-gray-700 dark:text-gray-200">{toolFilter}</span></> : null}
                </p>
              </div>
              <button
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.delete("sessionId");
                  next.delete("skillId");
                  next.delete("trajectoryId");
                  next.delete("toolId");
                  setSearchParams(next);
                }}
                className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-bg"
              >
                Clear filter
              </button>
            </div>
          )}
          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-xs" />
              <span className="flex-1">{error}</span>
              <button onClick={() => setError("")} className="text-red-400 hover:text-red-600"><FontAwesomeIcon icon={faXmark} className="text-xs" /></button>
            </div>
          )}

          {sessionResumeNotice && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
              <div>
                <p className="font-semibold">Approval applied to runtime session</p>
                <p className="mt-0.5 text-xs opacity-80">Open the original session to continue with the approved runtime state.</p>
              </div>
              <button
                onClick={() => navigate(`/session/${sessionResumeNotice.sessionId}`, { state: { approvalResume: true, approvalId: sessionResumeNotice.approvalId } })}
                className="h-8 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white hover:bg-emerald-700"
              >
                Open session
              </button>
            </div>
          )}

          {!companyId ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
              <span className="inline-flex w-14 h-14 rounded-2xl bg-gray-100 dark:bg-dark-border items-center justify-center mb-4 text-gray-400">
                <FontAwesomeIcon icon={faBuilding} className="text-xl" />
              </span>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No company selected</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">Select a company to review pending approvals.</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-1.5 mb-5 overflow-x-auto">
                {([
                  { key: "pending" as ApprovalTab, label: "Pending", icon: faClock },
                  { key: "approved" as ApprovalTab, label: "Approved", icon: faCheck },
                  { key: "rejected" as ApprovalTab, label: "Rejected", icon: faXmark },
                  { key: "all" as ApprovalTab, label: "All", icon: faClipboardCheck },
                ]).map((item) => (
                  <button
                    key={item.key}
                    onClick={() => {
                      setTab(item.key);
                      const next = new URLSearchParams(searchParams);
                      next.set("status", item.key);
                      setSearchParams(next);
                    }}
                    className={`h-9 px-3 rounded-lg text-xs font-semibold flex items-center gap-2 whitespace-nowrap transition-colors border ${
                      tab === item.key
                        ? "bg-amber-500 text-white border-transparent"
                        : "bg-white dark:bg-dark-surface text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border"
                    }`}
                  >
                    <FontAwesomeIcon icon={item.icon} className="text-[11px]" />
                    {item.label}
                    {item.key !== "all" && counts[item.key] ? <span className="text-[10px] opacity-80">{counts[item.key]}</span> : null}
                  </button>
                ))}
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-20">
                  <FontAwesomeIcon icon={faSpinner} className="text-amber-500 text-2xl animate-spin" />
                </div>
              ) : approvals.length === 0 ? (
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
                  <span className="inline-flex w-14 h-14 rounded-2xl bg-amber-50 dark:bg-amber-500/10 items-center justify-center mb-4 text-amber-500">
                    <FontAwesomeIcon icon={faClipboardCheck} className="text-xl" />
                  </span>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No approvals found</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">There are no {tab === "all" ? "" : tab} asynchronous approvals for this company.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  {approvals.map((approval) => (
                    <ApprovalCard
                      key={approval.approvalId}
                      approval={approval}
                      busy={busyId === approval.approvalId}
                      onApprove={() => decide(approval.approvalId, "approve")}
                      onReject={() => decide(approval.approvalId, "reject")}
                      onOpenSession={(sessionId) => navigate(`/session/${sessionId}`)}
                      onOpenCapability={(kind, id) => navigate(`/capabilities/${kind}/${id}`)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
