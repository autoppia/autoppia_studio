import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faCopy,
  faKey,
  faPlus,
  faRotate,
  faShieldHalved,
  faSpinner,
  faTrash,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import InfoIcon from "../components/common/info-icon";
import SelectDropdown from "../components/common/select-dropdown";
import ConfirmModal from "../components/common/confirm-modal";
import { useToast } from "../components/common/toast";
import { apiErrorMessage } from "../utils/api-error";
import { Credential } from "../utils/types";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

const TYPES = [
  { value: "token", label: "Token" },
  { value: "apikey", label: "API Key" },
  { value: "password", label: "Password" },
  { value: "oauth", label: "OAuth" },
];

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Badge({ children, tone = "gray" }: { children: React.ReactNode; tone?: "green" | "blue" | "gray" }) {
  const tones = {
    green: "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30",
    blue: "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30",
    gray: "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border",
  };
  return <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${tones[tone]}`}>{children}</span>;
}

const credentialError = (res: Response, fallback: string) => apiErrorMessage(res, fallback, "this credential");

export default function Credentials(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const { showToast } = useToast();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState("token");
  const [value, setValue] = useState("");
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Credential | null>(null);
  const [rotatingId, setRotatingId] = useState("");
  const [rotationValue, setRotationValue] = useState("");

  const loadCredentials = useCallback(async () => {
    if (!user.email) {
      setCredentials([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/credentials?${params.toString()}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCredentials(data.credentials || []);
    } catch (err) {
      console.error("Failed to load credentials:", err);
      showToast("Failed to load credentials", "error");
    } finally {
      setLoading(false);
    }
  }, [companyId, showToast, user.email]);

  useEffect(() => {
    loadCredentials();
  }, [loadCredentials]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const grouped = useMemo(() => {
    return credentials.reduce<Record<string, Credential[]>>((acc, credential) => {
      const key = credential.createdFor || "generic";
      acc[key] = [...(acc[key] || []), credential];
      return acc;
    }, {});
  }, [credentials]);

  const createCredential = async () => {
    if (!user.email || !name.trim() || !value || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: name.trim(),
          type,
          value,
          createdFor: "manual",
        }),
      });
      if (!res.ok) throw new Error(await credentialError(res, "Could not save credential."));
      setName("");
      setValue("");
      setType("token");
      setIsAddModalOpen(false);
      showToast("Credential saved", "success");
      await loadCredentials();
    } catch (err) {
      console.error("Failed to create credential:", err);
      showToast(err instanceof Error ? err.message : "Failed to save credential", "error");
    } finally {
      setSaving(false);
    }
  };

  const rotateCredential = async (credential: Credential) => {
    if (!rotationValue || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/credentials/${credential.credentialId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: rotationValue }),
      });
      if (!res.ok) throw new Error(await credentialError(res, "Could not rotate credential."));
      setRotatingId("");
      setRotationValue("");
      showToast("Credential rotated", "success");
      await loadCredentials();
    } catch (err) {
      console.error("Failed to rotate credential:", err);
      showToast(err instanceof Error ? err.message : "Failed to rotate credential", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteCredential = async (credential: Credential) => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/credentials/${credential.credentialId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await credentialError(res, "Could not delete credential."));
      setDeleteTarget(null);
      showToast("Credential deleted", "success");
      await loadCredentials();
    } catch (err) {
      console.error("Failed to delete credential:", err);
      showToast(err instanceof Error ? err.message : "Failed to delete credential", "error");
    } finally {
      setSaving(false);
    }
  };

  const copyRef = async (secretRef: string) => {
    await navigator.clipboard.writeText(secretRef);
    showToast("Secret ref copied", "success");
  };

  const closeAddModal = () => {
    if (saving) return;
    setIsAddModalOpen(false);
  };

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Credentials</h1>
            <InfoIcon title="Credentials Vault">
              <div className="space-y-3">
                <p>Credentials are encrypted secrets used by connectors, harvesters and agent runtimes.</p>
                <p>The UI never shows raw values after saving. Connectors reference credentials through stable <strong>secret://</strong> refs.</p>
                <p>Use this page to add shared credentials or rotate values without editing agent logic.</p>
              </div>
            </InfoIcon>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadCredentials} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface">
              <FontAwesomeIcon icon={faRotate} className="mr-2 text-[10px]" />
              Refresh
            </button>
            <button onClick={() => setIsAddModalOpen(true)} className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-medium shadow-sm">
              <FontAwesomeIcon icon={faPlus} className="mr-2 text-[10px]" />
              Add credential
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="rounded-xl border border-blue-100 dark:border-blue-500/20 bg-blue-50 dark:bg-blue-500/10 p-4 mb-5">
            <div className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-lg bg-white dark:bg-dark-surface text-blue-600 dark:text-blue-300 flex items-center justify-center flex-shrink-0">
                <FontAwesomeIcon icon={faShieldHalved} className="text-sm" />
              </span>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Secrets are write-only</p>
                <p className="text-sm leading-6 text-gray-600 dark:text-gray-300">After saving, raw values are encrypted in the backend. Agents and harvesters resolve them internally through secret refs; the browser only sees masked values.</p>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
            </div>
          ) : credentials.length === 0 ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center text-sm text-gray-500 dark:text-gray-400">
              No credentials yet. Add API keys, OAuth tokens or passwords here, then attach them to connectors.
            </div>
          ) : (
            <div className="space-y-5">
              {Object.entries(grouped).map(([group, items]) => (
                <section key={group} className="space-y-3">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-white capitalize">{group.replace(/_/g, " ")}</h2>
                    <Badge>{items.length}</Badge>
                  </div>
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                    {items.map((credential) => (
                      <div key={credential.credentialId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                              <FontAwesomeIcon icon={faKey} className="text-sm" />
                            </span>
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{credential.name}</p>
                              <p className="text-xs font-mono text-gray-400 dark:text-gray-500 truncate">{credential.maskedValue || "configured"}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <Badge tone="blue">{credential.type}</Badge>
                            <Badge tone={credential.configured ? "green" : "gray"}>{credential.configured ? "configured" : "empty"}</Badge>
                          </div>
                        </div>

                        <div className="mt-4 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-xs text-gray-600 dark:text-gray-300 truncate">{credential.secretRef}</span>
                            <button onClick={() => copyRef(credential.secretRef)} className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:bg-white dark:hover:bg-dark-surface" title="Copy secret ref">
                              <FontAwesomeIcon icon={faCopy} className="text-xs" />
                            </button>
                          </div>
                          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-2">Updated {formatDate(credential.updatedAt || credential.createdAt)}</p>
                        </div>

                        {rotatingId === credential.credentialId ? (
                          <div className="mt-3 flex items-center gap-2">
                            <input
                              type="password"
                              value={rotationValue}
                              onChange={(event) => setRotationValue(event.target.value)}
                              placeholder="New secret value"
                              className="flex-1 h-9 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none"
                            />
                            <button onClick={() => rotateCredential(credential)} disabled={saving || !rotationValue} className="h-9 px-3 rounded-lg bg-gradient-primary text-white text-xs font-medium disabled:opacity-60">
                              <FontAwesomeIcon icon={faCheck} className="mr-1.5 text-[10px]" />
                              Save
                            </button>
                          </div>
                        ) : (
                          <div className="mt-3 flex items-center justify-between gap-2">
                            <button onClick={() => { setRotatingId(credential.credentialId); setRotationValue(""); }} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border">
                              Rotate value
                            </button>
                            <button onClick={() => setDeleteTarget(credential)} className="h-8 px-3 rounded-lg border border-red-200 dark:border-red-500/30 text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10">
                              <FontAwesomeIcon icon={faTrash} className="mr-1.5 text-[10px]" />
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {isAddModalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={closeAddModal} />
          <div className="relative w-full max-w-lg mx-4 bg-white dark:bg-dark-surface rounded-2xl shadow-xl border border-gray-200 dark:border-dark-border p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-white">Add credential</h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Save a write-only secret for connectors, harvesters, and agent runtimes.</p>
              </div>
              <button
                onClick={closeAddModal}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border"
                title="Close"
              >
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>

            <div className="mt-5 space-y-4">
              <label className="block">
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300">Name</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Holded production API key"
                  className="mt-1 h-10 w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
                  autoFocus
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300">Type</span>
                <div className="mt-1">
                  <SelectDropdown value={type} onChange={setType} options={TYPES} />
                </div>
              </label>

              <label className="block">
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300">Secret value</span>
                <input
                  type="password"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                  placeholder="Paste secret value"
                  className="mt-1 h-10 w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
                />
              </label>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={closeAddModal}
                className="h-10 px-4 rounded-lg border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border"
              >
                Cancel
              </button>
              <button onClick={createCredential} disabled={saving || !name.trim() || !value} className="h-10 px-4 rounded-lg bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
                <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                Add credential
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <ConfirmModal
          title="Delete credential"
          message={`Delete "${deleteTarget.name}"? Connectors using this secret ref may stop working.`}
          onConfirm={() => deleteCredential(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
