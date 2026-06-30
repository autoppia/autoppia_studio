import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faFileCode,
  faFileCsv,
  faFileLines,
  faFilePdf,
  faFileWord,
  faPlus,
  faSpinner,
  faTrash,
  faTriangleExclamation,
  faXmark,
  faBuilding,
  faDatabase,
  faBook,
  faWrench,
  faRobot,
  faArrowUpRightFromSquare,
  faSliders,
  faCheck,
} from "@fortawesome/free-solid-svg-icons";
import { AgentConfig, KnowledgeDocument, VectorDatabase, VectorIndex } from "../utils/types";
import InfoIcon from "../components/common/info-icon";
import SectionTitle from "../components/layout/section-title";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

function formatSize(size: number) {
  if (!size) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function extOf(filename: string) {
  const parts = filename.split(".");
  return parts.length > 1 ? parts.pop()!.toUpperCase() : "FILE";
}

function resourceSegment(name: string) {
  const cleaned = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned.slice(0, 48) || "knowledge";
}

function generatedKnowledgeTools(name: string) {
  const segment = resourceSegment(name);
  return [
    `knowledge.${segment}.search`,
    `knowledge.${segment}.list_documents`,
    `knowledge.${segment}.stats`,
    `knowledge.${segment}.read_document`,
  ];
}

function toolPurpose(toolName: string) {
  if (toolName.endsWith(".search")) return "Search company resources by semantic similarity.";
  if (toolName.endsWith(".list_documents")) return "List available resources inside this store.";
  if (toolName.endsWith(".stats")) return "Return indexing and document stats.";
  return "Read a referenced resource chunk.";
}

function fileMeta(filename: string, contentType?: string) {
  const ext = (filename.split(".").pop() || "").toLowerCase();
  const ct = (contentType || "").toLowerCase();
  if (ext === "pdf" || ct.includes("pdf")) return { icon: faFilePdf, tint: "bg-red-50 dark:bg-red-500/10 text-red-500" };
  if (ext === "csv" || ct.includes("csv")) return { icon: faFileCsv, tint: "bg-green-50 dark:bg-green-500/10 text-green-600" };
  if (["doc", "docx"].includes(ext) || ct.includes("word")) return { icon: faFileWord, tint: "bg-blue-50 dark:bg-blue-500/10 text-blue-600" };
  if (["json", "xml", "yml", "yaml", "html"].includes(ext) || ct.includes("json")) return { icon: faFileCode, tint: "bg-purple-50 dark:bg-purple-500/10 text-purple-600" };
  return { icon: faFileLines, tint: "bg-primary/10 text-primary" };
}

function statusTone(status: string) {
  const s = (status || "").toLowerCase();
  if (s === "ready" || s === "indexed" || s === "connected") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (s === "error" || s === "failed" || s === "index_failed") return "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30";
  return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
}

function statusLabel(status: string) {
  const s = (status || "").toLowerCase();
  if (s === "indexed" || s === "ready") return "Indexed";
  if (s === "index_failed" || s === "failed" || s === "error") return "Index failed";
  if (s === "indexing" || s === "uploaded") return "Indexing";
  return status || "Stored";
}

const ACCEPT = ".pdf,.md,.markdown,.txt,.csv,.json,.doc,.docx,.html,.xml,.yml,.yaml";

/** Small labelled value used inside the detail modals. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-0.5 text-sm text-gray-900 dark:text-white">{children}</p>
    </div>
  );
}

/** Shared modal shell: backdrop + centered panel with a header row. */
function Modal({
  icon,
  title,
  subtitle,
  onClose,
  children,
  maxWidth = "max-w-lg",
}: {
  icon: typeof faBook;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className={`relative w-full ${maxWidth} max-h-[85vh] overflow-auto rounded-2xl border border-gray-200 bg-white p-5 shadow-xl dark:border-dark-border dark:bg-dark-surface dark:shadow-black/50`}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FontAwesomeIcon icon={icon} className="text-sm" />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-base font-semibold leading-tight text-gray-900 dark:text-white">{title}</h3>
              {subtitle && <p className="truncate text-[11px] leading-tight text-gray-400 dark:text-gray-500">{subtitle}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5"
          >
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Knowledge(): React.ReactElement {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [vectorDatabases, setVectorDatabases] = useState<VectorDatabase[]>([]);
  const [vectorIndex, setVectorIndex] = useState<VectorIndex | null>(null);
  const [selectedVectorDatabaseId, setSelectedVectorDatabaseId] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [showCreateDb, setShowCreateDb] = useState(false);
  const [newDbName, setNewDbName] = useState("");
  const [creatingDb, setCreatingDb] = useState(false);
  const [showStoreDetail, setShowStoreDetail] = useState(false);
  const [detailDocument, setDetailDocument] = useState<KnowledgeDocument | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const loadDocuments = useCallback(async () => {
    if (!user.email || !companyId) {
      setDocuments([]);
      setAgents([]);
      setVectorDatabases([]);
      setVectorIndex(null);
      setSelectedVectorDatabaseId("");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email, companyId });
      const [knowledgeRes, agentsRes] = await Promise.all([
        fetch(`${apiUrl}/knowledge/documents?${params.toString()}`),
        fetch(`${apiUrl}/agents?${params.toString()}`),
      ]);
      if (!knowledgeRes.ok) throw new Error(await knowledgeRes.text());
      const data = await knowledgeRes.json();
      const nextDocuments = data.documents || [];
      const nextVectorDatabases = data.vectorDatabases || [];
      setDocuments(nextDocuments);
      setVectorDatabases(nextVectorDatabases);
      setVectorIndex(data.vectorIndex || null);
      if (agentsRes.ok) {
        const agentsData = await agentsRes.json();
        setAgents(agentsData.agents || []);
      } else {
        setAgents([]);
      }
      setSelectedVectorDatabaseId((current) => {
        if (current && nextVectorDatabases.some((db: VectorDatabase) => db.vectorDatabaseId === current)) return current;
        return nextVectorDatabases[0]?.vectorDatabaseId || "";
      });
    } catch (err) {
      console.error("Failed to load knowledge documents:", err);
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!documents.some((document) => ["indexing", "uploaded"].includes((document.status || "").toLowerCase()))) return;
    const timer = window.setTimeout(() => {
      loadDocuments();
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [documents, loadDocuments]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const uploadFiles = async (files: FileList | File[] | null) => {
    const list = files ? Array.from(files) : [];
    if (!list.length || !user.email || !companyId || uploading) return;
    setUploading(true);
    setError("");
    try {
      for (const file of list) {
        const body = new FormData();
        body.append("email", user.email);
        body.append("companyId", companyId);
        body.append("vectorDatabaseId", selectedVectorDatabaseId);
        body.append("source", "knowledge_page");
        body.append("file", file);
        const res = await fetch(`${apiUrl}/knowledge/documents`, { method: "POST", body });
        if (!res.ok) throw new Error(await res.text());
      }
      await loadDocuments();
    } catch (err: any) {
      console.error("Failed to upload knowledge document:", err);
      setError(err?.message || "Could not upload one or more documents.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const deleteDocument = async (documentId: string) => {
    try {
      const res = await fetch(`${apiUrl}/knowledge/documents/${documentId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setDetailDocument((current) => (current?.documentId === documentId ? null : current));
      await loadDocuments();
    } catch (err: any) {
      console.error("Failed to delete knowledge document:", err);
      setError(err?.message || "Could not delete document.");
    }
  };

  const openCreateVectorDatabase = () => {
    setNewDbName("");
    setShowCreateDb(true);
  };

  const submitCreateVectorDatabase = async () => {
    const name = newDbName.trim();
    if (!name || !user.email || !companyId || creatingDb) return;
    setCreatingDb(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/knowledge/vector-databases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, companyId, name, provider: "local" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      await loadDocuments();
      if (data.vectorDatabase?.vectorDatabaseId) setSelectedVectorDatabaseId(data.vectorDatabase.vectorDatabaseId);
      setShowCreateDb(false);
    } catch (err: any) {
      console.error("Failed to create vector database:", err);
      setError(err?.message || "Could not create vector database.");
    } finally {
      setCreatingDb(false);
    }
  };

  const selectedVectorDatabase = useMemo(
    () => vectorDatabases.find((db) => db.vectorDatabaseId === selectedVectorDatabaseId) || vectorDatabases[0] || null,
    [selectedVectorDatabaseId, vectorDatabases],
  );
  const visibleDocuments = useMemo(
    () => documents.filter((doc) => !selectedVectorDatabase?.vectorDatabaseId || doc.vectorDatabaseId === selectedVectorDatabase.vectorDatabaseId),
    [documents, selectedVectorDatabase],
  );
  const visibleSearchableCount = useMemo(
    () => visibleDocuments.filter((doc) => !["index_failed", "failed", "error"].includes((doc.status || "").toLowerCase())).length,
    [visibleDocuments],
  );
  const consumerAgents = useMemo(
    () => agents.filter((agent) => Boolean(agent.runtimeCapabilities?.knowledge || agent.runtimeSpec?.tools?.knowledge)),
    [agents],
  );
  const resourceTools = useMemo(
    () => selectedVectorDatabase ? generatedKnowledgeTools(selectedVectorDatabase.name) : [],
    [selectedVectorDatabase],
  );

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 flex-shrink-0">
          <SectionTitle
            icon={faBook}
            title="Resources"
            subtitle="Company context your agents can search and cite"
            info={
              <InfoIcon title="Resources">
                <div className="space-y-3">
                  <p>Resources are readable company context, not executable actions. They back the selected company and power its <strong>Knowledge connector</strong>.</p>
                  <p>Upload manuals, policies, price lists and internal notes here. Agents consume them through read-only <strong>knowledge.*</strong> tools.</p>
                  <p className="text-gray-400">Each store becomes a searchable surface: uploads are extracted, chunked, embedded and indexed, then exposed through generated search and read tools. Open a store or a resource to see those details.</p>
                </div>
              </InfoIcon>
            }
          />
          <div className="flex items-center gap-2">
            <button onClick={openCreateVectorDatabase} disabled={!companyId} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors disabled:opacity-60">
              <FontAwesomeIcon icon={faDatabase} className="mr-2 text-[10px]" />
              New store
            </button>
            <button onClick={() => fileInputRef.current?.click()} disabled={uploading || !companyId || !selectedVectorDatabaseId} className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold disabled:opacity-60 transition-opacity">
              <FontAwesomeIcon icon={uploading ? faSpinner : faPlus} className={`mr-2 text-[10px] ${uploading ? "animate-spin" : ""}`} />
              {uploading ? "Adding…" : "Add document"}
            </button>
            <input ref={fileInputRef} type="file" accept={ACCEPT} multiple className="hidden" onChange={(event) => uploadFiles(event.target.files)} />
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-xs" />
              <span className="flex-1">{error}</span>
              <button onClick={() => setError("")} className="text-red-400 hover:text-red-600"><FontAwesomeIcon icon={faXmark} className="text-xs" /></button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
            </div>
          ) : !companyId ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
              <span className="inline-flex w-14 h-14 rounded-2xl bg-gray-100 dark:bg-dark-border items-center justify-center mb-4 text-gray-400">
                <FontAwesomeIcon icon={faBuilding} className="text-xl" />
              </span>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No company selected</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">Create or select a company from the top bar to manage its resources.</p>
            </div>
          ) : (
            <>
              {/* Store selector — pills replace the old wall of store cards. */}
              {vectorDatabases.length > 0 && (
                <div className="mb-5 flex flex-wrap items-center gap-2">
                  {vectorDatabases.map((db) => {
                    const active = db.vectorDatabaseId === selectedVectorDatabase?.vectorDatabaseId;
                    return (
                      <button
                        key={db.vectorDatabaseId}
                        onClick={() => setSelectedVectorDatabaseId(db.vectorDatabaseId)}
                        className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                          active
                            ? "border-primary/40 bg-primary/10 text-primary"
                            : "border-gray-200 bg-white text-gray-600 hover:border-primary/30 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300"
                        }`}
                      >
                        <FontAwesomeIcon icon={faDatabase} className="text-[10px]" />
                        <span className="max-w-[180px] truncate">{db.name}</span>
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${active ? "bg-primary/15 text-primary" : "bg-gray-100 text-gray-400 dark:bg-dark-bg"}`}>
                          {db.documentCount || 0}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Selected store — one calm context bar. Detail lives in the modal. */}
              {selectedVectorDatabase && (
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <FontAwesomeIcon icon={faDatabase} className="text-sm" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{selectedVectorDatabase.name}</p>
                      <p className="truncate text-[11px] text-gray-400">
                        {visibleDocuments.length} resources · {visibleSearchableCount} searchable · {selectedVectorDatabase.connectorId ? "4 tools" : "tools missing"}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setShowStoreDetail(true)}
                    className="inline-flex h-8 flex-shrink-0 items-center gap-2 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
                  >
                    <FontAwesomeIcon icon={faSliders} className="text-[11px]" />
                    Store details
                  </button>
                </div>
              )}

              {/* Documents */}
              {visibleDocuments.length === 0 ? (
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
                  <span className="inline-flex w-14 h-14 rounded-2xl bg-primary/10 items-center justify-center mb-4 text-primary">
                    <FontAwesomeIcon icon={faFileLines} className="text-xl" />
                  </span>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No resources yet</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-5">
                    Upload manuals, policies, price lists or internal notes into {selectedVectorDatabase?.name || "this store"}.
                  </p>
                  <button onClick={() => fileInputRef.current?.click()} disabled={!selectedVectorDatabaseId} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60">
                    <FontAwesomeIcon icon={faPlus} className="text-xs" />
                    Add your first document
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
                  {visibleDocuments.map((document) => {
                    const meta = fileMeta(document.filename, document.contentType);
                    const status = (document.status || "").toLowerCase();
                    return (
                      <button
                        key={document.documentId}
                        onClick={() => setDetailDocument(document)}
                        className="group text-left bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 hover:border-primary/40 hover:shadow-soft transition-all duration-200"
                      >
                        <div className="flex items-start gap-3">
                          <span className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${meta.tint}`}>
                            <FontAwesomeIcon icon={meta.icon} className="text-base" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={document.filename}>{document.filename}</p>
                            <p className="text-[11px] text-gray-400 mt-0.5">{extOf(document.filename)} · {formatSize(document.size)}</p>
                          </div>
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={(event) => { event.stopPropagation(); deleteDocument(document.documentId); }}
                            onKeyDown={(event) => { if (event.key === "Enter") { event.stopPropagation(); deleteDocument(document.documentId); } }}
                            className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center justify-center flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Delete resource"
                          >
                            <FontAwesomeIcon icon={faTrash} className="text-xs" />
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 dark:border-dark-border">
                          <span className="text-[11px] text-gray-400">{formatDate(document.createdAt)}</span>
                          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${statusTone(document.status)}`}>
                            {statusLabel(document.status)}
                          </span>
                        </div>
                        {["indexing", "uploaded"].includes(status) && (
                          <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-2 truncate">Preparing this resource for search…</p>
                        )}
                        {["index_failed", "failed", "error"].includes(status) && (
                          <p className="text-[10px] text-red-500 mt-2 truncate">Stored but not searchable yet.</p>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Create store modal */}
      {showCreateDb && (
        <Modal
          icon={faDatabase}
          title="New store"
          subtitle="A searchable index that holds your company resources"
          onClose={() => !creatingDb && setShowCreateDb(false)}
        >
          <label className="mb-1.5 block text-xs font-medium text-gray-500 dark:text-gray-400">Name</label>
          <input
            autoFocus
            value={newDbName}
            onChange={(e) => setNewDbName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitCreateVectorDatabase(); }}
            placeholder="e.g. Product manuals"
            className="h-10 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm text-gray-900 outline-none focus:border-primary/50 dark:border-zinc-800/80 dark:bg-zinc-950/70 dark:text-white"
          />

          <div className="mt-3 flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-dark-border dark:bg-zinc-950/50">
            <FontAwesomeIcon icon={faDatabase} className="text-[11px] text-gray-400" />
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              Provider <span className="font-medium text-gray-700 dark:text-gray-300">Local</span> — resources are embedded and indexed here.
            </span>
          </div>

          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setShowCreateDb(false)}
              disabled={creatingDb}
              className="h-9 rounded-xl border border-gray-200 px-4 text-sm font-medium text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              onClick={submitCreateVectorDatabase}
              disabled={creatingDb || !newDbName.trim()}
              className="inline-flex h-9 items-center gap-2 rounded-xl bg-gradient-primary px-4 text-sm font-semibold text-white shadow-glow disabled:opacity-60"
            >
              {creatingDb ? <FontAwesomeIcon icon={faSpinner} className="animate-spin text-xs" /> : <FontAwesomeIcon icon={faPlus} className="text-[10px]" />}
              Create
            </button>
          </div>
        </Modal>
      )}

      {/* Store detail modal — holds index, generated tools, links and consumers. */}
      {showStoreDetail && selectedVectorDatabase && (
        <Modal
          icon={faDatabase}
          title={selectedVectorDatabase.name}
          subtitle="Resource store details"
          maxWidth="max-w-2xl"
          onClose={() => setShowStoreDetail(false)}
        >
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Field label="Provider">{selectedVectorDatabase.provider || vectorIndex?.provider || "local"}</Field>
              <Field label="Collection">{selectedVectorDatabase.collectionName || vectorIndex?.collectionName || (companyId ? `company-${companyId}` : "company")}</Field>
              <Field label="Embeddings">
                {selectedVectorDatabase.embeddingProvider || "hash"} · {selectedVectorDatabase.embeddingModel || "hash-256"}
              </Field>
              <Field label="Resources">{visibleDocuments.length}</Field>
              <Field label="Searchable">{visibleSearchableCount}</Field>
              <Field label="Tools">{selectedVectorDatabase.connectorId ? "4 ready" : "Missing"}</Field>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <FontAwesomeIcon icon={faWrench} className="text-primary text-xs" />
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Generated tools</h4>
              </div>
              <p className="mt-1 text-[11px] text-gray-400">Read-only knowledge tools exposed inside Factory and Runtime. Context surfaces, not business actions.</p>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {resourceTools.map((toolName) => (
                  <div key={toolName} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-dark-border dark:bg-dark-bg">
                    <p className="font-mono text-xs text-gray-800 dark:text-gray-100">{toolName}</p>
                    <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{toolPurpose(toolName)}</p>
                  </div>
                ))}
              </div>
            </div>

            {consumerAgents.length > 0 && (
              <div>
                <div className="flex items-center gap-2">
                  <FontAwesomeIcon icon={faRobot} className="text-primary text-xs" />
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Agents consuming resources</h4>
                </div>
                <p className="mt-1 text-[11px] text-gray-400">AgentRuntimes with knowledge enabled can query this surface through the generated tools.</p>
                <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {consumerAgents.map((agent) => (
                    <button
                      key={agent.agentId}
                      onClick={() => navigate(`/agents/${agent.agentId}`)}
                      className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-left transition-colors hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:bg-dark-bg"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{agent.name}</p>
                        <p className="mt-0.5 text-[11px] text-gray-400">{agent.runtimeType || "agent runtime"} · knowledge enabled</p>
                      </div>
                      <FontAwesomeIcon icon={faArrowUpRightFromSquare} className="text-[10px] text-gray-400" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 border-t border-gray-100 pt-4 dark:border-dark-border">
              {selectedVectorDatabase.connectorId && (
                <button
                  onClick={() => navigate(`/capabilities?view=tools&connector=${encodeURIComponent(selectedVectorDatabase.connectorId || "")}`)}
                  className="h-8 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white"
                >
                  Inspect in Factory
                </button>
              )}
              {selectedVectorDatabase.connectorId && (
                <button
                  onClick={() => navigate(`/capabilities?view=runs&connector=${encodeURIComponent(selectedVectorDatabase.connectorId || "")}`)}
                  className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
                >
                  Harvester runs
                </button>
              )}
              <button
                onClick={() => navigate("/runtime")}
                className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
              >
                Open Workspace
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Document detail modal — holds the governance contract that used to clutter cards. */}
      {detailDocument && (() => {
        const meta = fileMeta(detailDocument.filename, detailDocument.contentType);
        const contract = detailDocument.resourceContract;
        const gov = contract?.governance;
        const gate = contract?.resourceGate;
        const readTools = (contract?.readTools && contract.readTools.length > 0)
          ? contract.readTools
          : (selectedVectorDatabase ? generatedKnowledgeTools(detailDocument.vectorDatabaseName || selectedVectorDatabase.name) : []);
        return (
          <Modal
            icon={meta.icon}
            title={detailDocument.filename}
            subtitle={`${extOf(detailDocument.filename)} · ${formatSize(detailDocument.size)} · ${detailDocument.vectorDatabaseName || selectedVectorDatabase?.name || "Knowledge"}`}
            maxWidth="max-w-xl"
            onClose={() => setDetailDocument(null)}
          >
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Field label="Status">
                  <span className={`inline-block rounded-md border px-2 py-0.5 text-[10px] font-medium ${statusTone(detailDocument.status)}`}>
                    {statusLabel(detailDocument.status)}
                  </span>
                </Field>
                <Field label="Uploaded">{formatDate(detailDocument.createdAt)}</Field>
                {detailDocument.source && <Field label="Source">{detailDocument.source.replace(/_/g, " ")}</Field>}
                {contract && <Field label="Kind">{contract.resourceKind || "document"}</Field>}
                {contract && <Field label="Access">{contract.readOnly ? "read-only" : "mutable"}</Field>}
                {gov?.versioning && <Field label="Version">{gov.versioning.versionLabel || `v${gov.versioning.version || 1}`}</Field>}
                {gov?.acl && <Field label="Visibility">{gov.acl.visibility || "company"}</Field>}
                {gov?.citability && <Field label="Citable">{gov.citability.citable ? "Yes" : "Not yet"}</Field>}
                {gov?.freshness && <Field label="Freshness">{gov.freshness.status || (gov.freshness.stale ? "stale" : "current")}</Field>}
              </div>

              {readTools.length > 0 && (
                <div>
                  <div className="flex items-center gap-2">
                    <FontAwesomeIcon icon={faWrench} className="text-primary text-xs" />
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Read tools</h4>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {readTools.map((toolName) => (
                      <span key={toolName} className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-[11px] text-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-gray-200">
                        {toolName}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {gate && (
                <div className={`rounded-xl border p-3 ${gate.readyForRuntime ? "border-green-200 bg-green-50 dark:border-green-500/30 dark:bg-green-500/10" : "border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10"}`}>
                  <div className="flex items-center gap-2">
                    <FontAwesomeIcon icon={gate.readyForRuntime ? faCheck : faTriangleExclamation} className={`text-xs ${gate.readyForRuntime ? "text-green-600" : "text-amber-600"}`} />
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                      {gate.readyForRuntime ? "Runtime-ready" : `Not ready · ${gate.state || "blocked"}`}
                    </h4>
                  </div>
                  {!gate.readyForRuntime && (gate.blockers?.length || gate.nextActions?.length) ? (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-[11px] text-gray-600 dark:text-gray-300">
                      {(gate.nextActions && gate.nextActions.length > 0 ? gate.nextActions : gate.blockers || []).map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}

              <div className="flex justify-end gap-2 border-t border-gray-100 pt-4 dark:border-dark-border">
                <button
                  onClick={() => deleteDocument(detailDocument.documentId)}
                  className="inline-flex h-9 items-center gap-2 rounded-xl border border-red-200 px-4 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-500/30 dark:hover:bg-red-500/10"
                >
                  <FontAwesomeIcon icon={faTrash} className="text-xs" />
                  Delete
                </button>
                <button
                  onClick={() => setDetailDocument(null)}
                  className="h-9 rounded-xl border border-gray-200 px-4 text-sm font-medium text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5"
                >
                  Close
                </button>
              </div>
            </div>
          </Modal>
        );
      })()}
    </div>
  );
}
