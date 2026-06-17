import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faFlagCheckered,
  faGlobe,
  faMagnifyingGlassMinus,
  faMagnifyingGlassPlus,
  faExpand,
  faPlus,
  faRobot,
  faWandMagicSparkles,
  faWrench,
} from "@fortawesome/free-solid-svg-icons";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import type { ReactNode } from "react";

/**
 * Studio-style runtime canvas.
 *
 * Ports the visual language of the older Autoppia Studio canvas into the
 * Automata Cloud runtime view: a surface that shares the app's dark backdrop,
 * animated signal paths, a black-faced CORE hub, rich glass agent cards, and a
 * pannable / zoomable viewport with a top-right work summary.
 */

export type RuntimeRunState = "idle" | "running" | "done" | "failed";
export type RuntimeActivity = "browser" | "skill" | "tool" | "done";

export interface RuntimeAgentNode {
  id: string;
  name: string;
  state: RuntimeRunState;
  /** Optional image or logo rendered on the canvas node. */
  imageUrl?: string;
  /** Optional persisted canvas position in percentages. */
  x?: number;
  y?: number;
  /** Latest activity surface the agent touched. */
  activity?: RuntimeActivity;
  /** Short status line, e.g. latest action label. */
  detail?: string;
  /** Whether the browser surface is enabled for this agent. */
  browserEnabled?: boolean;
}

export interface RuntimeTimelineStep {
  label: string;
  activity: RuntimeActivity;
  status: "ok" | "failed" | "pending";
}

interface RuntimeCanvasProps {
  agents: RuntimeAgentNode[];
  timeline?: RuntimeTimelineStep[];
  title?: string;
  subtitle?: string;
  hubLabel?: string;
  minHeight?: string;
  interactive?: boolean;
  addMenu?: ReactNode;
  /** Render the bottom "recent activity" dock. Off when the host moves it elsewhere (e.g. the session header). */
  showActivityDock?: boolean;
  onAgentMove?: (agentId: string, position: { x: number; y: number }) => void;
  onAgentClick?: (agentId: string) => void;
}

type PositionedAgent = RuntimeAgentNode & {
  x: number;
  y: number;
};

const ACTIVITY_ICON: Record<RuntimeActivity, IconDefinition> = {
  browser: faGlobe,
  skill: faWandMagicSparkles,
  tool: faWrench,
  done: faFlagCheckered,
};

const STATE_META: Record<RuntimeRunState, { label: string; dot: string; text: string; border: string; glow: string }> = {
  idle: {
    label: "Idle",
    dot: "bg-zinc-500",
    text: "text-zinc-400",
    border: "border-zinc-700/70",
    glow: "rgba(113,113,122,0.10)",
  },
  running: {
    label: "Running",
    dot: "bg-sky-300 animate-pulse",
    text: "text-sky-200",
    border: "border-sky-300/45",
    glow: "rgba(125,211,252,0.24)",
  },
  done: {
    label: "Done",
    dot: "bg-emerald-400",
    text: "text-emerald-200",
    border: "border-emerald-400/35",
    glow: "rgba(52,211,153,0.18)",
  },
  failed: {
    label: "Failed",
    dot: "bg-red-400",
    text: "text-red-200",
    border: "border-red-400/40",
    glow: "rgba(248,113,113,0.20)",
  },
};

const ZOOM_MIN = 0.45;
const ZOOM_MAX = 2.2;
const ZOOM_STEP = 0.2;
const clampZoom = (value: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number(value.toFixed(3))));

function activityLabel(activity?: RuntimeActivity) {
  if (!activity) return "standby";
  return activity;
}

function pathBetween(sourceX: number, sourceY: number, targetX: number, targetY: number) {
  const dy = Math.max(72, Math.abs(targetY - sourceY) * 0.5);
  return `M ${sourceX} ${sourceY} C ${sourceX} ${sourceY + dy}, ${targetX} ${targetY - dy}, ${targetX} ${targetY}`;
}

