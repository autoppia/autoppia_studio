import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSpinner } from "@fortawesome/free-solid-svg-icons";

import FlowCanvas, { FlowAgent, FlowRunState } from "../components/canvas/flow-canvas";
import { AgentConfig, Company } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function agentState(agent: AgentConfig): FlowRunState {
  const status = `${agent.status || ""} ${agent.trainingStatus || ""}`.toLowerCase();
  if (status.includes("running") || status.includes("training") || status.includes("progress")) return "running";
  if (status.includes("fail") || status.includes("error")) return "failed";
  if (status.includes("ready") || status.includes("verified") || status.includes("trained") || status.includes("active")) return "done";
  return "idle";
}

function agentDetail(agent: AgentConfig): string {
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

const CELERIS_FAVICON = "https://celeris.ad/favicon.svg";

function faviconUrl(websiteUrl?: string): string {
  // Agents with their own site use that site's favicon; otherwise the Celeris brand mark.
  if (websiteUrl) {
    try {
      const normalized = websiteUrl.startsWith("http") ? websiteUrl : `https://${websiteUrl}`;
      const host = new URL(normalized).hostname;
      return `https://www.google.com/s2/favicons?sz=128&domain=${host}`;
    } catch {
      /* fall through to the brand mark */
    }
  }
  return CELERIS_FAVICON;
}

function toFlowAgent(agent: AgentConfig): FlowAgent {
  return {
    id: agent.agentId,
    name: agent.name,
    state: agentState(agent),
    detail: agentDetail(agent),
    browserEnabled: agent.runtimeSpec?.browserEnabled ?? agent.runtimeCapabilities?.browser ?? Boolean(agent.websiteUrl),
    imageUrl: faviconUrl(agent.websiteUrl),
  };
}

export default function Canvas(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [companyName, setCompanyName] = useState("");
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

  const loadCompanyName = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/companies?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) return;
      const data = await res.json();
      const companies: Company[] = data.companies || [];
      const match = companies.find((company) => company.companyId === companyId) || companies[0];
      setCompanyName(match?.name || "");
    } catch (err) {
      console.error("Failed to load company name:", err);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    loadCompanyName();
  }, [loadCompanyName]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const flowAgents = useMemo(() => agents.map(toFlowAgent), [agents]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#0b0913]">
      {/* Layered dark backdrop with depth */}
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="h-full w-full object-cover opacity-50" />
      </div>
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(1100px 560px at 50% -8%, rgba(96,165,250,0.12), transparent 60%), radial-gradient(760px 520px at 10% 95%, rgba(167,139,250,0.10), transparent 58%), radial-gradient(760px 520px at 92% 90%, rgba(34,211,238,0.08), transparent 58%)",
        }}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 90% 80% at 50% 45%, transparent 55%, rgba(0,0,0,0.55) 100%)" }}
      />

      {loading ? (
        <div className="relative flex h-full items-center justify-center">
          <div className="flex items-center gap-3 text-sm text-zinc-400">
            <FontAwesomeIcon icon={faSpinner} className="animate-spin text-primary" />
            Loading canvas
          </div>
        </div>
      ) : error ? (
        <div className="relative flex h-full items-center justify-center">
          <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-5 py-3 text-sm text-red-200">{error}</div>
        </div>
      ) : (
        <div className="relative h-full w-full">
          <FlowCanvas agents={flowAgents} companyName={companyName} />
        </div>
      )}
    </div>
  );
}
