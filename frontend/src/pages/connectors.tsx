import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faEnvelope,
  faFileLines,
  faFlask,
  faGlobe,
  faKey,
  faPlus,
  faRotate,
  faSpinner,
  faTrash,
  faWrench,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { Connector } from "../utils/types";
import InfoIcon from "../components/common/info-icon";

const apiUrl = process.env.REACT_APP_API_URL;

const CONNECTOR_TYPES = [
  { value: "gmail", label: "Gmail", category: "email", icon: faEnvelope, logo: "/assets/images/connectors/mail.png" },
  { value: "smtp", label: "SMTP", category: "email", icon: faEnvelope, logo: "/assets/images/connectors/mail.png" },
  { value: "holded", label: "Holded", category: "software", icon: faFileLines },
  { value: "telegram", label: "Telegram", category: "communication", icon: faEnvelope, logo: "/assets/images/connectors/telegram.png" },
  { value: "web", label: "Web / Browser", category: "web", icon: faGlobe },
  { value: "knowledge", label: "Knowledge", category: "knowledge", icon: faFileLines },
  { value: "api", label: "OpenAPI / API", category: "api", icon: faWrench },
];

const STATUS_COPY: Record<string, string> = {
  connected: "Connected",
  needs_auth: "Needs auth",
  not_connected: "Not connected",
};