function useCanvasLayout(agents: RuntimeAgentNode[]): PositionedAgent[] {
  return useMemo(() => {
    if (agents.length === 0) return [];
    if (agents.length === 1) return [{ ...agents[0], x: agents[0].x ?? 50, y: agents[0].y ?? 57 }];

    const count = agents.length;
    const columns = Math.min(4, Math.ceil(Math.sqrt(count)));
    const rows = Math.ceil(count / columns);
    return agents.map((agent, index) => {
      const row = Math.floor(index / columns);
      const col = index % columns;
      const rowCount = row === rows - 1 ? count - row * columns : columns;
      const x = typeof agent.x === "number" ? agent.x : rowCount === 1 ? 50 : 18 + (col * 64) / Math.max(1, rowCount - 1);
      const y = typeof agent.y === "number" ? agent.y : rows === 1 ? 58 : 48 + (row * 34) / Math.max(1, rows - 1);
      return { ...agent, x, y };
    });
  }, [agents]);
}

function CoreHub({ busy, ready, label = "CORE" }: { busy: boolean; ready: boolean; label?: string }) {
  const accent = busy || ready ? "#22c55e" : "#ef4444";

  return (
    <div className="pointer-events-none absolute left-1/2 top-[18%] -translate-x-1/2 -translate-y-1/2 select-none">
      <div
        className="absolute left-1/2 top-1/2 h-56 w-56 -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
        style={{ background: `radial-gradient(circle, ${accent}35 0%, transparent 68%)` }}
      />
      <div className="relative h-36 w-36">
        <svg viewBox="0 0 120 120" className={`absolute inset-0 h-36 w-36 ${busy ? "animate-spin" : ""}`} style={{ animationDuration: "30s" }}>
          <defs>
            <linearGradient id="runtime-root-border" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={accent} stopOpacity="0.95" />
              <stop offset="50%" stopColor={accent} stopOpacity="0.35" />
              <stop offset="100%" stopColor={accent} stopOpacity="0.95" />
            </linearGradient>
          </defs>
          <path
            d="M60 5 L105 32.5 L105 87.5 L60 115 L15 87.5 L15 32.5 Z"
            fill="none"
            stroke="url(#runtime-root-border)"
            strokeWidth="2"
            strokeDasharray="12 6"
            strokeLinecap="round"
          />
        </svg>
        <svg viewBox="0 0 120 120" className="absolute inset-2 h-32 w-32">
          <defs>
            <linearGradient id="runtime-root-fill" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#16131f" />
              <stop offset="100%" stopColor="#0c0a14" />
            </linearGradient>
          </defs>
          <path
            d="M60 12 L98 36 L98 84 L60 108 L22 84 L22 36 Z"
            fill="url(#runtime-root-fill)"
            stroke={accent}
            strokeWidth="1.5"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex h-[72px] w-[72px] items-center justify-center rounded-2xl border border-white/10 bg-black shadow-[0_0_28px_rgba(0,0,0,0.55)]">
            <img src="/assets/images/logos/main.webp" alt="Autoppia" className="h-12 w-12 object-contain" />
          </div>
        </div>
      </div>
      <div className="mt-3 text-center text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-400">
        {label}
      </div>
    </div>
  );
}

function ActivityChip({ activity }: { activity?: RuntimeActivity }) {
  const picked = activity || "tool";
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-lg border border-zinc-700/60 bg-zinc-900/70 px-2 text-[10px] font-medium capitalize text-zinc-300">
      <FontAwesomeIcon icon={ACTIVITY_ICON[picked]} className="text-[10px] text-sky-300" />
      {activityLabel(activity)}
    </span>
  );
}

function CapabilityBadge({ icon, label, on }: { icon: IconDefinition; label: string; on: boolean }) {
  return (
    <span
      className={`inline-flex h-[18px] items-center gap-1 rounded-md border px-1.5 text-[8px] font-semibold uppercase tracking-wide ${
        on
          ? "border-sky-300/25 bg-sky-300/10 text-sky-200"
          : "border-zinc-700/60 bg-zinc-900/50 text-zinc-500"
      }`}
      title={`${label}${on ? "" : " (off)"}`}
    >
      <FontAwesomeIcon icon={icon} className="text-[8px]" />
      {label}
    </span>
  );
}

