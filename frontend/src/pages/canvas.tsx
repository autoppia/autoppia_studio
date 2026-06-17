import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircleExclamation,
  faCircleNodes,
  faDiagramProject,
  faPlus,
  faRobot,
  faRoute,
  faSpinner,
} from "@fortawesome/free-solid-svg-icons";

import RuntimeCanvas, { RuntimeAgentNode } from "../components/session/runtime-canvas";
import { AgentConfig } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function agentState(agent: AgentConfig): RuntimeAgentNode["state"] {
  const status = `${agent.status || ""} ${agent.trainingStatus || ""}`.toLowerCase();
  if (status.includes("running") || status.includes("training") || status.includes("progress")) return "running";
  if (status.includes("fail") || status.includes("error")) return "failed";
  if (status.includes("ready") || status.includes("verified") || status.includes("trained") || status.includes("active")) return "done";
  return "idle";
}

function agentActivity(agent: AgentConfig): RuntimeAgentNode["activity"] {
  const tools = agent.runtimeSpec?.tools;
  if (tools?.skills) return "skill";
  if (tools?.connectors || tools?.knowledge) return "tool";
  if (agent.runtimeSpec?.browserEnabled ?? agent.runtimeCapabilities?.browser) return "browser";
  return "tool";
}

function agentDetail(agent: AgentConfig) {
  const taskCount = agent.tasks?.length || 0;
  const runtime = agent.runtimeType || "runtime";
  let target = "company scope";
  try {
    target = agent.websiteUrl ? new URL(agent.websiteUrl).hostname.replace(/^www\./, "") : target;
  } catch {
    target = agent.websiteUrl || target;
  }
  return `${taskCount} task${taskCount === 1 ? "" : "s"} · ${runtime} · ${target}`;
}

function canvasNodes(agents: AgentConfig[]): RuntimeAgentNode[] {
  return agents.map((agent, index) => {
    const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(agents.length))));
    const row = Math.floor(index / columns);
    const col = index % columns;
    const rows = Math.max(1, Math.ceil(agents.length / columns));
    const rowCount = row === rows - 1 ? agents.length - row * columns : columns;
    const x = rowCount === 1 ? 50 : 18 + (col * 64) / Math.max(1, rowCount - 1);
    const y = rows === 1 ? 58 : 48 + (row * 32) / Math.max(1, rows - 1);
    return {
      id: agent.agentId,
      name: agent.name,
      state: agentState(agent),
      activity: agentActivity(agent),
      detail: agentDetail(agent),
      browserEnabled: agent.runtimeSpec?.browserEnabled ?? agent.runtimeCapabilities?.browser ?? Boolean(agent.websiteUrl),
      x,
      y,
    };
  });
}

export default function Canvas(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAgents = useCallback(async () => {
    if (!user.email) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/agents?${params.toString()}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const scopedAgents = companyId
        ? (data.agents || []).filter((agent: AgentConfig) => agent.companyId === companyId)
        : data.agents || [];
      setAgents(scopedAgents);
    } catch (err) {
      console.error("Failed to load canvas agents:", err);
      setError("Could not load company agents.");
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const nodes = useMemo(() => canvasNodes(agents), [agents]);
  const readyCount = nodes.filter((node) => node.state === "done").length;
  const runningCount = nodes.filter((node) => node.state === "running").length;
  const failedCount = nodes.filter((node) => node.state === "failed").length;

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="h-full w-full object-cover" />
      </div>

      <div className="relative flex h-full w-full flex-col">
        <div className="flex h-14 flex-shrink-0 items-center justify-between border-b border-gray-200 bg-white/80 px-6 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-gray-200 bg-white text-gray-700 shadow-soft dark:border-dark-border dark:bg-dark-surface dark:text-gray-200">
              <FontAwesomeIcon icon={faRoute} className="text-sm" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold text-gray-900 dark:text-white">Canvas</h1>
              <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                Router and company agents
              </p>
            </div>
          </div>

          <div className="hidden items-center gap-2 md:flex">
            <span className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 text-xs font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
              <FontAwesomeIcon icon={faRobot} className="text-[11px]" />
              {agents.length} agents
            </span>
            <span className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 text-xs font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
              <FontAwesomeIcon icon={faDiagramProject} className="text-[11px]" />
              {readyCount} ready
            </span>
            {runningCount > 0 && (
              <span className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-sky-300/30 bg-sky-500/10 px-2.5 text-xs font-medium text-sky-600 dark:text-sky-200">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
                {runningCount} running
              </span>
            )}
            {failedCount > 0 && (
              <span className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-300/30 bg-red-500/10 px-2.5 text-xs font-medium text-red-600 dark:text-red-200">
                <FontAwesomeIcon icon={faCircleExclamation} className="text-[11px]" />
                {failedCount} attention
              </span>
            )}
            <button
              onClick={() => navigate("/agents")}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-50 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-border"
            >
              <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
              Agents
            </button>
          </div>
        </div>

        <div className="relative min-h-0 flex-1 p-4 md:p-6">
          {loading ? (
            <div className="flex h-full items-center justify-center rounded-2xl border border-gray-200 bg-white/70 dark:border-dark-border dark:bg-dark-surface/50">
              <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
                <FontAwesomeIcon icon={faSpinner} className="animate-spin text-primary" />
                Loading canvas
              </div>
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center rounded-2xl border border-red-200 bg-red-50 text-sm text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
              {error}
            </div>
          ) : (
            <RuntimeCanvas
              agents={nodes}
              title="Company Router"
              subtitle={agents.length > 0 ? "Company agent network" : "No agents yet"}
              hubLabel="Router"
              minHeight="100%"
              interactive
              showActivityDock={false}
              onAgentClick={(agentId) => navigate(`/agents/${agentId}`)}
              addMenu={
                <div className="p-2">
                  <button
                    type="button"
                    onClick={() => navigate("/agents")}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-zinc-200 transition-colors hover:bg-white/10"
                  >
                    <FontAwesomeIcon icon={faCircleNodes} className="text-xs text-sky-300" />
                    Manage company agents
                  </button>
                </div>
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
