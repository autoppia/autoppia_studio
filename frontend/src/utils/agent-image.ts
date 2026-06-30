import { AgentConfig } from "./types";

export const CELERIS_AGENT_IMAGE = "https://celeris.ad/favicon.svg";

function normalizedHost(websiteUrl?: string): string {
  if (!websiteUrl) return "";
  try {
    const normalized = websiteUrl.startsWith("http") ? websiteUrl : `https://${websiteUrl}`;
    return new URL(normalized).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return websiteUrl.toLowerCase();
  }
}

export function isCelerisAgent(agent: Pick<AgentConfig, "name" | "websiteUrl">): boolean {
  const name = (agent.name || "").toLowerCase();
  const host = normalizedHost(agent.websiteUrl);
  return name.includes("celeris") || host === "celeris.ad" || host.endsWith(".celeris.ad");
}

export function agentImageUrl(agent: Pick<AgentConfig, "name" | "websiteUrl" | "imageUrl">): string {
  if (agent.imageUrl) return agent.imageUrl;
  if (isCelerisAgent(agent)) return CELERIS_AGENT_IMAGE;

  const host = normalizedHost(agent.websiteUrl);
  if (!host) return CELERIS_AGENT_IMAGE;
  return `https://www.google.com/s2/favicons?sz=128&domain=${encodeURIComponent(host)}`;
}

export function agentHostLabel(websiteUrl?: string): string {
  const host = normalizedHost(websiteUrl);
  return host || "company scope";
}
