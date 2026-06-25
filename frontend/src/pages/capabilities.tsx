import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
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
  ApprovalRequest,
  Artifact,
  CapabilityGraph,
  CompanySkill,
  CompanyTool,
  CompanyTrajectory,
  Connector,
  EvalItem,
  EvalRun,
  HarvesterRun,
  SessionItem,
  WorkItem,
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

type RegressionSummary = {
  evalCount: number;
  totalRuns: number;
  passCount: number;
  failCount: number;
  pendingCount: number;
  latestLabel: "pass" | "fail" | "pending" | "";
  latestCreatedAt?: string;
};

type ConnectorBenchmarkSpec = {
  key: string;
  name: string;
  description: string;
  connectorTypes: string[];
  runtimeType: string;
  tasks: Array<{
    key: string;
    name: string;
    expectedTools: string[];
    expectedArtifacts: string[];
    requiresApproval: boolean;
    requiresBrowser: boolean;
    runtimeExpectation: string;
  }>;
};

type ConnectorAuditRow = {
  benchmark: string;
  status: string;
  connectorId?: string;
  connectorName?: string;
  connectorType?: string;
  connectorStatus?: string;
  taskKeys?: string[];
  live?: { passed: number; total: number; failed: number };
  withSkill?: { passed: number; total: number; failed: number };
  harvested?: number;
  approvedSkills?: number;
  reason?: string;
};

type ConnectorAuditReport = {
  summary: { pass: number; blocked: number; missing: number; fail: number; total: number };
  rows: ConnectorAuditRow[];
};

function isViewKey(value?: string | null): value is ViewKey {
  return value === "tools" || value === "trajectories" || value === "skills" || value === "runs";
}

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