function tone(status: string) {
  if (status === "connected") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (status === "needs_auth") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function typeMeta(type: string) {
  return CONNECTOR_TYPES.find((item) => item.value === type) || CONNECTOR_TYPES[CONNECTOR_TYPES.length - 1];
}

function ConnectorLogo({ type, className = "w-9 h-9" }: { type: string; className?: string }) {
  const meta = typeMeta(type);
  if (meta.logo) {
    return (
      <span className={`${className} rounded-lg bg-white dark:bg-dark-bg border border-gray-100 dark:border-dark-border flex items-center justify-center flex-shrink-0 overflow-hidden`}>
        <img src={meta.logo} alt="" className="w-full h-full object-contain p-1.5" />
      </span>
    );
  }

  return (
    <span className={`${className} rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0`}>
      <FontAwesomeIcon icon={meta.icon} className="text-sm" />
    </span>
  );
}

function emptyConfig(connector?: Connector | null) {
  const fields = [...(connector?.toolkit.authFields || []), ...(connector?.toolkit.configFields || [])];
  return fields.reduce<Record<string, string>>((acc, field) => {
    acc[field] = String(connector?.config?.[field] || "");
    return acc;
  }, {});
}

export default function Connectors(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("gmail");
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState({ name: "", type: "gmail", description: "", config: {} as Record<string, string> });

  const selected = useMemo(() => connectors.find((connector) => connector.connectorId === selectedId) || null, [connectors, selectedId]);

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

  useEffect(() => {
    if (!selected) return;
    setDraft({
      name: selected.name,
      type: selected.type,
      description: selected.description || "",
      config: emptyConfig(selected),
    });
  }, [selected]);

  const createConnector = async () => {
    if (!user.email || !companyId || saving) return;
    const selectedType = typeMeta(type);
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: name.trim() || selectedType.label,
          type,
          category: selectedType.category,
          description: `${selectedType.label} connector for this company.`,
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

  const updateConnector = async () => {
    if (!selected || saving) return;
    const selectedType = typeMeta(draft.type);
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors/${selected.connectorId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: draft.name.trim() || selectedType.label,
          type: draft.type,
          category: selectedType.category,
          description: draft.description.trim(),
          status: selected.status,
          config: draft.config,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadConnectors();
    } catch (err) {
      console.error("Failed to update connector:", err);
    } finally {
      setSaving(false);
    }
  };

  const testConnector = async (connector: Connector) => {
    if (testingId) return;
    setTestingId(connector.connectorId);
    try {
      if (selected?.connectorId === connector.connectorId) await updateConnector();
      const res = await fetch(`${apiUrl}/connectors/${connector.connectorId}/test`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setConnectors((prev) => prev.map((item) => item.connectorId === connector.connectorId ? data.connector : item));
    } catch (err) {
      console.error("Failed to test connector:", err);
    } finally {
      setTestingId("");
    }
  };

  const deleteConnector = async (connectorId: string) => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors/${connectorId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      if (selectedId === connectorId) setSelectedId("");
      await loadConnectors();
    } catch (err) {
      console.error("Failed to delete connector:", err);
    } finally {
      setSaving(false);
    }
  };

  const configFields = selected ? [...(selected.toolkit.authFields || []), ...(selected.toolkit.configFields || [])] : [];

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
              <div className="space-y-3">
                <p><strong>Connector</strong> belongs to the Company and can be reused by multiple agents.</p>
                <p><strong>Toolkit</strong> is generated from the connector and is what agents actually call: Gmail tools, Holded tools, browser tools, API tools, or knowledge search.</p>
                <p>Configure auth, test the connector, then agents in this company can use its toolkit.</p>
              </div>
            </InfoIcon>
          </div>
          <button onClick={loadConnectors} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface">
            <FontAwesomeIcon icon={faRotate} className="mr-2 text-[10px]" />
            Refresh
          </button>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_190px_auto] gap-3 bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 mb-5">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Connector name, e.g. Gmail, Holded, BOPA"
              className="h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
            />
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
            >
              {CONNECTOR_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button onClick={createConnector} disabled={saving || !companyId} className="h-10 px-4 rounded-lg bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
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
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {connectors.map((connector) => {
                const testing = testingId === connector.connectorId;
                return (
                  <button
                    key={connector.connectorId}
                    onClick={() => setSelectedId(connector.connectorId)}
                    className="text-left bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 hover:border-primary/50 hover:shadow-sm transition-all"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <ConnectorLogo type={connector.type} />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{connector.name}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{connector.toolkit.name}</p>
                        </div>
                      </div>
                      <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border whitespace-nowrap ${tone(connector.status)}`}>
                        {STATUS_COPY[connector.status] || connector.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-4">
                      <span className="text-xs text-gray-400">{connector.toolkit.tools.length} tools</span>
                      <span
                        onClick={(event) => {
                          event.stopPropagation();
                          testConnector(connector);
                        }}
                        className="inline-flex items-center h-7 px-2 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border"
                      >
                        <FontAwesomeIcon icon={testing ? faSpinner : faFlask} className={`mr-1.5 text-[10px] ${testing ? "animate-spin" : ""}`} />
                        Test
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setSelectedId("")} />
          <div className="relative w-full max-w-4xl max-h-[calc(100vh-2rem)] overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl flex flex-col">
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <ConnectorLogo type={selected.type} className="w-8 h-8" />
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white truncate">{selected.name}</h2>
                  <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${tone(selected.status)}`}>{STATUS_COPY[selected.status] || selected.status}</span>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Company connector. Its toolkit can be reused by agents in this company.</p>
              </div>
              <button onClick={() => setSelectedId("")} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border">
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>

            <div className="overflow-auto p-5 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-5">
              <div className="space-y-4">
                <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Connector settings</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input value={draft.name} onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))} className="h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" placeholder="Name" />
                    <select value={draft.type} onChange={(e) => setDraft((prev) => ({ ...prev, type: e.target.value }))} className="h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none">
                      {CONNECTOR_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </select>
                    <textarea value={draft.description} onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))} rows={3} className="sm:col-span-2 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" placeholder="Description" />
                  </div>
                </div>

                <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FontAwesomeIcon icon={faKey} className="text-primary text-xs" />
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">Auth and config</p>
                  </div>
                  {configFields.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">This connector does not require auth fields.</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {configFields.map((field) => {
                        const secret = /token|key|password/i.test(field);
                        return (
                          <label key={field} className="block">
                            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{field}</span>
                            <input
                              type={secret ? "password" : "text"}
                              value={draft.config[field] || ""}
                              onChange={(e) => setDraft((prev) => ({ ...prev, config: { ...prev.config, [field]: e.target.value } }))}
                              className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none"
                            />
                          </label>
                        );
                      })}
                    </div>
                  )}
                  {selected.lastTestMessage && (
                    <p className={`mt-3 text-xs ${selected.lastTestStatus === "pass" ? "text-green-600 dark:text-green-400" : "text-amber-600 dark:text-amber-400"}`}>
                      {selected.lastTestMessage}
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4 bg-gray-50 dark:bg-dark-bg">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2">
                    <FontAwesomeIcon icon={faWrench} className="text-primary text-xs" />
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{selected.toolkit.name}</p>
                  </div>
                  <span className="text-xs text-gray-400">{selected.toolkit.tools.length} tools</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {selected.toolkit.runtimeRequirements.map((requirement) => (
                    <span key={requirement} className="px-2 py-0.5 rounded-md text-[11px] font-medium border bg-white dark:bg-dark-surface text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
                      {requirement.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
                <div className="space-y-2">
                  {selected.toolkit.tools.map((tool) => (
                    <div key={tool.name} className="rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono text-xs text-gray-800 dark:text-gray-100">{tool.name}</span>
                        <span className="text-[11px] text-gray-400">{tool.sideEffects}</span>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tool.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-gray-100 dark:border-dark-border">
              <button onClick={() => deleteConnector(selected.connectorId)} disabled={saving} className="h-9 px-3 rounded-lg border border-red-200 dark:border-red-500/30 text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-60">
                <FontAwesomeIcon icon={faTrash} className="mr-2 text-xs" />
                Delete
              </button>
              <div className="flex items-center gap-2">
                <button onClick={updateConnector} disabled={saving} className="h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
                  {saving ? "Saving..." : "Save"}
                </button>
                <button onClick={() => testConnector(selected)} disabled={!!testingId} className="h-9 px-3 rounded-lg bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60">
                  <FontAwesomeIcon icon={testingId ? faSpinner : faCheck} className={`mr-2 text-xs ${testingId ? "animate-spin" : ""}`} />
                  Save and Test
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