function AgentAvatar({ node, dot }: { node: PositionedAgent; dot: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [node.imageUrl]);
  const showImage = Boolean(node.imageUrl) && !failed;

  return (
    <div
      className="relative flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-sky-300/20"
      style={{ backgroundColor: showImage ? "#0c0a14" : "rgba(125,211,252,0.10)" }}
    >
      {showImage ? (
        <img
          src={node.imageUrl}
          alt=""
          className="h-full w-full object-cover"
          draggable={false}
          onError={() => setFailed(true)}
        />
      ) : (
        <FontAwesomeIcon icon={faRobot} className="relative z-10 text-base text-white/90" />
      )}
      <span className={`absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-[#0c0a14] ${dot}`} />
    </div>
  );
}

function AgentNode({
  node,
  interactive,
  onPointerDown,
  onClick,
}: {
  node: PositionedAgent;
  interactive?: boolean;
  onPointerDown?: (event: React.PointerEvent<HTMLDivElement>, node: PositionedAgent) => void;
  onClick?: (node: PositionedAgent) => void;
}) {
  const meta = STATE_META[node.state];
  const active = node.state === "running";
  const browserOn = node.browserEnabled !== false;
  const activity = node.activity || "tool";

  return (
    <div
      className={`pointer-events-auto absolute w-[240px] -translate-x-1/2 -translate-y-1/2 ${interactive ? "cursor-grab active:cursor-grabbing" : ""}`}
      style={{ left: `${node.x}%`, top: `${node.y}%` }}
      onPointerDown={(event) => onPointerDown?.(event, node)}
      onClick={() => onClick?.(node)}
    >
      {active && (
        <>
          <div
            className="absolute -inset-5 rounded-[30px] blur-2xl"
            style={{ background: `radial-gradient(ellipse at 50% 50%, ${meta.glow}, transparent 72%)` }}
          />
          <div className="absolute right-4 top-3 z-20 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-black/35 text-sky-100 animate-pulse">
            <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
          </div>
        </>
      )}

      <div
        className={`group relative overflow-hidden rounded-2xl border ${meta.border} bg-[linear-gradient(150deg,rgba(255,255,255,0.06),rgba(18,16,26,0.97)_60%)] p-3.5 shadow-[0_20px_48px_rgba(0,0,0,0.42)] backdrop-blur-md transition-all duration-300`}
        style={{ boxShadow: active ? `0 0 26px ${meta.glow}, 0 18px 44px rgba(0,0,0,0.5)` : undefined }}
      >
        {/* top accent line */}
        <div
          className={`absolute left-0 right-0 top-0 h-[3px] ${active ? "animate-pulse" : ""}`}
          style={{
            background: active
              ? "linear-gradient(90deg,transparent,#7dd3fc,transparent)"
              : node.state === "done"
                ? "linear-gradient(90deg,transparent,rgba(52,211,153,0.55),transparent)"
                : "linear-gradient(90deg,transparent,rgba(148,163,184,0.30),transparent)",
          }}
        />

        <div className="mb-3 flex items-center gap-3">
          <AgentAvatar node={node} dot={meta.dot} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold leading-tight text-white">{node.name}</p>
            <div className="mt-1 flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
              <span className={`text-[10px] font-semibold ${meta.text}`}>{meta.label}</span>
            </div>
          </div>
          <ActivityChip activity={node.activity} />
        </div>

        {/* capability badges */}
        <div className="mb-2.5 flex flex-wrap items-center gap-1">
          <CapabilityBadge icon={faGlobe} label="Browser" on={browserOn} />
          <CapabilityBadge icon={faWandMagicSparkles} label="Skill" on={activity === "skill"} />
          <CapabilityBadge icon={faWrench} label="Tools" on={activity === "tool" || activity === "browser"} />
        </div>

        <p className="truncate rounded-lg border border-zinc-800/70 bg-zinc-950/45 px-2.5 py-1.5 text-[10px] leading-tight text-zinc-400">
          {node.detail || (browserOn ? "Waiting for activity" : "Browser off")}
        </p>
      </div>
    </div>
  );
}