function regressionTone(label?: string) {
  if (label === "pass") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (label === "fail") return "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30";
  if (label === "pending") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function connectorAuditTone(status?: string) {
  const value = (status || "").toLowerCase();
  if (value === "pass") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (value === "fail") return "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30";
  if (value === "blocked" || value === "missing") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
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

function synthesisTone(status?: string) {
  if ((status || "").toLowerCase() === "ready") {
    return "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30";
  }
  return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
}

function graphSignalTone(tone: "critical" | "warning" | "neutral") {
  if (tone === "critical") return "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300";
  return "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300";
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

function runtimePolicyLabel(skill: CompanySkill) {
  const policy = skill.runtimePolicy;
  if (!policy) return skill.riskPolicy ? skill.riskPolicy.replace(/_/g, " ") : "runtime policy";
  const approvals = policy.approvalRequiredFor?.length ? `approval: ${policy.approvalRequiredFor.join("/")}` : "approval: none";
  return `${policy.runtimeClass || "api"} · ${policy.approvalMode || "auto"} · ${approvals}`;
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

function skillPromotionLabel(skill: CompanySkill) {
  return humanizeName(skill.promotionStatus || skill.status || "draft");
}

function hardeningTone(state?: string) {
  const value = (state || "").toLowerCase();
  if (value === "hardened") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (value === "drafting") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function hardeningLabel(skill: CompanySkill) {
  const status = skill.hardeningStatus;
  if (!status) return "hardening unknown";
  const score = typeof status.score === "number" ? `${Math.round(status.score * 100)}%` : null;
  return score ? `hardening ${score}` : `hardening ${humanizeName(status.state || "unknown")}`;
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

function parseCommaSeparated(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function matchesEntityName(value: string | undefined, entityFilter: string) {
  return Boolean(value && value.trim().toLowerCase() === entityFilter.trim().toLowerCase());
}

const RISK_POLICIES = [
  { value: "human_approval_for_writes", label: "Human approval for writes" },
  { value: "human_approval_always", label: "Human approval always" },
  { value: "autonomous", label: "Fully autonomous" },
];

const SKILL_STATUSES = [
  { value: "draft", label: "Draft" },
  { value: "ready", label: "Ready" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
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

function CoverageCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  );
}

function CapabilityRuntimeSignals({
  sessionsCount,
  approvalsCount,
  pendingApprovalsCount = 0,
  artifactsCount,
}: {
  sessionsCount: number;
  approvalsCount: number;
  pendingApprovalsCount?: number;
  artifactsCount: number;
}) {
  if (sessionsCount === 0 && approvalsCount === 0 && artifactsCount === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      {sessionsCount > 0 && (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border">
          {sessionsCount} {sessionsCount === 1 ? "session" : "sessions"}
        </span>
      )}
      {approvalsCount > 0 && (
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
          pendingApprovalsCount > 0
            ? "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30"
            : "bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border"
        }`}>
          {approvalsCount} approvals{pendingApprovalsCount > 0 ? ` · ${pendingApprovalsCount} pending` : ""}
        </span>
      )}
      {artifactsCount > 0 && (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30">
          {artifactsCount} {artifactsCount === 1 ? "artifact" : "artifacts"}
        </span>
      )}
    </div>
  );
}

function formatRuntimeDate(value?: string | Date) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function latestActivityTimestamp(values: Array<string | Date | undefined>) {
  let latest = 0;
  for (const value of values) {
    if (!value) continue;
    const stamp = new Date(value).getTime();
    if (!Number.isNaN(stamp) && stamp > latest) latest = stamp;
  }
  return latest > 0 ? new Date(latest).toISOString() : "";
}

function stageTone(stage: "published" | "ready" | "needs_review" | "needs_harvest") {
  if (stage === "published") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (stage === "ready") return "bg-primary/10 text-primary border-primary/30";
  if (stage === "needs_review") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function stageLabel(stage: "published" | "ready" | "needs_review" | "needs_harvest") {
  if (stage === "published") return "Published";
  if (stage === "ready") return "Ready to promote";
  if (stage === "needs_review") return "Needs review";
  return "Needs harvest";
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
  onPromote: (payload: { name: string; whenToUse: string; instructions: string; preconditions: string[]; expectedArtifacts: string[]; riskPolicy: string }) => void;
  promoting: boolean;
}) {
  const [name, setName] = useState(trajectory.name || "");
  const [whenToUse, setWhenToUse] = useState(trajectory.intent || trajectory.description || "");
  const [instructions, setInstructions] = useState(trajectory.description || trajectory.intent || "");
  const [preconditions, setPreconditions] = useState("");
  const [expectedArtifacts, setExpectedArtifacts] = useState("");
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
          A skill is a reusable capability your agents can call. It wraps this trajectory with activation guidance, reusable instructions and governance.
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
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Instructions</span>
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={4} className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" placeholder="Reusable playbook the runtime should follow after matching this skill." />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Preconditions</span>
            <input value={preconditions} onChange={(e) => setPreconditions(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="Identity verified, claim exists, customer email known" />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Expected artifacts</span>
            <input value={expectedArtifacts} onChange={(e) => setExpectedArtifacts(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="draft_email, case_summary" />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Risk policy</span>
            <SelectDropdown value={riskPolicy} onChange={setRiskPolicy} options={RISK_POLICIES} />
          </label>
        </div>
        <button
          onClick={() => onPromote({
            name: name.trim() || trajectory.name,
            whenToUse: whenToUse.trim(),
            instructions: instructions.trim(),
            preconditions: parseCommaSeparated(preconditions),
            expectedArtifacts: parseCommaSeparated(expectedArtifacts),
            riskPolicy,
          })}
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
  trajectories,
  trajectoriesById,
  connectorsById,
  benchmarkNamesById,
  regression,
  lineage,
  runtimeUsage,
  userEmail,
  onOpenSession,
  onOpenApprovals,
  onOpenArtifacts,
  onOpenWork,
  onOpenRuntime,
  onOpenCapability,
  onOpenBenchmarkOps,
  onReload,
  onClose,
}: {
  detail: Exclude<CapabilityDetail, null>;
  toolsByName: Map<string, CompanyTool>;
  trajectories: CompanyTrajectory[];
  trajectoriesById: Map<string, CompanyTrajectory>;
  connectorsById: Map<string, Connector>;
  benchmarkNamesById: Map<string, string>;
  regression: {
    bySkillId: Map<string, RegressionSummary>;
    byTrajectoryId: Map<string, RegressionSummary>;
  };
  lineage: {
    trajectoryCountByToolId: Map<string, number>;
    skillCountByToolId: Map<string, number>;
    skillCountByTrajectoryId: Map<string, number>;
  };
  runtimeUsage: {
    sessions: SessionItem[];
    approvals: ApprovalRequest[];
    artifacts: Artifact[];
    workItems: WorkItem[];
  };
  userEmail: string;
  onOpenSession: (sessionId: string) => void;
  onOpenApprovals: (params: { sessionId?: string; skillId?: string; trajectoryId?: string; toolId?: string }) => void;
  onOpenArtifacts: (params: { sessionId?: string; skillId?: string; trajectoryId?: string; toolId?: string }) => void;
  onOpenWork: (params: { sessionId?: string; skillId?: string; trajectoryId?: string; toolId?: string; workItemId?: string }) => void;
  onOpenRuntime: (params: { skillId?: string; sessionIds?: string[] }) => void;
  onOpenCapability: (next: Exclude<CapabilityDetail, null>) => void;
  onOpenBenchmarkOps: (params: { mode: "benchmarks" | "runs"; benchmarkId?: string }) => void;
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
  const [skillName, setSkillName] = useState(isSkill ? detail.item.name || "" : "");
  const [skillDescription, setSkillDescription] = useState(isSkill ? detail.item.description || "" : "");
  const [skillWhenToUse, setSkillWhenToUse] = useState(isSkill ? detail.item.whenToUse || "" : "");
  const [skillInstructions, setSkillInstructions] = useState(isSkill ? detail.item.instructions || "" : "");
  const [skillRiskPolicy, setSkillRiskPolicy] = useState(isSkill ? detail.item.riskPolicy || RISK_POLICIES[0].value : RISK_POLICIES[0].value);
  const [skillStatus, setSkillStatus] = useState(isSkill ? detail.item.status || "draft" : "draft");
  const [skillInputEntities, setSkillInputEntities] = useState(isSkill ? (detail.item.inputEntities || []).join(", ") : "");
  const [skillOutputEntity, setSkillOutputEntity] = useState(isSkill ? detail.item.outputEntity || "" : "");
  const [skillPreconditions, setSkillPreconditions] = useState(isSkill ? (detail.item.preconditions || []).join(", ") : "");
  const [skillExpectedArtifacts, setSkillExpectedArtifacts] = useState(isSkill ? (detail.item.expectedArtifacts || []).join(", ") : "");
  const [selectedTrajectoryIds, setSelectedTrajectoryIds] = useState<string[]>(isSkill ? detail.item.trajectoryIds || [] : []);
  const title = isTool ? detail.item.name : detail.item.name || (isTrajectory ? detail.item.trajectoryId : detail.item.skillId);
  const icon = isTool ? faWrench : isTrajectory ? faRoute : faWandMagicSparkles;
  const kindLabel = isTool ? "Atomic action" : isTrajectory ? "Concrete attempt" : "Reusable procedure";
  const linkedTrajectory = isSkill ? (detail.item.trajectoryIds || []).map((id) => trajectoriesById.get(id)).find(Boolean) : null;
  const calls = isTrajectory ? trajectoryToolCallList(detail.item) : linkedTrajectory ? trajectoryToolCallList(linkedTrajectory) : [];
  const requirements = isTool || isTrajectory || isSkill ? detail.item.runtimeRequirements : [];
  const entityItem: CompanyTool | CompanySkill | null = isTool ? detail.item : isSkill ? detail.item : null;
  const benchmarkId = isTool ? "" : detail.item.benchmarkId || linkedTrajectory?.benchmarkId || "";
  const benchmarkName = benchmarkId ? benchmarkNamesById.get(benchmarkId) || benchmarkId : "";
  const evalId = isTool ? "" : detail.item.evalId || linkedTrajectory?.evalId || "";
  const recentSessions = runtimeUsage.sessions.slice(0, 4);
  const recentApprovals = runtimeUsage.approvals.slice(0, 4);
  const recentArtifacts = runtimeUsage.artifacts.slice(0, 4);
  const recentWorkItems = runtimeUsage.workItems.slice(0, 4);
  const regressionSummary = isSkill
    ? regression.bySkillId.get(detail.item.skillId)
    : isTrajectory
      ? regression.byTrajectoryId.get(detail.item.trajectoryId)
      : null;
  const skillLatestRegression = isSkill ? detail.item.latestRegression : null;
  const hardeningStatus = isSkill ? detail.item.hardeningStatus : null;
  const hardeningChecks = hardeningStatus?.checks || {};
  const skillPackage = isSkill ? detail.item.skillPackage : null;
  const packageRegressionSuite = skillPackage?.evidence?.regressionSuite;
  const packageIoContract = skillPackage?.ioContract || skillPackage?.interface?.ioContract;
  const versionHistory = isSkill ? detail.item.versionHistory || skillPackage?.evidence?.versionHistory || [] : [];
  const hardeningChecklist = isSkill ? [
    { key: "activation", label: "Activation" },
    { key: "instructions", label: "Instructions" },
    { key: "riskPolicy", label: "Risk policy" },
    { key: "lineage", label: "Lineage" },
    { key: "regression", label: "Regression linked" },
    { key: "publishableRegression", label: "Regression passing" },
    { key: "entities", label: "Entities" },
    { key: "artifacts", label: "Artifacts" },
  ] : [];
  const publishBlockedReason = isSkill && skillStatus === "published"
    ? !regressionSummary || regressionSummary.evalCount === 0
      ? "No benchmark evidence is linked to this skill yet."
      : regressionSummary.latestLabel === "fail"
        ? "The latest benchmark-linked regression is failing."
        : regressionSummary.latestLabel !== "pass"
          ? "The latest benchmark-linked regression is still pending."
          : ""
    : "";
  const lineageSummary = isTool
    ? {
        trajectories: lineage.trajectoryCountByToolId.get(detail.item.toolId) || 0,
        skills: lineage.skillCountByToolId.get(detail.item.toolId) || 0,
      }
    : isTrajectory
      ? {
          trajectories: 1,
          skills: lineage.skillCountByTrajectoryId.get(detail.item.trajectoryId) || 0,
        }
      : {
          trajectories: (detail.item.trajectoryIds || []).length,
          skills: 1,
        };
  const capabilityGraph = useMemo(() => {
    const entities = new Set<string>();
    const tools = new Set<string>();
    const benchmarks = new Set<string>();
    const trajectories = new Set<string>();
    const skills = new Set<string>();
    const toolsById = new Map(Array.from(toolsByName.values()).map((tool) => [tool.toolId, tool]));

    const addTool = (tool?: CompanyTool | null, fallbackName?: string) => {
      if (tool) {
        tools.add(tool.name || tool.toolId);
        (tool.inputEntities || []).forEach((entity) => entities.add(entity));
        if (tool.outputEntity) entities.add(tool.outputEntity);
        return;
      }
      if (fallbackName) tools.add(fallbackName);
    };

    const addTrajectory = (trajectory?: CompanyTrajectory | null) => {
      if (!trajectory) return;
      trajectories.add(trajectory.trajectoryId);
      const relatedBenchmarkId = trajectory.benchmarkId || "";
      if (relatedBenchmarkId) benchmarks.add(benchmarkNamesById.get(relatedBenchmarkId) || relatedBenchmarkId);
      trajectoryToolCallList(trajectory).forEach((call) => {
        const normalized = call.name.startsWith("browser.") ? call.name.split(".", 2)[1] : call.name;
        addTool(toolsByName.get(call.name) || toolsByName.get(normalized), call.name);
      });
    };

    if (detail.kind === "tool") {
      addTool(detail.item);
    } else if (detail.kind === "trajectory") {
      addTrajectory(detail.item);
    } else {
      skills.add(detail.item.name || detail.item.skillId);
      (detail.item.inputEntities || []).forEach((entity) => entities.add(entity));
      if (detail.item.outputEntity) entities.add(detail.item.outputEntity);
      (detail.item.trajectoryIds || []).forEach((trajectoryId) => addTrajectory(trajectoriesById.get(trajectoryId)));
      (detail.item.toolIds || []).forEach((toolId) => addTool(toolsById.get(toolId), toolId));
      const relatedBenchmarkIds = new Set([detail.item.benchmarkId, ...(detail.item.lineage?.benchmarkIds || [])].filter(Boolean) as string[]);
      relatedBenchmarkIds.forEach((relatedBenchmarkId) => benchmarks.add(benchmarkNamesById.get(relatedBenchmarkId) || relatedBenchmarkId));
    }

    if (benchmarkName) benchmarks.add(benchmarkName);
    return {
      entities: Array.from(entities),
      tools: Array.from(tools),
      benchmarks: Array.from(benchmarks),
      trajectories: Array.from(trajectories),
      skills: Array.from(skills),
    };
  }, [benchmarkName, benchmarkNamesById, detail, toolsByName, trajectoriesById]);
  const capabilityGraphCards = [
    {
      label: "Entities",
      count: capabilityGraph.entities.length,
      items: capabilityGraph.entities,
      empty: "No entities mapped",
    },
    {
      label: "Tools",
      count: capabilityGraph.tools.length,
      items: capabilityGraph.tools,
      empty: "No tools resolved",
    },
    {
      label: "Benchmarks",
      count: capabilityGraph.benchmarks.length,
      items: capabilityGraph.benchmarks,
      empty: "No benchmark linked",
    },
    {
      label: "Trajectories",
      count: capabilityGraph.trajectories.length || lineageSummary.trajectories,
      items: capabilityGraph.trajectories,
      empty: lineageSummary.trajectories ? "Tracked by lineage counts" : "No trajectories linked",
    },
    {
      label: "Skills",
      count: capabilityGraph.skills.length || lineageSummary.skills,
      items: capabilityGraph.skills,
      empty: lineageSummary.skills ? "Tracked by lineage counts" : "No skills promoted",
    },
  ];
  const skillCandidateTrajectories = useMemo(() => {
    if (!isSkill) return [] as CompanyTrajectory[];
    return trajectories.filter((trajectory) => {
      const selected = selectedTrajectoryIds.includes(trajectory.trajectoryId);
      const sharedConnector = (trajectory.connectorIds || []).some((connectorId) => (detail.item.connectorIds || []).includes(connectorId));
      const sharedBenchmark = Boolean(detail.item.benchmarkId) && trajectory.benchmarkId === detail.item.benchmarkId;
      return selected || sharedConnector || sharedBenchmark;
    });
  }, [detail.item, isSkill, selectedTrajectoryIds, trajectories]);

  useEffect(() => {
    if (!isSkill) return;
    setSkillName(detail.item.name || "");
    setSkillDescription(detail.item.description || "");
    setSkillWhenToUse(detail.item.whenToUse || "");
    setSkillInstructions(detail.item.instructions || "");
    setSkillRiskPolicy(detail.item.riskPolicy || RISK_POLICIES[0].value);
    setSkillStatus(detail.item.status || "draft");
    setSkillInputEntities((detail.item.inputEntities || []).join(", "));
    setSkillOutputEntity(detail.item.outputEntity || "");
    setSkillPreconditions((detail.item.preconditions || []).join(", "));
    setSkillExpectedArtifacts((detail.item.expectedArtifacts || []).join(", "));
    setSelectedTrajectoryIds(detail.item.trajectoryIds || []);
  }, [detail, isSkill]);

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

  const saveSkillHardening = async () => {
    if (!isSkill || busyAction) return;
    setBusyAction("save-skill");
    setActionResult(null);
    try {
      const res = await fetch(`${apiUrl}/skills/${detail.item.skillId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: userEmail,
          name: skillName.trim(),
          description: skillDescription.trim(),
          whenToUse: skillWhenToUse.trim(),
          instructions: skillInstructions.trim(),
          preconditions: parseCommaSeparated(skillPreconditions),
          expectedArtifacts: parseCommaSeparated(skillExpectedArtifacts),
          riskPolicy: skillRiskPolicy,
          status: skillStatus,
          inputEntities: parseCommaSeparated(skillInputEntities),
          outputEntity: skillOutputEntity.trim(),
          trajectoryIds: selectedTrajectoryIds,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "Could not save skill hardening.");
      setActionResult(data);
      await onReload();
    } catch (err: any) {
      setActionResult({ success: false, error: err?.message || "Could not save skill hardening." });
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

          <section>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Factory lineage</p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Benchmark</p>
                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{benchmarkName || "Not linked yet"}</p>
                {evalId && <p className="mt-1 font-mono text-[10px] text-gray-400">{evalId}</p>}
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Trajectory coverage</p>
                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{lineageSummary.trajectories}</p>
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  {isTool ? "Trajectories linked to this action" : isSkill ? "Source trajectories behind this skill" : "Trajectory under inspection"}
                </p>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Skill coverage</p>
                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{lineageSummary.skills}</p>
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  {isTool ? "Published skills that depend on this action" : isTrajectory ? "Skills promoted from this trajectory" : "This capability is production-ready"}
                </p>
              </div>
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between gap-3 mb-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Capability graph</p>
              <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                <FontAwesomeIcon icon={faCircleNodes} className="text-[9px]" />
                entities to skills
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              {capabilityGraphCards.map((card) => (
                <div key={card.label} className="rounded-xl border border-gray-200 bg-white px-3 py-3 shadow-sm dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{card.label}</p>
                    <span className="rounded-md bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-dark-bg dark:text-gray-300">
                      {card.count}
                    </span>
                  </div>
                  <div className="mt-2 space-y-1">
                    {card.items.slice(0, 4).map((item) => (
                      <p key={item} className="truncate rounded-md bg-gray-50 px-2 py-1 font-mono text-[10px] text-gray-600 dark:bg-dark-bg dark:text-gray-300">
                        {item}
                      </p>
                    ))}
                    {card.items.length > 4 && (
                      <p className="text-[10px] text-gray-400">+{card.items.length - 4} more</p>
                    )}
                    {card.items.length === 0 && (
                      <p className="text-[11px] text-gray-400">{card.empty}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {isSkill && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Skill package</p>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Hardening</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span className={`inline-flex rounded-md border px-2 py-1 text-[11px] font-medium ${hardeningTone(hardeningStatus?.state)}`}>
                      {humanizeName(hardeningStatus?.state || "unknown")}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    {hardeningStatus?.passedChecks || 0}/{hardeningStatus?.totalChecks || hardeningChecklist.length} checks
                    {typeof hardeningStatus?.score === "number" ? ` · ${Math.round(hardeningStatus.score * 100)}%` : ""}
                  </p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Playbook steps</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{detail.item.instructions ? "Defined" : "Missing"}</p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    {detail.item.instructions ? "Reusable operator instructions are attached." : "No reusable instructions stored yet."}
                  </p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Preconditions</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{detail.item.preconditions?.length || 0}</p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Inputs or safety checks required before replay.</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Expected artifacts</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{detail.item.expectedArtifacts?.length || 0}</p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Business outputs this skill is expected to produce.</p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {hardeningChecklist.map((item) => (
                  <span
                    key={item.key}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium ${
                      hardeningChecks[item.key]
                        ? "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-300 border-green-200 dark:border-green-500/30"
                        : "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border"
                    }`}
                  >
                    <FontAwesomeIcon icon={hardeningChecks[item.key] ? faCheck : faClockRotateLeft} className="text-[9px]" />
                    {item.label}
                  </span>
                ))}
              </div>
            </section>
          )}

          {(isSkill || isTrajectory) && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Benchmark gating</p>
              {!regressionSummary || regressionSummary.evalCount === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 text-xs text-gray-400">
                  No benchmark-linked eval runs are associated with this {isSkill ? "skill" : "trajectory"} yet.
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Eval tasks</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{regressionSummary.evalCount}</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Run history</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{regressionSummary.totalRuns}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{regressionSummary.passCount} pass · {regressionSummary.failCount} fail</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Latest regression</p>
                    <div className="mt-1 flex items-center gap-2">
                      <span className={`inline-flex rounded-md border px-2 py-1 text-[11px] font-medium ${regressionTone(regressionSummary.latestLabel)}`}>
                        {regressionSummary.latestLabel || "unknown"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                      {formatDate(skillLatestRegression?.createdAt || regressionSummary.latestCreatedAt)}
                      {skillLatestRegression?.runId ? ` · ${skillLatestRegression.runId.slice(0, 8)}` : ""}
                    </p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Gate status</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                      {regressionSummary.latestLabel === "pass" ? "Ready" : regressionSummary.latestLabel === "fail" ? "Blocked" : "Pending"}
                    </p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                      {regressionSummary.latestLabel === "pass"
                        ? "Latest benchmark evidence is passing."
                        : regressionSummary.latestLabel === "fail"
                          ? "Latest benchmark evidence is failing."
                          : "Benchmark evidence has not converged yet."}
                    </p>
                  </div>
                </div>
              )}
            </section>
          )}

          {isSkill && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Skill lifecycle</p>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Version</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{detail.item.versionLabel || `v${detail.item.version || 1}`}</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Promotion</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{skillPromotionLabel(detail.item)}</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Ready at</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{formatDate(detail.item.readyAt)}</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Published at</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{formatDate(detail.item.publishedAt)}</p>
                </div>
              </div>
            </section>
          )}

          {isSkill && versionHistory.length > 0 && (
            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Version history</p>
                <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  {versionHistory.length} events
                </span>
              </div>
              <div className="space-y-2">
                {versionHistory.slice(-5).reverse().map((event, index) => (
                  <div key={`${event.versionLabel || event.version || index}-${event.createdAt || index}`} className="flex items-start justify-between gap-3 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-dark-border dark:bg-dark-bg">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {event.versionLabel || `v${event.version || "?"}`} · {(event.promotionStatus || "draft").replace(/_/g, " ")}
                      </p>
                      <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">{(event.reason || "updated").replace(/_/g, " ")}</p>
                    </div>
                    <p className="shrink-0 text-[11px] text-gray-400">{formatDate(event.createdAt)}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {isSkill && skillPackage && (
            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Package manifest</p>
                <span className="rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">
                  {skillPackage.format || "autoppia.agent_skill"}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Manifest</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">v{skillPackage.manifestVersion || 1}</p>
                  <p className="mt-1 truncate font-mono text-[10px] text-gray-400">{skillPackage.packageId || detail.item.skillId}</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Activation</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                    {skillPackage.activation?.description ? "Declared" : "Missing"}
                  </p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{skillPackage.activation?.preconditions?.length || 0} preconditions</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Regression suite</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                    {packageRegressionSuite?.publishable ? "Publishable" : "Not publishable"}
                  </p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    {(packageRegressionSuite?.benchmarkIds || []).length} benchmarks · {(packageRegressionSuite?.evalIds || []).length} evals
                  </p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">IO contract</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                    {packageIoContract?.declared ? "Declared" : "Missing"}
                  </p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    {(packageIoContract?.inputs?.entities || []).length} inputs · {(packageIoContract?.outputs?.artifacts || []).length} outputs
                  </p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Disclosure</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{skillPackage.progressiveDisclosure?.summaryFields?.length || 0} summary fields</p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{skillPackage.progressiveDisclosure?.fullFields?.join(", ") || "execution, evidence"}</p>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <JsonBlock
                  value={{
                    metadata: skillPackage.metadata || {},
                    interface: skillPackage.interface || {},
                    ioContract: packageIoContract || {},
                    policies: skillPackage.policies || {},
                  }}
                />
                <JsonBlock
                  value={{
                    execution: skillPackage.execution || {},
                    evidence: {
                      regressionSuite: packageRegressionSuite || {},
                      latestRegression: skillPackage.evidence?.latestRegression || null,
                    },
                  }}
                />
              </div>
            </section>
          )}

          {isSkill && publishBlockedReason && (
            <section>
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-500/30 dark:bg-red-500/10">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-lg bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-300">
                    <FontAwesomeIcon icon={faTriangleExclamation} className="text-[11px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-red-700 dark:text-red-200">Publish blocked by regression</p>
                    <p className="mt-1 text-xs leading-5 text-red-600 dark:text-red-300">{publishBlockedReason}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSkillStatus("ready")}
                        className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-dark-surface dark:text-red-200 dark:hover:bg-red-500/10"
                      >
                        Keep as Ready
                      </button>
                      {linkedTrajectory && (
                        <button
                          type="button"
                          onClick={() => onOpenCapability({ kind: "trajectory", item: linkedTrajectory })}
                          className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-dark-surface dark:text-red-200 dark:hover:bg-red-500/10"
                        >
                          Review source trajectory
                        </button>
                      )}
                      {benchmarkId && (
                        <>
                          <button
                            type="button"
                            onClick={() => onOpenBenchmarkOps({ mode: "benchmarks", benchmarkId })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-dark-surface dark:text-red-200 dark:hover:bg-red-500/10"
                          >
                            Open benchmark
                          </button>
                          <button
                            type="button"
                            onClick={() => onOpenBenchmarkOps({ mode: "runs", benchmarkId })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-dark-surface dark:text-red-200 dark:hover:bg-red-500/10"
                          >
                            Open recent runs
                          </button>
                        </>
                      )}
                    </div>
                    <div className="mt-3 text-[11px] leading-5 text-red-600 dark:text-red-300">
                      Next steps: get the benchmark back to `pass`, then publish this version.
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}

          <section>
            <div className="flex items-center justify-between gap-3 mb-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Runtime usage</p>
              {(recentSessions.length > 0 || recentApprovals.length > 0 || recentArtifacts.length > 0 || recentWorkItems.length > 0) && (
                <div className="flex flex-wrap items-center gap-2">
                  {recentSessions.length > 0 && (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border">
                      {runtimeUsage.sessions.length} sessions
                    </span>
                  )}
                  {recentApprovals.length > 0 && (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30">
                      {runtimeUsage.approvals.length} approvals
                    </span>
                  )}
                  {recentArtifacts.length > 0 && (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30">
                      {runtimeUsage.artifacts.length} artifacts
                    </span>
                  )}
                  {recentWorkItems.length > 0 && (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">
                      {runtimeUsage.workItems.length} jobs
                    </span>
                  )}
                </div>
              )}
            </div>
            {(isSkill || isTrajectory || isTool) && runtimeUsage.sessions.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onOpenRuntime(
                    isSkill
                      ? { skillId: detail.item.skillId }
                      : { sessionIds: runtimeUsage.sessions.map((session) => session.sessionId) },
                  )}
                  className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                >
                  Open Runtime Lab
                </button>
                <button
                  type="button"
                  onClick={() => onOpenWork({
                    skillId: isSkill ? detail.item.skillId : "",
                    trajectoryId: isTrajectory ? detail.item.trajectoryId : "",
                    toolId: isTool ? detail.item.toolId : "",
                    sessionId: runtimeUsage.sessions.length === 1 ? runtimeUsage.sessions[0]?.sessionId || "" : "",
                  })}
                  className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                >
                  Open Work
                </button>
              </div>
            )}
            {recentSessions.length === 0 && recentApprovals.length === 0 && recentArtifacts.length === 0 && recentWorkItems.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 text-xs text-gray-400">
                No runtime evidence is linked to this capability yet.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Sessions</p>
                    <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{runtimeUsage.sessions.length}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Runtime executions that used this capability.</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Approvals</p>
                    <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{runtimeUsage.approvals.length}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Approval events triggered while executing it.</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Artifacts</p>
                    <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{runtimeUsage.artifacts.length}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Business outputs from linked runtime sessions.</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Jobs</p>
                    <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{runtimeUsage.workItems.length}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">Work items whose latest execution referenced this capability.</p>
                  </div>
                </div>
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Recent sessions</p>
                  {recentSessions.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-400">
                      No session usage recorded.
                    </div>
                  ) : recentSessions.map((session) => (
                    <button
                      key={session.sessionId}
                      onClick={() => onOpenSession(session.sessionId)}
                      className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-left transition-colors hover:border-primary/30"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{session.prompt || "Runtime session"}</p>
                          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {formatRuntimeDate(session.createdAt)} · {session.agentName || session.provider || "autoppia"}
                          </p>
                        </div>
                        <span className="text-[10px] text-primary">Open</span>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Recent jobs</p>
                    {runtimeUsage.workItems.length > 0 && (
                      <button
                        onClick={() => onOpenWork({
                          skillId: isSkill ? detail.item.skillId : "",
                          trajectoryId: isTrajectory ? detail.item.trajectoryId : isSkill ? linkedTrajectory?.trajectoryId || "" : "",
                          toolId: isTool ? detail.item.toolId : "",
                        })}
                        className="text-[11px] font-semibold text-primary"
                      >
                        Open work
                      </button>
                    )}
                  </div>
                  {recentWorkItems.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-400">
                      No work evidence linked yet.
                    </div>
                  ) : recentWorkItems.map((item) => (
                    <button
                      key={item.workItemId}
                      onClick={() => onOpenWork({ workItemId: item.workItemId })}
                      className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-left transition-colors hover:border-primary/30"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{item.title || "Work item"}</p>
                          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {item.status} · {formatDate(item.updatedAt || item.createdAt)}
                          </p>
                        </div>
                        <span className="text-[10px] text-primary">Open</span>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Recent approvals</p>
                    {runtimeUsage.approvals.length > 0 && (
                      <button
                        onClick={() => onOpenApprovals({
                          skillId: isSkill ? detail.item.skillId : "",
                          trajectoryId: isTrajectory ? detail.item.trajectoryId : isSkill ? linkedTrajectory?.trajectoryId || "" : "",
                          toolId: isTool ? detail.item.toolId : "",
                        })}
                        className="text-[11px] font-semibold text-primary"
                      >
                        Open approvals
                      </button>
                    )}
                  </div>
                  {recentApprovals.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-400">
                      No approval events linked yet.
                    </div>
                  ) : recentApprovals.map((approval) => (
                    <div key={approval.approvalId} className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{approval.title || approval.toolName || "Approval"}</p>
                          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {approval.status} · {formatDate(approval.createdAt)}
                          </p>
                        </div>
                        {approval.sessionId && (
                          <button
                            onClick={() => onOpenSession(approval.sessionId || "")}
                            className="text-[10px] text-primary"
                          >
                            Session
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Recent artifacts</p>
                    {runtimeUsage.artifacts.length > 0 && (
                      <button
                        onClick={() => onOpenArtifacts({
                          skillId: isSkill ? detail.item.skillId : "",
                          trajectoryId: isTrajectory ? detail.item.trajectoryId : isSkill ? linkedTrajectory?.trajectoryId || "" : "",
                          toolId: isTool ? detail.item.toolId : "",
                          sessionId: runtimeUsage.sessions.length === 1 ? runtimeUsage.sessions[0]?.sessionId || "" : "",
                        })}
                        className="text-[11px] font-semibold text-primary"
                      >
                        Open artifacts
                      </button>
                    )}
                  </div>
                  {recentArtifacts.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-400">
                      No persisted artifacts linked yet.
                    </div>
                  ) : recentArtifacts.map((artifact) => (
                    <div key={artifact.artifactId} className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{artifact.title || "Artifact"}</p>
                          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                            {artifact.artifactType} · {formatDate(artifact.updatedAt || artifact.createdAt)}
                          </p>
                        </div>
                        {artifact.sessionId && (
                          <button
                            onClick={() => onOpenSession(artifact.sessionId || "")}
                            className="text-[10px] text-primary"
                          >
                            Session
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              </div>
            )}
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

          {isSkill && (
            <section>
              <div className="flex items-center justify-between gap-3 mb-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Runtime policy</p>
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${approvalTone((detail.item.runtimePolicy?.approvalMode as ApprovalMode) || approvalMode(detail.item))}`}>
                  {detail.item.runtimePolicy?.runtimeClass || "api"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {[
                  { label: "Approval mode", value: detail.item.runtimePolicy?.approvalMode || approvalMode(detail.item) },
                  { label: "Approval scopes", value: detail.item.runtimePolicy?.approvalRequiredFor?.join(", ") || "none" },
                  { label: "Runtime type", value: (detail.item.runtimePolicy?.runtimeType || `${detail.item.runtimePolicy?.runtimeClass || "api"}_runtime`).replace(/_/g, " ") },
                  { label: "Browser use", value: detail.item.runtimePolicy?.browserPolicy?.defaultUse || (detail.item.runtimePolicy?.browserRuntime ? "exception" : "none") },
                  { label: "Browser sandbox", value: detail.item.runtimePolicy?.browserPolicy?.requiresSandbox ? "required" : "not required" },
                  { label: "Domain restriction", value: detail.item.runtimePolicy?.browserPolicy?.restrictedByDomain ? "enabled" : "not configured" },
                  { label: "Runtime classes", value: detail.item.runtimePolicy?.runtimeTypes?.map((item) => item.replace(/_/g, " ")).join(", ") || detail.item.runtimePolicy?.runtimeClass || "api" },
                  { label: "Allowed domains", value: detail.item.runtimePolicy?.browserPolicy?.allowedDomains?.join(", ") || "none" },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{item.label}</p>
                    <p className="mt-1 truncate text-xs font-semibold text-gray-800 dark:text-gray-100">{item.value}</p>
                  </div>
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
              <section>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Tool synthesis contract</p>
                  <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${synthesisTone(detail.item.toolSynthesis?.readiness?.status)}`}>
                    {(detail.item.toolSynthesis?.readiness?.status || "needs_hardening").replace(/_/g, " ")}
                  </span>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  <div className="grid grid-cols-2 gap-2">
                    <p><span className="text-gray-400">Atomic:</span> {detail.item.toolSynthesis?.atomic ? "yes" : "unknown"}</p>
                    <p><span className="text-gray-400">Typed input:</span> {detail.item.toolSynthesis?.typedInput ? "yes" : "no"}</p>
                    <p><span className="text-gray-400">Typed output:</span> {detail.item.toolSynthesis?.typedOutput ? "yes" : "no"}</p>
                    <p><span className="text-gray-400">Approval:</span> {detail.item.toolSynthesis?.permissions?.approval || approvalMode(detail.item)}</p>
                    <p className="col-span-2"><span className="text-gray-400">Scopes:</span> {detail.item.toolSynthesis?.permissions?.scopes?.join(", ") || "not declared"}</p>
                    <p className="col-span-2"><span className="text-gray-400">Gaps:</span> {detail.item.toolSynthesis?.readiness?.gaps?.join(", ") || "none"}</p>
                  </div>
                </div>
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
              <div className="flex items-center justify-between gap-3 mb-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Skill hardening</p>
                <button
                  type="button"
                  onClick={saveSkillHardening}
                  disabled={busyAction === "save-skill"}
                  className="inline-flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white disabled:opacity-60"
                >
                  {busyAction === "save-skill" ? <FontAwesomeIcon icon={faSpinner} className="animate-spin text-[10px]" /> : <FontAwesomeIcon icon={faCheck} className="text-[10px]" />}
                  Save skill
                </button>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="block md:col-span-1">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Skill name</span>
                  <input value={skillName} onChange={(e) => setSkillName(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" />
                </label>
                <label className="block md:col-span-1">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Status</span>
                  <SelectDropdown value={skillStatus} onChange={(value) => setSkillStatus(value)} options={SKILL_STATUSES} />
                  <span className="mt-1 block text-[11px] leading-4 text-gray-400 dark:text-gray-500">
                    `Published` now requires the latest benchmark-linked eval run to pass.
                  </span>
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">When to use</span>
                  <textarea value={skillWhenToUse} onChange={(e) => setSkillWhenToUse(e.target.value)} rows={3} className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" />
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Instructions</span>
                  <textarea value={skillInstructions} onChange={(e) => setSkillInstructions(e.target.value)} rows={4} className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" placeholder="Reusable playbook the runtime should follow when this skill is matched." />
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Description</span>
                  <textarea value={skillDescription} onChange={(e) => setSkillDescription(e.target.value)} rows={3} className="w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Risk policy</span>
                  <SelectDropdown value={skillRiskPolicy} onChange={(value) => setSkillRiskPolicy(value)} options={RISK_POLICIES} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Output entity</span>
                  <input value={skillOutputEntity} onChange={(e) => setSkillOutputEntity(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="Draft email, Updated claim, Policy note..." />
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Input entities</span>
                  <input value={skillInputEntities} onChange={(e) => setSkillInputEntities(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="Policy, Customer, Claim" />
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Preconditions</span>
                  <input value={skillPreconditions} onChange={(e) => setSkillPreconditions(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="Identity verified, policy number known, claim already opened" />
                </label>
                <label className="block md:col-span-2">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Expected artifacts</span>
                  <input value={skillExpectedArtifacts} onChange={(e) => setSkillExpectedArtifacts(e.target.value)} className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="draft_email, claim_summary, policy_note" />
                </label>
              </div>
              <div className="mt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Source trajectories</p>
                {skillCandidateTrajectories.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-xs text-gray-400">
                    No related trajectories available yet. Promote or harvest more trajectories first.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {skillCandidateTrajectories.map((trajectory) => {
                      const checked = selectedTrajectoryIds.includes(trajectory.trajectoryId);
                      const benchmarkLabel = trajectory.benchmarkId ? benchmarkNamesById.get(trajectory.benchmarkId) || trajectory.benchmarkId : "";
                      return (
                        <label key={trajectory.trajectoryId} className="flex items-start gap-3 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) => {
                              setSelectedTrajectoryIds((current) => event.target.checked
                                ? Array.from(new Set([...current, trajectory.trajectoryId]))
                                : current.filter((item) => item !== trajectory.trajectoryId));
                            }}
                            className="mt-0.5 h-4 w-4 accent-primary"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-sm font-semibold text-gray-900 dark:text-white">{trajectory.name || trajectory.trajectoryId}</p>
                              <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${statusTone(trajectory.status || "")}`}>{trajectory.status || "draft"}</span>
                            </div>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{trajectory.intent || trajectory.description || "No trajectory intent."}</p>
                            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                              {benchmarkLabel && <span>{benchmarkLabel}</span>}
                              {trajectory.evalId && <span className="font-mono">{trajectory.evalId}</span>}
                              {(trajectory.toolIds || []).length > 0 && <span>{trajectory.toolIds.length} tools</span>}
                            </div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>
          )}

          {isSkill && (((detail.item.preconditions || []).length > 0) || ((detail.item.expectedArtifacts || []).length > 0) || detail.item.instructions) && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Playbook package</p>
              <div className="space-y-3">
                {detail.item.instructions && (
                  <div className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Instructions</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-700 dark:text-gray-200">{detail.item.instructions}</p>
                  </div>
                )}
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Preconditions</p>
                    {(detail.item.preconditions || []).length === 0 ? (
                      <p className="mt-2 text-xs text-gray-400">No preconditions declared yet.</p>
                    ) : (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(detail.item.preconditions || []).map((item) => (
                          <span key={item} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Expected artifacts</p>
                    {(detail.item.expectedArtifacts || []).length === 0 ? (
                      <p className="mt-2 text-xs text-gray-400">No expected artifacts declared yet.</p>
                    ) : (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(detail.item.expectedArtifacts || []).map((item) => (
                          <span key={item} className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
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

          {isSkill && detail.item.lineage && (
            <section>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Source lineage</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <JsonBlock value={{ benchmarkIds: detail.item.lineage.benchmarkIds || [], evalIds: detail.item.lineage.evalIds || [] }} />
                <JsonBlock value={{ connectorIds: detail.item.lineage.connectorIds || [], toolIds: detail.item.lineage.toolIds || [], sources: detail.item.lineage.sources || [] }} />
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
  const { kind: routeKind, id: routeId } = useParams<{ kind?: string; id?: string }>();
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [tools, setTools] = useState<CompanyTool[]>([]);
  const [trajectories, setTrajectories] = useState<CompanyTrajectory[]>([]);
  const [skills, setSkills] = useState<CompanySkill[]>([]);
  const [runs, setRuns] = useState<HarvesterRun[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [connectorBenchmarks, setConnectorBenchmarks] = useState<ConnectorBenchmarkSpec[]>([]);
  const [connectorAuditReport, setConnectorAuditReport] = useState<ConnectorAuditReport | null>(null);
  const [connectorAuditLoading, setConnectorAuditLoading] = useState(false);
  const [connectorAuditError, setConnectorAuditError] = useState("");
  const [evals, setEvals] = useState<EvalItem[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvalRun[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [backendCapabilityGraph, setBackendCapabilityGraph] = useState<CapabilityGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ViewKey>("tools");
  const [expandedToolConnectorKeys, setExpandedToolConnectorKeys] = useState<Set<string>>(new Set());
  const [promoteTarget, setPromoteTarget] = useState<CompanyTrajectory | null>(null);
  const [detail, setDetail] = useState<CapabilityDetail>(null);
  const [promoting, setPromoting] = useState(false);
  const [activeGraphNode, setActiveGraphNode] = useState("");

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
      setConnectorBenchmarks([]);
      setConnectorAuditReport(null);
      setConnectorAuditError("");
      setEvals([]);
      setEvalRuns([]);
      setSessions([]);
      setApprovals([]);
      setArtifacts([]);
      setWorkItems([]);
      setBackendCapabilityGraph(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      const connectorParams = new URLSearchParams({ email: user.email, companyId });
      const approvalParams = new URLSearchParams({ email: user.email, companyId, includeRuntime: "true", status: "" });
      const [capRes, runsRes, connectorsRes, connectorBenchmarksRes, evalsRes, evalRunsRes, sessionsRes, approvalsRes, artifactsRes, workItemsRes, graphRes] = await Promise.all([
        fetch(`${apiUrl}/companies/${companyId}/capabilities?${params.toString()}`),
        fetch(`${apiUrl}/companies/${companyId}/harvester-runs?${params.toString()}`),
        fetch(`${apiUrl}/connectors?${connectorParams.toString()}`),
        fetch(`${apiUrl}/connector-benchmarks/catalog`),
        fetch(`${apiUrl}/evals?${connectorParams.toString()}`),
        fetch(`${apiUrl}/eval-runs?${connectorParams.toString()}`),
        fetch(`${apiUrl}/sessions?${connectorParams.toString()}`),
        fetch(`${apiUrl}/approvals?${approvalParams.toString()}`),
        fetch(`${apiUrl}/companies/${companyId}/artifacts?${params.toString()}`),
        fetch(`${apiUrl}/work-items?${connectorParams.toString()}`),
        fetch(`${apiUrl}/companies/${companyId}/capability-graph?${params.toString()}`),
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
      if (connectorBenchmarksRes.ok) {
        const data = await connectorBenchmarksRes.json();
        setConnectorBenchmarks(data.benchmarks || []);
      }
      if (evalsRes.ok) {
        const data = await evalsRes.json();
        setEvals(data.evals || []);
      }
      if (evalRunsRes.ok) {
        const data = await evalRunsRes.json();
        setEvalRuns(data.runs || []);
      }
      if (sessionsRes.ok) {
        const data = await sessionsRes.json();
        setSessions(data.sessions || []);
      }
      if (approvalsRes.ok) {
        const data = await approvalsRes.json();
        setApprovals(data.approvals || []);
      }
      if (artifactsRes.ok) {
        const data = await artifactsRes.json();
        setArtifacts(data.artifacts || []);
      }
      if (workItemsRes.ok) {
        const data = await workItemsRes.json();
        setWorkItems(data.workItems || []);
      }
      if (graphRes.ok) {
        const data = await graphRes.json();
        setBackendCapabilityGraph(data.graph || null);
      } else {
        setBackendCapabilityGraph(null);
      }
    } catch (err) {
      console.error("Failed to load capabilities:", err);
      setBackendCapabilityGraph(null);
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  const runConnectorAuditMatrix = useCallback(async () => {
    if (!companyId || !user.email || connectorAuditLoading) return;
    setConnectorAuditLoading(true);
    setConnectorAuditError("");
    try {
      const res = await fetch(`${apiUrl}/connector-benchmarks/audit-matrix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, companyId, publishTools: true }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "Could not run connector benchmark matrix.");
      setConnectorAuditReport(data?.connectorAudit || null);
    } catch (err: any) {
      setConnectorAuditError(err?.message || "Could not run connector benchmark matrix.");
    } finally {
      setConnectorAuditLoading(false);
    }
  }, [companyId, connectorAuditLoading, user.email]);

  useEffect(() => {
    loadCapabilities();
  }, [loadCapabilities]);

  useEffect(() => {
    if (routeKind) return;
    const requestedView = searchParams.get("view");
    if (isViewKey(requestedView) && requestedView !== view) {
      setView(requestedView);
    }
  }, [routeKind, searchParams, view]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const setFactoryView = useCallback((nextView: ViewKey, options?: { replace?: boolean }) => {
    setView(nextView);
    if (routeKind) {
      navigate(`/capabilities?view=${nextView}`, { replace: options?.replace ?? false });
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("view", nextView);
    setSearchParams(next, { replace: options?.replace ?? false });
  }, [navigate, routeKind, searchParams, setSearchParams]);

  const customConnectors = useMemo(
    () => connectors.filter((connector) => (connector.provider || "official") === "custom"),
    [connectors],
  );
  const connectorFilter = searchParams.get("connector") || "";
  const benchmarkFilter = searchParams.get("benchmark") || "";
  const entityFilter = searchParams.get("entity") || "";

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

  const promoteTrajectory = async (payload: { name: string; whenToUse: string; instructions: string; preconditions: string[]; expectedArtifacts: string[]; riskPolicy: string }) => {
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
      setFactoryView("skills");
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
  const toolsByName = useMemo(() => new Map(tools.map((tool) => [tool.name, tool])), [tools]);
  const trajectoriesById = useMemo(() => new Map(trajectories.map((trajectory) => [trajectory.trajectoryId, trajectory])), [trajectories]);
  const skillsById = useMemo(() => new Map(skills.map((skill) => [skill.skillId, skill])), [skills]);

  const regression = useMemo(() => {
    const evalIdsByBenchmarkId = new Map<string, Set<string>>();
    for (const item of evals) {
      const benchmarkId = String(item.benchmarkId || "");
      const evalId = String(item.evalId || "");
      if (!benchmarkId || !evalId) continue;
      if (!evalIdsByBenchmarkId.has(benchmarkId)) evalIdsByBenchmarkId.set(benchmarkId, new Set());
      evalIdsByBenchmarkId.get(benchmarkId)!.add(evalId);
    }

    const summarize = (candidateEvalIds: Set<string>): RegressionSummary => {
      const relatedRuns = evalRuns
        .filter((run) => candidateEvalIds.has(String(run.evalId || "")))
        .sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime());
      const latest = relatedRuns[0];
      return {
        evalCount: candidateEvalIds.size,
        totalRuns: relatedRuns.length,
        passCount: relatedRuns.filter((run) => run.label === "pass").length,
        failCount: relatedRuns.filter((run) => run.label === "fail").length,
        pendingCount: relatedRuns.filter((run) => run.label === "pending").length,
        latestLabel: latest?.label || "",
        latestCreatedAt: latest?.createdAt,
      };
    };

    const byTrajectoryId = new Map<string, RegressionSummary>();
    for (const trajectory of trajectories) {
      const candidateEvalIds = new Set<string>();
      if (trajectory.evalId) candidateEvalIds.add(trajectory.evalId);
      if (trajectory.benchmarkId && evalIdsByBenchmarkId.has(trajectory.benchmarkId)) {
        for (const evalId of Array.from(evalIdsByBenchmarkId.get(trajectory.benchmarkId) || [])) candidateEvalIds.add(evalId);
      }
      byTrajectoryId.set(trajectory.trajectoryId, summarize(candidateEvalIds));
    }

    const bySkillId = new Map<string, RegressionSummary>();
    for (const skill of skills) {
      const candidateEvalIds = new Set<string>();
      if (skill.evalId) candidateEvalIds.add(skill.evalId);
      if (skill.benchmarkId && evalIdsByBenchmarkId.has(skill.benchmarkId)) {
        for (const evalId of Array.from(evalIdsByBenchmarkId.get(skill.benchmarkId) || [])) candidateEvalIds.add(evalId);
      }
      for (const trajectoryId of skill.trajectoryIds || []) {
        const trajectory = trajectoriesById.get(trajectoryId);
        if (!trajectory) continue;
        if (trajectory.evalId) candidateEvalIds.add(trajectory.evalId);
        if (trajectory.benchmarkId && evalIdsByBenchmarkId.has(trajectory.benchmarkId)) {
          for (const evalId of Array.from(evalIdsByBenchmarkId.get(trajectory.benchmarkId) || [])) candidateEvalIds.add(evalId);
        }
      }
      bySkillId.set(skill.skillId, summarize(candidateEvalIds));
    }

    return { bySkillId, byTrajectoryId };
  }, [evalRuns, evals, skills, trajectories, trajectoriesById]);

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
      setFactoryView("trajectories");
    } catch (err: any) {
      console.error("Failed to generate capabilities:", err);
      setGenerateError(err?.message || "Could not generate capabilities for this connector.");
    } finally {
      setGenerating(false);
    }
  };

  const connectorsById = useMemo(() => new Map(connectors.map((connector) => [connector.connectorId, connector])), [connectors]);
  const filteredConnector = useMemo(
    () => connectors.find((connector) => connector.connectorId === connectorFilter) || null,
    [connectorFilter, connectors],
  );
  const benchmarkNamesById = useMemo(() => new Map(benchmarks.map((benchmark) => [benchmark.benchmarkId, benchmark.name])), [benchmarks]);
  const filteredBenchmark = useMemo(
    () => benchmarks.find((benchmark) => benchmark.benchmarkId === benchmarkFilter) || null,
    [benchmarkFilter, benchmarks],
  );
  const filteredEntity = useMemo(() => {
    if (!entityFilter) return "";
    const candidates = new Set<string>();
    for (const tool of tools) {
      for (const entity of [...(tool.inputEntities || []), ...(tool.outputEntity ? [tool.outputEntity] : [])]) {
        if (entity) candidates.add(entity);
      }
    }
    for (const skill of skills) {
      for (const entity of [...(skill.inputEntities || []), ...(skill.outputEntity ? [skill.outputEntity] : [])]) {
        if (entity) candidates.add(entity);
      }
    }
    for (const entity of Array.from(candidates)) {
      if (entity.toLowerCase() === entityFilter.toLowerCase()) return entity;
    }
    return entityFilter;
  }, [entityFilter, skills, tools]);
  const benchmarkFilterEvalIds = useMemo(
    () => new Set((filteredBenchmark?.tasks || []).map((task) => task.evalId).filter(Boolean)),
    [filteredBenchmark],
  );
  const benchmarkScopedConnectorIds = useMemo(() => {
    if (!benchmarkFilter) return null;
    const scoped = new Set<string>();
    for (const trajectory of trajectories) {
      const matches = trajectory.benchmarkId === benchmarkFilter || (trajectory.evalId && benchmarkFilterEvalIds.has(trajectory.evalId));
      if (!matches) continue;
      for (const connectorId of trajectory.connectorIds || []) {
        if (connectorId) scoped.add(connectorId);
      }
    }
    for (const skill of skills) {
      const directMatch = skill.benchmarkId === benchmarkFilter || (skill.evalId && benchmarkFilterEvalIds.has(skill.evalId));
      const trajectoryMatch = (skill.trajectoryIds || []).some((trajectoryId) => {
        const trajectory = trajectoriesById.get(trajectoryId);
        return Boolean(trajectory && (trajectory.benchmarkId === benchmarkFilter || (trajectory.evalId && benchmarkFilterEvalIds.has(trajectory.evalId))));
      });
      if (!directMatch && !trajectoryMatch) continue;
      for (const connectorId of skill.connectorIds || []) {
        if (connectorId) scoped.add(connectorId);
      }
    }
    return scoped;
  }, [benchmarkFilter, benchmarkFilterEvalIds, skills, trajectories, trajectoriesById]);
  const filteredTools = useMemo(
    () => tools.filter((tool) => {
      if (connectorFilter && tool.connectorId !== connectorFilter) return false;
      const benchmarkMatch = !benchmarkScopedConnectorIds || benchmarkScopedConnectorIds.has(tool.connectorId);
      if (!benchmarkMatch) return false;
      if (!entityFilter) return true;
      return [...(tool.inputEntities || []), ...(tool.outputEntity ? [tool.outputEntity] : [])]
        .some((entity) => matchesEntityName(entity, entityFilter));
    }),
    [benchmarkScopedConnectorIds, connectorFilter, entityFilter, tools],
  );
  const filteredTrajectories = useMemo(
    () => trajectories.filter((trajectory) => {
      if (connectorFilter && !(trajectory.connectorIds || []).includes(connectorFilter)) return false;
      if (benchmarkFilter && !(trajectory.benchmarkId === benchmarkFilter || (trajectory.evalId && benchmarkFilterEvalIds.has(trajectory.evalId)))) return false;
      if (!entityFilter) return true;
      const toolEntityMatch = (trajectory.toolIds || []).some((toolId) => {
        const tool = tools.find((item) => item.toolId === toolId);
        return Boolean(tool && [...(tool.inputEntities || []), ...(tool.outputEntity ? [tool.outputEntity] : [])].some((entity) => matchesEntityName(entity, entityFilter)));
      });
      if (toolEntityMatch) return true;
      return skills.some((skill) =>
        (skill.trajectoryIds || []).includes(trajectory.trajectoryId)
        && [...(skill.inputEntities || []), ...(skill.outputEntity ? [skill.outputEntity] : [])].some((entity) => matchesEntityName(entity, entityFilter)),
      );
    }),
    [benchmarkFilter, benchmarkFilterEvalIds, connectorFilter, entityFilter, skills, tools, trajectories],
  );
  const filteredSkills = useMemo(
    () => skills.filter((skill) => {
      if (connectorFilter && !(skill.connectorIds || []).includes(connectorFilter)) return false;
      const benchmarkMatch = !benchmarkFilter
        || skill.benchmarkId === benchmarkFilter
        || (skill.evalId && benchmarkFilterEvalIds.has(skill.evalId))
        || (skill.trajectoryIds || []).some((trajectoryId) => {
        const trajectory = trajectoriesById.get(trajectoryId);
        return Boolean(trajectory && (trajectory.benchmarkId === benchmarkFilter || (trajectory.evalId && benchmarkFilterEvalIds.has(trajectory.evalId))));
      });
      if (!benchmarkMatch) return false;
      if (!entityFilter) return true;
      return [...(skill.inputEntities || []), ...(skill.outputEntity ? [skill.outputEntity] : [])]
        .some((entity) => matchesEntityName(entity, entityFilter));
    }),
    [benchmarkFilter, benchmarkFilterEvalIds, connectorFilter, entityFilter, skills, trajectoriesById],
  );
  const filteredRuns = useMemo(
    () => runs.filter((run) => {
      if (connectorFilter && run.connectorId !== connectorFilter) return false;
      if (benchmarkFilter && !(run.benchmarkId === benchmarkFilter || (run.evalId && benchmarkFilterEvalIds.has(run.evalId)))) return false;
      if (!entityFilter) return true;
      return filteredTools.some((tool) => tool.connectorId === run.connectorId)
        || filteredSkills.some((skill) => (skill.connectorIds || []).includes(run.connectorId));
    }),
    [benchmarkFilter, benchmarkFilterEvalIds, connectorFilter, entityFilter, filteredSkills, filteredTools, runs],
  );
  const toolsByConnector = useMemo(() => {
    const groups = new Map<string, { connectorKey: string; connectorName: string; tools: CompanyTool[] }>();
    for (const tool of filteredTools) {
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
  }, [connectorsById, filteredTools]);

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

  const toolsCount = filteredTools.length;
  const skillTrajectoryIds = useMemo(() => new Set(filteredSkills.flatMap((skill) => skill.trajectoryIds || [])), [filteredSkills]);
  const runtimeUsage = useMemo(() => {
    const sessionsBySkillId = new Map<string, SessionItem[]>();
    for (const session of sessions) {
      const skillId = String(session.matchedSkillId || "");
      if (!skillId) continue;
      if (!sessionsBySkillId.has(skillId)) sessionsBySkillId.set(skillId, []);
      sessionsBySkillId.get(skillId)!.push(session);
    }

    const approvalsBySkillId = new Map<string, ApprovalRequest[]>();
    const approvalsByTrajectoryId = new Map<string, ApprovalRequest[]>();
    const approvalsByToolId = new Map<string, ApprovalRequest[]>();
    for (const approval of approvals) {
      const skillId = String(approval.metadata?.skillId || "");
      const trajectoryId = String(approval.metadata?.trajectoryId || "");
      const toolId = String(approval.metadata?.toolId || "");
      if (skillId) {
        if (!approvalsBySkillId.has(skillId)) approvalsBySkillId.set(skillId, []);
        approvalsBySkillId.get(skillId)!.push(approval);
      }
      if (trajectoryId) {
        if (!approvalsByTrajectoryId.has(trajectoryId)) approvalsByTrajectoryId.set(trajectoryId, []);
        approvalsByTrajectoryId.get(trajectoryId)!.push(approval);
      }
      if (toolId) {
        if (!approvalsByToolId.has(toolId)) approvalsByToolId.set(toolId, []);
        approvalsByToolId.get(toolId)!.push(approval);
      }
    }

    const sessionsByTrajectoryId = new Map<string, SessionItem[]>();
    const sessionsByToolId = new Map<string, SessionItem[]>();
    const workItemsBySkillId = new Map<string, WorkItem[]>();
    const workItemsByTrajectoryId = new Map<string, WorkItem[]>();
    const workItemsByToolId = new Map<string, WorkItem[]>();
    const artifactsBySkillId = new Map<string, Artifact[]>();
    const artifactsByTrajectoryId = new Map<string, Artifact[]>();
    const artifactsByToolId = new Map<string, Artifact[]>();
    const artifactsBySessionId = new Map<string, Artifact[]>();
    for (const artifact of artifacts) {
      const sessionId = String(artifact.sessionId || "");
      if (sessionId) {
        if (!artifactsBySessionId.has(sessionId)) artifactsBySessionId.set(sessionId, []);
        artifactsBySessionId.get(sessionId)!.push(artifact);
      }
      const skillId = String(artifact.metadata?.skillId || "");
      const trajectoryId = String(artifact.metadata?.trajectoryId || "");
      const toolId = String(artifact.metadata?.toolId || "");
      if (skillId) {
        if (!artifactsBySkillId.has(skillId)) artifactsBySkillId.set(skillId, []);
        artifactsBySkillId.get(skillId)!.push(artifact);
      }
      if (trajectoryId) {
        if (!artifactsByTrajectoryId.has(trajectoryId)) artifactsByTrajectoryId.set(trajectoryId, []);
        artifactsByTrajectoryId.get(trajectoryId)!.push(artifact);
      }
      if (toolId) {
        if (!artifactsByToolId.has(toolId)) artifactsByToolId.set(toolId, []);
        artifactsByToolId.get(toolId)!.push(artifact);
      }
    }
    for (const item of workItems) {
      for (const skillId of item.operational?.latestMatchedSkillIds || []) {
        if (!workItemsBySkillId.has(skillId)) workItemsBySkillId.set(skillId, []);
        workItemsBySkillId.get(skillId)!.push(item);
      }
      for (const trajectoryId of item.operational?.latestMatchedTrajectoryIds || []) {
        if (!workItemsByTrajectoryId.has(trajectoryId)) workItemsByTrajectoryId.set(trajectoryId, []);
        workItemsByTrajectoryId.get(trajectoryId)!.push(item);
      }
      for (const toolId of item.operational?.latestToolIds || []) {
        if (!workItemsByToolId.has(toolId)) workItemsByToolId.set(toolId, []);
        workItemsByToolId.get(toolId)!.push(item);
      }
    }
    for (const trajectory of trajectories) {
      const linkedSessions = skills
        .filter((skill) => (skill.trajectoryIds || []).includes(trajectory.trajectoryId))
        .flatMap((skill) => sessionsBySkillId.get(skill.skillId) || []);
      if (linkedSessions.length > 0) {
        sessionsByTrajectoryId.set(trajectory.trajectoryId, Array.from(new Map(linkedSessions.map((session) => [session.sessionId, session])).values()));
      }
    }
    for (const tool of tools) {
      const linkedSkillIds = skills
        .filter((skill) => (skill.toolIds || []).includes(tool.toolId))
        .map((skill) => skill.skillId);
      const linkedSessions = linkedSkillIds.flatMap((skillId) => sessionsBySkillId.get(skillId) || []);
      if (linkedSessions.length > 0) {
        sessionsByToolId.set(tool.toolId, Array.from(new Map(linkedSessions.map((session) => [session.sessionId, session])).values()));
      }
    }

    return {
      sessionsBySkillId,
      sessionsByTrajectoryId,
      sessionsByToolId,
      approvalsBySkillId,
      approvalsByTrajectoryId,
      approvalsByToolId,
      workItemsBySkillId,
      workItemsByTrajectoryId,
      workItemsByToolId,
      artifactsBySkillId,
      artifactsByTrajectoryId,
      artifactsByToolId,
      artifactsBySessionId,
    };
  }, [approvals, artifacts, sessions, skills, tools, trajectories, workItems]);

  const mergeArtifacts = useCallback((directArtifacts: Artifact[], sessionItems: SessionItem[]) => {
    return Array.from(new Map([
      ...directArtifacts,
      ...sessionItems.flatMap((session) => runtimeUsage.artifactsBySessionId.get(session.sessionId) || []),
    ].map((artifact) => [artifact.artifactId, artifact])).values());
  }, [runtimeUsage.artifactsBySessionId]);

  const openCapabilityRoute = useCallback((path: string) => {
    const suffix = searchParams.toString();
    navigate(suffix ? `${path}?${suffix}` : path);
  }, [navigate, searchParams]);

  const openCapabilityDetail = useCallback((next: Exclude<CapabilityDetail, null>) => {
    const path = next.kind === "tool"
      ? `/capabilities/tool/${next.item.toolId}`
      : next.kind === "trajectory"
        ? `/capabilities/trajectory/${next.item.trajectoryId}`
        : `/capabilities/skill/${next.item.skillId}`;
    openCapabilityRoute(path);
  }, [openCapabilityRoute]);

  const openCapabilityByRef = useCallback((kind: "trajectory" | "skill", id: string) => {
    if (kind === "trajectory") {
      const item = trajectoriesById.get(id);
      if (item) {
        openCapabilityDetail({ kind: "trajectory", item });
        return;
      }
      openCapabilityRoute(`/capabilities/trajectory/${id}`);
      return;
    }
    const item = skillsById.get(id);
    if (item) {
      openCapabilityDetail({ kind: "skill", item });
      return;
    }
    openCapabilityRoute(`/capabilities/skill/${id}`);
  }, [openCapabilityDetail, openCapabilityRoute, skillsById, trajectoriesById]);

  const openScopedApprovals = useCallback((params: { skillId?: string; trajectoryId?: string; toolId?: string }) => {
    const next = new URLSearchParams({ status: "all" });
    if (params.skillId) next.set("skillId", params.skillId);
    if (params.trajectoryId) next.set("trajectoryId", params.trajectoryId);
    if (params.toolId) next.set("toolId", params.toolId);
    navigate(`/approvals?${next.toString()}`);
  }, [navigate]);

  const openScopedArtifacts = useCallback((params: { skillId?: string; trajectoryId?: string; toolId?: string; sessionId?: string }) => {
    const next = new URLSearchParams();
    if (params.skillId) next.set("skillId", params.skillId);
    if (params.trajectoryId) next.set("trajectoryId", params.trajectoryId);
    if (params.toolId) next.set("toolId", params.toolId);
    if (params.sessionId) next.set("sessionId", params.sessionId);
    navigate(`/artifacts${next.toString() ? `?${next.toString()}` : ""}`);
  }, [navigate]);

  const openScopedWork = useCallback((params: { skillId?: string; trajectoryId?: string; toolId?: string; sessionId?: string }) => {
    const next = new URLSearchParams();
    if (params.skillId) next.set("skillId", params.skillId);
    if (params.trajectoryId) next.set("trajectoryId", params.trajectoryId);
    if (params.toolId) next.set("toolId", params.toolId);
    if (params.sessionId) next.set("sessionId", params.sessionId);
    navigate(`/work${next.toString() ? `?${next.toString()}` : ""}`);
  }, [navigate]);

  const openScopedRuntime = useCallback((params: { skillId?: string; sessionIds?: string[] }) => {
    const next = new URLSearchParams();
    if (params.skillId) next.set("skillId", params.skillId);
    if (params.sessionIds && params.sessionIds.length > 0) next.set("sessionIds", params.sessionIds.join(","));
    navigate(`/runtime${next.toString() ? `?${next.toString()}` : ""}`);
  }, [navigate]);

  const setFactoryScope = useCallback((options: { view?: ViewKey; connectorId?: string; benchmarkId?: string; entityId?: string; replace?: boolean }) => {
    const next = new URLSearchParams(searchParams);
    if (options.view) next.set("view", options.view);
    if (options.connectorId) next.set("connector", options.connectorId);
    else if (options.connectorId === "") next.delete("connector");
    if (options.benchmarkId) next.set("benchmark", options.benchmarkId);
    else if (options.benchmarkId === "") next.delete("benchmark");
    if (options.entityId) next.set("entity", options.entityId);
    else if (options.entityId === "") next.delete("entity");
    if (routeKind) {
      navigate(`/capabilities?${next.toString()}`, { replace: options.replace ?? false });
      return;
    }
    if (options.view) setView(options.view);
    setSearchParams(next, { replace: options.replace ?? false });
  }, [navigate, routeKind, searchParams, setSearchParams]);

  useEffect(() => {
    if (!routeKind || !routeId) {
      setDetail(null);
      return;
    }
    if (routeKind === "tool") {
      const found = tools.find((item) => item.toolId === routeId);
      if (found) {
        setView("tools");
        setDetail({ kind: "tool", item: found });
        return;
      }
    }
    if (routeKind === "trajectory") {
      const found = trajectories.find((item) => item.trajectoryId === routeId);
      if (found) {
        setView("trajectories");
        setDetail({ kind: "trajectory", item: found });
        return;
      }
    }
    if (routeKind === "skill") {
      const found = skills.find((item) => item.skillId === routeId);
      if (found) {
        setView("skills");
        setDetail({ kind: "skill", item: found });
        return;
      }
    }
    setDetail(null);
  }, [routeId, routeKind, skills, tools, trajectories]);
  // Skill candidates are not a separate artifact. They are trajectories that
  // passed judging and have not yet been promoted into a reusable skill.
  const skillCandidates = useMemo(
    () => filteredTrajectories.filter((trajectory) => {
      const status = (trajectory.status || "").toLowerCase();
      return status === "harvested" && trajectoryJudgeLabel(trajectory) === "pass" && !skillTrajectoryIds.has(trajectory.trajectoryId);
    }),
    [filteredTrajectories, skillTrajectoryIds],
  );
  const sortedTrajectories = useMemo(
    () => [...filteredTrajectories].sort((a, b) => {
      const aApproved = skillTrajectoryIds.has(a.trajectoryId) || (a.status || "").toLowerCase() === "approved";
      const bApproved = skillTrajectoryIds.has(b.trajectoryId) || (b.status || "").toLowerCase() === "approved";
      if (aApproved !== bApproved) return aApproved ? -1 : 1;
      return new Date(b.updatedAt || b.createdAt || 0).getTime() - new Date(a.updatedAt || a.createdAt || 0).getTime();
    }),
    [filteredTrajectories, skillTrajectoryIds],
  );
  const lineage = useMemo(() => {
    const trajectoryCountByToolId = new Map<string, number>();
    const skillCountByToolId = new Map<string, number>();
    const skillCountByTrajectoryId = new Map<string, number>();

    for (const trajectory of trajectories) {
      const toolIds = new Set<string>();
      for (const toolId of trajectory.toolIds || []) {
        if (toolId) toolIds.add(toolId);
      }
      for (const call of trajectoryToolCallList(trajectory)) {
        const normalized = call.name.startsWith("browser.") ? call.name.split(".", 2)[1] : call.name;
        const tool = toolsByName.get(call.name) || toolsByName.get(normalized);
        if (tool?.toolId) toolIds.add(tool.toolId);
      }
      for (const toolId of Array.from(toolIds)) {
        trajectoryCountByToolId.set(toolId, (trajectoryCountByToolId.get(toolId) || 0) + 1);
      }
    }

    for (const skill of skills) {
      const toolIds = new Set<string>((skill.toolIds || []).filter(Boolean));
      for (const trajectoryId of skill.trajectoryIds || []) {
        skillCountByTrajectoryId.set(trajectoryId, (skillCountByTrajectoryId.get(trajectoryId) || 0) + 1);
        const trajectory = trajectoriesById.get(trajectoryId);
        if (!trajectory) continue;
        for (const toolId of trajectory.toolIds || []) {
          if (toolId) toolIds.add(toolId);
        }
        for (const call of trajectoryToolCallList(trajectory)) {
          const normalized = call.name.startsWith("browser.") ? call.name.split(".", 2)[1] : call.name;
          const tool = toolsByName.get(call.name) || toolsByName.get(normalized);
          if (tool?.toolId) toolIds.add(tool.toolId);
        }
      }
      for (const toolId of Array.from(toolIds)) {
        skillCountByToolId.set(toolId, (skillCountByToolId.get(toolId) || 0) + 1);
      }
    }

    return { trajectoryCountByToolId, skillCountByToolId, skillCountByTrajectoryId };
  }, [skills, toolsByName, trajectories, trajectoriesById]);
  const coverage = useMemo(() => {
    const typedTools = filteredTools.filter((tool) => (tool.inputEntities || []).length > 0 || Boolean(tool.outputEntity)).length;
    const benchmarkBackedTrajectories = filteredTrajectories.filter((trajectory) => Boolean(trajectory.benchmarkId || trajectory.evalId)).length;
    const benchmarkBackedSkills = filteredSkills.filter((skill) => Boolean(skill.benchmarkId || skill.evalId || (skill.trajectoryIds || []).some((trajectoryId) => {
      const trajectory = trajectoriesById.get(trajectoryId);
      return Boolean(trajectory?.benchmarkId || trajectory?.evalId);
    }))).length;
    const regressionPassingSkills = filteredSkills.filter((skill) => regression.bySkillId.get(skill.skillId)?.latestLabel === "pass").length;
    return {
      typedTools,
      benchmarkBackedTrajectories,
      benchmarkBackedSkills,
      regressionPassingSkills,
      promotableTrajectories: skillCandidates.length,
    };
  }, [filteredSkills, filteredTools, filteredTrajectories, regression.bySkillId, skillCandidates.length, trajectoriesById]);
  const backendGraphStats = useMemo(() => {
    const coverage = backendCapabilityGraph?.coverage || {};
    return {
      nodeCount: backendCapabilityGraph?.nodes?.length || 0,
      edgeCount: backendCapabilityGraph?.edges?.length || 0,
      indexedResources: coverage.resources?.indexed || 0,
      totalResources: coverage.resources?.total || 0,
      citableResources: coverage.resources?.citable || 0,
      resourcesLinked: Boolean(
        coverage.resources?.linkedVectorStores
        || coverage.resources?.linkedToConnectors
        || coverage.resources?.linkedToTools
        || coverage.resources?.linkedToTasks
        || coverage.resources?.linkedToSkills,
      ),
      governedTools: coverage.tools?.governed || 0,
      totalTools: coverage.tools?.total || 0,
      taskContracts: coverage.benchmarks?.tasksWithContracts || 0,
      totalTasks: coverage.benchmarks?.tasks || 0,
      reusableSkills: coverage.skills?.reusable || 0,
      totalSkills: coverage.skills?.total || 0,
      runtimeSessions: coverage.runtime?.sessions || 0,
      runtimeApprovals: coverage.runtime?.approvals || 0,
      runtimeArtifacts: coverage.runtime?.artifacts || 0,
      runtimeLinked: Boolean(
        coverage.runtime?.linkedSessions
        || coverage.runtime?.linkedApprovals
        || coverage.runtime?.linkedArtifacts,
      ),
      workItems: coverage.work?.total || 0,
      scheduledWork: coverage.work?.scheduled || 0,
      reviewWork: coverage.work?.review || 0,
      approvalBlockedWork: coverage.work?.blockedByApproval || 0,
      workLinked: Boolean(
        coverage.work?.linkedToTasks
        || coverage.work?.linkedToRuntime
        || coverage.work?.linkedToCapabilities,
      ),
      hasPromotionPath: Boolean(
        coverage.promotionPath?.hasTaskToTrajectory
        || coverage.promotionPath?.hasTrajectoryToSkill
        || coverage.promotionPath?.hasToolToSkill,
      ),
    };
  }, [backendCapabilityGraph]);
  const connectorCoverage = useMemo(() => {
    const auditByBenchmark = new Map((connectorAuditReport?.rows || []).map((row) => [row.benchmark, row]));
    return connectorBenchmarks.map((spec) => {
      const matchingBenchmark = benchmarks.find((benchmark) => benchmark.name === spec.name);
      const connector = connectors
        .filter((item) => (spec.connectorTypes || []).includes(item.type))
        .sort((a, b) => {
          const aReady = (a.status || "").toLowerCase() === "connected" ? 0 : 1;
          const bReady = (b.status || "").toLowerCase() === "connected" ? 0 : 1;
          if (aReady !== bReady) return aReady - bReady;
          return (spec.connectorTypes || []).indexOf(a.type) - (spec.connectorTypes || []).indexOf(b.type);
        })[0];
      const toolIds = new Set(
        filteredTools
          .filter((tool) => tool.connectorId && connector?.connectorId === tool.connectorId)
          .map((tool) => tool.toolId),
      );
      const trajectories = filteredTrajectories.filter((trajectory) =>
        connector?.connectorId
          ? (trajectory.connectorIds || []).includes(connector.connectorId)
          : false,
      );
      const trajectoryIds = new Set(trajectories.map((trajectory) => trajectory.trajectoryId));
      const skills = filteredSkills.filter((skill) =>
        connector?.connectorId
          ? (skill.connectorIds || []).includes(connector.connectorId)
            || (skill.trajectoryIds || []).some((trajectoryId) => trajectoryIds.has(trajectoryId))
          : false,
      );
      const blockedSkills = skills.filter((skill) => regression.bySkillId.get(skill.skillId)?.latestLabel === "fail");
      const promotableTrajectories = trajectories.filter((trajectory) =>
        !skills.some((skill) => (skill.trajectoryIds || []).includes(trajectory.trajectoryId))
        && trajectoryJudgeLabel(trajectory) === "pass",
      );
      const audit = auditByBenchmark.get(spec.name);
      return {
        spec,
        connector,
        benchmark: matchingBenchmark || null,
        audit,
        tools: toolIds.size,
        trajectories: trajectories.length,
        skills: skills.length,
        blockedSkills: blockedSkills.length,
        regressionReady: skills.filter((skill) => regression.bySkillId.get(skill.skillId)?.latestLabel === "pass").length,
        primaryBlockedSkillId: blockedSkills[0]?.skillId || "",
        primarySkillId: skills[0]?.skillId || "",
        primaryTrajectoryId: promotableTrajectories[0]?.trajectoryId || trajectories[0]?.trajectoryId || "",
      };
    });
  }, [benchmarks, connectorAuditReport?.rows, connectorBenchmarks, connectors, filteredSkills, filteredTools, filteredTrajectories, regression.bySkillId]);
  const factoryGaps = useMemo(() => {
    const failedRuns = filteredRuns.filter((run) => ["failed", "error"].includes((run.status || "").toLowerCase()) || (run.errors || []).length > 0);
    const untypedTools = filteredTools.filter((tool) => (tool.inputEntities || []).length === 0 && !tool.outputEntity);
    const regressionBlockedSkills = filteredSkills.filter((skill) => regression.bySkillId.get(skill.skillId)?.latestLabel === "fail");
    const benchmarkIdsWithTrajectories = new Set(
      filteredTrajectories
        .map((trajectory) => trajectory.benchmarkId || "")
        .filter(Boolean),
    );
    const benchmarksWithoutTrajectories = benchmarks.filter((benchmark) => !benchmarkIdsWithTrajectories.has(benchmark.benchmarkId));

    return [
      {
        key: "promote",
        label: "Promote proven work",
        count: skillCandidates.length,
        hint: "Passing trajectories exist but are not hardened as reusable skills yet.",
        action: () => setFactoryView("trajectories"),
        actionLabel: "Review trajectories",
      },
      {
        key: "runs",
        label: "Fix broken runs",
        count: failedRuns.length,
        hint: "Harvesting produced errors or failed before the capability could be promoted.",
        action: () => setFactoryView("runs"),
        actionLabel: "Inspect runs",
      },
      {
        key: "benchmarks",
        label: "Benchmarks without evidence",
        count: benchmarksWithoutTrajectories.length,
        hint: "Tasks exist, but there is still no trajectory evidence behind them.",
        action: () => navigate("/evals"),
        actionLabel: "Open Benchmarks",
      },
      {
        key: "regressions",
        label: "Skills failing regressions",
        count: regressionBlockedSkills.length,
        hint: "Skills exist, but the latest benchmark evidence is failing and should block rollout.",
        action: () => setFactoryView("skills"),
        actionLabel: "Inspect skills",
      },
      {
        key: "entities",
        label: "Untyped tools",
        count: untypedTools.length,
        hint: "Tools exist without entity mapping, so the factory still lacks semantic business coverage.",
        action: () => setFactoryView("tools"),
        actionLabel: "Open tools",
      },
    ].filter((item) => item.count > 0);
  }, [benchmarks, filteredRuns, filteredSkills, filteredTools, filteredTrajectories, navigate, regression.bySkillId, setFactoryView, skillCandidates.length]);
  const benchmarkPipeline = useMemo(() => {
    const rows = benchmarks.map((benchmark) => {
      const benchmarkEvalIds = new Set((benchmark.tasks || []).map((task) => task.evalId).filter(Boolean));
      const benchmarkTrajectories = filteredTrajectories.filter((trajectory) =>
        trajectory.benchmarkId === benchmark.benchmarkId || (trajectory.evalId && benchmarkEvalIds.has(trajectory.evalId)),
      );
      const benchmarkTrajectoryIds = new Set(benchmarkTrajectories.map((trajectory) => trajectory.trajectoryId));
      const benchmarkSkills = filteredSkills.filter((skill) =>
        skill.benchmarkId === benchmark.benchmarkId
        || (skill.evalId && benchmarkEvalIds.has(skill.evalId))
        || (skill.trajectoryIds || []).some((trajectoryId) => benchmarkTrajectoryIds.has(trajectoryId)),
      );
      const relatedConnectorIds = new Set<string>();
      for (const trajectory of benchmarkTrajectories) {
        for (const connectorId of trajectory.connectorIds || []) {
          if (connectorId) relatedConnectorIds.add(connectorId);
        }
      }
      for (const skill of benchmarkSkills) {
        for (const connectorId of skill.connectorIds || []) {
          if (connectorId) relatedConnectorIds.add(connectorId);
        }
      }
      const benchmarkRuns = filteredRuns.filter((run) => relatedConnectorIds.has(run.connectorId));
      const passingTrajectories = benchmarkTrajectories.filter((trajectory) => trajectoryJudgeLabel(trajectory) === "pass");
      const promotedTrajectoryIds = new Set(benchmarkSkills.flatMap((skill) => skill.trajectoryIds || []));
      const promotable = passingTrajectories.filter((trajectory) => !promotedTrajectoryIds.has(trajectory.trajectoryId));
      const blockedSkills = benchmarkSkills.filter((skill) => regression.bySkillId.get(skill.skillId)?.latestLabel === "fail");
      const runFailures = benchmarkRuns.filter((run) => ["failed", "error"].includes((run.status || "").toLowerCase()) || (run.errors || []).length > 0);
      const stage: "published" | "ready" | "needs_review" | "needs_harvest" =
        benchmarkSkills.length > 0 ? "published"
          : promotable.length > 0 ? "ready"
            : benchmarkTrajectories.length > 0 ? "needs_review"
              : "needs_harvest";
      const gaps: string[] = [];
      if (benchmarkTrajectories.length === 0) gaps.push("No trajectory evidence yet");
      if (benchmarkTrajectories.length > 0 && passingTrajectories.length === 0) gaps.push("No passing trajectory yet");
      if (promotable.length > 0) gaps.push(`${promotable.length} promotable ${promotable.length === 1 ? "trajectory" : "trajectories"}`);
      if (runFailures.length > 0) gaps.push(`${runFailures.length} failed ${runFailures.length === 1 ? "run" : "runs"}`);
      return {
        benchmarkId: benchmark.benchmarkId,
        name: benchmark.name,
        taskCount: benchmark.tasks.length,
        trajectoryCount: benchmarkTrajectories.length,
        passingCount: passingTrajectories.length,
        skillCount: benchmarkSkills.length,
        blockedSkills: blockedSkills.length,
        runCount: benchmarkRuns.length,
        runFailures: runFailures.length,
        primaryBlockedSkillId: blockedSkills[0]?.skillId || "",
        primarySkillId: benchmarkSkills[0]?.skillId || "",
        primaryPromotableTrajectoryId: promotable[0]?.trajectoryId || "",
        primaryTrajectoryId: benchmarkTrajectories[0]?.trajectoryId || "",
        stage,
        gaps,
      };
    });

    return rows
      .filter((row) => !connectorFilter || row.trajectoryCount > 0 || row.skillCount > 0 || row.runCount > 0)
      .sort((a, b) => {
        const stageOrder = { ready: 0, needs_review: 1, needs_harvest: 2, published: 3 };
        if (stageOrder[a.stage] !== stageOrder[b.stage]) return stageOrder[a.stage] - stageOrder[b.stage];
        if (b.runFailures !== a.runFailures) return b.runFailures - a.runFailures;
        if (b.trajectoryCount !== a.trajectoryCount) return b.trajectoryCount - a.trajectoryCount;
        return a.name.localeCompare(b.name);
      });
  }, [benchmarks, connectorFilter, filteredRuns, filteredSkills, filteredTrajectories, regression.bySkillId]);
  const benchmarkCoverageSummary = useMemo(() => {
    const summary = {
      published: 0,
      ready: 0,
      needsReview: 0,
      needsHarvest: 0,
      blocked: 0,
    };
    for (const row of benchmarkPipeline) {
      if (row.stage === "published") summary.published += 1;
      if (row.stage === "ready") summary.ready += 1;
      if (row.stage === "needs_review") summary.needsReview += 1;
      if (row.stage === "needs_harvest") summary.needsHarvest += 1;
      if (row.blockedSkills > 0) summary.blocked += 1;
    }
    return summary;
  }, [benchmarkPipeline]);
  const entityCoverage = useMemo(() => {
    const rows = new Map<string, {
      entity: string;
      tools: Set<string>;
      skills: Set<string>;
      benchmarkedSkills: Set<string>;
      regressionReadySkills: Set<string>;
      trajectories: Set<string>;
      sessions: Set<string>;
    }>();
    const ensure = (raw: string) => {
      const entity = raw.trim();
      if (!entity) return null;
      const key = entity.toLowerCase();
      if (!rows.has(key)) {
        rows.set(key, {
          entity,
          tools: new Set<string>(),
          skills: new Set<string>(),
          benchmarkedSkills: new Set<string>(),
          regressionReadySkills: new Set<string>(),
          trajectories: new Set<string>(),
          sessions: new Set<string>(),
        });
      }
      return rows.get(key)!;
    };

    for (const tool of filteredTools) {
      for (const entity of [...(tool.inputEntities || []), ...(tool.outputEntity ? [tool.outputEntity] : [])]) {
        const row = ensure(entity);
        if (!row) continue;
        row.tools.add(tool.toolId);
        for (const trajectory of trajectories.filter((item) => (item.toolIds || []).includes(tool.toolId))) {
          row.trajectories.add(trajectory.trajectoryId);
        }
      }
    }

    for (const skill of filteredSkills) {
      const sessionItems = runtimeUsage.sessionsBySkillId.get(skill.skillId) || [];
      const isBenchmarked = Boolean(skill.benchmarkId || skill.evalId || skill.lineage?.benchmarkIds?.length || skill.lineage?.evalIds?.length);
      const isRegressionReady = (skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel) === "pass";
      for (const entity of [...(skill.inputEntities || []), ...(skill.outputEntity ? [skill.outputEntity] : [])]) {
        const row = ensure(entity);
        if (!row) continue;
        row.skills.add(skill.skillId);
        if (isBenchmarked) row.benchmarkedSkills.add(skill.skillId);
        if (isRegressionReady) row.regressionReadySkills.add(skill.skillId);
        for (const trajectoryId of skill.trajectoryIds || []) row.trajectories.add(trajectoryId);
        for (const session of sessionItems) row.sessions.add(session.sessionId);
      }
    }

    return Array.from(rows.values())
      .map((row) => ({
        entity: row.entity,
        tools: row.tools.size,
        skills: row.skills.size,
        benchmarkedSkills: row.benchmarkedSkills.size,
        regressionReadySkills: row.regressionReadySkills.size,
        trajectories: row.trajectories.size,
        sessions: row.sessions.size,
      }))
      .sort((a, b) => {
        if (b.skills !== a.skills) return b.skills - a.skills;
        if (b.tools !== a.tools) return b.tools - a.tools;
        return a.entity.localeCompare(b.entity);
      });
  }, [filteredSkills, filteredTools, regression.bySkillId, runtimeUsage.sessionsBySkillId, trajectories]);
  const activeScopeGraph = useMemo(() => {
    if (!benchmarkFilter && !entityFilter) return null;

    const connectorIds = new Set<string>();
    for (const tool of filteredTools) {
      if (tool.connectorId) connectorIds.add(tool.connectorId);
    }
    for (const trajectory of filteredTrajectories) {
      for (const connectorId of trajectory.connectorIds || []) {
        if (connectorId) connectorIds.add(connectorId);
      }
    }
    for (const skill of filteredSkills) {
      for (const connectorId of skill.connectorIds || []) {
        if (connectorId) connectorIds.add(connectorId);
      }
    }

    const connectorNames = Array.from(connectorIds)
      .map((connectorId) => connectorsById.get(connectorId)?.name || connectorId)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b));

    const sessionMap = new Map<string, SessionItem>();
    const approvalMap = new Map<string, ApprovalRequest>();
    const artifactMap = new Map<string, Artifact>();
    const workMap = new Map<string, WorkItem>();

    for (const skill of filteredSkills) {
      for (const session of runtimeUsage.sessionsBySkillId.get(skill.skillId) || []) sessionMap.set(session.sessionId, session);
      for (const approval of runtimeUsage.approvalsBySkillId.get(skill.skillId) || []) approvalMap.set(approval.approvalId, approval);
      for (const artifact of runtimeUsage.artifactsBySkillId.get(skill.skillId) || []) artifactMap.set(artifact.artifactId, artifact);
      for (const item of runtimeUsage.workItemsBySkillId.get(skill.skillId) || []) workMap.set(item.workItemId, item);
    }
    for (const trajectory of filteredTrajectories) {
      for (const session of runtimeUsage.sessionsByTrajectoryId.get(trajectory.trajectoryId) || []) sessionMap.set(session.sessionId, session);
      for (const approval of runtimeUsage.approvalsByTrajectoryId.get(trajectory.trajectoryId) || []) approvalMap.set(approval.approvalId, approval);
      for (const artifact of runtimeUsage.artifactsByTrajectoryId.get(trajectory.trajectoryId) || []) artifactMap.set(artifact.artifactId, artifact);
      for (const item of runtimeUsage.workItemsByTrajectoryId.get(trajectory.trajectoryId) || []) workMap.set(item.workItemId, item);
    }
    for (const tool of filteredTools) {
      for (const session of runtimeUsage.sessionsByToolId.get(tool.toolId) || []) sessionMap.set(session.sessionId, session);
      for (const approval of runtimeUsage.approvalsByToolId.get(tool.toolId) || []) approvalMap.set(approval.approvalId, approval);
      for (const artifact of runtimeUsage.artifactsByToolId.get(tool.toolId) || []) artifactMap.set(artifact.artifactId, artifact);
      for (const item of runtimeUsage.workItemsByToolId.get(tool.toolId) || []) workMap.set(item.workItemId, item);
    }

    const pendingApprovals = Array.from(approvalMap.values()).filter((approval) => approval.status === "pending");
    const writeTools = filteredTools.filter((tool) => ["writes", "deletes"].includes((tool.sideEffects || "").toLowerCase()));
    const highRiskTools = filteredTools.filter((tool) => (tool.riskLevel || "").toLowerCase() === "high");
    const failingSkills = filteredSkills.filter((skill) => (skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel) === "fail");
    const approvalHotspots = [
      ...filteredSkills.map((skill) => ({
        kind: "skill" as const,
        id: skill.skillId,
        label: skill.name,
        count: (runtimeUsage.approvalsBySkillId.get(skill.skillId) || []).filter((approval) => approval.status === "pending").length,
        item: skill,
      })),
      ...filteredTrajectories.map((trajectory) => ({
        kind: "trajectory" as const,
        id: trajectory.trajectoryId,
        label: trajectory.name,
        count: (runtimeUsage.approvalsByTrajectoryId.get(trajectory.trajectoryId) || []).filter((approval) => approval.status === "pending").length,
        item: trajectory,
      })),
      ...filteredTools.map((tool) => ({
        kind: "tool" as const,
        id: tool.toolId,
        label: tool.displayName || tool.name,
        count: (runtimeUsage.approvalsByToolId.get(tool.toolId) || []).filter((approval) => approval.status === "pending").length,
        item: tool,
      })),
    ]
      .filter((item) => item.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 3);

    return {
      title: filteredBenchmark ? filteredBenchmark.name : filteredEntity,
      subtitle: filteredBenchmark
        ? "Benchmark-scoped graph from tasks and evidence through reusable skills and runtime proof."
        : "Entity-scoped graph from typed actions through reusable skills and runtime proof.",
      connectors: connectorNames,
      tools: filteredTools.slice(0, 4),
      trajectories: filteredTrajectories.slice(0, 4),
      skills: filteredSkills.slice(0, 4),
      sessionCount: sessionMap.size,
      approvalCount: approvalMap.size,
      artifactCount: artifactMap.size,
      workCount: workMap.size,
      regressionReadySkills: filteredSkills.filter((skill) => (skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel) === "pass").length,
      blockedSkills: failingSkills.length,
      pendingApprovalCount: pendingApprovals.length,
      writeTools,
      highRiskTools,
      failingSkills,
      approvalHotspots,
    };
  }, [
    benchmarkFilter,
    connectorsById,
    entityFilter,
    filteredBenchmark,
    filteredEntity,
    filteredSkills,
    filteredTools,
    filteredTrajectories,
    regression.bySkillId,
    runtimeUsage.approvalsBySkillId,
    runtimeUsage.approvalsByToolId,
    runtimeUsage.approvalsByTrajectoryId,
    runtimeUsage.artifactsBySkillId,
    runtimeUsage.artifactsByToolId,
    runtimeUsage.artifactsByTrajectoryId,
    runtimeUsage.sessionsBySkillId,
    runtimeUsage.sessionsByToolId,
    runtimeUsage.sessionsByTrajectoryId,
    runtimeUsage.workItemsBySkillId,
    runtimeUsage.workItemsByToolId,
    runtimeUsage.workItemsByTrajectoryId,
  ]);

  // The pipeline band doubles as the primary navigation: Tools -> Trajectories ->
  // Skills -> Harvester Runs. Tasks stay under Benchmarks/Harvester Runs because
  // they are inputs to harvesting, not capabilities.
  const pipelineSteps: Array<{ key: ViewKey; label: string; icon: typeof faWrench; count: number; blurb: string }> = [
    { key: "tools", label: "Tools", icon: faWrench, count: toolsCount, blurb: "Atomic actions from connectors" },
    { key: "trajectories", label: "Trajectories", icon: faRoute, count: filteredTrajectories.length, blurb: "Concrete attempts with tool calls" },
    { key: "skills", label: "Skills", icon: faWandMagicSparkles, count: filteredSkills.length, blurb: "Reusable, versioned procedures" },
    { key: "runs", label: "Runs", icon: faTractor, count: filteredRuns.length, blurb: "Harvester run history" },
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
                <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">Capability Factory</h1>
                <CapabilitiesBuildInfo counts={{ customTools: toolsCount, trajectories: trajectories.length, skills: skills.length }} />
              </div>
              <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">Turn connector actions into trajectories, and trajectories into governed reusable skills</p>
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
              {detail && (
                <div className="mb-4 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary dark:border-primary/20 dark:bg-primary/10">
                  <span className="font-semibold">Capability detail active.</span>{" "}
                  You are inspecting a {detail.kind} inside the Factory flow. Close the detail panel to return to the broader catalog.
                </div>
              )}
              {filteredConnector && (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">Connector filter active</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Showing Factory surfaces only for <span className="font-semibold text-gray-700 dark:text-gray-200">{filteredConnector.name}</span>.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setFactoryScope({ connectorId: "" });
                    }}
                    className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-bg"
                  >
                    Clear filter
                  </button>
                </div>
              )}
              {filteredBenchmark && (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">Benchmark filter active</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Showing Factory evidence only for <span className="font-semibold text-gray-700 dark:text-gray-200">{filteredBenchmark.name}</span>.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setFactoryScope({ benchmarkId: "" });
                    }}
                    className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-bg"
                  >
                    Clear benchmark
                  </button>
                </div>
              )}
              {filteredEntity && (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">Entity filter active</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Showing Factory graph only for <span className="font-semibold text-gray-700 dark:text-gray-200">{filteredEntity}</span>.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setFactoryScope({ entityId: "" });
                    }}
                    className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-bg"
                  >
                    Clear entity
                  </button>
                </div>
              )}
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

                    <button onClick={() => { setShowCreate(false); setFactoryView("trajectories"); }} className="text-left rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 flex flex-col hover:border-primary/40 transition-colors">
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

                    <button onClick={() => { setShowCreate(false); setFactoryView("skills"); }} className="text-left rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-4 flex flex-col hover:border-primary/40 transition-colors">
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
                      onClick={() => setFactoryView(step.key)}
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

              <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
                <CoverageCard
                  label="Typed Tools"
                  value={`${coverage.typedTools}/${toolsCount}`}
                  hint="Tools already mapped to business entities."
                />
                <CoverageCard
                  label="Benchmarked Trajectories"
                  value={`${coverage.benchmarkBackedTrajectories}/${trajectories.length}`}
                  hint="Traces with explicit benchmark or eval lineage."
                />
                <CoverageCard
                  label="Benchmarked Skills"
                  value={`${coverage.benchmarkBackedSkills}/${skills.length}`}
                  hint="Reusable skills linked to benchmarked evidence."
                />
                <CoverageCard
                  label="Regression Ready"
                  value={`${coverage.regressionPassingSkills}/${skills.length}`}
                  hint="Skills whose latest benchmark run is passing."
                />
                <CoverageCard
                  label="Promotable"
                  value={coverage.promotableTrajectories}
                  hint="Passing trajectories ready to harden into skills."
                />
              </div>

              {activeScopeGraph && (
                <div className="mb-5 rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Factory Graph</p>
                      <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{activeScopeGraph.title}</p>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{activeScopeGraph.subtitle}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-semibold text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                          {backendGraphStats.nodeCount} backend nodes
                        </span>
                        <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-semibold text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                          {backendGraphStats.edgeCount} backend edges
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.resourcesLinked && backendGraphStats.indexedResources > 0 ? "border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-300" : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>
                          {backendGraphStats.indexedResources}/{backendGraphStats.totalResources} indexed resources · {backendGraphStats.citableResources} citable
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.governedTools === backendGraphStats.totalTools && backendGraphStats.totalTools > 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300" : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"}`}>
                          {backendGraphStats.governedTools}/{backendGraphStats.totalTools} governed tools
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.taskContracts === backendGraphStats.totalTasks && backendGraphStats.totalTasks > 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300" : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>
                          {backendGraphStats.taskContracts}/{backendGraphStats.totalTasks} task contracts
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.hasPromotionPath && backendGraphStats.reusableSkills > 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300" : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>
                          {backendGraphStats.reusableSkills}/{backendGraphStats.totalSkills} reusable skills
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.runtimeLinked ? "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300" : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>
                          {backendGraphStats.runtimeSessions} sessions · {backendGraphStats.runtimeApprovals} approvals · {backendGraphStats.runtimeArtifacts} artifacts
                        </span>
                        <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${backendGraphStats.workLinked ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300" : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>
                          {backendGraphStats.workItems} jobs · {backendGraphStats.scheduledWork} scheduled · {backendGraphStats.approvalBlockedWork || backendGraphStats.reviewWork} review
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {filteredBenchmark && (
                        <button
                          onClick={() => navigate(`/eval-runs?benchmark=${encodeURIComponent(filteredBenchmark.benchmarkId)}`)}
                          className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                        >
                          Recent runs
                        </button>
                      )}
                      {filteredEntity && (
                        <button
                          onClick={() => navigate(`/entities`)}
                          className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                        >
                          Entity map
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
                    {[
                      { label: "Connectors", value: activeScopeGraph.connectors.length },
                      { label: "Tools", value: filteredTools.length },
                      { label: "Trajectories", value: filteredTrajectories.length },
                      { label: "Skills", value: filteredSkills.length },
                      { label: "Sessions", value: activeScopeGraph.sessionCount },
                      { label: "Approvals", value: activeScopeGraph.approvalCount },
                      { label: "Artifacts", value: activeScopeGraph.artifactCount },
                      { label: "Jobs", value: activeScopeGraph.workCount },
                    ].map((item) => (
                      <div key={item.label} className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{item.label}</p>
                        <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{item.value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Critical Path</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Immediate operational signals for this scope before a capability is promoted or trusted in runtime.
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          { label: "Pending approvals", value: activeScopeGraph.pendingApprovalCount, tone: activeScopeGraph.pendingApprovalCount > 0 ? "critical" as const : "neutral" as const },
                          { label: "Write-capable tools", value: activeScopeGraph.writeTools.length, tone: activeScopeGraph.writeTools.length > 0 ? "warning" as const : "neutral" as const },
                          { label: "High-risk tools", value: activeScopeGraph.highRiskTools.length, tone: activeScopeGraph.highRiskTools.length > 0 ? "critical" as const : "neutral" as const },
                          { label: "Regression blocked", value: activeScopeGraph.failingSkills.length, tone: activeScopeGraph.failingSkills.length > 0 ? "critical" as const : "neutral" as const },
                        ].map((signal) => (
                          <span key={signal.label} className={`rounded-lg border px-3 py-2 text-[11px] font-semibold ${graphSignalTone(signal.tone)}`}>
                            {signal.value} {signal.label}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-3">
                      {activeScopeGraph.approvalHotspots.map((hotspot) => (
                        <div key={`${hotspot.kind}:${hotspot.id}`} className="rounded-lg border border-red-200 bg-white p-3 dark:border-red-500/30 dark:bg-dark-surface">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-500">{hotspot.count} pending approvals</p>
                          <p className="mt-1 truncate text-xs font-semibold text-gray-900 dark:text-white">{hotspot.label}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <button
                              onClick={() => {
                                if (hotspot.kind === "tool") openCapabilityDetail({ kind: "tool", item: hotspot.item });
                                if (hotspot.kind === "trajectory") openCapabilityDetail({ kind: "trajectory", item: hotspot.item });
                                if (hotspot.kind === "skill") openCapabilityDetail({ kind: "skill", item: hotspot.item });
                              }}
                              className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg"
                            >
                              Inspect
                            </button>
                            <button
                              onClick={() => {
                                if (hotspot.kind === "tool") openScopedApprovals({ toolId: hotspot.id });
                                if (hotspot.kind === "trajectory") openScopedApprovals({ trajectoryId: hotspot.id });
                                if (hotspot.kind === "skill") openScopedApprovals({ skillId: hotspot.id });
                              }}
                              className="inline-flex h-7 items-center rounded-lg border border-red-200 px-2.5 text-[11px] font-semibold text-red-600 hover:bg-red-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10"
                            >
                              Approvals
                            </button>
                          </div>
                        </div>
                      ))}
                      {activeScopeGraph.failingSkills.slice(0, Math.max(0, 3 - activeScopeGraph.approvalHotspots.length)).map((skill) => (
                        <div key={`failing:${skill.skillId}`} className="rounded-lg border border-red-200 bg-white p-3 dark:border-red-500/30 dark:bg-dark-surface">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-500">Regression failed</p>
                          <p className="mt-1 truncate text-xs font-semibold text-gray-900 dark:text-white">{skill.name}</p>
                          <button
                            onClick={() => openCapabilityDetail({ kind: "skill", item: skill })}
                            className="mt-2 inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg"
                          >
                            Inspect
                          </button>
                        </div>
                      ))}
                      {activeScopeGraph.approvalHotspots.length === 0 && activeScopeGraph.failingSkills.length === 0 && activeScopeGraph.highRiskTools.slice(0, 3).map((tool) => (
                        <div key={`risk:${tool.toolId}`} className="rounded-lg border border-red-200 bg-white p-3 dark:border-red-500/30 dark:bg-dark-surface">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-500">High-risk tool</p>
                          <p className="mt-1 truncate text-xs font-semibold text-gray-900 dark:text-white">{tool.displayName || tool.name}</p>
                          <button
                            onClick={() => openCapabilityDetail({ kind: "tool", item: tool })}
                            className="mt-2 inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg"
                          >
                            Inspect
                          </button>
                        </div>
                      ))}
                      {activeScopeGraph.approvalHotspots.length === 0 && activeScopeGraph.failingSkills.length === 0 && activeScopeGraph.highRiskTools.length === 0 && (
                        <div className="rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400 lg:col-span-3">
                          No pending approvals, failed regressions or high-risk tools are visible in this scope.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-4">
                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Connectors</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {activeScopeGraph.connectors.length === 0 ? (
                          <span className="text-xs text-gray-400">No connector evidence in scope.</span>
                        ) : activeScopeGraph.connectors.map((name) => (
                          <span key={name} className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                            {name}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Tools</p>
                        <button onClick={() => setFactoryScope({ view: "tools" })} className="text-[11px] font-semibold text-primary">Open</button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {activeScopeGraph.tools.length === 0 ? (
                          <span className="text-xs text-gray-400">No tools in this scope.</span>
                        ) : activeScopeGraph.tools.map((tool) => {
                          const nodeKey = `tool:${tool.toolId}`;
                          const expanded = activeGraphNode === nodeKey;
                          const nodeSessions = runtimeUsage.sessionsByToolId.get(tool.toolId) || [];
                          const nodeApprovals = runtimeUsage.approvalsByToolId.get(tool.toolId) || [];
                          const nodeArtifacts = runtimeUsage.artifactsByToolId.get(tool.toolId) || [];
                          const nodeWork = runtimeUsage.workItemsByToolId.get(tool.toolId) || [];
                          const pendingApprovals = nodeApprovals.filter((item) => item.status === "pending").length;
                          const lastActiveAt = latestActivityTimestamp([
                            ...nodeSessions.map((item) => item.createdAt),
                            ...nodeApprovals.map((item) => item.createdAt),
                            ...nodeArtifacts.map((item) => item.updatedAt || item.createdAt),
                            ...nodeWork.map((item) => item.updatedAt || item.createdAt),
                          ]);
                          return (
                            <div key={tool.toolId} className="rounded-lg border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
                              <button
                                onClick={() => setActiveGraphNode(expanded ? "" : nodeKey)}
                                className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-xs transition-colors hover:border-primary/30"
                              >
                                <div className="min-w-0">
                                  <p className="truncate font-semibold text-gray-900 dark:text-white">{tool.name}</p>
                                  <p className="mt-1 truncate text-[11px] text-gray-500 dark:text-gray-400">{tool.connectorName || connectorsById.get(tool.connectorId)?.name || "Connector"}</p>
                                </div>
                                <FontAwesomeIcon icon={faChevronDown} className={`mt-1 text-[10px] text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                              </button>
                              {expanded && (
                                <div className="border-t border-gray-200 px-3 py-3 dark:border-dark-border">
                                  <div className="mb-3 flex flex-wrap gap-1.5">
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeSessions.length} sessions</span>
                                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${pendingApprovals > 0 ? approvalTone("always") : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>{nodeApprovals.length} approvals{pendingApprovals > 0 ? ` · ${pendingApprovals} pending` : ""}</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeArtifacts.length} artifacts</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeWork.length} jobs</span>
                                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${sideEffectTone(tool.sideEffects)}`}>{tool.sideEffects}</span>
                                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${riskTone(tool.riskLevel)}`}>{tool.riskLevel}</span>
                                  </div>
                                  <div className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">
                                    Last active: {formatRuntimeDate(lastActiveAt)}
                                  </div>
                                  {((nodeApprovals.length > 0) || (nodeArtifacts.length > 0) || (nodeWork.length > 0)) && (
                                    <div className="mb-3 flex flex-wrap gap-1.5">
                                      {nodeApprovals.slice(0, 1).map((item) => <span key={item.approvalId} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">{item.title || item.toolName || "Approval"}</span>)}
                                      {nodeArtifacts.slice(0, 1).map((item) => <span key={item.artifactId} className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">{item.title || item.artifactType || "Artifact"}</span>)}
                                      {nodeWork.slice(0, 1).map((item) => <span key={item.workItemId} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">{item.title || "Job"}</span>)}
                                    </div>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    <button onClick={() => openCapabilityDetail({ kind: "tool", item: tool })} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Inspect</button>
                                    <button onClick={() => openScopedRuntime({ sessionIds: nodeSessions.map((session) => session.sessionId) })} disabled={nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Runtime</button>
                                    <button onClick={() => openScopedApprovals({ toolId: tool.toolId })} disabled={nodeApprovals.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Approvals</button>
                                    <button onClick={() => openScopedArtifacts({ toolId: tool.toolId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeArtifacts.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Artifacts</button>
                                    <button onClick={() => openScopedWork({ toolId: tool.toolId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeWork.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Work</button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Trajectories</p>
                        <button onClick={() => setFactoryScope({ view: "trajectories" })} className="text-[11px] font-semibold text-primary">Open</button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {activeScopeGraph.trajectories.length === 0 ? (
                          <span className="text-xs text-gray-400">No trajectory evidence in this scope.</span>
                        ) : activeScopeGraph.trajectories.map((trajectory) => {
                          const nodeKey = `trajectory:${trajectory.trajectoryId}`;
                          const expanded = activeGraphNode === nodeKey;
                          const nodeSessions = runtimeUsage.sessionsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const nodeApprovals = runtimeUsage.approvalsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const nodeArtifacts = runtimeUsage.artifactsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const nodeWork = runtimeUsage.workItemsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const linkedSkills = filteredSkills.filter((skill) => (skill.trajectoryIds || []).includes(trajectory.trajectoryId)).slice(0, 3);
                          const linkedTools = filteredTools.filter((tool) => (trajectory.toolIds || []).includes(tool.toolId)).slice(0, 4);
                          const pendingApprovals = nodeApprovals.filter((item) => item.status === "pending").length;
                          const failingSkills = linkedSkills.filter((skill) => (skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel) === "fail").length;
                          const lastActiveAt = latestActivityTimestamp([
                            ...nodeSessions.map((item) => item.createdAt),
                            ...nodeApprovals.map((item) => item.createdAt),
                            ...nodeArtifacts.map((item) => item.updatedAt || item.createdAt),
                            ...nodeWork.map((item) => item.updatedAt || item.createdAt),
                          ]);
                          return (
                            <div key={trajectory.trajectoryId} className="rounded-lg border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
                              <button
                                onClick={() => setActiveGraphNode(expanded ? "" : nodeKey)}
                                className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-xs transition-colors hover:border-primary/30"
                              >
                                <div className="min-w-0">
                                  <p className="truncate font-semibold text-gray-900 dark:text-white">{trajectory.name || trajectory.trajectoryId}</p>
                                  <p className="mt-1 truncate text-[11px] text-gray-500 dark:text-gray-400">{trajectory.intent || trajectory.description || "No intent"}</p>
                                </div>
                                <FontAwesomeIcon icon={faChevronDown} className={`mt-1 text-[10px] text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                              </button>
                              {expanded && (
                                <div className="border-t border-gray-200 px-3 py-3 dark:border-dark-border">
                                  <div className="mb-3 flex flex-wrap gap-1.5">
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeSessions.length} sessions</span>
                                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${pendingApprovals > 0 ? approvalTone("always") : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>{nodeApprovals.length} approvals{pendingApprovals > 0 ? ` · ${pendingApprovals} pending` : ""}</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeArtifacts.length} artifacts</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeWork.length} jobs</span>
                                    {failingSkills > 0 && (
                                      <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionTone("fail")}`}>{failingSkills} regression fail</span>
                                    )}
                                  </div>
                                  <div className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">
                                    Last active: {formatRuntimeDate(lastActiveAt)}
                                  </div>
                                  {((nodeApprovals.length > 0) || (nodeArtifacts.length > 0) || (nodeWork.length > 0)) && (
                                    <div className="mb-3 flex flex-wrap gap-1.5">
                                      {nodeApprovals.slice(0, 1).map((item) => <span key={item.approvalId} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">{item.title || item.toolName || "Approval"}</span>)}
                                      {nodeArtifacts.slice(0, 1).map((item) => <span key={item.artifactId} className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">{item.title || item.artifactType || "Artifact"}</span>)}
                                      {nodeWork.slice(0, 1).map((item) => <span key={item.workItemId} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">{item.title || "Job"}</span>)}
                                    </div>
                                  )}
                                  {((linkedSkills.length > 0) || (linkedTools.length > 0)) && (
                                    <div className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                                      <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Linked skills</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {linkedSkills.length === 0 ? (
                                            <span className="text-[10px] text-gray-400">No promoted skill yet.</span>
                                          ) : linkedSkills.map((skill) => (
                                            <button key={skill.skillId} onClick={() => openCapabilityDetail({ kind: "skill", item: skill })} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-border">
                                              {skill.name}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                      <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Called tools</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {linkedTools.length === 0 ? (
                                            <span className="text-[10px] text-gray-400">No typed tool references.</span>
                                          ) : linkedTools.map((tool) => (
                                            <button key={tool.toolId} onClick={() => openCapabilityDetail({ kind: "tool", item: tool })} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-border">
                                              {tool.name}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    <button onClick={() => openCapabilityDetail({ kind: "trajectory", item: trajectory })} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Inspect</button>
                                    <button onClick={() => openScopedRuntime({ sessionIds: nodeSessions.map((session) => session.sessionId) })} disabled={nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Runtime</button>
                                    <button onClick={() => openScopedApprovals({ trajectoryId: trajectory.trajectoryId })} disabled={nodeApprovals.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Approvals</button>
                                    <button onClick={() => openScopedArtifacts({ trajectoryId: trajectory.trajectoryId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeArtifacts.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Artifacts</button>
                                    <button onClick={() => openScopedWork({ trajectoryId: trajectory.trajectoryId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeWork.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Work</button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Skills</p>
                        <button onClick={() => setFactoryScope({ view: "skills" })} className="text-[11px] font-semibold text-primary">Open</button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {activeScopeGraph.skills.length === 0 ? (
                          <span className="text-xs text-gray-400">No reusable skills in this scope.</span>
                        ) : activeScopeGraph.skills.map((skill) => {
                          const nodeKey = `skill:${skill.skillId}`;
                          const expanded = activeGraphNode === nodeKey;
                          const nodeSessions = runtimeUsage.sessionsBySkillId.get(skill.skillId) || [];
                          const nodeApprovals = runtimeUsage.approvalsBySkillId.get(skill.skillId) || [];
                          const nodeArtifacts = runtimeUsage.artifactsBySkillId.get(skill.skillId) || [];
                          const nodeWork = runtimeUsage.workItemsBySkillId.get(skill.skillId) || [];
                          const sourceTrajectories = (skill.trajectoryIds || []).map((trajectoryId) => trajectoriesById.get(trajectoryId)).filter(Boolean).slice(0, 3) as CompanyTrajectory[];
                          const sourceTools = filteredTools.filter((tool) => (skill.toolIds || []).includes(tool.toolId)).slice(0, 4);
                          const pendingApprovals = nodeApprovals.filter((item) => item.status === "pending").length;
                          const regressionState = skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel || "";
                          const lastActiveAt = latestActivityTimestamp([
                            ...nodeSessions.map((item) => item.createdAt),
                            ...nodeApprovals.map((item) => item.createdAt),
                            ...nodeArtifacts.map((item) => item.updatedAt || item.createdAt),
                            ...nodeWork.map((item) => item.updatedAt || item.createdAt),
                          ]);
                          return (
                            <div key={skill.skillId} className="rounded-lg border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
                              <button
                                onClick={() => setActiveGraphNode(expanded ? "" : nodeKey)}
                                className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-xs transition-colors hover:border-primary/30"
                              >
                                <div className="min-w-0">
                                  <div className="flex items-center justify-between gap-2">
                                    <p className="truncate font-semibold text-gray-900 dark:text-white">{skill.name}</p>
                                    <span className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${regressionTone(skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel)}`}>
                                      {skill.latestRegression?.label || regression.bySkillId.get(skill.skillId)?.latestLabel || "n/a"}
                                    </span>
                                  </div>
                                  <p className="mt-1 truncate text-[11px] text-gray-500 dark:text-gray-400">{skill.whenToUse || skill.description || "No activation guidance"}</p>
                                </div>
                                <FontAwesomeIcon icon={faChevronDown} className={`mt-1 text-[10px] text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                              </button>
                              {expanded && (
                                <div className="border-t border-gray-200 px-3 py-3 dark:border-dark-border">
                                  <div className="mb-3 flex flex-wrap gap-1.5">
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeSessions.length} sessions</span>
                                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${pendingApprovals > 0 ? approvalTone("always") : "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300"}`}>{nodeApprovals.length} approvals{pendingApprovals > 0 ? ` · ${pendingApprovals} pending` : ""}</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeArtifacts.length} artifacts</span>
                                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">{nodeWork.length} jobs</span>
                                    {skill.riskPolicy && (
                                      <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionState === "fail" ? regressionTone("fail") : approvalTone(approvalMode(skill))}`}>{skill.riskPolicy.replace(/_/g, " ")}</span>
                                    )}
                                    {skill.runtimePolicy && (
                                      <>
                                        <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                                          runtime {skill.runtimePolicy.runtimeClass}
                                        </span>
                                        <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${approvalTone(skill.runtimePolicy.approvalMode as ApprovalMode)}`}>
                                          {runtimePolicyLabel(skill)}
                                        </span>
                                      </>
                                    )}
                                    {regressionState && (
                                      <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionTone(regressionState)}`}>regression {regressionState}</span>
                                    )}
                                  </div>
                                  <div className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">
                                    Last active: {formatRuntimeDate(lastActiveAt)}
                                  </div>
                                  {((nodeApprovals.length > 0) || (nodeArtifacts.length > 0) || (nodeWork.length > 0)) && (
                                    <div className="mb-3 flex flex-wrap gap-1.5">
                                      {nodeApprovals.slice(0, 1).map((item) => <span key={item.approvalId} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">{item.title || item.toolName || "Approval"}</span>)}
                                      {nodeArtifacts.slice(0, 1).map((item) => <span key={item.artifactId} className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">{item.title || item.artifactType || "Artifact"}</span>)}
                                      {nodeWork.slice(0, 1).map((item) => <span key={item.workItemId} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">{item.title || "Job"}</span>)}
                                    </div>
                                  )}
                                  {((sourceTrajectories.length > 0) || (sourceTools.length > 0)) && (
                                    <div className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                                      <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Source trajectories</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {sourceTrajectories.length === 0 ? (
                                            <span className="text-[10px] text-gray-400">No source trajectories attached.</span>
                                          ) : sourceTrajectories.map((trajectory) => (
                                            <button key={trajectory.trajectoryId} onClick={() => openCapabilityDetail({ kind: "trajectory", item: trajectory })} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-border">
                                              {trajectory.name || trajectory.trajectoryId}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                      <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Source tools</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {sourceTools.length === 0 ? (
                                            <span className="text-[10px] text-gray-400">No typed tools attached.</span>
                                          ) : sourceTools.map((tool) => (
                                            <button key={tool.toolId} onClick={() => openCapabilityDetail({ kind: "tool", item: tool })} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-border">
                                              {tool.name}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex flex-wrap gap-2">
                                    <button onClick={() => openCapabilityDetail({ kind: "skill", item: skill })} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Inspect</button>
                                    <button onClick={() => openScopedRuntime({ skillId: skill.skillId, sessionIds: nodeSessions.map((session) => session.sessionId) })} disabled={nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Runtime</button>
                                    <button onClick={() => openScopedApprovals({ skillId: skill.skillId })} disabled={nodeApprovals.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Approvals</button>
                                    <button onClick={() => openScopedArtifacts({ skillId: skill.skillId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeArtifacts.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Artifacts</button>
                                    <button onClick={() => openScopedWork({ skillId: skill.skillId, sessionId: nodeSessions.length === 1 ? nodeSessions[0].sessionId : "" })} disabled={nodeWork.length === 0 && nodeSessions.length === 0} className="inline-flex h-7 items-center rounded-lg border border-gray-200 px-2.5 text-[11px] font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-200 dark:hover:bg-dark-bg">Work</button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionTone(activeScopeGraph.regressionReadySkills > 0 ? "pass" : "")}`}>
                      {activeScopeGraph.regressionReadySkills} regression-ready skills
                    </span>
                    {activeScopeGraph.blockedSkills > 0 && (
                      <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionTone("fail")}`}>
                        {activeScopeGraph.blockedSkills} regression-blocked skills
                      </span>
                    )}
                  </div>
                </div>
              )}

              <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Benchmark Coverage</p>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Which benchmarks already have evidence, promotable trajectories or published reusable skills.
                      </p>
                    </div>
                    <button
                      onClick={() => navigate("/evals")}
                      className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                    >
                      <FontAwesomeIcon icon={faClipboardCheck} className="text-[10px]" />
                      Benchmarks
                    </button>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
                    {[
                      { label: "Published", value: benchmarkCoverageSummary.published, tone: stageTone("published") },
                      { label: "Ready", value: benchmarkCoverageSummary.ready, tone: stageTone("ready") },
                      { label: "Review", value: benchmarkCoverageSummary.needsReview, tone: stageTone("needs_review") },
                      { label: "No evidence", value: benchmarkCoverageSummary.needsHarvest, tone: stageTone("needs_harvest") },
                      { label: "Blocked", value: benchmarkCoverageSummary.blocked, tone: regressionTone("fail") },
                    ].map((item) => (
                      <div key={item.label} className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-dark-border dark:bg-dark-bg">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{item.label}</p>
                        <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">{item.value}</p>
                        <span className={`mt-2 inline-flex rounded-md border px-2 py-0.5 text-[10px] font-medium ${item.tone}`}>{item.label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 space-y-3">
                    {benchmarkPipeline.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                        No benchmark pipeline is visible yet for the current scope.
                      </div>
                    ) : benchmarkPipeline.slice(0, 4).map((row) => (
                      <div key={`coverage-${row.benchmarkId}`} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{row.name}</p>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {row.taskCount} tasks · {row.trajectoryCount} trajectories · {row.skillCount} skills
                            </p>
                          </div>
                          <span className={`inline-flex items-center rounded-lg border px-2 py-1 text-[10px] font-semibold ${stageTone(row.stage)}`}>
                            {stageLabel(row.stage)}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-1.5">
                          {row.gaps.slice(0, 3).map((gap) => (
                            <span key={gap} className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                              {gap}
                            </span>
                          ))}
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <button
                            onClick={() => setFactoryScope({ view: "trajectories", benchmarkId: row.benchmarkId })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                          >
                            Review evidence
                          </button>
                          <button
                            onClick={() => setFactoryScope({ view: row.skillCount > 0 ? "skills" : "trajectories", benchmarkId: row.benchmarkId })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
                          >
                            Open pipeline
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Entity Coverage</p>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Business entities already mapped to typed tools and reusable skills, with benchmark and runtime evidence.
                      </p>
                    </div>
                    <button
                      onClick={() => navigate("/entities")}
                      className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                    >
                      <FontAwesomeIcon icon={faCube} className="text-[10px]" />
                      Entities
                    </button>
                  </div>
                  <div className="mt-4 space-y-3">
                    {entityCoverage.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                        No entity mapping is visible yet for the current scope.
                      </div>
                    ) : entityCoverage.slice(0, 6).map((row) => (
                      <div key={row.entity} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{row.entity}</p>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {row.tools} tools · {row.skills} skills · {row.trajectories} trajectories
                            </p>
                          </div>
                          <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-medium ${row.regressionReadySkills > 0 ? regressionTone("pass") : row.benchmarkedSkills > 0 ? stageTone("ready") : stageTone("needs_harvest")}`}>
                            {row.regressionReadySkills > 0 ? "runtime-ready" : row.benchmarkedSkills > 0 ? "benchmarked" : "unverified"}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2">
                          <div className="rounded-lg border border-gray-200 bg-white px-2 py-2 text-center dark:border-dark-border dark:bg-dark-surface">
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Benchmarked</p>
                            <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{row.benchmarkedSkills}</p>
                          </div>
                          <div className="rounded-lg border border-gray-200 bg-white px-2 py-2 text-center dark:border-dark-border dark:bg-dark-surface">
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Regression ready</p>
                            <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{row.regressionReadySkills}</p>
                          </div>
                          <div className="rounded-lg border border-gray-200 bg-white px-2 py-2 text-center dark:border-dark-border dark:bg-dark-surface">
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Sessions</p>
                            <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{row.sessions}</p>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <button
                            onClick={() => setFactoryScope({ view: "tools", entityId: row.entity })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                          >
                            Tools graph
                          </button>
                          <button
                            onClick={() => setFactoryScope({ view: row.skills > 0 ? "skills" : "trajectories", entityId: row.entity })}
                            className="inline-flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
                          >
                            Open factory scope
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {connectorCoverage.length > 0 && (
                <div className="mb-5 rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Connector Coverage</p>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Expected benchmark surfaces per connector, plus live matrix evidence when audited.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {connectorAuditReport && (
                        <>
                          <span className="rounded-md bg-green-50 px-2 py-0.5 text-[11px] font-semibold text-green-600 dark:bg-green-500/10 dark:text-green-400">
                            {connectorAuditReport.summary.pass} pass
                          </span>
                          <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-600 dark:bg-amber-500/10 dark:text-amber-400">
                            {connectorAuditReport.summary.blocked} blocked
                          </span>
                          <span className="rounded-md bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-500 dark:bg-red-500/10 dark:text-red-400">
                            {connectorAuditReport.summary.fail} fail
                          </span>
                        </>
                      )}
                      <button
                        onClick={runConnectorAuditMatrix}
                        disabled={connectorAuditLoading || !companyId}
                        className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 disabled:opacity-60 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300 dark:hover:bg-dark-border"
                      >
                        <FontAwesomeIcon icon={connectorAuditLoading ? faSpinner : faClipboardCheck} className={`text-[10px] ${connectorAuditLoading ? "animate-spin" : ""}`} />
                        {connectorAuditLoading ? "Auditing..." : connectorAuditReport ? "Refresh matrix" : "Run matrix"}
                      </button>
                      <button
                        onClick={() => navigate("/evals")}
                        className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/15"
                      >
                        Open Benchmarks
                      </button>
                    </div>
                  </div>
                  {connectorAuditError && (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                      <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-[10px]" />
                      <span>{connectorAuditError}</span>
                    </div>
                  )}
                  <div className="mt-4 grid gap-3 xl:grid-cols-2">
                    {connectorCoverage.map((row) => (
                      <div key={row.spec.key} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{row.spec.name}</p>
                            <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{row.spec.description}</p>
                          </div>
                          <span className={`inline-flex rounded-md border px-2 py-1 text-[10px] font-semibold ${connectorAuditTone(row.audit?.status || (row.connector ? row.connector.status : "missing"))}`}>
                            {row.audit?.status || (row.connector ? row.connector.status : "missing")}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-1.5">
                          <span className="rounded-md border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                            {(row.spec.tasks || []).length} tasks
                          </span>
                          <span className="rounded-md border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                            {row.tools} tools
                          </span>
                          <span className="rounded-md border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                            {row.trajectories} trajectories
                          </span>
                          <span className="rounded-md border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                            {row.skills} skills
                          </span>
                          <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${regressionTone(row.regressionReady > 0 ? "pass" : "")}`}>
                            {row.regressionReady} regression-ready
                          </span>
                          {row.blockedSkills > 0 && (
                            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${regressionTone("fail")}`}>
                              {row.blockedSkills} regression-blocked
                            </span>
                          )}
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                          <div className="rounded-lg border border-gray-200 bg-white px-2 py-2 dark:border-dark-border dark:bg-dark-surface">
                            <p className="text-gray-400">Connector</p>
                            <p className="mt-1 font-semibold text-gray-700 dark:text-gray-200">{row.connector?.name || "Not connected"}</p>
                            <p className="mt-0.5 text-gray-400">{row.connector?.type || (row.spec.connectorTypes || []).join(", ")}</p>
                          </div>
                          <div className="rounded-lg border border-gray-200 bg-white px-2 py-2 dark:border-dark-border dark:bg-dark-surface">
                            <p className="text-gray-400">Runtime</p>
                            {row.audit ? (
                              <p className="mt-1 font-semibold text-gray-700 dark:text-gray-200">
                                {row.audit.live?.passed || 0}/{row.audit.live?.total || 0} live · {row.audit.withSkill?.passed || 0}/{row.audit.withSkill?.total || 0} skill
                              </p>
                            ) : (
                              <p className="mt-1 text-gray-500 dark:text-gray-400">Matrix not run yet.</p>
                            )}
                          </div>
                        </div>
                        <div className="mt-3">
                          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Expected tasks</p>
                          <div className="flex flex-wrap gap-1.5">
                            {row.spec.tasks.map((task) => (
                              <span key={task.key} className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                                {task.requiresBrowser && <FontAwesomeIcon icon={faCircleNodes} className="text-[9px] text-sky-500" />}
                                {task.requiresApproval && <FontAwesomeIcon icon={faShieldHalved} className="text-[9px] text-amber-500" />}
                                {task.name}
                              </span>
                            ))}
                          </div>
                          {row.audit?.reason && (
                            <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">{row.audit.reason}</p>
                          )}
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-200 pt-3 dark:border-dark-border">
                          {row.primaryBlockedSkillId && (
                            <button
                              onClick={() => openCapabilityByRef("skill", row.primaryBlockedSkillId)}
                              className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 text-xs font-semibold text-red-600 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
                            >
                              Fix regression
                            </button>
                          )}
                          {(row.primarySkillId || row.primaryTrajectoryId) && (
                            <button
                              onClick={() => row.primarySkillId
                                ? openCapabilityByRef("skill", row.primarySkillId)
                                : openCapabilityByRef("trajectory", row.primaryTrajectoryId)}
                              className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/15"
                            >
                              {row.primarySkillId ? "Inspect skill" : "Inspect evidence"}
                            </button>
                          )}
                          <button
                            onClick={() => setFactoryScope({
                              view: "trajectories",
                              connectorId: row.connector?.connectorId || "",
                              benchmarkId: row.benchmark?.benchmarkId || "",
                            })}
                            disabled={!row.connector?.connectorId}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 disabled:opacity-60 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-border"
                          >
                            Open trajectories
                          </button>
                          <button
                            onClick={() => row.benchmark
                              ? setFactoryScope({
                                view: "skills",
                                connectorId: row.connector?.connectorId || "",
                                benchmarkId: row.benchmark.benchmarkId,
                              })
                              : navigate("/evals")}
                            className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/15"
                          >
                            {row.benchmark ? "Open skill pipeline" : "Seed benchmark"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(factoryGaps.length > 0 || benchmarkPipeline.length > 0) && (
                <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                  <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Operational gaps</p>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          What is still blocking the factory from turning validated work into governed capabilities.
                        </p>
                      </div>
                      <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 px-2 text-xs font-semibold text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                        {factoryGaps.length}
                      </span>
                    </div>
                    <div className="mt-4 space-y-3">
                      {factoryGaps.length === 0 ? (
                        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 dark:border-green-500/30 dark:bg-green-500/10 dark:text-green-300">
                          No immediate factory gaps detected in the current scope.
                        </div>
                      ) : factoryGaps.map((gap) => (
                        <div key={gap.key} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-gray-900 dark:text-white">{gap.label}</p>
                              <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{gap.hint}</p>
                            </div>
                            <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-lg bg-white px-2 text-xs font-semibold text-gray-700 dark:bg-dark-surface dark:text-gray-200">
                              {gap.count}
                            </span>
                          </div>
                          <button
                            onClick={gap.action}
                            className="mt-3 inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                          >
                            <FontAwesomeIcon icon={faArrowRight} className="text-[10px]" />
                            {gap.actionLabel}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Promotion pipeline</p>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          Benchmark-by-benchmark status from task evidence to reusable skill publication.
                        </p>
                      </div>
                      <button
                        onClick={() => navigate("/evals")}
                        className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                      >
                        <FontAwesomeIcon icon={faClipboardCheck} className="text-[10px]" />
                        Benchmarks
                      </button>
                    </div>
                    <div className="mt-4 space-y-3">
                      {benchmarkPipeline.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                          No benchmark pipeline is visible yet for the current scope.
                        </div>
                      ) : benchmarkPipeline.slice(0, 6).map((row) => (
                        <div key={row.benchmarkId} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{row.name}</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                {row.taskCount} {row.taskCount === 1 ? "task" : "tasks"} · {row.trajectoryCount} trajectories · {row.skillCount} skills
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center justify-end gap-1.5">
                              {row.blockedSkills > 0 && (
                                <span className={`inline-flex items-center rounded-lg border px-2 py-1 text-[10px] font-semibold ${regressionTone("fail")}`}>
                                  Regression blocked
                                </span>
                              )}
                              <span className={`inline-flex items-center rounded-lg border px-2 py-1 text-[10px] font-semibold ${stageTone(row.stage)}`}>
                                {stageLabel(row.stage)}
                              </span>
                            </div>
                          </div>
                          <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                            {[
                              { label: "Tasks", value: row.taskCount },
                              { label: "Pass", value: row.passingCount },
                              { label: "Skills", value: row.skillCount },
                              { label: "Runs", value: row.runCount },
                            ].map((metric) => (
                              <div key={metric.label} className="rounded-lg border border-gray-200 bg-white px-2 py-2 dark:border-dark-border dark:bg-dark-surface">
                                <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">{metric.label}</p>
                                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">{metric.value}</p>
                              </div>
                            ))}
                          </div>
                          {row.gaps.length > 0 && (
                            <div className="mt-3 flex flex-wrap items-center gap-1.5">
                              {row.gaps.map((gap) => (
                                <span key={gap} className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                                  {gap}
                                </span>
                              ))}
                              {row.blockedSkills > 0 && (
                                <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${regressionTone("fail")}`}>
                                  {row.blockedSkills} blocked {row.blockedSkills === 1 ? "skill" : "skills"}
                                </span>
                              )}
                            </div>
                          )}
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            {row.primaryBlockedSkillId && (
                              <button
                                onClick={() => openCapabilityByRef("skill", row.primaryBlockedSkillId)}
                                className="inline-flex h-8 items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 text-xs font-semibold text-red-600 transition-colors hover:bg-red-100 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
                              >
                                Fix regression
                              </button>
                            )}
                            {(row.primarySkillId || row.primaryPromotableTrajectoryId || row.primaryTrajectoryId) && (
                              <button
                                onClick={() => row.primarySkillId
                                  ? openCapabilityByRef("skill", row.primarySkillId)
                                  : openCapabilityByRef("trajectory", row.primaryPromotableTrajectoryId || row.primaryTrajectoryId)}
                                className="inline-flex h-8 items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/15"
                              >
                                {row.primarySkillId ? "Inspect skill" : row.primaryPromotableTrajectoryId ? "Inspect candidate" : "Inspect evidence"}
                              </button>
                            )}
                            <button
                              onClick={() => setFactoryScope({ view: "trajectories", benchmarkId: row.benchmarkId })}
                              className="inline-flex h-8 items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
                            >
                              <FontAwesomeIcon icon={faRoute} className="text-[10px]" />
                              Review evidence
                            </button>
                            <button
                              onClick={() => setFactoryScope({
                                view: row.skillCount > 0 ? "skills" : row.runFailures > 0 ? "runs" : "trajectories",
                                benchmarkId: row.benchmarkId,
                              })}
                              className="inline-flex h-8 items-center gap-2 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
                            >
                              <FontAwesomeIcon icon={row.skillCount > 0 ? faWandMagicSparkles : row.runFailures > 0 ? faTractor : faArrowRight} className="text-[10px]" />
                              {row.skillCount > 0 ? "Open skills" : row.runFailures > 0 ? "Inspect runs" : "Advance pipeline"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

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
                                        (() => {
                                          const toolSessions = runtimeUsage.sessionsByToolId.get(tool.toolId) || [];
                                          const toolApprovals = runtimeUsage.approvalsByToolId.get(tool.toolId) || [];
                                          const toolArtifacts = mergeArtifacts(runtimeUsage.artifactsByToolId.get(tool.toolId) || [], toolSessions);
                                          const pendingToolApprovals = toolApprovals.filter((approval) => approval.status === "pending").length;
                                          return (
                                            <button
                                              key={tool.toolId}
                                              onClick={() => openCapabilityDetail({ kind: "tool", item: tool })}
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
                                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${synthesisTone(tool.toolSynthesis?.readiness?.status)}`}>
                                                  {(tool.toolSynthesis?.readiness?.status || "needs_hardening").replace(/_/g, " ")}
                                                </span>
                                                {tool.surface && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{tool.surface}</span>}
                                                {tool.discoveryScope && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">{tool.discoveryScope}</span>}
                                                {tool.discoveryRelevance?.score !== undefined && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">rel {tool.discoveryRelevance.score}</span>}
                                              </div>
                                              <CapabilityRuntimeSignals
                                                sessionsCount={toolSessions.length}
                                                approvalsCount={toolApprovals.length}
                                                pendingApprovalsCount={pendingToolApprovals}
                                                artifactsCount={toolArtifacts.length}
                                              />
                                              {((tool.inputEntities || []).length > 0 || tool.outputEntity) && (
                                                <div className="mt-2">
                                                  <EntityChips inputEntities={tool.inputEntities} outputEntity={tool.outputEntity} />
                                                </div>
                                              )}
                                            </button>
                                          );
                                        })()
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
                  {view === "trajectories" && filteredTrajectories.length > 0 && (
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
                          const trajectorySessions = runtimeUsage.sessionsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const trajectoryApprovals = runtimeUsage.approvalsByTrajectoryId.get(trajectory.trajectoryId) || [];
                          const trajectoryArtifacts = mergeArtifacts(runtimeUsage.artifactsByTrajectoryId.get(trajectory.trajectoryId) || [], trajectorySessions);
                          const pendingTrajectoryApprovals = trajectoryApprovals.filter((approval) => approval.status === "pending").length;
                          const trajectoryRegression = regression.byTrajectoryId.get(trajectory.trajectoryId);
                          return (
                            <div
                              key={trajectory.trajectoryId}
                              onClick={() => openCapabilityDetail({ kind: "trajectory", item: trajectory })}
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
                                {trajectoryRegression && trajectoryRegression.evalCount > 0 && (
                                  <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${regressionTone(trajectoryRegression.latestLabel)}`}>
                                    regression {trajectoryRegression.latestLabel || "unknown"}
                                  </span>
                                )}
                                {trajectory.harvester?.adapter && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">{humanizeName(trajectory.harvester.adapter)}</span>
                                )}
                                {(trajectory.recoverySteps?.length || 0) > 0 && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">recovery</span>
                                )}
                              </div>
                              <CapabilityRuntimeSignals
                                sessionsCount={trajectorySessions.length}
                                approvalsCount={trajectoryApprovals.length}
                                pendingApprovalsCount={pendingTrajectoryApprovals}
                                artifactsCount={trajectoryArtifacts.length}
                              />
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
                  {view === "trajectories" && filteredTrajectories.length === 0 && (
                    <EmptyState
                      icon={faRoute}
                      title="No trajectories yet"
                      body="Run a harvester against a task benchmark to create concrete trajectories with tool calls and observations."
                      action={<button onClick={openCreate} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faPlus} className="text-xs" />Create Capability</button>}
                    />
                  )}

                  {/* Skills */}
                  {view === "skills" && filteredSkills.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">Skills</p>
                      <div className="flex flex-col gap-3">
                        {filteredSkills.map((skill) => {
                          const originLabel = skillOriginLabel(skill);
                          const skillSessions = runtimeUsage.sessionsBySkillId.get(skill.skillId) || [];
                          const skillApprovals = runtimeUsage.approvalsBySkillId.get(skill.skillId) || [];
                          const skillArtifacts = mergeArtifacts(runtimeUsage.artifactsBySkillId.get(skill.skillId) || [], skillSessions);
                          const pendingSkillApprovals = skillApprovals.filter((approval) => approval.status === "pending").length;
                          const skillRegression = regression.bySkillId.get(skill.skillId);
                          return (
                          <div
                            key={skill.skillId}
                            onClick={() => openCapabilityDetail({ kind: "skill", item: skill })}
                            className="flex flex-col bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-soft hover:-translate-y-0.5 cursor-pointer"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="w-8 h-8 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
                                  <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
                                </span>
                                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{skill.name}</p>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
                                  {skill.versionLabel || `v${skill.version || 1}`}
                                </span>
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${statusTone(skill.promotionStatus || skill.status)}`}>{skillPromotionLabel(skill)}</span>
                              </div>
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
                              {skillRegression && skillRegression.evalCount > 0 && (
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${regressionTone(skillRegression.latestLabel)}`}>
                                  regression {skillRegression.latestLabel || "unknown"}
                                </span>
                              )}
                              {skill.hardeningStatus && (
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${hardeningTone(skill.hardeningStatus.state)}`}>
                                  {hardeningLabel(skill)}
                                </span>
                              )}
                            </div>
                            <CapabilityRuntimeSignals
                              sessionsCount={skillSessions.length}
                              approvalsCount={skillApprovals.length}
                              pendingApprovalsCount={pendingSkillApprovals}
                              artifactsCount={skillArtifacts.length}
                            />
                            {((skill.preconditions || []).length > 0 || (skill.expectedArtifacts || []).length > 0) && (
                              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                                {(skill.preconditions || []).length > 0 && (
                                  <span className="px-2 py-0.5 rounded-md border bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">
                                    {(skill.preconditions || []).length} preconditions
                                  </span>
                                )}
                                {(skill.expectedArtifacts || []).length > 0 && (
                                  <span className="px-2 py-0.5 rounded-md border bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30">
                                    {(skill.expectedArtifacts || []).length} expected artifacts
                                  </span>
                                )}
                              </div>
                            )}
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
                              <span className="text-[11px] text-gray-400">{formatDate(skill.publishedAt || skill.updatedAt || skill.createdAt)}</span>
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
                  {view === "skills" && filteredSkills.length === 0 && (
                    <EmptyState
                      icon={faWandMagicSparkles}
                      title="No skills yet"
                      body="Promote a reliable Skill Candidate, or author a reusable skill manually once that flow is enabled."
                      action={<button onClick={() => setFactoryView("trajectories")} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faRoute} className="text-xs" />View Trajectories</button>}
                    />
                  )}

                  {/* Harvester runs */}
                  {view === "runs" && (
                    filteredRuns.length === 0 ? (
                      <EmptyState
                        icon={faClockRotateLeft}
                        title="No harvester runs yet"
                        body={filteredTrajectories.length > 0
                          ? "There are trajectories, but no UI harvester run record. This can happen when a benchmark was seeded or harvested from a script."
                          : "Runs appear here when a harvester executes a benchmark and produces trajectories."}
                        action={<button onClick={openCreate} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"><FontAwesomeIcon icon={faTractor} className="text-xs" />Run Harvester</button>}
                      />
                    ) : (
                      <div className="space-y-3">
                        {filteredRuns.map((run) => (
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
          trajectories={trajectories}
          trajectoriesById={trajectoriesById}
          connectorsById={connectorsById}
          benchmarkNamesById={benchmarkNamesById}
          regression={regression}
          lineage={lineage}
          runtimeUsage={
              detail.kind === "tool"
                ? {
                    sessions: runtimeUsage.sessionsByToolId.get(detail.item.toolId) || [],
                    approvals: runtimeUsage.approvalsByToolId.get(detail.item.toolId) || [],
                    artifacts: Array.from(new Map([
                      ...(runtimeUsage.artifactsByToolId.get(detail.item.toolId) || []),
                      ...((runtimeUsage.sessionsByToolId.get(detail.item.toolId) || []).flatMap((session) => runtimeUsage.artifactsBySessionId.get(session.sessionId) || [])),
                    ].map((artifact) => [artifact.artifactId, artifact])).values()),
                    workItems: runtimeUsage.workItemsByToolId.get(detail.item.toolId) || [],
                  }
                : detail.kind === "trajectory"
                  ? {
                      sessions: runtimeUsage.sessionsByTrajectoryId.get(detail.item.trajectoryId) || [],
                      approvals: runtimeUsage.approvalsByTrajectoryId.get(detail.item.trajectoryId) || [],
                      artifacts: Array.from(new Map([
                        ...(runtimeUsage.artifactsByTrajectoryId.get(detail.item.trajectoryId) || []),
                        ...((runtimeUsage.sessionsByTrajectoryId.get(detail.item.trajectoryId) || []).flatMap((session) => runtimeUsage.artifactsBySessionId.get(session.sessionId) || [])),
                      ].map((artifact) => [artifact.artifactId, artifact])).values()),
                      workItems: runtimeUsage.workItemsByTrajectoryId.get(detail.item.trajectoryId) || [],
                    }
                  : {
                      sessions: runtimeUsage.sessionsBySkillId.get(detail.item.skillId) || [],
                      approvals: runtimeUsage.approvalsBySkillId.get(detail.item.skillId) || [],
                      artifacts: Array.from(new Map([
                        ...(runtimeUsage.artifactsBySkillId.get(detail.item.skillId) || []),
                        ...((runtimeUsage.sessionsBySkillId.get(detail.item.skillId) || []).flatMap((session) => runtimeUsage.artifactsBySessionId.get(session.sessionId) || [])),
                      ].map((artifact) => [artifact.artifactId, artifact])).values()),
                      workItems: runtimeUsage.workItemsBySkillId.get(detail.item.skillId) || [],
                    }
            }
            userEmail={user.email}
            onOpenSession={(sessionId) => navigate(`/session/${sessionId}`)}
            onOpenApprovals={({ sessionId, skillId, trajectoryId, toolId }) => {
              const params = new URLSearchParams({ status: "all" });
              if (sessionId) params.set("sessionId", sessionId);
              if (skillId) params.set("skillId", skillId);
              if (trajectoryId) params.set("trajectoryId", trajectoryId);
              if (toolId) params.set("toolId", toolId);
              navigate(`/approvals?${params.toString()}`);
            }}
            onOpenArtifacts={({ sessionId, skillId, trajectoryId, toolId }) => {
              const params = new URLSearchParams();
              if (sessionId) params.set("sessionId", sessionId);
              if (skillId) params.set("skillId", skillId);
              if (trajectoryId) params.set("trajectoryId", trajectoryId);
              if (toolId) params.set("toolId", toolId);
              navigate(`/artifacts${params.toString() ? `?${params.toString()}` : ""}`);
            }}
            onOpenWork={({ sessionId, skillId, trajectoryId, toolId, workItemId }) => {
              const params = new URLSearchParams();
              if (workItemId) {
                params.set("item", workItemId);
                navigate(`/work?${params.toString()}`);
                return;
              }
              if (sessionId) params.set("sessionId", sessionId);
              if (skillId) params.set("skillId", skillId);
              if (trajectoryId) params.set("trajectoryId", trajectoryId);
              if (toolId) params.set("toolId", toolId);
              navigate(`/work${params.toString() ? `?${params.toString()}` : ""}`);
            }}
            onOpenRuntime={({ skillId, sessionIds }) => {
              const params = new URLSearchParams();
              if (skillId) params.set("skillId", skillId);
              if (sessionIds && sessionIds.length > 0) params.set("sessionIds", sessionIds.join(","));
              navigate(`/runtime${params.toString() ? `?${params.toString()}` : ""}`);
            }}
            onOpenCapability={openCapabilityDetail}
            onOpenBenchmarkOps={({ mode, benchmarkId }) => {
              const params = new URLSearchParams();
              if (benchmarkId) params.set("benchmark", benchmarkId);
              navigate(`${mode === "runs" ? "/eval-runs" : "/evals"}${params.toString() ? `?${params.toString()}` : ""}`);
            }}
            onReload={loadCapabilities}
            onClose={() => setFactoryScope({
              view: detail.kind === "tool" ? "tools" : detail.kind === "trajectory" ? "trajectories" : "skills",
            })}
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
