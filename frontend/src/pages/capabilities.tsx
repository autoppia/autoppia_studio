import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faArrowRightLong,
  faBuilding,
  faCheck,
  faChevronDown,
  faCircleNodes,
  faClipboardCheck,
  faCube,
  faClockRotateLeft,
  faFlask,
  faPlus,
  faRobot,
  faRoute,
  faShieldHalved,
  faSpinner,
  faTractor,
  faTriangleExclamation,
  faWandMagicSparkles,
  faWrench,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import {
  CompanySkill,
  CompanyTool,
  CompanyTrajectory,
  Connector,
  EvalItem,
  HarvesterRun,
} from "../utils/types";
import InfoIcon from "../components/common/info-icon";
import SelectDropdown from "../components/common/select-dropdown";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type ViewKey = "tools" | "trajectories" | "skills" | "runs";
type ApprovalMode = "always" | "auto" | "never";
type CapabilityDetail =
  | { kind: "tool"; item: CompanyTool }
  | { kind: "trajectory"; item: CompanyTrajectory }
  | { kind: "skill"; item: CompanySkill }
  | null;

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function statusTone(status: string) {
  const s = (status || "").toLowerCase();
  if (["ready", "active", "completed", "promoted", "published", "approved"].includes(s)) return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (["failed", "error"].includes(s)) return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30";
  if (["running", "draft", "pending", "harvested"].includes(s)) return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function judgeTone(label?: string) {
  const s = (label || "").toLowerCase();
  if (s === "pass") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (s === "fail") return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function sideEffectTone(sideEffects: string) {
  const s = (sideEffects || "").toLowerCase();
  if (s === "writes" || s === "deletes") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function riskTone(risk: string) {
  const s = (risk || "").toLowerCase();
  if (s === "high") return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30";
  if (s === "medium") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function approvalMode(item?: { permissions?: Record<string, any>; riskLevel?: string; sideEffects?: string }): ApprovalMode {
  const explicit = String(item?.permissions?.approval || "").toLowerCase();
  if (explicit === "always" || explicit === "never" || explicit === "auto") return explicit;
  return "auto";
}

function approvalTone(mode: ApprovalMode) {
  if (mode === "always") return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-300 border-red-200 dark:border-red-500/30";
  if (mode === "never") return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
  return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300 border-amber-200 dark:border-amber-500/30";
}

function approvalLabel(mode: ApprovalMode) {
  if (mode === "always") return "approval always";
  if (mode === "never") return "approval never";
  return "approval auto";
}

function humanizeName(value?: string) {
  return (value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

function skillOriginLabel(skill: CompanySkill) {
  if (skill.harvesterType) return `${humanizeName(skill.harvesterType)} harvester`;
  if (skill.source) return humanizeName(skill.source);
  return "";
}

function trajectoryToolCalls(trajectory: CompanyTrajectory) {
  return trajectoryToolCallList(trajectory).length;
}

function trajectoryToolCallList(trajectory: CompanyTrajectory) {
  const raw = trajectory.trajectory?.length ? trajectory.trajectory : trajectory.steps || [];
  return raw
    .map((item, index) => {
      const name = String(item?.name || item?.action || item?.tool || "");
      const args = item?.arguments && typeof item.arguments === "object" ? item.arguments : item?.args && typeof item.args === "object" ? item.args : {};
      return name ? { index, name, arguments: args } : null;
    })
    .filter(Boolean) as Array<{ index: number; name: string; arguments: Record<string, any> }>;
}

function trajectoryJudgeLabel(trajectory: CompanyTrajectory) {
  return String(trajectory.judge?.label || "");
}

const RISK_POLICIES = [
  { value: "human_approval_for_writes", label: "Human approval for writes" },
  { value: "human_approval_always", label: "Human approval always" },
  { value: "autonomous", label: "Fully autonomous" },
];

function RequirementChips({ values }: { values?: string[] }) {
  const items = (values || []).filter(Boolean);
  if (items.length === 0) return <span className="text-xs text-gray-400">No runtime requirements declared.</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
          {item}
        </span>
      ))}
    </div>
  );
}

/** Semantic-entity chips for a tool/skill: which entities it reads and which it produces. */
function EntityChips({ inputEntities, outputEntity }: { inputEntities?: string[]; outputEntity?: string }) {
  const inputs = (inputEntities || []).filter(Boolean);
  const output = (outputEntity || "").trim();
  if (inputs.length === 0 && !output) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {inputs.map((name) => (
        <span key={`in-${name}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">
          <FontAwesomeIcon icon={faCube} className="text-[9px]" />
          {name}
        </span>
      ))}
      {output && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border bg-primary/10 text-primary border-primary/30">
          <FontAwesomeIcon icon={faArrowRightLong} className="text-[9px]" />
          {output}
        </span>
      )}
    </div>
  );
}

function JsonBlock({ value }: { value: any }) {
  return (
    <pre className="max-h-52 overflow-auto rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-[11px] leading-4 text-gray-700 dark:text-gray-200">
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

/** Connector -> Tools -> Trajectories -> Skills -> Agents pipeline explanation. */
function CapabilitiesBuildInfo({ counts }: { counts: { customTools: number; trajectories: number; skills: number } }) {
  const steps = [
    { icon: faCircleNodes, label: "Connectors", hint: "Authenticated systems", value: null as number | null },
    { icon: faWrench, label: "Tools", hint: "Connector actions", value: counts.customTools },
    { icon: faRoute, label: "Trajectories", hint: "Proven task flows", value: counts.trajectories },
    { icon: faWandMagicSparkles, label: "Skills", hint: "Reusable capabilities", value: counts.skills },
    { icon: faRobot, label: "Agents", hint: "Use the skills", value: null as number | null },
  ];
  return (
    <InfoIcon title="How capabilities are built">
      <div className="space-y-4">
        <p>
          Capabilities move from authenticated systems to reusable agent actions.
          Official connectors can publish tools directly; custom APIs and web apps
          usually need benchmarks and harvesters to produce reliable trajectories.
        </p>
        <div className="space-y-2">
          {steps.map((step, index) => (
            <div key={step.label} className="flex items-center gap-3 rounded-lg border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
              <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                <FontAwesomeIcon icon={step.icon} className="text-xs" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-semibold text-gray-800 dark:text-gray-100">{index + 1}. {step.label}</p>
                  {step.value !== null && (
                    <span className="px-1.5 rounded-md text-[10px] bg-white dark:bg-dark-surface text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-dark-border">{step.value}</span>
                  )}
                </div>
                <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-tight">{step.hint}</p>
              </div>
              {index < steps.length - 1 && (
                <FontAwesomeIcon icon={faArrowRight} className="text-[10px] text-gray-300 dark:text-gray-600 flex-shrink-0" />
              )}
            </div>
          ))}
        </div>
        <p>
          Once a trajectory is judged reliable, promote it to a Skill with a
          clear "when to use" hint and risk policy. Agents can then call that
          skill instead of rediscovering the workflow from scratch.
        </p>
      </div>
    </InfoIcon>
  );
}

function PromoteModal({
  trajectory,
  onClose,
  onPromote,
  promoting,
}: {
  trajectory: CompanyTrajectory;
  onClose: () => void;
  onPromote: (payload: { name: string; whenToUse: string; riskPolicy: string }) => void;
  promoting: boolean;
}) {
  const [name, setName] = useState(trajectory.name || "");
  const [whenToUse, setWhenToUse] = useState(trajectory.intent || trajectory.description || "");
  const [riskPolicy, setRiskPolicy] = useState(RISK_POLICIES[0].value);

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-gradient-primary text-white flex items-center justify-center">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
            </span>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Promote to Skill</h3>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border">
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 leading-relaxed">
          A skill is a reusable capability your agents can call. It wraps this trajectory with a clear name, a "when to use" hint and a risk policy.
        </p>
        <div className="space-y-3">
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Skill name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="e.g. Send invoice reminder" />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">When to use</span>
            <textarea value={whenToUse} onChange={(e) => setWhenToUse(e.target.value)} rows={3} className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" placeholder="Describe when an agent should pick this skill." />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Risk policy</span>
            <SelectDropdown value={riskPolicy} onChange={setRiskPolicy} options={RISK_POLICIES} />
          </label>
        </div>
        <button
          onClick={() => onPromote({ name: name.trim() || trajectory.name, whenToUse: whenToUse.trim(), riskPolicy })}
          disabled={promoting}
          className="mt-4 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60"
        >
          {promoting ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : "Promote to Skill"}
        </button>
      </div>
    </div>
  );
}

function CapabilityDetailModal({
  detail,
  toolsByName,
  trajectoriesById,
  connectorsById,
  userEmail,
  onReload,
  onClose,
}: {
  detail: Exclude<CapabilityDetail, null>;
  toolsByName: Map<string, CompanyTool>;
  trajectoriesById: Map<string, CompanyTrajectory>;
  connectorsById: Map<string, Connector>;
  userEmail: string;
  onReload: () => Promise<void>;
  onClose: () => void;
}) {
  const [busyAction, setBusyAction] = useState("");
  const [actionResult, setActionResult] = useState<any>(null);
  const isTool = detail.kind === "tool";
  const isTrajectory = detail.kind === "trajectory";
  const isSkill = detail.kind === "skill";
  const configurableApprovalItem: CompanyTool | CompanySkill | null = isTool ? detail.item : isSkill ? detail.item : null;
  const [selectedApproval, setSelectedApproval] = useState<ApprovalMode>(approvalMode(configurableApprovalItem || undefined));
  const title = isTool ? detail.item.name : detail.item.name || (isTrajectory ? detail.item.trajectoryId : detail.item.skillId);
  const icon = isTool ? faWrench : isTrajectory ? faRoute : faWandMagicSparkles;
  const kindLabel = isTool ? "Atomic action" : isTrajectory ? "Concrete attempt" : "Reusable procedure";
  const linkedTrajectory = isSkill ? (detail.item.trajectoryIds || []).map((id) => trajectoriesById.get(id)).find(Boolean) : null;
  const calls = isTrajectory ? trajectoryToolCallList(detail.item) : linkedTrajectory ? trajectoryToolCallList(linkedTrajectory) : [];
  const requirements = isTool || isTrajectory || isSkill ? detail.item.runtimeRequirements : [];
  const entityItem: CompanyTool | CompanySkill | null = isTool ? detail.item : isSkill ? detail.item : null;

  const updateApprovalMode = async (mode: ApprovalMode) => {
    if (!configurableApprovalItem || busyAction || mode === selectedApproval) return;
    setBusyAction(`approval-${mode}`);
    setActionResult(null);
    try {
      const endpoint = isTool
        ? `${apiUrl}/tools/${(configurableApprovalItem as CompanyTool).toolId}/approval`
        : `${apiUrl}/skills/${(configurableApprovalItem as CompanySkill).skillId}/approval`;
      const res = await fetch(endpoint, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: userEmail, approval: mode }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "Could not update approval policy.");
      setSelectedApproval(mode);
      setActionResult(data);
      await onReload();
    } catch (err: any) {
      setActionResult({ success: false, error: err?.message || "Could not update approval policy." });
    } finally {
      setBusyAction("");
    }
  };

  const testTool = async () => {
    if (!isTool || busyAction) return;
    setBusyAction("test");
    setActionResult(null);
    try {
      const res = await fetch(`${apiUrl}/tools/${detail.item.toolId}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: userEmail, arguments: {} }),
      });
      const data = await res.json();
      setActionResult(data);
      await onReload();
    } catch (err: any) {
      setActionResult({ success: false, error: err?.message || "Tool test failed." });
    } finally {
      setBusyAction("");
    }
  };

  const reviewTrajectory = async (label: "approved" | "rejected") => {
    if (!isTrajectory || busyAction) return;
    setBusyAction(label);
    setActionResult(null);
    try {
      const res = await fetch(`${apiUrl}/trajectories/${detail.item.trajectoryId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: userEmail, label }),
      });
      const data = await res.json();
      setActionResult(data);
      await onReload();
    } catch (err: any) {
      setActionResult({ success: false, error: err?.message || "Review failed." });
    } finally {
      setBusyAction("");
    }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-3xl max-h-[86vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl">
        <div className="h-14 px-5 border-b border-gray-200 dark:border-dark-border flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={icon} className="text-xs" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{title}</p>
              <p className="text-[11px] text-gray-400 dark:text-gray-500">{kindLabel}</p>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border">
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <div className="overflow-auto max-h-[calc(86vh-3.5rem)] p-5 space-y-5">
          <section>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Runtime requirements</p>
            <RequirementChips values={requirements} />
          </section>

          {configurableApprovalItem && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Approval policy</p>
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${approvalTone(selectedApproval)}`}>
                  <FontAwesomeIcon icon={faShieldHalved} className="mr-1 text-[9px]" />
                  {approvalLabel(selectedApproval)}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { value: "auto" as ApprovalMode, label: "Auto", hint: "Writes stop when risk policy requires it." },
                  { value: "always" as ApprovalMode, label: "Always", hint: "Every call requires explicit approval." },
                  { value: "never" as ApprovalMode, label: "Never", hint: "This capability runs without approval." },
                ]).map((item) => (
                  <button
                    key={item.value}
                    onClick={() => updateApprovalMode(item.value)}
                    disabled={!!busyAction}
                    className={`min-h-[72px] rounded-lg border p-3 text-left transition-colors disabled:opacity-60 ${
                      selectedApproval === item.value
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 hover:border-primary/30"
                    }`}
                  >
                    <span className="block text-xs font-semibold">
                      {busyAction === `approval-${item.value}` ? <FontAwesomeIcon icon={faSpinner} className="mr-1 animate-spin" /> : null}
                      {item.label}
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-gray-400 dark:text-gray-500">{item.hint}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {entityItem && (((entityItem.inputEntities || []).length > 0) || entityItem.outputEntity || (entityItem.outputCard && Object.keys(entityItem.outputCard).length > 0)) && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Entities</p>
              <EntityChips inputEntities={entityItem.inputEntities} outputEntity={entityItem.outputEntity} />
              {entityItem.outputCard && Object.keys(entityItem.outputCard).length > 0 && (
                <div className="mt-2">
                  <p className="text-[11px] text-gray-400 mb-1">Output card</p>
                  <JsonBlock value={entityItem.outputCard} />
                </div>
              )}
            </section>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {isTool && (
              <button
                onClick={testTool}
                disabled={!!busyAction}
                className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold disabled:opacity-60 inline-flex items-center gap-2"
              >
                <FontAwesomeIcon icon={busyAction === "test" ? faSpinner : faWrench} className={`text-[10px] ${busyAction === "test" ? "animate-spin" : ""}`} />
                Test tool
              </button>
            )}
            {isTrajectory && (
              <>
                <button onClick={() => reviewTrajectory("approved")} disabled={!!busyAction} className="h-8 px-3 rounded-lg bg-green-600 text-white text-xs font-semibold disabled:opacity-60">
                  {busyAction === "approved" ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : "Approve"}
                </button>
                <button onClick={() => reviewTrajectory("rejected")} disabled={!!busyAction} className="h-8 px-3 rounded-lg border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 text-xs font-semibold disabled:opacity-60">
                  {busyAction === "rejected" ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : "Reject"}
                </button>
              </>
            )}
          </div>

          {actionResult && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Action result</p>
              <JsonBlock value={actionResult} />
            </section>
          )}

          {isTool && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <section>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Tool info</p>
                <div className="space-y-2 text-xs text-gray-600 dark:text-gray-300">
                  <p><span className="text-gray-400">Connector:</span> {connectorsById.get(detail.item.connectorId)?.name || detail.item.connectorName || "Unknown"}</p>
                  <p><span className="text-gray-400">Execution:</span> {detail.item.executionType || "api_call"}</p>
                  <p><span className="text-gray-400">Surface:</span> {detail.item.surface || "api"}</p>
                  <p><span className="text-gray-400">Side effects:</span> {detail.item.sideEffects}</p>
                  <p><span className="text-gray-400">Risk:</span> {detail.item.riskLevel}</p>
                  {detail.item.discovererName && <p><span className="text-gray-400">Discoverer:</span> {detail.item.discovererName} {detail.item.discovererVersion || ""}</p>}
                  {detail.item.discoveryScope && <p><span className="text-gray-400">Scope:</span> {detail.item.discoveryScope}</p>}
                  {detail.item.discoveryRelevance?.reason && <p><span className="text-gray-400">Relevance:</span> {detail.item.discoveryRelevance.reason} ({detail.item.discoveryRelevance.score ?? "n/a"})</p>}
                  {detail.item.lastTestStatus && <p><span className="text-gray-400">Last test:</span> {detail.item.lastTestStatus}</p>}
                </div>
              </section>
              <section>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Input schema</p>
                <JsonBlock value={detail.item.inputSchema} />
              </section>
            </div>
          )}

          {isTool && (detail.item.discoveryEvidence || []).length > 0 && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Discovery evidence</p>
              <JsonBlock value={detail.item.discoveryEvidence} />
            </section>
          )}

          {(isTrajectory || isSkill) && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Tool call sequence</p>
              {calls.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 text-xs text-gray-400">
                  No executable tool calls stored yet.
                </div>
              ) : (
                <div className="space-y-2">
                  {calls.map((call, index) => {
                    const normalized = call.name.startsWith("browser.") ? call.name.split(".", 2)[1] : call.name;
                    const tool = toolsByName.get(call.name) || toolsByName.get(normalized);
                    return (
                      <div key={`${call.name}-${index}`} className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="font-mono text-xs text-gray-800 dark:text-gray-100 break-all">{index + 1}. {call.name}</p>
                            {tool && (
                              <p className="text-[11px] text-gray-400 mt-0.5">
                                {tool.connectorName} · {tool.executionType} · {(tool.runtimeRequirements || []).join(", ") || "no requirements"}
                              </p>
                            )}
                          </div>
                          {tool ? (
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${riskTone(tool.riskLevel)}`}>{tool.riskLevel}</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-100 dark:bg-dark-border text-gray-400 border-gray-200 dark:border-dark-border">unlinked</span>
                          )}
                        </div>
                        <div className="mt-2">
                          <JsonBlock value={call.arguments} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {isTrajectory && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Evidence & artifacts</p>
              <div className="space-y-2">
                {detail.item.finalUrl && (
                  <a href={detail.item.finalUrl} target="_blank" rel="noreferrer" className="block font-mono text-xs text-primary break-all">
                    {detail.item.finalUrl}
                  </a>
                )}
                {(detail.item.harvester?.evidence || []).length > 0 && (
                  <div className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-600 dark:text-gray-300 space-y-1">
                    {(detail.item.harvester?.evidence || []).map((item: string, index: number) => <p key={index}>{item}</p>)}
                  </div>
                )}
                {detail.item.review && Object.keys(detail.item.review).length > 0 && <JsonBlock value={detail.item.review} />}
              </div>
            </section>
          )}

          {isSkill && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Dependencies</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <JsonBlock value={{ connectorIds: detail.item.connectorIds || [] }} />
                <JsonBlock value={{ toolIds: detail.item.toolIds || [] }} />
                <JsonBlock value={{ trajectoryIds: detail.item.trajectoryIds || [] }} />
              </div>
            </section>
          )}

          <section>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Raw capability</p>
            <JsonBlock value={detail.item} />
          </section>
        </div>
      </div>
    </div>
  );
}

export default function Capabilities(): React.ReactElement {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [tools, setTools] = useState<CompanyTool[]>([]);
  const [trajectories, setTrajectories] = useState<CompanyTrajectory[]>([]);
  const [skills, setSkills] = useState<CompanySkill[]>([]);
  const [runs, setRuns] = useState<HarvesterRun[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ViewKey>("tools");
  const [expandedToolConnectorKeys, setExpandedToolConnectorKeys] = useState<Set<string>>(new Set());
  const [promoteTarget, setPromoteTarget] = useState<CompanyTrajectory | null>(null);
  const [detail, setDetail] = useState<CapabilityDetail>(null);
  const [promoting, setPromoting] = useState(false);

  // Create Capability wizard state. `createPath` tracks which of the four paths is expanded.
  const [showCreate, setShowCreate] = useState(false);
  const [createPath, setCreatePath] = useState<"menu" | "task">("menu");
  const [generateConnectorId, setGenerateConnectorId] = useState("");
  const [generateBenchmarkId, setGenerateBenchmarkId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");
  const [generateMessage, setGenerateMessage] = useState("");

  const loadCapabilities = useCallback(async () => {
    if (!user.email || !companyId) {
      setTools([]);
      setTrajectories([]);
      setSkills([]);
      setRuns([]);
      setConnectors([]);
      setEvals([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      const connectorParams = new URLSearchParams({ email: user.email, companyId });
      const [capRes, runsRes, connectorsRes, evalsRes] = await Promise.all([
        fetch(`${apiUrl}/companies/${companyId}/capabilities?${params.toString()}`),
        fetch(`${apiUrl}/companies/${companyId}/harvester-runs?${params.toString()}`),
        fetch(`${apiUrl}/connectors?${connectorParams.toString()}`),
        fetch(`${apiUrl}/evals?${connectorParams.toString()}`),
      ]);
      if (capRes.ok) {
        const data = await capRes.json();
        setTools(data.tools || []);
        setTrajectories(data.trajectories || []);
        setSkills(data.skills || []);
      }
      if (runsRes.ok) {
        const data = await runsRes.json();
        setRuns(data.runs || []);
      }
      if (connectorsRes.ok) {
        const data = await connectorsRes.json();
        setConnectors(data.connectors || []);
      }
      if (evalsRes.ok) {
        const data = await evalsRes.json();
        setEvals(data.evals || []);
      }
    } catch (err) {
      console.error("Failed to load capabilities:", err);
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadCapabilities();
  }, [loadCapabilities]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const customConnectors = useMemo(
    () => connectors.filter((connector) => (connector.provider || "official") === "custom"),
    [connectors],
  );

  const generateConnector = useMemo(
    () => customConnectors.find((connector) => connector.connectorId === generateConnectorId) || null,
    [customConnectors, generateConnectorId],
  );

  // Preselect a connector coming from the Connectors page, then drop the query param.
  useEffect(() => {
    const preselect = searchParams.get("connectorId");
    if (preselect) {
      setGenerateConnectorId(preselect);
      const next = new URLSearchParams(searchParams);
      next.delete("connectorId");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Default the connector selection to the first custom connector.
  useEffect(() => {
    if (customConnectors.length === 0) {
      if (generateConnectorId) setGenerateConnectorId("");
      return;
    }
    if (!generateConnectorId || !customConnectors.some((connector) => connector.connectorId === generateConnectorId)) {
      setGenerateConnectorId(customConnectors[0].connectorId);
    }
  }, [customConnectors, generateConnectorId]);

  const promoteTrajectory = async (payload: { name: string; whenToUse: string; riskPolicy: string }) => {
    if (!promoteTarget || promoting) return;
    setPromoting(true);
    try {
      const res = await fetch(`${apiUrl}/trajectories/${promoteTarget.trajectoryId}/promote-to-skill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, ...payload }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPromoteTarget(null);
      await loadCapabilities();
      setView("skills");
    } catch (err) {
      console.error("Failed to promote trajectory:", err);
    } finally {
      setPromoting(false);
    }
  };

  const benchmarks = useMemo(() => {
    const grouped = new Map<string, { benchmarkId: string; name: string; tasks: EvalItem[] }>();
    for (const item of evals) {
      const key = item.benchmarkId || item.agentId || `manual:${item.initialUrl || "default"}`;
      if (!grouped.has(key)) grouped.set(key, { benchmarkId: key, name: item.benchmarkName || item.agentName || "Manual Benchmark", tasks: [] });
      grouped.get(key)!.tasks.push(item);
    }
    return Array.from(grouped.values());
  }, [evals]);

  const runGeneration = async () => {
    if (!generateConnector || generating || !companyId) return;
    if (!generateBenchmarkId) return;
    setGenerating(true);
    setGenerateError("");
    setGenerateMessage("");
    try {
      const body = { connectorId: generateConnector.connectorId, benchmarkId: generateBenchmarkId, evalIds: [] };
      const res = await fetch(`${apiUrl}/companies/${companyId}/capabilities/harvest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (!data.success) {
        setGenerateError((data.run?.errors || []).join(" · ") || "Generation failed. Check the connector setup and try again.");
      } else {
        const toolCount = data.tools?.length || 0;
        const skillCount = data.skills?.length || 0;
        setGenerateMessage(
          `Harvested ${toolCount} ${toolCount === 1 ? "tool" : "tools"} and ${skillCount} ${skillCount === 1 ? "skill" : "skills"} from ${generateConnector.name}.`,
        );
      }
      await loadCapabilities();
      setView("trajectories");
    } catch (err: any) {
      console.error("Failed to generate capabilities:", err);
      setGenerateError(err?.message || "Could not generate capabilities for this connector.");
    } finally {
      setGenerating(false);
    }
  };

  const connectorsById = useMemo(() => new Map(connectors.map((connector) => [connector.connectorId, connector])), [connectors]);
  const toolsByConnector = useMemo(() => {
    const groups = new Map<string, { connectorKey: string; connectorName: string; tools: CompanyTool[] }>();
    for (const tool of tools) {
      const key = tool.connectorId || tool.connectorName || "unknown";
      const connectorName = connectorsById.get(tool.connectorId)?.name || tool.connectorName || "Unknown connector";
      if (!groups.has(key)) groups.set(key, { connectorKey: key, connectorName, tools: [] });
      groups.get(key)!.tools.push(tool);
    }
    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        tools: [...group.tools].sort((a, b) => a.name.localeCompare(b.name)),
      }))
      .sort((a, b) => a.connectorName.localeCompare(b.connectorName));
  }, [connectorsById, tools]);

  const toggleToolConnector = (connectorKey: string) => {
    setExpandedToolConnectorKeys((current) => {
      const next = new Set(current);
      if (next.has(connectorKey)) next.delete(connectorKey);
      else next.add(connectorKey);
      return next;
    });
  };

  const expandAllToolConnectors = () => {
    setExpandedToolConnectorKeys(new Set(toolsByConnector.map((group) => group.connectorKey)));
  };

  const collapseAllToolConnectors = () => {
    setExpandedToolConnectorKeys(new Set());
  };

  const toolsCount = tools.length;
  const toolsByName = useMemo(() => new Map(tools.map((tool) => [tool.name, tool])), [tools]);
  const trajectoriesById = useMemo(() => new Map(trajectories.map((trajectory) => [trajectory.trajectoryId, trajectory])), [trajectories]);
  const skillTrajectoryIds = useMemo(() => new Set(skills.flatMap((skill) => skill.trajectoryIds || [])), [skills]);
  // Skill candidates are not a separate artifact. They are trajectories that
  // passed judging and have not yet been promoted into a reusable skill.
  const skillCandidates = useMemo(
    () => trajectories.filter((trajectory) => {
      const status = (trajectory.status || "").toLowerCase();
      return status === "harvested" && trajectoryJudgeLabel(trajectory) === "pass" && !skillTrajectoryIds.has(trajectory.trajectoryId);
    }),
    [skillTrajectoryIds, trajectories],
  );
  const sortedTrajectories = useMemo(
    () => [...trajectories].sort((a, b) => {
      const aApproved = skillTrajectoryIds.has(a.trajectoryId) || (a.status || "").toLowerCase() === "approved";
      const bApproved = skillTrajectoryIds.has(b.trajectoryId) || (b.status || "").toLowerCase() === "approved";
      if (aApproved !== bApproved) return aApproved ? -1 : 1;
      return new Date(b.updatedAt || b.createdAt || 0).getTime() - new Date(a.updatedAt || a.createdAt || 0).getTime();
    }),
    [skillTrajectoryIds, trajectories],
  );

  // The pipeline band doubles as the primary navigation: Tools -> Trajectories ->
  // Skills -> Harvester Runs. Tasks stay under Benchmarks/Harvester Runs because
  // they are inputs to harvesting, not capabilities.
  const pipelineSteps: Array<{ key: ViewKey; label: string; icon: typeof faWrench; count: number; blurb: string }> = [
    { key: "tools", label: "Tools", icon: faWrench, count: toolsCount, blurb: "Atomic actions from connectors" },
    { key: "trajectories", label: "Trajectories", icon: faRoute, count: trajectories.length, blurb: "Concrete attempts with tool calls" },
    { key: "skills", label: "Skills", icon: faWandMagicSparkles, count: skills.length, blurb: "Reusable, versioned procedures" },
    { key: "runs", label: "Runs", icon: faTractor, count: runs.length, blurb: "Harvester run history" },
  ];
  const openCreate = () => { setGenerateError(""); setGenerateMessage(""); setCreatePath("menu"); setShowCreate(true); };

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-glow">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-sm" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">Capability Studio</h1>
                <CapabilitiesBuildInfo counts={{ customTools: toolsCount, trajectories: trajectories.length, skills: skills.length }} />
              </div>
              <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">Turn tools into trajectories, and trajectories into reusable skills</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {companyId && (
              <button
                onClick={openCreate}
                className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold inline-flex items-center gap-2 shadow-glow"
                title="Create a new capability"
              >
                <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
                Create Capability
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          {!companyId ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
              <span className="inline-flex w-14 h-14 rounded-2xl bg-gray-100 dark:bg-dark-border items-center justify-center mb-4 text-gray-400">
                <FontAwesomeIcon icon={faBuilding} className="text-xl" />
              </span>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No company selected</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">Create or select a company from the top bar to see its capabilities.</p>
            </div>
          ) : (
            <>
              {/* Create Capability wizard — opened from the header "Create Capability" button */}
              {showCreate && (
              <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowCreate(false)} />
                <div className="relative w-full max-w-5xl max-h-[86vh] overflow-auto rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-6">
                <div className="flex items-start justify-between gap-4 mb-5">
                  <div className="flex items-start gap-2.5 min-w-0">
                    <span className="w-9 h-9 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
                      <FontAwesomeIcon icon={createPath === "task" ? faTractor : faPlus} className="text-xs" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-base font-semibold text-gray-900 dark:text-white">{createPath === "task" ? "Learn from a task" : "Create Capability"}</p>
                      <p className="text-xs leading-5 text-gray-500 dark:text-gray-400 max-w-2xl">
                        {createPath === "task"
                          ? "Run a harvester against a custom connector and a benchmark. It produces trajectories — concrete evidence — that you can later distill into skills."
                          : "Pick how you want to add a reusable capability. Skills come from proven trajectories or are authored directly."}
                      </p>
                    </div>
                  </div>
                  <button onClick={() => setShowCreate(false)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border flex-shrink-0">
                    <FontAwesomeIcon icon={faXmark} className="text-sm" />
                  </button>
                </div>

                {createPath === "menu" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 flex flex-col">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0"><FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" /></span>
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Create skill manually</p>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed flex-1">Author a skill from scratch with your own instructions and when-to-use notes. Coming soon.</p>
                      <button disabled className="mt-3 h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-400 dark:text-gray-500 cursor-not-allowed inline-flex items-center justify-center gap-2">
                        Coming soon
                      </button>
                    </div>

                    <button onClick={() => setCreatePath("task")} className="text-left rounded-xl border border-primary/30 bg-primary/5 p-4 flex flex-col hover:border-primary/50 transition-colors">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0"><FontAwesomeIcon icon={faTractor} className="text-xs" /></span>
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Learn from a task</p>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed flex-1">Run a harvester against a connector and benchmark to generate trajectories you can promote into skills.</p>
                      <span className="mt-3 h-9 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold inline-flex items-center justify-center gap-2">
                        <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
                        Run Harvester
                      </span>
                    </button>

                    <button onClick={() => { setShowCreate(false); setView("trajectories"); }} className="text-left rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 flex flex-col hover:border-primary/40 transition-colors">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0"><FontAwesomeIcon icon={faFlask} className="text-xs" /></span>
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Create skill from trajectory</p>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed flex-1">Pick a passing trajectory and distill it into a reusable skill.</p>
                      <span className="mt-3 h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 inline-flex items-center justify-center gap-2">
                        <FontAwesomeIcon icon={faFlask} className="text-[10px]" />
                        View promotable trajectories ({skillCandidates.length})
                      </span>
                    </button>

                    <button onClick={() => { setShowCreate(false); setView("skills"); }} className="text-left rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 flex flex-col hover:border-primary/40 transition-colors">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0"><FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" /></span>
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Improve existing skill</p>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed flex-1">Open your published skills to refine instructions, risk policy or add source trajectories.</p>
                      <span className="mt-3 h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 inline-flex items-center justify-center gap-2">
                        <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
                        Go to Skills ({skills.length})
                      </span>
                    </button>
                  </div>
                )}

                {createPath === "task" && (
                <div>
                <button onClick={() => setCreatePath("menu")} className="mb-4 text-xs font-medium text-gray-500 dark:text-gray-400 inline-flex items-center gap-1.5 hover:text-primary">
                  <FontAwesomeIcon icon={faArrowRight} className="text-[9px] rotate-180" />
                  Back to options
                </button>
                {customConnectors.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-4 py-6 text-center">
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                      No custom connectors yet. Official connectors already provide default tools; create a custom API or web connector to harvest task-scoped capabilities.
                    </p>
                    <button onClick={() => navigate("/connectors")} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2">
                      <FontAwesomeIcon icon={faCircleNodes} className="text-xs" />
                      Go to Connectors
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-4">
                      <label className="block">
                        <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Connector</span>
                        <SelectDropdown
                          value={generateConnectorId}
                          onChange={(next) => { setGenerateConnectorId(next); setGenerateBenchmarkId(""); setGenerateError(""); setGenerateMessage(""); }}
                          placeholder="Select connector..."
                          options={customConnectors.map((connector) => ({
                            value: connector.connectorId,
                            label: connector.name,
                            hint: "Custom",
                          }))}
                        />
                      </label>

                      <label className="block">
                        <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                          Benchmark <span className="text-primary">· required</span>
                        </span>
                        <SelectDropdown
                          value={generateBenchmarkId}
                          onChange={setGenerateBenchmarkId}
                          placeholder="Select benchmark..."
                          options={benchmarks.map((benchmark) => ({
                            value: benchmark.benchmarkId,
                            label: benchmark.name,
                            hint: `${benchmark.tasks.length} ${benchmark.tasks.length === 1 ? "task" : "tasks"}`,
                          }))}
                        />
                      </label>

                      <div className="flex items-end">
                        <button
                          onClick={runGeneration}
                          disabled={generating || !generateConnector || !generateBenchmarkId}
                          className="h-10 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2 w-full lg:w-auto"
                          title="Run a harvester for this custom connector"
                        >
                          <FontAwesomeIcon icon={generating ? faSpinner : faTractor} className={`text-xs ${generating ? "animate-spin" : ""}`} />
                          {generating ? "Working…" : "Run harvester"}
                        </button>
                      </div>
                    </div>

                    {benchmarks.length === 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-[11px] text-amber-600 dark:text-amber-400">
                        <FontAwesomeIcon icon={faClipboardCheck} className="text-[10px]" />
                        <span className="flex-1">Custom connectors need a benchmark to harvest task-scoped capabilities. Create one first.</span>
                        <button onClick={() => navigate("/evals")} className="h-7 px-2.5 rounded-lg bg-white dark:bg-dark-surface border border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-300 font-semibold">
                          Go to Benchmarks
                        </button>
                      </div>
                    )}

                    {generateError && (
                      <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-[11px] text-red-600 dark:text-red-400">
                        <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-[10px]" />
                        <span className="flex-1">{generateError}</span>
                      </div>
                    )}

                    {generateMessage && !generateError && (
                      <div className="mt-3 flex items-center gap-2 rounded-lg border border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 px-3 py-2 text-[11px] text-green-600 dark:text-green-400">
                        <FontAwesomeIcon icon={faCheck} className="text-[10px]" />
                        <span className="flex-1">{generateMessage}</span>
                      </div>
                    )}
                  </>
                )}
                </div>
                )}
                </div>
              </div>
              )}

              {/* Pipeline band — explains the model and acts as the primary navigation */}
              <div className="mb-5">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {pipelineSteps.map((step, index) => (
                    <button
                      key={step.key}
                      onClick={() => setView(step.key)}
                      className={`relative text-left rounded-xl border p-3 transition-all duration-200 ${
                        view === step.key
                          ? "border-primary/40 bg-primary/5 shadow-sm"
                          : "border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface hover:border-primary/30"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${view === step.key ? "bg-gradient-primary text-white" : "bg-primary/10 text-primary"}`}>
                          <FontAwesomeIcon icon={step.icon} className="text-[11px]" />
                        </span>
                        <span className={`text-sm font-semibold tabular-nums ${view === step.key ? "text-primary" : "text-gray-700 dark:text-gray-200"}`}>{step.count}</span>
                      </div>
                      <p className="text-xs font-semibold text-gray-900 dark:text-white truncate">{step.label}</p>
                      <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500 mt-0.5 line-clamp-2 min-h-[1.75rem]">{step.blurb}</p>
                      {index < pipelineSteps.length - 1 && (
                        <FontAwesomeIcon icon={faArrowRight} className="hidden lg:block absolute -right-[7px] top-1/2 -translate-y-1/2 z-10 text-[9px] text-gray-300 dark:text-gray-600" />
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-20">
                  <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
                </div>
              ) : (
                <>
                  {/* Tools */}
                  {view === "tools" && toolsCount > 0 && (
                      <div className="space-y-5">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Connector Tools</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                              Tools are atomic actions exposed by connectors. Connectors stay collapsed so large workspaces remain scannable.
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">
                              {toolsByConnector.length} connectors
                            </span>
                            <button onClick={expandAllToolConnectors} className="h-8 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-border">
                              Expand all
                            </button>
                            <button onClick={collapseAllToolConnectors} className="h-8 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-border">
                              Collapse all
                            </button>
                          </div>
                        </div>

                        <div className="space-y-3">
                          {toolsByConnector.map((group) => {
                            const expanded = expandedToolConnectorKeys.has(group.connectorKey);
                            const writeCount = group.tools.filter((tool) => ["writes", "deletes"].includes((tool.sideEffects || "").toLowerCase())).length;
                            const typedCount = group.tools.filter((tool) => (tool.inputEntities || []).length > 0 || Boolean(tool.outputEntity)).length;
                            const highRiskCount = group.tools.filter((tool) => (tool.riskLevel || "").toLowerCase() === "high").length;
                            return (
                              <div key={group.connectorKey} className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
                                <button
                                  onClick={() => toggleToolConnector(group.connectorKey)}
                                  className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-dark-border/40"
                                >
                                  <div className="flex min-w-0 items-center gap-3">
                                    <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                                      <FontAwesomeIcon icon={faCircleNodes} className="text-xs" />
                                    </span>
                                    <div className="min-w-0">
                                      <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{group.connectorName}</p>
                                      <p className="mt-0.5 text-[11px] text-gray-400">{group.tools.length} {group.tools.length === 1 ? "tool" : "tools"}</p>
                                    </div>
                                  </div>
                                  <div className="flex flex-shrink-0 items-center gap-2">
                                    {writeCount > 0 && <span className="hidden rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400 sm:inline-flex">{writeCount} writes</span>}
                                    {typedCount > 0 && <span className="hidden rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary sm:inline-flex">{typedCount} typed</span>}
                                    {highRiskCount > 0 && <span className="hidden rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-medium text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400 sm:inline-flex">{highRiskCount} high risk</span>}
                                    <FontAwesomeIcon icon={faChevronDown} className={`text-xs text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                                  </div>
                                </button>

                                {expanded && (
                                  <div className="border-t border-gray-200 bg-gray-50 p-3 dark:border-dark-border dark:bg-dark-bg/60">
                                    <div className="flex flex-col gap-3">
                                      {group.tools.map((tool) => (
                                        <button
                                          key={tool.toolId}
                                          onClick={() => setDetail({ kind: "tool", item: tool })}
                                          className="text-left bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-soft hover:-translate-y-0.5"
                                        >
                                          <div className="flex items-start justify-between gap-2">
                                            <span className="font-mono text-xs text-gray-800 dark:text-gray-100 break-all">{tool.name}</span>
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${statusTone(tool.status)}`}>{tool.status}</span>
                                          </div>
                                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 line-clamp-2 min-h-[2rem]">{tool.description || "No description."}</p>
                                          <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-3 border-t border-gray-100 dark:border-dark-border">
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${sideEffectTone(tool.sideEffects)}`}>{tool.sideEffects}</span>
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${riskTone(tool.riskLevel)}`}>
                                              <FontAwesomeIcon icon={faShieldHalved} className="mr-1 text-[9px]" />{tool.riskLevel} risk
                                            </span>
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${approvalTone(approvalMode(tool))}`}>
                                              {approvalLabel(approvalMode(tool))}
                                            </span>
                                            {tool.surface && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{tool.surface}</span>}
                                            {tool.discoveryScope && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">{tool.discoveryScope}</span>}
                                            {tool.discoveryRelevance?.score !== undefined && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">rel {tool.discoveryRelevance.score}</span>}
                                          </div>
                                          {((tool.inputEntities || []).length > 0 || tool.outputEntity) && (
                                            <div className="mt-2">
                                              <EntityChips inputEntities={tool.inputEntities} outputEntity={tool.outputEntity} />
                                            </div>
                                          )}
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                  )}
                  {view === "tools" && toolsCount === 0 && (
                    <EmptyState
                      icon={faWrench}
                      title="No tools yet"
                      body="Tools are atomic actions from connectors. Publish official connector tools or run a harvester to create them for this company."
                      action={<button onClick={() => navigate("/connectors")} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faCircleNodes} className="text-xs" />Go to Connectors</button>}
                    />
                  )}

                  {/* Trajectories */}
                  {view === "trajectories" && trajectories.length > 0 && (
                      <div>
                        <div className="mb-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Trajectories</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            A trajectory is concrete evidence from a harvester run: task attempt, tool calls, observations and judge result. Passing unpromoted trajectories can be promoted into skills.
                          </p>
                          {skillCandidates.length > 0 && (
                            <p className="mt-1 text-xs text-primary">{skillCandidates.length} promotable {skillCandidates.length === 1 ? "trajectory" : "trajectories"} available.</p>
                          )}
                        </div>
                      <div className="flex flex-col gap-3">
                        {sortedTrajectories.map((trajectory) => {
                          const status = (trajectory.status || "").toLowerCase();
                          const judgeLabel = trajectoryJudgeLabel(trajectory);
                          const coveredBySkill = skillTrajectoryIds.has(trajectory.trajectoryId);
                          const promotable = status === "harvested" && judgeLabel === "pass" && !coveredBySkill;
                          const approved = status === "approved" || coveredBySkill;
                          return (
                            <div
                              key={trajectory.trajectoryId}
                              onClick={() => setDetail({ kind: "trajectory", item: trajectory })}
                              className="flex flex-col bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-soft hover:-translate-y-0.5 cursor-pointer"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                                    <FontAwesomeIcon icon={faRoute} className="text-xs" />
                                  </span>
                                  <div className="min-w-0">
                                    <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{trajectory.name || "Untitled trajectory"}</p>
                                    <p className="font-mono text-[10px] text-gray-300 dark:text-gray-600 truncate" title={trajectory.trajectoryId}>{trajectory.trajectoryId.slice(0, 8)}</p>
                                  </div>
                                </div>
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${statusTone(trajectory.status)}`}>{trajectory.status}</span>
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 line-clamp-2 min-h-[2rem]">{trajectory.intent || trajectory.description || "No intent provided."}</p>
                              <div className="flex flex-wrap items-center gap-1.5 mt-3">
                                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{trajectoryToolCalls(trajectory)} tool calls</span>
                                {judgeLabel && (
                                  <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${judgeTone(judgeLabel)}`}>judge {judgeLabel}</span>
                                )}
                                {approved && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30">skill ready</span>
                                )}
                                {trajectory.harvester?.adapter && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{humanizeName(trajectory.harvester.adapter)}</span>
                                )}
                                {(trajectory.recoverySteps?.length || 0) > 0 && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">recovery</span>
                                )}
                              </div>
                              {trajectory.finalUrl && (
                                <p className="mt-2 font-mono text-[11px] text-gray-400 dark:text-gray-500 truncate" title={trajectory.finalUrl}>{trajectory.finalUrl}</p>
                              )}
                              <div className="flex items-center justify-between mt-auto pt-3 border-t border-gray-100 dark:border-dark-border">
                                <span className="text-[11px] text-gray-400">{formatDate(trajectory.createdAt)}</span>
                                {promotable ? (
                                  <button
                                    onClick={(event) => { event.stopPropagation(); setPromoteTarget(trajectory); }}
                                    className="inline-flex items-center h-7 px-2.5 rounded-lg bg-gradient-primary text-white text-xs font-semibold"
                                    title="Promote to skill"
                                  >
                                    <FontAwesomeIcon icon={faWandMagicSparkles} className="mr-1.5 text-[10px]" />
                                    Promote
                                  </button>
                                ) : (
                                  <span className="inline-flex items-center h-7 px-2.5 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-500 dark:text-gray-400">
                                    {approved ? "Approved" : judgeLabel === "fail" ? "Failed judge" : "Review"}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      </div>
                  )}
                  {view === "trajectories" && trajectories.length === 0 && (
                    <EmptyState
                      icon={faRoute}
                      title="No trajectories yet"
                      body="Run a harvester against a task benchmark to create concrete trajectories with tool calls and observations."
                      action={<button onClick={openCreate} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faPlus} className="text-xs" />Create Capability</button>}
                    />
                  )}

                  {/* Skills */}
                  {view === "skills" && skills.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Skills</p>
                      <div className="flex flex-col gap-3">
                        {skills.map((skill) => {
                          const originLabel = skillOriginLabel(skill);
                          return (
                          <div
                            key={skill.skillId}
                            onClick={() => setDetail({ kind: "skill", item: skill })}
                            className="flex flex-col bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-soft hover:-translate-y-0.5 cursor-pointer"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="w-8 h-8 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
                                  <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
                                </span>
                                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{skill.name}</p>
                              </div>
                              <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${statusTone(skill.status)}`}>{skill.status}</span>
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 line-clamp-2 min-h-[2rem]">{skill.whenToUse || skill.description || "No description."}</p>
                            <div className="flex flex-wrap items-center gap-1.5 mt-3">
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{(skill.trajectoryIds?.length || 0)} trajectories</span>
                              {skill.riskPolicy && (
                                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
                                  <FontAwesomeIcon icon={faShieldHalved} className="mr-1 text-[9px]" />{skill.riskPolicy.replace(/_/g, " ")}
                                </span>
                              )}
                              <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${approvalTone(approvalMode(skill))}`}>
                                {approvalLabel(approvalMode(skill))}
                              </span>
                            </div>
                            {((skill.inputEntities || []).length > 0 || skill.outputEntity) && (
                              <div className="mt-2">
                                <EntityChips inputEntities={skill.inputEntities} outputEntity={skill.outputEntity} />
                              </div>
                            )}
                            {originLabel && (
                              <div className="mt-2 flex items-center gap-1.5 text-[11px] text-gray-400 dark:text-gray-500">
                                <FontAwesomeIcon icon={faTractor} className="text-[9px]" />
                                <span className="truncate">Created by {originLabel}</span>
                                {skill.harvesterRunId && (
                                  <span className="font-mono text-[10px] text-gray-300 dark:text-gray-600 truncate" title={skill.harvesterRunId}>
                                    {skill.harvesterRunId.slice(0, 8)}
                                  </span>
                                )}
                              </div>
                            )}
                            <div className="flex items-center justify-between mt-auto pt-3 border-t border-gray-100 dark:border-dark-border">
                              <span className="text-[11px] text-gray-400">{formatDate(skill.createdAt)}</span>
                              <button onClick={(event) => { event.stopPropagation(); navigate("/agents"); }} className="inline-flex items-center h-7 px-2.5 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border">
                                <FontAwesomeIcon icon={faRobot} className="mr-1.5 text-[10px]" />
                                Use in agents
                              </button>
                            </div>
                          </div>
                          );
                        })}
                      </div>
                      </div>
                  )}
                  {view === "skills" && skills.length === 0 && (
                    <EmptyState
                      icon={faWandMagicSparkles}
                      title="No skills yet"
                      body="Promote a reliable Skill Candidate, or author a reusable skill manually once that flow is enabled."
                      action={<button onClick={() => setView("trajectories")} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faRoute} className="text-xs" />View Trajectories</button>}
                    />
                  )}

                  {/* Harvester runs */}
                  {view === "runs" && (
                    runs.length === 0 ? (
                      <EmptyState
                        icon={faClockRotateLeft}
                        title="No harvester runs yet"
                        body={trajectories.length > 0
                          ? "There are trajectories, but no UI harvester run record. This can happen when a benchmark was seeded or harvested from a script."
                          : "Runs appear here when a harvester executes a benchmark and produces trajectories."}
                        action={<button onClick={openCreate} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faTractor} className="text-xs" />Run Harvester</button>}
                      />
                    ) : (
                      <div className="space-y-3">
                        {runs.map((run) => (
                          <div key={run.harvesterRunId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-soft">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                                  <FontAwesomeIcon icon={run.status === "running" ? faSpinner : faClockRotateLeft} className={`text-xs ${run.status === "running" ? "animate-spin" : ""}`} />
                                </span>
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{run.connectorName || "Connector"}</p>
                                  <p className="text-[11px] text-gray-400">
                                    {run.runKind === "tool_publication" ? "default tools published" : run.harvesterType || run.surface || "harvester"} · {formatDate(run.createdAt)}
                                  </p>
                                </div>
                              </div>
                              <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${statusTone(run.status)}`}>{run.status}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-1.5 mt-3">
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{run.discoveredTools} tools</span>
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{run.generatedTrajectories} trajectories</span>
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{run.generatedSkills} skills</span>
                            </div>
                            {run.errors && run.errors.length > 0 && (
                              <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                                <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-[10px]" />
                                <span className="flex-1">{run.errors.join(" · ")}</span>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {promoteTarget && (
        <PromoteModal
          trajectory={promoteTarget}
          promoting={promoting}
          onClose={() => setPromoteTarget(null)}
          onPromote={promoteTrajectory}
        />
      )}
      {detail && (
        <CapabilityDetailModal
          detail={detail}
          toolsByName={toolsByName}
          trajectoriesById={trajectoriesById}
          connectorsById={connectorsById}
          userEmail={user.email}
          onReload={loadCapabilities}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

function EmptyState({ icon, title, body, action }: { icon: typeof faWrench; title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
      <span className="inline-flex w-14 h-14 rounded-2xl bg-primary/10 items-center justify-center mb-4 text-primary">
        <FontAwesomeIcon icon={icon} className="text-xl" />
      </span>
      <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">{title}</p>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-5">{body}</p>
      {action}
    </div>
  );
}