function SignalPaths({ agents }: { agents: PositionedAgent[] }) {
  const rootX = 50;
  const rootY = 27;

  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 100 100">
      <defs>
        <linearGradient id="runtime-signal-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.22" />
          <stop offset="45%" stopColor="#60a5fa" stopOpacity="0.88" />
          <stop offset="78%" stopColor="#a78bfa" stopOpacity="0.70" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.22" />
        </linearGradient>
      </defs>
      {agents.map((agent) => {
        const processing = agent.state === "running";
        const active = processing || agent.state === "done";
        const path = pathBetween(rootX, rootY, agent.x, agent.y - 9);
        return (
          <g key={`signal-${agent.id}`}>
            {active && (
              <path
                d={path}
                fill="none"
                stroke={processing ? "url(#runtime-signal-gradient)" : "rgba(96,165,250,0.42)"}
                strokeWidth={processing ? 1.35 : 1.1}
                opacity={processing ? 0.46 : 0.28}
                strokeLinecap="round"
                filter="blur(0.35px)"
              />
            )}
            <path
              d={path}
              fill="none"
              stroke={processing ? "url(#runtime-signal-gradient)" : active ? "rgba(96,165,250,0.62)" : "rgba(120,130,150,0.42)"}
              strokeWidth={processing ? 0.62 : 0.46}
              strokeDasharray={processing ? "1.5 1.4" : undefined}
              opacity={processing ? 0.95 : 0.70}
              strokeLinecap="round"
            >
              {processing && (
                <animate attributeName="stroke-dashoffset" from="5.8" to="0" dur="0.9s" repeatCount="indefinite" />
              )}
            </path>
          </g>
        );
      })}
    </svg>
  );
}

function ZoomControls({
  zoom,
  onZoomIn,
  onZoomOut,
  onReset,
}: {
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}) {
  return (
    <div className="absolute left-4 top-4 z-20 flex flex-col gap-1.5">
      <div className="flex flex-col overflow-hidden rounded-xl border border-zinc-800/60 bg-zinc-900/85 shadow-lg shadow-black/30 backdrop-blur-sm">
        <button
          onClick={onZoomIn}
          disabled={zoom >= ZOOM_MAX}
          className="flex h-8 w-8 items-center justify-center text-zinc-300 transition-colors hover:bg-white/10 disabled:opacity-30"
          title="Zoom in"
        >
          <FontAwesomeIcon icon={faMagnifyingGlassPlus} className="text-[12px]" />
        </button>
        <div className="px-1 py-0.5 text-center text-[9px] font-semibold tabular-nums text-zinc-400">
          {Math.round(zoom * 100)}%
        </div>
        <button
          onClick={onZoomOut}
          disabled={zoom <= ZOOM_MIN}
          className="flex h-8 w-8 items-center justify-center text-zinc-300 transition-colors hover:bg-white/10 disabled:opacity-30"
          title="Zoom out"
        >
          <FontAwesomeIcon icon={faMagnifyingGlassMinus} className="text-[12px]" />
        </button>
      </div>
      <button
        onClick={onReset}
        className="flex h-8 w-8 items-center justify-center rounded-xl border border-zinc-800/60 bg-zinc-900/85 text-zinc-300 shadow-lg shadow-black/30 backdrop-blur-sm transition-colors hover:bg-white/10"
        title="Fit view"
      >
        <FontAwesomeIcon icon={faExpand} className="text-[11px]" />
      </button>
    </div>
  );
}

