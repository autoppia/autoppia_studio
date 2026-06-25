import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  Handle,
  Position,
  BaseEdge,
  getBezierPath,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type EdgeProps,
  type NodeChange,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faRobot,
  faMousePointer,
  faHand,
  faMagnifyingGlassPlus,
  faMagnifyingGlassMinus,
  faExpand,
  faPlus,
  faGlobe,
  faBrain,
  faArrowsToCircle,
} from "@fortawesome/free-solid-svg-icons";

/**
 * ReactFlow-based company canvas.
 *
 * Brings the Autoppia Studio refactor canvas to Automata Cloud: a CORE hub
 * wired to draggable agent "personas" with animated bezier signal edges, a
 * floating tool dock and a centered add button — powered by @xyflow/react.
 */

export type FlowRunState = "idle" | "running" | "done" | "failed";

export interface FlowAgent {
  id: string;
  name: string;
  state: FlowRunState;
  detail?: string;
  browserEnabled?: boolean;
  imageUrl?: string;
}

interface FlowCanvasProps {
  agents: FlowAgent[];
  companyName: string;
  onAgentClick?: (agentId: string) => void;
}

const STATE_META: Record<
  FlowRunState,
  { label: string; rgb: string; dot: string; text: string }
> = {
  idle: { label: "Idle", rgb: "148,163,184", dot: "bg-zinc-500", text: "text-zinc-400" },
  running: { label: "Running", rgb: "125,211,252", dot: "bg-sky-300", text: "text-sky-200" },
  done: { label: "Ready", rgb: "233,124,60", dot: "bg-primary", text: "text-primary" },
  failed: { label: "Attention", rgb: "248,113,113", dot: "bg-red-400", text: "text-red-200" },
};

/* ------------------------------------------------------------------ */
/* CORE root node — hexagon with the Autoppia logo (no black backing). */
/* ------------------------------------------------------------------ */

const RootNode = memo(function RootNode({ data }: { data: Record<string, unknown> }) {
  const status = (data.status as "ready" | "incomplete" | "busy") || "incomplete";
  const accent = status === "incomplete" ? "#ef4444" : "#E97C3C";
  const spinning = status === "busy";

  return (
    <div className="relative select-none" title="Company router">
      <Handle type="source" id="left" position={Position.Left} className="!h-2.5 !w-2.5 !border-2 !opacity-0" style={{ background: accent, borderColor: accent }} />
      <Handle type="source" id="right" position={Position.Right} className="!h-2.5 !w-2.5 !border-2 !opacity-0" style={{ background: accent, borderColor: accent }} />
      <Handle type="source" id="bottom" position={Position.Bottom} className="!h-2.5 !w-2.5 !border-2 !opacity-0" style={{ background: accent, borderColor: accent }} />

      <div className="flex flex-col items-center">
        {/* Outer glow */}
        <div
          className="pointer-events-none absolute left-1/2 top-[60px] h-52 w-52 -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl animate-pulse-soft"
          style={{ background: `radial-gradient(circle, ${accent}30 0%, transparent 70%)` }}
        />

        <div className="relative flex h-32 w-32 items-center justify-center">
          {/* Rotating dashed border */}
          <svg
            viewBox="0 0 120 120"
            className={`absolute h-32 w-32 ${spinning ? "animate-spin" : ""}`}
            style={{ animationDuration: "30s", filter: `drop-shadow(0 0 16px ${accent}55)` }}
          >
            <defs>
              <linearGradient id="flow-root-border" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor={accent} stopOpacity="0.9" />
                <stop offset="50%" stopColor={accent} stopOpacity="0.4" />
                <stop offset="100%" stopColor={accent} stopOpacity="0.9" />
              </linearGradient>
            </defs>
            <path
              d="M60 5 L105 32.5 L105 87.5 L60 115 L15 87.5 L15 32.5 Z"
              fill="none"
              stroke="url(#flow-root-border)"
              strokeWidth="2"
              strokeDasharray="12 6"
              strokeLinecap="round"
            />
          </svg>

          {/* Inner hexagon */}
          <svg viewBox="0 0 120 120" className="absolute h-28 w-28">
            <defs>
              <linearGradient id="flow-root-fill" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0c1929" />
                <stop offset="100%" stopColor="#0a0f1a" />
              </linearGradient>
              <filter id="flow-root-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <path
              d="M60 12 L98 36 L98 84 L60 108 L22 84 L22 36 Z"
              fill="url(#flow-root-fill)"
              stroke={accent}
              strokeWidth="1.5"
              filter="url(#flow-root-glow)"
            />
          </svg>

          {/* Logo — no black backing, just the mark with a soft glow */}
          <img
            src="/assets/images/logos/main.webp"
            alt="Autoppia"
            className="relative z-10 h-12 w-12 object-contain"
            style={{ filter: "drop-shadow(0 0 10px rgba(33,150,243,0.5))" }}
            draggable={false}
          />
        </div>

        <span className="mt-2.5 text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-400">
          Router
        </span>
      </div>
    </div>
  );
});

