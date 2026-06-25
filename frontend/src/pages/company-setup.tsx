import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faBolt,
  faBook,
  faBriefcase,
  faCheckCircle,
  faCubes,
  faGear,
  faGlobe,
  faKey,
  faPlug,
  faRobot,
  faTriangleExclamation,
  faWandMagicSparkles,
} from "@fortawesome/free-solid-svg-icons";
import SectionTitle from "../components/layout/section-title";
import InfoIcon from "../components/common/info-icon";
import { Company, CompanySetupContract } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function SummaryCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  hint: string;
  tone?: "neutral" | "good" | "warning";
}) {
  const toneClass = tone === "good"
    ? "border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10"
    : tone === "warning"
      ? "border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10"
      : "border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface";

  return (
    <div className={`rounded-2xl border p-4 ${toneClass}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  );
}

function CountPill({ label, count }: { label: string; count: number }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
      <span className="font-semibold text-gray-800 dark:text-gray-100">{count}</span>
      {label}
    </span>
  );
}

function SurfaceLabel({ value }: { value: string }) {
  const label = value.replace(/_/g, " ");
  const tone = value.includes("browser") || value === "webapp"
    ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300"
    : value.includes("hybrid")
      ? "border-primary/20 bg-primary/10 text-primary"
      : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300";
  return <span className={`inline-flex rounded-md border px-2 py-1 text-[11px] font-medium ${tone}`}>{label}</span>;
}

function statusTone(status: string) {
  if (status === "connected") return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300";
  if (status === "needs_auth") return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300";
  return "border-gray-200 bg-gray-50 text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300";
}

export default function CompanySetup(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [company, setCompany] = useState<Company | null>(null);
  const [contract, setContract] = useState<CompanySetupContract | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const loadSetup = useCallback(async () => {
    if (!user.email) {
      setCompany(null);
      setContract(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const companyParams = new URLSearchParams({ email: user.email });
      const companiesRes = await fetch(`${apiUrl}/companies?${companyParams.toString()}`);
      if (!companiesRes.ok) throw new Error("Could not load companies.");
      const companyData = await companiesRes.json();
      const companies = (companyData.companies || []) as Company[];
      const selected = companies.find((item) => item.companyId === companyId) || companies[0] || null;
      if (!selected) {
        setCompany(null);
        setContract(null);
        setLoading(false);
        return;
      }
      if (!companyId || selected.companyId !== companyId) {
        localStorage.setItem("automata_company_id", selected.companyId);
        setCompanyId(selected.companyId);
      }
      const contractRes = await fetch(`${apiUrl}/companies/${selected.companyId}/setup-contract`);
      if (!contractRes.ok) throw new Error("Could not load company setup contract.");
      const contractData = await contractRes.json();
      setCompany(contractData.company || selected);
      setContract(contractData.contract || null);
    } catch (err: any) {
      console.error("Failed to load company setup:", err);
      setError(err?.message || "Could not load company setup.");
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadSetup();
  }, [loadSetup]);

  const quickActions = useMemo(() => ([
    { label: "Connectors", icon: faPlug, path: "/connectors" },
    { label: "Resources", icon: faBook, path: "/knowledge" },
    { label: "Entities", icon: faCubes, path: "/entities" },
    { label: "Capabilities", icon: faWandMagicSparkles, path: "/capabilities" },
    { label: "Runtime Lab", icon: faBolt, path: "/runtime" },
    { label: "Credentials", icon: faKey, path: "/credentials" },
  ]), []);

  if (loading) {
    return (
      <div className="h-full overflow-auto bg-gray-50/70 px-6 py-6 dark:bg-dark-bg">
        <div className="mx-auto max-w-7xl rounded-3xl border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">
          Loading company setup...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full overflow-auto bg-gray-50/70 px-6 py-6 dark:bg-dark-bg">
        <div className="mx-auto max-w-7xl rounded-3xl border border-red-200 bg-red-50 px-6 py-10 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          <div className="flex items-center gap-3">
            <FontAwesomeIcon icon={faTriangleExclamation} />
            {error}
          </div>
        </div>
      </div>
    );
  }

  if (!company || !contract) {
    return (
      <div className="h-full overflow-auto bg-gray-50/70 px-6 py-6 dark:bg-dark-bg">
        <div className="mx-auto max-w-7xl rounded-3xl border border-dashed border-gray-300 bg-white px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-surface dark:text-gray-400">
          Select or create a company to define its setup contract.
        </div>
      </div>
    );
  }

  const governanceReady = contract.governance.credentials > 0 && contract.systems.summary.connectedConnectors > 0;

  return (
    <div className="h-full overflow-auto bg-gray-50/70 px-6 py-6 dark:bg-dark-bg">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <SectionTitle
                icon={faGear}
                title="Company Setup"
                subtitle="Turn company profile, systems, resources and controls into an explicit integration contract."
              />
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
                  {company.name}
                </span>
                <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  <FontAwesomeIcon icon={faCheckCircle} className="text-[10px]" />
                  Contract v{contract.integrationContractVersion}
                </span>
                {company.industry ? (
                  <span className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                    <FontAwesomeIcon icon={faBriefcase} className="text-[10px]" />
                    {company.industry}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:w-[420px]">
              {quickActions.map((action) => (
                <button
                  key={action.path}
                  type="button"
                  onClick={() => navigate(action.path)}
                  className="flex items-center justify-between rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-left transition-colors hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:bg-dark-bg dark:hover:border-primary/30 dark:hover:bg-primary/10"
                >
                  <span className="inline-flex items-center gap-3 text-sm font-semibold text-gray-800 dark:text-gray-100">
                    <FontAwesomeIcon icon={action.icon} className="text-primary" />
                    {action.label}
                  </span>
                  <FontAwesomeIcon icon={faArrowRight} className="text-xs text-gray-400" />
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <SummaryCard label="Systems" value={contract.systems.summary.totalConnectors} hint={`${contract.systems.summary.connectedConnectors} connected connectors`} tone={contract.systems.summary.connectedConnectors > 0 ? "good" : "warning"} />
          <SummaryCard label="Credentials" value={contract.governance.credentials} hint="Secrets available to connectors and runtimes" tone={contract.governance.credentials > 0 ? "good" : "warning"} />
          <SummaryCard label="Resources" value={contract.context.resources} hint={`${contract.context.entities} entities and ${contract.context.vectorStores} vector stores`} tone={contract.context.resources > 0 ? "good" : "neutral"} />
          <SummaryCard label="Factory" value={contract.factory.skills} hint={`${contract.factory.readySkills} ready skills, ${contract.factory.tools} tools`} tone={contract.factory.readySkills > 0 ? "good" : "neutral"} />
          <SummaryCard label="Runtime" value={contract.runtime.sessions} hint={`${contract.runtime.pendingApprovals} pending approvals`} tone={contract.runtime.pendingApprovals > 0 ? "warning" : "neutral"} />
          <SummaryCard label="Governance" value={governanceReady ? "Ready" : "Needs work"} hint={`${contract.governance.allowedOrigins.length} allowed origins, ${contract.governance.discoveredDomains.length} discovered domains`} tone={governanceReady ? "good" : "warning"} />
        </div>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">Integration Contract</h2>
              <InfoIcon title="Integration contract">
                <div className="space-y-2 text-sm">
                  <p>This is the operating contract for the selected company: access, context, production capabilities, runtime evidence and controls.</p>
                  <p>The goal is to make enterprise readiness legible before any AgentRuntime touches customer systems.</p>
                </div>
              </InfoIcon>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Profile</p>
                <p className="mt-2 text-sm font-semibold text-gray-900 dark:text-white">{contract.profile.name}</p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{contract.profile.description || "No company description yet."}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <CountPill label="status" count={contract.profile.status === "active" ? 1 : 0} />
                  {contract.profile.industry ? <span className="inline-flex rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">{contract.profile.industry}</span> : null}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Governance</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <CountPill label="credentials" count={contract.governance.credentials} />
                  <CountPill label="allowed origins" count={contract.governance.allowedOrigins.length} />
                  <CountPill label="domains" count={contract.governance.discoveredDomains.length} />
                </div>
                <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                  Host JWT: <span className="font-semibold text-gray-800 dark:text-gray-100">{contract.governance.hostJwtConfigured ? "configured" : "not configured"}</span>
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Context</p>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">Resources: <span className="font-semibold text-gray-900 dark:text-white">{contract.context.resources}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Entities: <span className="font-semibold text-gray-900 dark:text-white">{contract.context.entities}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Vector stores: <span className="font-semibold text-gray-900 dark:text-white">{contract.context.vectorStores}</span></p>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Factory</p>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">Tools: <span className="font-semibold text-gray-900 dark:text-white">{contract.factory.tools}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Trajectories: <span className="font-semibold text-gray-900 dark:text-white">{contract.factory.trajectories}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Skills ready: <span className="font-semibold text-gray-900 dark:text-white">{contract.factory.readySkills}</span></p>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Runtime</p>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">Sessions: <span className="font-semibold text-gray-900 dark:text-white">{contract.runtime.sessions}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Pending approvals: <span className="font-semibold text-gray-900 dark:text-white">{contract.runtime.pendingApprovals}</span></p>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Artifacts: <span className="font-semibold text-gray-900 dark:text-white">{contract.runtime.artifacts}</span></p>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Coverage</h2>
            <div className="mt-5 space-y-5">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Connector categories</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {contract.systems.categoryCoverage.length === 0 ? <span className="text-sm text-gray-500 dark:text-gray-400">No connectors yet.</span> : contract.systems.categoryCoverage.map((item) => <CountPill key={`category-${item.name}`} label={item.name} count={item.count} />)}
                </div>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Runtime kinds</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {contract.runtime.runtimeKinds.length === 0 ? <span className="text-sm text-gray-500 dark:text-gray-400">No runtime sessions yet.</span> : contract.runtime.runtimeKinds.map((item) => <CountPill key={`runtime-${item.name}`} label={item.name.replace(/_/g, " ")} count={item.count} />)}
                </div>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Skill policies</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {contract.governance.skillPolicies.length === 0 ? <span className="text-sm text-gray-500 dark:text-gray-400">No published skill policies yet.</span> : contract.governance.skillPolicies.map((item) => <CountPill key={`policy-${item.name}`} label={item.name} count={item.count} />)}
                </div>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Allowed origins</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {contract.governance.allowedOrigins.length === 0 ? <span className="text-sm text-gray-500 dark:text-gray-400">No browser/embed allowlist yet.</span> : contract.governance.allowedOrigins.map((origin) => (
                    <span key={origin} className="inline-flex rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                      {origin}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-gray-200 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">System Access Map</h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Connectors are access. This view makes clear what is connected, what still needs auth and which runtime surface each system drives.</p>
            </div>
            <button
              type="button"
              onClick={() => navigate("/connectors")}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200 dark:hover:bg-dark-surface"
            >
              Open connectors
              <FontAwesomeIcon icon={faArrowRight} className="text-xs" />
            </button>
          </div>
          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            {contract.systems.connectors.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-6 py-10 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                No systems registered yet. Start by connecting the customer software estate here.
              </div>
            ) : contract.systems.connectors.map((connector) => (
              <div key={connector.connectorId} className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{connector.name}</p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{connector.type} · {connector.category} · {connector.provider}</p>
                  </div>
                  <span className={`inline-flex rounded-lg border px-2 py-1 text-[11px] font-medium ${statusTone(connector.status)}`}>
                    {connector.status.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <SurfaceLabel value={connector.surface} />
                  {connector.authRequired ? (
                    <span className="inline-flex rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                      Auth required
                    </span>
                  ) : null}
                  {(connector.runtimeRequirements || []).slice(0, 3).map((requirement) => (
                    <span key={`${connector.connectorId}-${requirement}`} className="inline-flex rounded-md border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                      {requirement}
                    </span>
                  ))}
                </div>
                {connector.domains && connector.domains.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {connector.domains.map((domain) => (
                      <span key={`${connector.connectorId}-${domain}`} className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                        <FontAwesomeIcon icon={faGlobe} className="text-[10px]" />
                        {domain}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