function AddAgentMenu({ children }: { children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  if (!children) return null;

  return (
    <div ref={ref} className="absolute bottom-4 left-1/2 z-30 -translate-x-1/2">
      {open && (
        <div className="absolute bottom-14 left-1/2 w-[280px] -translate-x-1/2 overflow-hidden rounded-2xl border border-zinc-800/80 bg-zinc-950/95 shadow-2xl shadow-black/50 backdrop-blur-md">
          {children}
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`flex h-12 w-12 items-center justify-center rounded-2xl border border-sky-300/30 bg-sky-300 text-black shadow-[0_0_28px_rgba(125,211,252,0.35)] transition-transform hover:scale-105 ${open ? "rotate-45" : ""}`}
        title="Add agent"
      >
        <FontAwesomeIcon icon={faPlus} className="text-sm" />
      </button>
    </div>
  );
}

type SummaryTile = { label: string; value: number; tone: string };

/** Compute a compact "summary of work" from the agents + timeline, in the spirit of the top-bar activity tiles. */
function buildWorkSummary(agents: RuntimeAgentNode[], timeline: RuntimeTimelineStep[]): SummaryTile[] {
  const running = agents.filter((a) => a.state === "running").length;
  const done = agents.filter((a) => a.state === "done").length;
  const failed = agents.filter((a) => a.state === "failed").length;
  const browser = agents.filter((a) => a.browserEnabled !== false).length;

  if (timeline.length > 0) {
    const ok = timeline.filter((s) => s.status === "ok").length;
    const failedSteps = timeline.filter((s) => s.status === "failed").length;
    const pending = timeline.filter((s) => s.status === "pending").length;
    return [
      { label: "Steps", value: timeline.length, tone: "text-white" },
      { label: "Done", value: ok, tone: "text-emerald-300" },
      { label: "Active", value: pending, tone: "text-sky-300" },
      { label: "Failed", value: failedSteps, tone: failedSteps ? "text-red-300" : "text-zinc-300" },
      { label: "Agents", value: agents.length, tone: "text-white" },
      { label: "Browser", value: browser, tone: "text-sky-300" },
    ];
  }

  return [
    { label: "Agents", value: agents.length, tone: "text-white" },
    { label: "Running", value: running, tone: running ? "text-sky-300" : "text-zinc-300" },
    { label: "Ready", value: done, tone: "text-emerald-300" },
    { label: "Failed", value: failed, tone: failed ? "text-red-300" : "text-zinc-300" },
    { label: "Browser", value: browser, tone: "text-sky-300" },
    { label: "Signals", value: agents.length, tone: "text-violet-300" },
  ];
}

function WorkSummaryPanel({
  title,
  subtitle,
  agents,
  timeline,
}: {
  title: string;
  subtitle?: string;
  agents: RuntimeAgentNode[];
  timeline: RuntimeTimelineStep[];
}) {
  const running = agents.some((agent) => agent.state === "running");
  const failed = agents.some((agent) => agent.state === "failed");
  const ready = agents.length > 0 && agents.every((agent) => agent.state === "done" || agent.state === "idle");
  const label = running ? "Live" : failed ? "Attention" : ready ? "Ready" : "Empty";
  const tiles = buildWorkSummary(agents, timeline);

  return (
    <div className="absolute right-4 top-4 z-20 w-[280px] max-w-[calc(100%-2rem)] overflow-hidden rounded-xl border border-zinc-800/60 bg-zinc-900/85 shadow-xl shadow-black/30 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-zinc-800/50 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${running ? "bg-sky-300 animate-pulse" : failed ? "bg-red-400" : "bg-emerald-400"}`} />
          <span className="truncate text-[11px] font-semibold text-white">{title}</span>
        </div>
        <span className="rounded-lg border border-zinc-700/50 bg-zinc-800/80 px-2.5 py-1 text-[10px] text-zinc-300">
          {label}
        </span>
      </div>
      {subtitle ? (
        <p className="truncate border-b border-zinc-800/50 px-3 py-2 text-[11px] text-zinc-400">{subtitle}</p>
      ) : null}
      <div className="grid grid-cols-3 gap-1.5 p-2.5">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-lg border border-zinc-800/70 bg-zinc-950/50 px-2 py-1.5">
            <span className={`block text-base font-semibold leading-tight tabular-nums ${tile.tone}`}>{tile.value}</span>
            <span className="block text-[9px] uppercase tracking-wide text-zinc-500">{tile.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Compact recent-activity strip — the last N steps as chips. Exported so a host
 * (e.g. the session header) can render it outside the canvas surface.
 */
export function RecentActivityStrip({
  timeline,
  limit = 5,
  className = "",
}: {
  timeline: RuntimeTimelineStep[];
  limit?: number;
  className?: string;
}) {
  const recent = timeline.slice(-limit);
  if (recent.length === 0) return null;

  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <span className="hidden text-[10px] font-semibold uppercase tracking-[0.16em] text-gray-400 dark:text-zinc-500 lg:inline">
        Recent
      </span>
      {recent.map((step, index) => {
        const statusClass =
          step.status === "ok"
            ? "text-emerald-600 border-emerald-400/30 bg-emerald-500/10 dark:text-emerald-300"
            : step.status === "failed"
              ? "text-red-500 border-red-400/30 bg-red-500/10 dark:text-red-300"
              : "text-sky-600 border-sky-400/30 bg-sky-500/10 dark:text-sky-200";
        return (
          <span
            key={`${step.label}-${index}`}
            className={`inline-flex h-7 max-w-[150px] flex-shrink-0 items-center gap-1.5 rounded-lg border px-2 text-[11px] ${statusClass}`}
            title={step.label}
          >
            <FontAwesomeIcon icon={ACTIVITY_ICON[step.activity]} className={`text-[10px] ${step.status === "pending" ? "animate-pulse" : ""}`} />
            <span className="truncate">{step.label}</span>
          </span>
        );
      })}
    </div>
  );
}

function ActivityDock({ timeline }: { timeline: RuntimeTimelineStep[] }) {
  const recent = timeline.slice(-8);
  if (recent.length === 0) return null;

  return (
    <div className="absolute bottom-4 left-1/2 z-20 w-[min(720px,calc(100%-2rem))] -translate-x-1/2 rounded-2xl border border-zinc-800/60 bg-zinc-900/85 p-2 shadow-2xl shadow-black/40 backdrop-blur-md">
      <div className="mb-1.5 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500">Recent activity</div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {recent.map((step, index) => {
          const statusClass =
            step.status === "ok"
              ? "text-emerald-300 border-emerald-400/20 bg-emerald-500/10"
              : step.status === "failed"
                ? "text-red-300 border-red-400/20 bg-red-500/10"
                : "text-sky-200 border-sky-400/20 bg-sky-500/10";
          return (
            <span
              key={`${step.label}-${index}`}
              className={`inline-flex h-8 min-w-0 flex-shrink-0 items-center gap-1.5 rounded-xl border px-2.5 text-[11px] ${statusClass}`}
            >
              <FontAwesomeIcon icon={ACTIVITY_ICON[step.activity]} className={`text-[10px] ${step.status === "pending" ? "animate-pulse" : ""}`} />
              <span className="max-w-[150px] truncate">{step.label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default function RuntimeCanvas({
  agents,
  timeline = [],
  title = "Runtime",
  subtitle,
  hubLabel = "CORE",
  minHeight = "600px",
  interactive = false,
  addMenu,
  showActivityDock = true,
  onAgentMove,
  onAgentClick,
}: RuntimeCanvasProps) {
  const canvasRef = useRef<HTMLElement | null>(null);
  const [dragging, setDragging] = useState<{ id: string; moved: boolean } | null>(null);
  const positionedAgents = useCanvasLayout(agents);
  const busy = agents.some((agent) => agent.state === "running");
  const ready = agents.length > 0 && agents.every((agent) => agent.state !== "failed");

  // --- Viewport (zoom + pan) ---
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const panOriginRef = useRef<{ startX: number; startY: number; baseX: number; baseY: number } | null>(null);

  const zoomIn = useCallback(() => setZoom((z) => clampZoom(z + ZOOM_STEP)), []);
  const zoomOut = useCallback(() => setZoom((z) => clampZoom(z - ZOOM_STEP)), []);
  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Wheel to zoom (native listener so we can preventDefault without passive warnings).
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const direction = event.deltaY < 0 ? 1 : -1;
      setZoom((z) => clampZoom(z + direction * 0.12));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Drag the empty surface to pan.
  const startPan = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    panOriginRef.current = { startX: event.clientX, startY: event.clientY, baseX: pan.x, baseY: pan.y };
    setPanning(true);
  }, [pan.x, pan.y]);

  useEffect(() => {
    if (!panning) return undefined;
    const handleMove = (event: PointerEvent) => {
      const origin = panOriginRef.current;
      if (!origin) return;
      setPan({ x: origin.baseX + (event.clientX - origin.startX), y: origin.baseY + (event.clientY - origin.startY) });
    };
    const handleUp = () => {
      setPanning(false);
      panOriginRef.current = null;
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [panning]);

  // --- Agent dragging (only when interactive) ---
  const moveAgent = useCallback((event: PointerEvent, agentId: string) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !onAgentMove) return;
    const x = Math.min(90, Math.max(10, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.min(88, Math.max(28, ((event.clientY - rect.top) / rect.height) * 100));
    onAgentMove(agentId, { x, y });
  }, [onAgentMove]);

  useEffect(() => {
    if (!dragging) return undefined;
    const handleMove = (event: PointerEvent) => {
      event.preventDefault();
      setDragging((current) => current ? { ...current, moved: true } : current);
      moveAgent(event, dragging.id);
    };
    const handleUp = () => {
      setTimeout(() => setDragging(null), 0);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [dragging, moveAgent]);

  const handleAgentPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>, node: PositionedAgent) => {
    if (!interactive || !onAgentMove) return;
    event.preventDefault();
    event.stopPropagation();
    setDragging({ id: node.id, moved: false });
  }, [interactive, onAgentMove]);

  const handleAgentClick = useCallback((node: PositionedAgent) => {
    if (dragging?.moved) return;
    onAgentClick?.(node.id);
  }, [dragging?.moved, onAgentClick]);

  return (
    <section
      ref={canvasRef}
      className="relative h-full w-full overflow-hidden rounded-2xl border border-gray-200 bg-gray-50 text-white shadow-[0_24px_70px_rgba(0,0,0,0.30)] dark:border-dark-border dark:bg-dark-bg"
      style={{ minHeight }}
      data-testid="runtime-canvas"
    >
      {/* Shared app backdrop — same treatment as the other sections (dark-bg image in dark mode). */}
      <div className="absolute inset-0 hidden dark:block">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="h-full w-full object-cover opacity-90" />
      </div>
      <div
        className="absolute inset-0 opacity-[0.10] dark:opacity-[0.14]"
        style={{
          backgroundImage: "linear-gradient(rgba(148,163,184,0.20) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.20) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />

      {/* Pan surface — sits behind the scaled content; dragging it pans the viewport. */}
      <div
        className={`absolute inset-0 ${panning ? "cursor-grabbing" : "cursor-grab"}`}
        onPointerDown={startPan}
      />

      {/* Scaled / panned content layer. pointer-events-none so empty space falls through to the pan surface. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
          transformOrigin: "50% 50%",
          transition: panning ? "none" : "transform 0.15s ease-out",
        }}
      >
        <SignalPaths agents={positionedAgents} />
        <CoreHub busy={busy} ready={ready} label={hubLabel} />

        {positionedAgents.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="rounded-3xl border border-white/10 bg-black/55 px-6 py-5 text-center shadow-2xl backdrop-blur-md">
              <p className="text-sm font-semibold text-zinc-200">No agents to show</p>
              <p className="mt-1 text-xs text-zinc-500">Start a session to bind an AgentRuntime.</p>
            </div>
          </div>
        ) : (
          positionedAgents.map((node) => (
            <AgentNode
              key={node.id}
              node={node}
              interactive={interactive}
              onPointerDown={handleAgentPointerDown}
              onClick={handleAgentClick}
            />
          ))
        )}
      </div>

      {/* Fixed overlays (do not scale) */}
      <ZoomControls zoom={zoom} onZoomIn={zoomIn} onZoomOut={zoomOut} onReset={resetView} />
      <WorkSummaryPanel title={title} subtitle={subtitle} agents={agents} timeline={timeline} />
      {showActivityDock && <ActivityDock timeline={timeline} />}
      <AddAgentMenu>{addMenu}</AddAgentMenu>
    </section>
  );
}