/* ------------------------------------------------------------------ */
/* Agent node — a persona: circular avatar + name + status.            */
/* ------------------------------------------------------------------ */

function hashHue(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i += 1) h = (h * 31 + value.charCodeAt(i)) % 360;
  return h;
}

const AgentNode = memo(function AgentNode({ data }: { data: Record<string, unknown> }) {
  const name = String(data.name || "Agent");
  const state = (data.state as FlowRunState) || "idle";
  const detail = data.detail ? String(data.detail) : "";
  const browserOn = data.browserEnabled !== false;
  const imageUrl = data.imageUrl ? String(data.imageUrl) : "";
  const meta = STATE_META[state];
  const running = state === "running";
  const hue = useMemo(() => hashHue(name), [name]);
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = Boolean(imageUrl) && !imgFailed;

  return (
    <div className="group relative flex w-[150px] cursor-pointer flex-col items-center select-none">
      <Handle type="target" id="input-top" position={Position.Top} className="!h-2.5 !w-2.5 !border-2 !border-white/30 !bg-zinc-950 !opacity-0 transition-opacity group-hover:!opacity-100" />
      <Handle type="source" id="output-bottom" position={Position.Bottom} className="!h-2.5 !w-2.5 !border-2 !border-white/30 !bg-zinc-950 !opacity-0 transition-opacity group-hover:!opacity-100" />

      {/* Avatar */}
      <div className="relative">
        {running && (
          <span
            className="pointer-events-none absolute -inset-3 rounded-full blur-xl animate-pulse-soft"
            style={{ background: `radial-gradient(circle, rgba(${meta.rgb},0.45), transparent 70%)` }}
          />
        )}
        {/* status ring */}
        <div
          className={`relative flex h-[68px] w-[68px] items-center justify-center rounded-full p-[2.5px] transition-transform duration-300 group-hover:scale-105 ${running ? "animate-pulse-soft" : ""}`}
          style={{ background: `conic-gradient(from 140deg, rgba(${meta.rgb},0.95), rgba(${meta.rgb},0.25), rgba(${meta.rgb},0.95))` }}
        >
          <div
            className="flex h-full w-full items-center justify-center overflow-hidden rounded-full border border-white/10"
            style={{
              background: showImage
                ? "#0e0c08"
                : `radial-gradient(circle at 35% 30%, hsl(${hue} 70% 55% / 0.55), #0c0a14 72%)`,
              boxShadow: running
                ? `0 0 22px rgba(${meta.rgb},0.5), inset 0 1px 0 rgba(255,255,255,0.15)`
                : "inset 0 1px 0 rgba(255,255,255,0.12), 0 8px 18px rgba(0,0,0,0.45)",
            }}
          >
            {showImage ? (
              <img
                src={imageUrl}
                alt={name}
                className="h-full w-full rounded-full object-cover"
                draggable={false}
                onError={() => setImgFailed(true)}
              />
            ) : (
              <FontAwesomeIcon icon={faRobot} className="text-[22px] text-white/95" />
            )}
          </div>
        </div>

        {/* status dot */}
        <span className={`absolute bottom-0.5 right-0.5 h-4 w-4 rounded-full border-[3px] border-[#0b0913] ${meta.dot} ${running ? "animate-pulse" : ""}`} />

        {/* working glyph */}
        {running && (
          <span className="absolute -right-2 -top-1 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-black/55 text-sky-200 animate-pulse">
            <FontAwesomeIcon icon={faBrain} className="text-[10px]" />
          </span>
        )}
      </div>

      {/* Name */}
      <p className="mt-2.5 max-w-full truncate text-center text-[13px] font-semibold leading-tight text-white">
        {name}
      </p>

      {/* Status line */}
      <div className="mt-1 inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-white/[0.04] px-2 py-0.5">
        <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
        <span className={`text-[9.5px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
        {browserOn && <FontAwesomeIcon icon={faGlobe} className="text-[8px] text-zinc-500" />}
      </div>

      {/* Detail on hover */}
      {detail && (
        <div className="pointer-events-none absolute top-full mt-1.5 max-w-[180px] truncate rounded-lg border border-white/10 bg-black/80 px-2 py-1 text-[9.5px] text-zinc-300 opacity-0 backdrop-blur-sm transition-opacity duration-200 group-hover:opacity-100">
          {detail}
        </div>
      )}
    </div>
  );
});

/* ------------------------------------------------------------------ */
/* Signal edge — animated bezier, cyan→blue→green when active.         */
/* ------------------------------------------------------------------ */

function SignalEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps) {
  const meta = (data || {}) as { active?: boolean; processing?: boolean };
  const active = Boolean(meta.active);
  const processing = Boolean(meta.processing);
  const [edgePath] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const gradId = `flow-edge-${String(id).replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <>
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.25" />
          <stop offset="35%" stopColor="#60a5fa" stopOpacity="0.9" />
          <stop offset="70%" stopColor="#34d399" stopOpacity="0.75" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.25" />
        </linearGradient>
      </defs>

      {/* glow underlay */}
      {active || processing ? (
        <path
          d={edgePath}
          fill="none"
          stroke={processing ? `url(#${gradId})` : "rgba(96,165,250,0.5)"}
          strokeWidth={processing ? 6 : 5}
          opacity={processing ? 0.5 : 0.32}
          strokeLinecap="round"
          style={{ filter: "blur(2px)" }}
        />
      ) : null}

      {processing ? (
        <path d={edgePath} fill="none" stroke={`url(#${gradId})`} strokeWidth={2.4} strokeLinecap="round" strokeDasharray="7 7">
          <animate attributeName="stroke-dashoffset" from="14" to="0" dur="0.8s" repeatCount="indefinite" />
        </path>
      ) : (
        <BaseEdge
          path={edgePath}
          style={{
            stroke: active ? "#60a5fa" : "rgba(120,130,150,0.45)",
            strokeWidth: active ? 2.4 : 1.8,
            opacity: active ? 1 : 0.7,
          }}
        />
      )}
    </>
  );
}

const nodeTypes = { rootNode: RootNode, agentNode: AgentNode };
const edgeTypes = { signal: SignalEdge };

/* ------------------------------------------------------------------ */
/* Layout + persistence                                                */
/* ------------------------------------------------------------------ */

const ROOT_ID = "__root__";
const posKey = (companyName: string) => `automata_canvas_pos_${companyName || "default"}`;

function loadPositions(companyName: string): Record<string, { x: number; y: number }> {
  try {
    return JSON.parse(localStorage.getItem(posKey(companyName)) || "{}");
  } catch {
    return {};
  }
}

const AGENT_W = 150;
const ROOT_W = 128;

function buildLayout(agents: FlowAgent[], companyName: string): Node[] {
  const saved = loadPositions(companyName);
  const cols = Math.max(1, Math.min(5, Math.ceil(Math.sqrt(agents.length || 1))));
  const gapX = 210;
  const gapY = 180;
  const rowCount = Math.min(cols, agents.length || 1);
  // Center the agent row(s) on x=0 (accounting for node width) so the row sits
  // symmetrically under the router. A single agent lands directly below it.
  const rowWidth = (rowCount - 1) * gapX + AGENT_W;
  const startX = -rowWidth / 2;
  const rootY = 0;

  const rootNode: Node = {
    id: ROOT_ID,
    type: "rootNode",
    position: saved[ROOT_ID] || { x: -ROOT_W / 2, y: rootY },
    data: {},
    draggable: true,
    // Keep nodes above the signal edges so links never paint over the cards.
    zIndex: 10,
  };

  const agentNodes: Node[] = agents.map((agent, idx) => {
    const row = Math.floor(idx / cols);
    const col = idx % cols;
    return {
      id: agent.id,
      type: "agentNode",
      position: saved[agent.id] || { x: startX + col * gapX, y: rootY + 220 + row * gapY },
      data: { name: agent.name, state: agent.state, detail: agent.detail, browserEnabled: agent.browserEnabled, imageUrl: agent.imageUrl },
      zIndex: 10,
    };
  });

  return [rootNode, ...agentNodes];
}

/* ------------------------------------------------------------------ */
/* Inner canvas                                                        */
/* ------------------------------------------------------------------ */

type Tool = "select" | "pan";

function CanvasInner({ agents, companyName, onAgentClick }: FlowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges] = useEdgesState<Edge>([]);
  const [tool, setTool] = useState<Tool>("select");
  const [rf, setRf] = useState<ReactFlowInstance<Node, Edge> | null>(null);
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({});

  const ready = agents.length > 0 && agents.every((a) => a.state !== "failed" && a.state !== "idle");
  const busy = agents.some((a) => a.state === "running");
  const rootStatus = busy ? "busy" : ready ? "ready" : "incomplete";

  // Build / refresh nodes when the agent set changes.
  const agentSignature = useMemo(
    () => agents.map((a) => `${a.id}:${a.state}:${a.name}`).join("|"),
    [agents]
  );
  useEffect(() => {
    const next = buildLayout(agents, companyName);
    positionsRef.current = Object.fromEntries(next.map((n) => [n.id, n.position]));
    setNodes(
      next.map((n) =>
        n.id === ROOT_ID ? { ...n, data: { status: rootStatus } } : n
      )
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentSignature, companyName]);

  // Keep root status fresh without relaying out.
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => (n.id === ROOT_ID ? { ...n, data: { status: rootStatus } } : n))
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootStatus]);

  // Edges root → agent.
  useEffect(() => {
    setEdges(
      agents.map((a) => {
        const processing = a.state === "running";
        const active = processing || a.state === "done";
        return {
          id: `e-${a.id}`,
          source: ROOT_ID,
          sourceHandle: "bottom",
          target: a.id,
          targetHandle: "input-top",
          type: "signal",
          data: { active, processing },
          zIndex: 0,
        } as Edge;
      })
    );
  }, [agentSignature, setEdges, agents]);

  const persist = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);
      let dirty = false;
      for (const change of changes) {
        if (change.type === "position" && !change.dragging && change.position) {
          positionsRef.current[change.id] = change.position;
          dirty = true;
        }
      }
      if (dirty) {
        try {
          localStorage.setItem(posKey(companyName), JSON.stringify(positionsRef.current));
        } catch {
          /* ignore */
        }
      }
    },
    [onNodesChange, companyName]
  );

  // Reset positions to the auto grid layout and refocus the view on the canvas.
  const rearrange = useCallback(() => {
    try {
      localStorage.removeItem(posKey(companyName));
    } catch {
      /* ignore */
    }
    const next = buildLayout(agents, companyName);
    positionsRef.current = Object.fromEntries(next.map((n) => [n.id, n.position]));
    setNodes(next.map((n) => (n.id === ROOT_ID ? { ...n, data: { status: rootStatus } } : n)));
    window.setTimeout(() => rf?.fitView({ padding: 0.25, maxZoom: 1.1, duration: 300 }), 60);
  }, [agents, companyName, rootStatus, setNodes, rf]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onInit={setRf}
      onNodesChange={persist}
      onNodeClick={(_e, node) => {
        if (node.id !== ROOT_ID) onAgentClick?.(node.id);
      }}
      panOnDrag={tool === "pan"}
      selectionOnDrag={tool === "select"}
      nodesConnectable={false}
      fitView
      fitViewOptions={{ padding: 0.25, maxZoom: 1.1 }}
      minZoom={0.3}
      maxZoom={2.2}
      proOptions={{ hideAttribution: true }}
      className="bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={26} size={1.4} color="rgba(148,163,184,0.18)" />
      <Controls showZoom={false} showFitView={false} showInteractive={false} className="hidden" />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => (n.type === "rootNode" ? "#E97C3C" : "#60a5fa")}
        maskColor="rgba(0,0,0,0.7)"
        style={{ borderRadius: 12, border: "1px solid rgba(63,63,70,0.5)", background: "rgba(12,10,20,0.85)" }}
      />

      {/* Company panel + work summary — top right */}
      <Panel position="top-right">
        <div className="m-2 w-60 rounded-xl border border-zinc-800/70 bg-zinc-900/85 p-3 shadow-xl shadow-black/30 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-semibold text-white">{companyName || "Company"}</p>
              <p className="text-[11px] text-zinc-400">
                {agents.length} {agents.length === 1 ? "agent" : "agents"}
              </p>
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10px] font-semibold ${
                ready
                  ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-300"
                  : busy
                    ? "border-sky-400/30 bg-sky-500/10 text-sky-200"
                    : "border-zinc-700/60 bg-zinc-800/60 text-zinc-400"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${ready ? "bg-emerald-400" : busy ? "bg-sky-300 animate-pulse" : "bg-zinc-500"}`} />
              {ready ? "Ready" : busy ? "Live" : "Setup"}
            </span>
          </div>
        </div>
      </Panel>

      {/* Tool dock — top left */}
      <Panel position="top-left">
        <div className="m-2 flex flex-col gap-1.5">
          <div className="flex flex-col gap-0.5 rounded-xl border border-zinc-800/60 bg-zinc-900/85 p-1 shadow-lg shadow-black/30 backdrop-blur-sm">
            <ToolButton active={tool === "select"} onClick={() => setTool("select")} icon={faMousePointer} title="Select" />
            <ToolButton active={tool === "pan"} onClick={() => setTool("pan")} icon={faHand} title="Pan" />
          </div>
          <div className="flex flex-col gap-0.5 rounded-xl border border-zinc-800/60 bg-zinc-900/85 p-1 shadow-lg shadow-black/30 backdrop-blur-sm">
            <ToolButton onClick={() => rf?.zoomIn({ duration: 180 })} icon={faMagnifyingGlassPlus} title="Zoom in" />
            <ToolButton onClick={() => rf?.zoomOut({ duration: 180 })} icon={faMagnifyingGlassMinus} title="Zoom out" />
            <ToolButton onClick={() => rf?.fitView({ padding: 0.25, maxZoom: 1.1, duration: 250 })} icon={faExpand} title="Fit view" />
            <ToolButton onClick={rearrange} icon={faArrowsToCircle} title="Re-arrange & refocus" />
          </div>
        </div>
      </Panel>

      {agents.length === 0 && (
        <Panel position="top-center">
          <div className="mt-24 flex flex-col items-center rounded-2xl border border-white/10 bg-black/45 px-7 py-6 text-center shadow-2xl backdrop-blur-md">
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-zinc-300">
              <FontAwesomeIcon icon={faRobot} className="text-base" />
            </div>
            <p className="text-sm font-semibold text-zinc-200">No agents yet</p>
            <p className="mt-1 text-xs text-zinc-500">Add agents to wire them to the company router.</p>
          </div>
        </Panel>
      )}
    </ReactFlow>
  );
}

function ToolButton({
  icon,
  title,
  active,
  onClick,
}: {
  icon: typeof faPlus;
  title: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${
        active ? "bg-white/10 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
      }`}
    >
      <FontAwesomeIcon icon={icon} className="text-[13px]" />
    </button>
  );
}

export default function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
