import React, { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCircleNodes, faPlus, faSpinner, faTrash, faWrench } from "@fortawesome/free-solid-svg-icons";
import { Connector } from "../utils/types";
import InfoIcon from "../components/common/info-icon";

const apiUrl = process.env.REACT_APP_API_URL;

const CONNECTOR_TYPES = [
  { value: "gmail", label: "Gmail" },
  { value: "holded", label: "Holded" },
  { value: "telegram", label: "Telegram" },
  { value: "web", label: "Web / Browser" },
  { value: "knowledge", label: "Knowledge" },
  { value: "api", label: "OpenAPI / API" },
];

function tone(status: string) {
  if (status === "connected") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (status === "needs_auth") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

export default function Connectors(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState("gmail");

  const loadConnectors = useCallback(async () => {
    if (!user.email || !companyId) {
      setConnectors([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email, companyId });
      const res = await fetch(`${apiUrl}/connectors?${params.toString()}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setConnectors(data.connectors || []);
    } catch (err) {
      console.error("Failed to load connectors:", err);
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const createConnector = async () => {
    if (!user.email || !companyId || saving) return;
    const selected = CONNECTOR_TYPES.find((item) => item.value === type);
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: name.trim() || selected?.label || "Connector",
          type,
          category: type === "knowledge" ? "knowledge" : type === "web" ? "web" : "software",
          description: `${selected?.label || "Connector"} connector for this company.`,
          status: type === "web" || type === "knowledge" ? "connected" : "not_connected",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setName("");
      await loadConnectors();
    } catch (err) {
      console.error("Failed to create connector:", err);
    } finally {
      setSaving(false);
    }
  };

  const deleteConnector = async (connectorId: string) => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors/${connectorId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      await loadConnectors();
    } catch (err) {
      console.error("Failed to delete connector:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Connectors</h1>
            <InfoIcon title="Connectors and Toolkits">
              <p>A Connector belongs to the Company and can be reused by multiple agents. Each connector creates a Toolkit: the actual tools an agent can call, such as Gmail, Holded, BOPA web access, or company knowledge search.</p>
            </InfoIcon>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_180px_auto] gap-3 bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 mb-5">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Connector name, e.g. Gmail, Holded, BOPA"
              className="h-10 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
            />
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="h-10 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
            >
              {CONNECTOR_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button onClick={createConnector} disabled={saving || !companyId} className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
              <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
              Add Connector
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
            </div>
          ) : connectors.length === 0 ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center text-sm text-gray-500 dark:text-gray-400">
              No connectors yet. Add Gmail, Holded, Telegram, BOPA, or Knowledge for this company.
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {connectors.map((connector) => (
                <div key={connector.connectorId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-5">
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FontAwesomeIcon icon={faCircleNodes} className="text-primary text-xs" />
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">{connector.name}</p>
                      </div>
                      <p className="text-xs text-gray-400 dark:text-gray-500">{connector.description || connector.type}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${tone(connector.status)}`}>{connector.status.replace(/_/g, " ")}</span>
                      <button onClick={() => deleteConnector(connector.connectorId)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10">
                        <FontAwesomeIcon icon={faTrash} className="text-xs" />
                      </button>
                    </div>
                  </div>

                  <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4 bg-gray-50 dark:bg-dark-bg">
                    <div className="flex items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2">
                        <FontAwesomeIcon icon={faWrench} className="text-primary text-xs" />
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">{connector.toolkit.name}</p>
                      </div>
                      <span className="text-xs text-gray-400">{connector.toolkit.tools.length} tools</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {connector.toolkit.runtimeRequirements.map((requirement) => (
                        <span key={requirement} className="px-2 py-0.5 rounded-md text-[11px] font-medium border bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
                          {requirement.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                    <div className="space-y-2">
                      {connector.toolkit.tools.map((tool) => (
                        <div key={tool.name} className="flex items-center justify-between gap-3 text-xs">
                          <span className="font-mono text-gray-700 dark:text-gray-200">{tool.name}</span>
                          <span className="text-gray-400">{tool.sideEffects}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
