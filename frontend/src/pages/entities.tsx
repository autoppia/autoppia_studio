import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRightLong,
  faBuilding,
  faChevronDown,
  faCircleInfo,
  faCode,
  faCube,
  faDiagramProject,
  faKey,
  faList,
  faMagnifyingGlass,
  faPenToSquare,
  faPlugCircleBolt,
  faPlus,
  faShareNodes,
  faSpinner,
  faTrash,
  faTriangleExclamation,
  faWandMagicSparkles,
  faXmark,
  faRobot,
  faArrowUpRightFromSquare,
} from "@fortawesome/free-solid-svg-icons";
import { AgentConfig, CompanySkill, CompanyTool, Connector, EntityField, EntityModel, EntityRelationship } from "../utils/types";
import InfoIcon from "../components/common/info-icon";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type EntitiesTab = "list" | "graph";

function formatDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function sourceTone(source?: string) {
  const s = (source || "manual").toLowerCase();
  if (s === "openapi") return "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30";
  if (s === "llm_mapper") return "bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-300 border-purple-200 dark:border-purple-500/30";
  if (s === "imported") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

async function responseErrorMessage(res: Response, fallback: string) {
  const text = await res.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (typeof parsed?.message === "string") return parsed.message;
    return fallback;
  } catch {
    return text.trim().startsWith("{") ? fallback : text;
  }
}

/** Parse a textarea of JSON into a typed array, tolerating empty input. */
function parseJsonArray<T>(raw: string): { value: T[]; error: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { value: [], error: "" };
  try {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) return { value: [], error: "Expected a JSON array." };
    return { value: parsed as T[], error: "" };
  } catch (err: any) {
    return { value: [], error: err?.message || "Invalid JSON." };
  }
}

const FIELDS_PLACEHOLDER = `[
  { "name": "id", "type": "string", "role": "identifier", "required": true },
  { "name": "title", "type": "string", "role": "display" }
]`;

const RELATIONSHIPS_PLACEHOLDER = `[
  { "name": "owner", "kind": "belongsTo", "target": "User", "via": "ownerId" }
]`;

function EntityFormModal({
  initial,
  saving,
  onClose,
  onSubmit,
}: {
  initial: EntityModel | null;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    name: string;
    description: string;
    fields: EntityField[];
    relationships: EntityRelationship[];
    sourceConnectorId: string;
    source: string;
  }) => void;
}) {
  const editing = Boolean(initial);
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [sourceConnectorId, setSourceConnectorId] = useState(initial?.sourceConnectorId || "");
  const [source, setSource] = useState(initial?.source || "manual");
  const [fieldsText, setFieldsText] = useState(
    initial?.fields?.length ? JSON.stringify(initial.fields, null, 2) : "",
  );
  const [relationshipsText, setRelationshipsText] = useState(
    initial?.relationships?.length ? JSON.stringify(initial.relationships, null, 2) : "",
  );
  const [error, setError] = useState("");

  const handleSubmit = () => {
    const cleanName = name.trim();
    if (!cleanName) {
      setError("Name is required.");
      return;
    }
    const fields = parseJsonArray<EntityField>(fieldsText);
    if (fields.error) {
      setError(`Fields: ${fields.error}`);
      return;
    }
    const relationships = parseJsonArray<EntityRelationship>(relationshipsText);
    if (relationships.error) {
      setError(`Relationships: ${relationships.error}`);
      return;
    }
    setError("");
    onSubmit({
      name: cleanName,
      description: description.trim(),
      fields: fields.value,
      relationships: relationships.value,
      sourceConnectorId: sourceConnectorId.trim(),
      source: (source || "manual").trim(),
    });
  };

  const inputClass =
    "w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all";
  const textareaClass =
    "w-full rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-xs font-mono leading-5 text-gray-900 dark:text-white outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all resize-y";

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[88vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl flex flex-col">
        <div className="h-14 px-5 border-b border-gray-200 dark:border-dark-border flex items-center justify-between gap-3 flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-8 h-8 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={faCube} className="text-xs" />
            </span>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
              {editing ? "Edit entity" : "New entity"}
            </h3>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border">
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <div className="overflow-auto p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} placeholder="e.g. Invoice" autoFocus />
            </label>
            <label className="block">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Source</span>
              <input value={source} onChange={(e) => setSource(e.target.value)} className={inputClass} placeholder="manual" />
            </label>
          </div>

          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className={textareaClass.replace("font-mono", "")} placeholder="What this entity represents." />
          </label>

          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Source connector ID <span className="text-gray-400">(optional)</span></span>
            <input value={sourceConnectorId} onChange={(e) => setSourceConnectorId(e.target.value)} className={inputClass} placeholder="connector-uuid" />
          </label>

          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Fields <span className="text-gray-400">(JSON array)</span></span>
            <textarea value={fieldsText} onChange={(e) => setFieldsText(e.target.value)} rows={6} className={textareaClass} placeholder={FIELDS_PLACEHOLDER} spellCheck={false} />
          </label>

          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Relationships <span className="text-gray-400">(JSON array)</span></span>
            <textarea value={relationshipsText} onChange={(e) => setRelationshipsText(e.target.value)} rows={5} className={textareaClass} placeholder={RELATIONSHIPS_PLACEHOLDER} spellCheck={false} />
          </label>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-[11px] text-red-600 dark:text-red-400">
              <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5 text-[10px]" />
              <span className="flex-1">{error}</span>
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-gray-200 dark:border-dark-border flex items-center justify-end gap-2 flex-shrink-0">
          <button onClick={onClose} className="h-9 px-4 rounded-lg border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={saving} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60 inline-flex items-center gap-2">
            {saving ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : <FontAwesomeIcon icon={editing ? faPenToSquare : faPlus} className="text-[10px]" />}
            {editing ? "Save changes" : "Create entity"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EntityGenerateModal({
  saving,
  preview,
  connectors,
  sourceUrl,
  sourceConnectorId,
  onSourceUrlChange,
  onSourceConnectorChange,
  onPreview,
  onApply,
  onClose,
}: {
  saving: boolean;
  preview: EntityModel[];
  connectors: Connector[];
  sourceUrl: string;
  sourceConnectorId: string;
  onSourceUrlChange: (value: string) => void;
  onSourceConnectorChange: (value: string) => void;
  onPreview: () => void;
  onApply: () => void;
  onClose: () => void;
}) {
  const inputClass =
    "w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all";

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={saving ? undefined : onClose} />
      <div className="relative w-full max-w-3xl max-h-[88vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl flex flex-col">
        <div className="h-14 px-5 border-b border-gray-200 dark:border-dark-border flex items-center justify-between gap-3 flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-8 h-8 rounded-lg bg-gradient-primary text-white flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
            </span>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">Generate entities</h3>
          </div>
          <button onClick={onClose} disabled={saving} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <div className="overflow-auto p-5 space-y-4">
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Source connector</span>
            <select value={sourceConnectorId} onChange={(e) => onSourceConnectorChange(e.target.value)} className={inputClass}>
              <option value="">Use manual docs URL</option>
              {connectors.map((connector) => (
                <option key={connector.connectorId} value={connector.connectorId}>
                  {connector.name} · {connector.type}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">OpenAPI or Swagger docs URL</span>
            <input value={sourceUrl} onChange={(e) => onSourceUrlChange(e.target.value)} className={inputClass} placeholder="https://app.celeris.ad/openapi.json" autoFocus={!sourceConnectorId} />
          </label>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Preview first, then create the proposed entity models in this company.
            </p>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button onClick={onPreview} disabled={saving || (!sourceUrl.trim() && !sourceConnectorId)} className="h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
                {saving ? <FontAwesomeIcon icon={faSpinner} className="animate-spin mr-2 text-[10px]" /> : null}
                Preview
              </button>
              <button onClick={onApply} disabled={saving || (!sourceUrl.trim() && !sourceConnectorId)} className="h-9 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold shadow-glow disabled:opacity-60">
                Create entities
              </button>
            </div>
          </div>

          {preview.length > 0 && (
            <div className="rounded-xl border border-gray-200 dark:border-dark-border overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg flex items-center justify-between">
                <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{preview.length} proposed entities</p>
                <p className="text-[11px] text-gray-400">Duplicates are skipped on create</p>
              </div>
              <div className="max-h-72 overflow-auto divide-y divide-gray-100 dark:divide-dark-border">
                {preview.slice(0, 50).map((entity) => (
                  <div key={entity.name} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{entity.name}</p>
                      <span className="text-[11px] text-gray-400">{entity.fields?.length || 0} fields · {entity.relationships?.length || 0} rels</span>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-1">{entity.description || "No description."}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EntityCard({
  entity,
  onEdit,
  onDelete,
  onDetails,
}: {
  entity: EntityModel;
  onEdit: () => void;
  onDelete: () => void;
  onDetails: () => void;
}) {
  const fields = entity.fields || [];
  const relationships = entity.relationships || [];
  return (
    <div className="group flex flex-col text-left bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-3.5 hover:border-primary/40 hover:shadow-soft transition-all duration-200">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
            <FontAwesomeIcon icon={faCube} className="text-[11px]" />
          </span>
          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{entity.name}</p>
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
          <button onClick={onEdit} className="w-7 h-7 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/10 flex items-center justify-center" title="Edit entity" aria-label="Edit entity">
            <FontAwesomeIcon icon={faPenToSquare} className="text-[11px]" />
          </button>
          <button onClick={onDelete} className="w-7 h-7 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center justify-center" title="Delete entity" aria-label="Delete entity">
            <FontAwesomeIcon icon={faTrash} className="text-[11px]" />
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-1">{entity.description || "No description."}</p>

      <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
          <FontAwesomeIcon icon={faList} className="mr-1 text-[9px]" />{fields.length} {fields.length === 1 ? "field" : "fields"}
        </span>
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
          <FontAwesomeIcon icon={faShareNodes} className="mr-1 text-[9px]" />{relationships.length} {relationships.length === 1 ? "rel" : "rels"}
        </span>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${sourceTone(entity.source)}`}>{(entity.source || "manual").replace(/_/g, " ")}</span>
      </div>

      {fields.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
          {fields.slice(0, 3).map((field) => (
            <span key={field.name} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border max-w-full" title={field.description || field.type}>
              {(field.role === "identifier") && <FontAwesomeIcon icon={faKey} className="text-[8px] text-amber-500 flex-shrink-0" />}
              <span className="truncate">{field.name}{field.type && <span className="text-gray-400">:{field.type}</span>}</span>
            </span>
          ))}
          {fields.length > 3 && (
            <span className="text-[10px] text-gray-400">+{fields.length - 3} more</span>
          )}
        </div>
      )}

      <div className="mt-2.5 pt-2.5 border-t border-gray-100 dark:border-dark-border flex items-center justify-between">
        <span className="text-[10px] text-gray-400">{formatDate(entity.createdAt)}</span>
        <button
          onClick={onDetails}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:gap-1.5 transition-all"
          aria-label={`View ${entity.name} details`}
        >
          <FontAwesomeIcon icon={faCircleInfo} className="text-[10px]" />
          Details
        </button>
      </div>
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 text-xs">
      <span className="w-28 flex-shrink-0 text-gray-400 dark:text-gray-500">{label}</span>
      <span className="flex-1 min-w-0 text-gray-700 dark:text-gray-200 break-words">{children}</span>
    </div>
  );
}

function EntityDetailModal({
  entity,
  linkedTools,
  linkedSkills,
  consumerAgents,
  onOpenFactory,
  onOpenAgent,
  onEdit,
  onDelete,
  onClose,
}: {
  entity: EntityModel;
  linkedTools: CompanyTool[];
  linkedSkills: CompanySkill[];
  consumerAgents: AgentConfig[];
  onOpenFactory: (view: "tools" | "skills", connectorId?: string) => void;
  onOpenAgent: (agentId: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const fields = entity.fields || [];
  const relationships = entity.relationships || [];
  const [rawOpen, setRawOpen] = useState(false);
  const metadataEntries = Object.entries(entity.metadata || {});

  return (
    <div className="fixed inset-0 z-[135] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[88vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl flex flex-col">
        <div className="px-5 py-4 border-b border-gray-200 dark:border-dark-border flex items-start justify-between gap-3 flex-shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={faCube} className="text-sm" />
            </span>
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white truncate">{entity.name}</h3>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${sourceTone(entity.source)}`}>{(entity.source || "manual").replace(/_/g, " ")}</span>
                <span className="text-[11px] text-gray-400">{fields.length} {fields.length === 1 ? "field" : "fields"} · {relationships.length} {relationships.length === 1 ? "rel" : "rels"}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <button onClick={onEdit} className="w-8 h-8 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/10 flex items-center justify-center" title="Edit entity" aria-label="Edit entity">
              <FontAwesomeIcon icon={faPenToSquare} className="text-xs" />
            </button>
            <button onClick={onDelete} className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center justify-center" title="Delete entity" aria-label="Delete entity">
              <FontAwesomeIcon icon={faTrash} className="text-xs" />
            </button>
            <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border" aria-label="Close">
              <FontAwesomeIcon icon={faXmark} className="text-sm" />
            </button>
          </div>
        </div>

        <div className="overflow-auto p-5 space-y-5">
          {/* Description */}
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">Description</p>
            <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{entity.description || "No description."}</p>
          </div>

          {/* Metadata / source */}
          <div className="rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50/60 dark:bg-dark-bg/60 p-3.5 space-y-2">
            <DetailRow label="Source">{(entity.source || "manual").replace(/_/g, " ")}</DetailRow>
            {entity.sourceConnectorId && (
              <DetailRow label="Connector">
                <span className="inline-flex items-center gap-1.5 font-mono text-[11px]">
                  <FontAwesomeIcon icon={faPlugCircleBolt} className="text-[10px] text-gray-400" />
                  {entity.sourceConnectorId}
                </span>
              </DetailRow>
            )}
            <DetailRow label="Created">{formatDate(entity.createdAt)}</DetailRow>
            <DetailRow label="Updated">{formatDate(entity.updatedAt)}</DetailRow>
            {metadataEntries.map(([key, value]) => (
              <DetailRow key={key} label={key}>
                <span className="font-mono text-[11px]">{typeof value === "string" ? value : JSON.stringify(value)}</span>
              </DetailRow>
            ))}
          </div>

          {/* Fields */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <FontAwesomeIcon icon={faList} className="text-[11px] text-gray-400" />
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Fields ({fields.length})</p>
            </div>
            {fields.length === 0 ? (
              <p className="text-xs text-gray-400">No fields defined.</p>
            ) : (
              <div className="rounded-xl border border-gray-200 dark:border-dark-border overflow-hidden divide-y divide-gray-100 dark:divide-dark-border">
                {fields.map((field) => (
                  <div key={field.name} className="px-3.5 py-2.5 flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {field.role === "identifier" && <FontAwesomeIcon icon={faKey} className="text-[10px] text-amber-500" />}
                        <span className="text-xs font-mono font-medium text-gray-900 dark:text-white break-all">{field.name}</span>
                        {field.required && <span className="text-[9px] font-semibold text-red-500 uppercase">required</span>}
                      </div>
                      {field.description && <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">{field.description}</p>}
                      {(field.target || field.ref) && (
                        <p className="text-[11px] text-gray-400 mt-0.5">
                          → <span className="text-primary font-medium">{field.target || field.ref}</span>
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      {field.type && <span className="px-2 py-0.5 rounded-md text-[10px] font-mono border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border">{field.type}</span>}
                      {field.role && <span className="text-[10px] text-gray-400">{field.role}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Relationships */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <FontAwesomeIcon icon={faShareNodes} className="text-[11px] text-gray-400" />
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Relationships ({relationships.length})</p>
            </div>
            {relationships.length === 0 ? (
              <p className="text-xs text-gray-400">No relationships defined.</p>
            ) : (
              <div className="space-y-1.5">
                {relationships.map((rel, index) => (
                  <div key={`${rel.name}-${index}`} className="rounded-lg border border-gray-200 dark:border-dark-border px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-medium text-gray-700 dark:text-gray-200">{rel.name || "relationship"}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400">{rel.kind || "references"}</span>
                      <FontAwesomeIcon icon={faArrowRightLong} className="text-gray-300 dark:text-gray-600" />
                      <span className="px-2 py-0.5 rounded-md font-medium border bg-primary/10 text-primary border-primary/30">{rel.target}</span>
                      {rel.via && <span className="text-gray-400">via {rel.via}</span>}
                    </div>
                    {rel.description && <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">{rel.description}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[11px] text-gray-400" />
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Capabilities using this entity</p>
              </div>
              {linkedTools.length === 0 && linkedSkills.length === 0 ? (
                <p className="text-xs text-gray-400">No tools or skills currently declare this entity.</p>
              ) : (
                <div className="space-y-2">
                  {linkedTools.map((tool) => (
                    <button
                      key={tool.toolId}
                      onClick={() => onOpenFactory("tools", tool.connectorId)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-left hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:hover:bg-primary/5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{tool.name}</p>
                        <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">Tool · {tool.connectorName || "connector"}</p>
                      </div>
                      <FontAwesomeIcon icon={faArrowUpRightFromSquare} className="text-[10px] text-gray-400" />
                    </button>
                  ))}
                  {linkedSkills.map((skill) => (
                    <button
                      key={skill.skillId}
                      onClick={() => onOpenFactory("skills", skill.connectorIds?.[0] || "")}
                      className="flex w-full items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-left hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:hover:bg-primary/5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{skill.name}</p>
                        <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">Skill · {skill.status || "draft"}</p>
                      </div>
                      <FontAwesomeIcon icon={faArrowUpRightFromSquare} className="text-[10px] text-gray-400" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-2">
                <FontAwesomeIcon icon={faRobot} className="text-[11px] text-gray-400" />
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Agents consuming this entity</p>
              </div>
              {consumerAgents.length === 0 ? (
                <p className="text-xs text-gray-400">No agent is currently configured to consume capabilities tied to this entity.</p>
              ) : (
                <div className="space-y-2">
                  {consumerAgents.map((agent) => (
                    <button
                      key={agent.agentId}
                      onClick={() => onOpenAgent(agent.agentId)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-left hover:border-primary/30 hover:bg-primary/5 dark:border-dark-border dark:hover:bg-primary/5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{agent.name}</p>
                        <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">{agent.runtimeType || "runtime"} · {agent.status || "draft"}</p>
                      </div>
                      <FontAwesomeIcon icon={faArrowUpRightFromSquare} className="text-[10px] text-gray-400" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Raw JSON */}
          <div>
            <button
              onClick={() => setRawOpen((v) => !v)}
              className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <FontAwesomeIcon icon={faCode} className="text-[11px]" />
              Raw JSON
              <FontAwesomeIcon icon={faChevronDown} className={`text-[9px] transition-transform ${rawOpen ? "rotate-180" : ""}`} />
            </button>
            {rawOpen && (
              <pre className="mt-2 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3 text-[11px] font-mono leading-5 text-gray-700 dark:text-gray-300 overflow-auto max-h-72">
                {JSON.stringify(entity, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Adjacency-list view of relationships: a graph without a graph library. */
function EntityGraphView({ entities }: { entities: EntityModel[] }) {
  const names = useMemo(() => new Set(entities.map((e) => e.name)), [entities]);
  const edges = useMemo(
    () =>
      entities.flatMap((entity) =>
        (entity.relationships || []).map((rel) => ({
          from: entity.name,
          to: rel.target,
          name: rel.name,
          kind: rel.kind || "references",
          via: rel.via,
          unresolved: !names.has(rel.target),
        })),
      ),
    [entities, names],
  );

  if (edges.length === 0) {
    return (
      <div className="bg-white dark:bg-dark-surface rounded-xl border border-dashed border-gray-200 dark:border-dark-border p-10 text-center">
        <span className="inline-flex w-12 h-12 rounded-2xl bg-primary/10 items-center justify-center mb-3 text-primary">
          <FontAwesomeIcon icon={faShareNodes} className="text-lg" />
        </span>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No relationships defined</p>
        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto">
          Add relationships to your entities to see how they connect. Each relationship links a source entity to a target.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {entities
        .filter((entity) => (entity.relationships || []).length > 0)
        .map((entity) => (
          <div key={entity.entityId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                <FontAwesomeIcon icon={faCube} className="text-[11px]" />
              </span>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{entity.name}</p>
            </div>
            <div className="space-y-2 pl-2">
              {(entity.relationships || []).map((rel, index) => {
                const unresolved = !names.has(rel.target);
                return (
                  <div key={`${rel.name}-${index}`} className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="px-2 py-0.5 rounded-md font-medium bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-dark-border">{rel.name || "relationship"}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400">{rel.kind || "references"}</span>
                    <FontAwesomeIcon icon={faArrowRightLong} className="text-gray-300 dark:text-gray-600" />
                    <span className={`px-2 py-0.5 rounded-md font-medium border ${unresolved ? "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30" : "bg-primary/10 text-primary border-primary/30"}`}>
                      {rel.target}{unresolved ? " (unknown)" : ""}
                    </span>
                    {rel.via && <span className="text-gray-400">via {rel.via}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
    </div>
  );
}

export default function Entities(): React.ReactElement {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [entities, setEntities] = useState<EntityModel[]>([]);
  const [tools, setTools] = useState<CompanyTool[]>([]);
  const [skills, setSkills] = useState<CompanySkill[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<EntitiesTab>("list");
  const [search, setSearch] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<EntityModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EntityModel | null>(null);
  const [detailTarget, setDetailTarget] = useState<EntityModel | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateUrl, setGenerateUrl] = useState("");
  const [generateConnectorId, setGenerateConnectorId] = useState("");
  const [generatePreview, setGeneratePreview] = useState<EntityModel[]>([]);
  const [generating, setGenerating] = useState(false);

  const loadEntities = useCallback(async () => {
    if (!user.email || !companyId) {
      setEntities([]);
      setTools([]);
      setSkills([]);
      setAgents([]);
      setConnectors([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      const scoped = new URLSearchParams({ email: user.email, companyId });
      const [entitiesRes, capabilitiesRes, agentsRes, connectorsRes] = await Promise.all([
        fetch(`${apiUrl}/companies/${companyId}/entities?${params.toString()}`),
        fetch(`${apiUrl}/companies/${companyId}/capabilities?${params.toString()}`),
        fetch(`${apiUrl}/agents?${scoped.toString()}`),
        fetch(`${apiUrl}/connectors?${scoped.toString()}`),
      ]);
      if (entitiesRes.status === 404) {
        setEntities([]);
        return;
      }
      if (!entitiesRes.ok) throw new Error(await responseErrorMessage(entitiesRes, "Could not load entities."));
      const data = await entitiesRes.json();
      setEntities(data.entities || []);
      if (capabilitiesRes.ok) {
        const capabilityData = await capabilitiesRes.json();
        setTools(capabilityData.tools || []);
        setSkills(capabilityData.skills || []);
      } else {
        setTools([]);
        setSkills([]);
      }
      if (agentsRes.ok) {
        const agentData = await agentsRes.json();
        setAgents(agentData.agents || []);
      } else {
        setAgents([]);
      }
      if (connectorsRes.ok) {
        const connectorData = await connectorsRes.json();
        setConnectors(connectorData.connectors || []);
      } else {
        setConnectors([]);
      }
    } catch (err: any) {
      console.error("Failed to load entities:", err);
      setError("");
    } finally {
      setLoading(false);
    }
  }, [companyId, user.email]);

  useEffect(() => {
    loadEntities();
  }, [loadEntities]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const openCreate = () => {
    setEditTarget(null);
    setFormOpen(true);
  };

  const openEdit = (entity: EntityModel) => {
    setEditTarget(entity);
    setFormOpen(true);
  };

  const submitEntity = async (payload: {
    name: string;
    description: string;
    fields: EntityField[];
    relationships: EntityRelationship[];
    sourceConnectorId: string;
    source: string;
  }) => {
    if (!companyId || !user.email || saving) return;
    setSaving(true);
    setError("");
    try {
      const editing = editTarget;
      const res = editing
        ? await fetch(`${apiUrl}/entities/${editing.entityId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          })
        : await fetch(`${apiUrl}/companies/${companyId}/entities`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: user.email, ...payload }),
          });
      if (!res.ok) {
        throw new Error(await responseErrorMessage(res, "Could not save entity."));
      }
      setFormOpen(false);
      setEditTarget(null);
      await loadEntities();
    } catch (err: any) {
      console.error("Failed to save entity:", err);
      setError(err?.message || "Could not save entity.");
    } finally {
      setSaving(false);
    }
  };

  const generateEntities = async (apply: boolean) => {
    if (!companyId || !user.email || generating || (!generateUrl.trim() && !generateConnectorId)) return;
    setGenerating(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/companies/${companyId}/entities/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          sourceUrl: generateUrl.trim(),
          sourceConnectorId: generateConnectorId,
          apply,
          limit: 50,
        }),
      });
      if (!res.ok) {
        throw new Error(await responseErrorMessage(res, "Could not generate entities."));
      }
      const data = await res.json();
      setGeneratePreview(data.entities || []);
      if (apply) {
        setGenerateOpen(false);
        setGeneratePreview([]);
        setGenerateConnectorId("");
        await loadEntities();
      }
    } catch (err: any) {
      console.error("Failed to generate entities:", err);
      setError(err?.message || "Could not generate entities.");
    } finally {
      setGenerating(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      const res = await fetch(`${apiUrl}/entities/${target.entityId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await responseErrorMessage(res, "Could not delete entity."));
      await loadEntities();
    } catch (err: any) {
      console.error("Failed to delete entity:", err);
      setError(err?.message || "Could not delete entity.");
    }
  };

  const totalFields = useMemo(() => entities.reduce((acc, e) => acc + (e.fields?.length || 0), 0), [entities]);
  const totalRelationships = useMemo(() => entities.reduce((acc, e) => acc + (e.relationships?.length || 0), 0), [entities]);
  const entityUsage = useMemo(() => {
    const result = new Map<string, { tools: CompanyTool[]; skills: CompanySkill[]; agents: AgentConfig[] }>();

    const ensure = (name: string) => {
      const key = name.trim().toLowerCase();
      if (!key) return null;
      if (!result.has(key)) result.set(key, { tools: [], skills: [], agents: [] });
      return result.get(key)!;
    };

    for (const tool of tools) {
      const names = [...(tool.inputEntities || []), ...(tool.outputEntity ? [tool.outputEntity] : [])];
      for (const name of names) {
        const bucket = ensure(name);
        if (bucket && !bucket.tools.some((item) => item.toolId === tool.toolId)) bucket.tools.push(tool);
      }
    }

    for (const skill of skills) {
      const names = [...(skill.inputEntities || []), ...(skill.outputEntity ? [skill.outputEntity] : [])];
      for (const name of names) {
        const bucket = ensure(name);
        if (bucket && !bucket.skills.some((item) => item.skillId === skill.skillId)) bucket.skills.push(skill);
      }
    }

    for (const entity of entities) {
      const key = entity.name.trim().toLowerCase();
      const bucket = result.get(key);
      if (!bucket) continue;
      const connectorIds = new Set<string>([
        ...bucket.tools.map((tool) => tool.connectorId).filter(Boolean),
        ...bucket.skills.flatMap((skill) => skill.connectorIds || []).filter(Boolean),
      ]);
      for (const agent of agents) {
        const agentKnowledge = Boolean(agent.runtimeCapabilities?.knowledge || agent.runtimeSpec?.tools?.knowledge);
        const agentUsesSkills = bucket.skills.some((skill) => skill.agentId && skill.agentId === agent.agentId);
        const agentMatchesConnector = connectorIds.size > 0 && agentKnowledge;
        if ((agentUsesSkills || agentMatchesConnector) && !bucket.agents.some((item) => item.agentId === agent.agentId)) {
          bucket.agents.push(agent);
        }
      }
    }

    return result;
  }, [agents, entities, skills, tools]);
  const totalToolLinks = useMemo(() => Array.from(entityUsage.values()).reduce((sum, item) => sum + item.tools.length, 0), [entityUsage]);
  const totalSkillLinks = useMemo(() => Array.from(entityUsage.values()).reduce((sum, item) => sum + item.skills.length, 0), [entityUsage]);
  const totalAgentLinks = useMemo(() => Array.from(entityUsage.values()).reduce((sum, item) => sum + item.agents.length, 0), [entityUsage]);
  const filteredEntities = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entities;
    return entities.filter(
      (e) => e.name.toLowerCase().includes(q) || (e.description || "").toLowerCase().includes(q),
    );
  }, [entities, search]);

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-glow">
              <FontAwesomeIcon icon={faCube} className="text-sm" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">Entities</h1>
                <InfoIcon title="Entities">
                  <div className="space-y-3">
                    <p>Entities describe the <strong>business objects</strong> this company works with: invoices, customers, tickets, orders.</p>
                    <p>Each entity has typed <strong>fields</strong> and <strong>relationships</strong> to other entities. Tools and skills declare the entities they read (<em>input entities</em>) and produce (<em>output entity</em>), giving agents a shared semantic layer.</p>
                    <p className="text-gray-400">Edit fields and relationships as JSON arrays for full control.</p>
                  </div>
                </InfoIcon>
              </div>
              <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">The semantic objects your agents reason about</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {companyId && (
              <>
                <button onClick={() => setGenerateOpen(true)} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface inline-flex items-center gap-2 transition-colors">
                  <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[10px]" />
                  Generate
                </button>
                <button onClick={openCreate} className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold inline-flex items-center gap-2 shadow-glow">
                  <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
                  New entity
                </button>
              </>
            )}
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

          {!companyId ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
              <span className="inline-flex w-14 h-14 rounded-2xl bg-gray-100 dark:bg-dark-border items-center justify-center mb-4 text-gray-400">
                <FontAwesomeIcon icon={faBuilding} className="text-xl" />
              </span>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No company selected</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">Create or select a company from the top bar to manage its entities.</p>
            </div>
          ) : (
            <>
              {/* Stats */}
              <div className="flex gap-3 mb-5">
                {[
                  { icon: faCube, label: "Entities", value: entities.length },
                  { icon: faList, label: "Fields", value: totalFields },
                  { icon: faShareNodes, label: "Relationships", value: totalRelationships },
                  { icon: faPlugCircleBolt, label: "Tool links", value: totalToolLinks },
                  { icon: faWandMagicSparkles, label: "Skill links", value: totalSkillLinks },
                  { icon: faRobot, label: "Agent links", value: totalAgentLinks },
                ].map((stat) => (
                  <div key={stat.label} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 min-w-[120px]">
                    <div className="flex items-center gap-1.5 mb-1">
                      <FontAwesomeIcon icon={stat.icon} className="text-[10px] text-gray-400" />
                      <p className="text-[10px] uppercase tracking-wide text-gray-400">{stat.label}</p>
                    </div>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white leading-none">{stat.value}</p>
                  </div>
                ))}
              </div>

              {/* Tabs */}
              <div className="flex items-center gap-1.5 mb-5">
                {([
                  { key: "list" as EntitiesTab, label: "Entities", icon: faList },
                  { key: "graph" as EntitiesTab, label: "Relationships", icon: faDiagramProject },
                ]).map((item) => (
                  <button
                    key={item.key}
                    onClick={() => setTab(item.key)}
                    className={`h-9 px-3 rounded-lg text-xs font-semibold flex items-center gap-2 whitespace-nowrap transition-colors border ${
                      tab === item.key
                        ? "bg-gradient-primary text-white border-transparent shadow-glow"
                        : "bg-white dark:bg-dark-surface text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-dark-border"
                    }`}
                  >
                    <FontAwesomeIcon icon={item.icon} className="text-[11px]" />
                    {item.label}
                  </button>
                ))}
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-20">
                  <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
                </div>
              ) : entities.length === 0 ? (
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-12 text-center">
                  <span className="inline-flex w-14 h-14 rounded-2xl bg-primary/10 items-center justify-center mb-4 text-primary">
                    <FontAwesomeIcon icon={faCube} className="text-xl" />
                  </span>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">No entities yet</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-5">
                    Define the business objects your agents reason about. Start with a customer, invoice or ticket and connect them with relationships.
                  </p>
                  <button onClick={openCreate} className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2">
                    <FontAwesomeIcon icon={faPlus} className="text-xs" />
                    Create your first entity
                  </button>
                </div>
              ) : tab === "list" ? (
                <>
                  <div className="flex items-center gap-2 px-3 h-10 mb-4 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border focus-within:border-primary/50 transition-colors">
                    <FontAwesomeIcon icon={faMagnifyingGlass} className="text-gray-400 text-sm" />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search entities by name or description..."
                      className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                    />
                    {search && (
                      <button onClick={() => setSearch("")} className="text-gray-400 hover:text-gray-600">
                        <FontAwesomeIcon icon={faXmark} className="text-xs" />
                      </button>
                    )}
                  </div>
                  {filteredEntities.length === 0 ? (
                    <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center">
                      <p className="text-sm text-gray-500 dark:text-gray-400">No entities match “{search}”.</p>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {filteredEntities.map((entity) => (
                        <EntityCard
                          key={entity.entityId}
                          entity={entity}
                          onEdit={() => openEdit(entity)}
                          onDelete={() => setDeleteTarget(entity)}
                          onDetails={() => setDetailTarget(entity)}
                        />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <EntityGraphView entities={entities} />
              )}
            </>
          )}
        </div>
      </div>

      {detailTarget && (
        <EntityDetailModal
          entity={detailTarget}
          linkedTools={entityUsage.get(detailTarget.name.trim().toLowerCase())?.tools || []}
          linkedSkills={entityUsage.get(detailTarget.name.trim().toLowerCase())?.skills || []}
          consumerAgents={entityUsage.get(detailTarget.name.trim().toLowerCase())?.agents || []}
          onOpenFactory={(view, connectorId) => navigate(`/capabilities?view=${view}${connectorId ? `&connector=${encodeURIComponent(connectorId)}` : ""}`)}
          onOpenAgent={(agentId) => navigate(`/agents/${agentId}`)}
          onEdit={() => { openEdit(detailTarget); setDetailTarget(null); }}
          onDelete={() => { setDeleteTarget(detailTarget); setDetailTarget(null); }}
          onClose={() => setDetailTarget(null)}
        />
      )}

      {formOpen && (
        <EntityFormModal
          initial={editTarget}
          saving={saving}
          onClose={() => { setFormOpen(false); setEditTarget(null); }}
          onSubmit={submitEntity}
        />
      )}

      {generateOpen && (
        <EntityGenerateModal
          saving={generating}
          preview={generatePreview}
          connectors={connectors}
          sourceUrl={generateUrl}
          sourceConnectorId={generateConnectorId}
          onSourceUrlChange={setGenerateUrl}
          onSourceConnectorChange={setGenerateConnectorId}
          onPreview={() => generateEntities(false)}
          onApply={() => generateEntities(true)}
          onClose={() => {
            setGenerateOpen(false);
            setGeneratePreview([]);
            setGenerateConnectorId("");
          }}
        />
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[140] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setDeleteTarget(null)} />
          <div className="relative w-full max-w-sm rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-8 h-8 rounded-lg bg-red-50 dark:bg-red-500/10 text-red-500 flex items-center justify-center flex-shrink-0">
                <FontAwesomeIcon icon={faTrash} className="text-xs" />
              </span>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">Delete entity</h3>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-5">
              Delete <span className="font-semibold text-gray-700 dark:text-gray-200">{deleteTarget.name}</span>? This cannot be undone. Tools or skills referencing it will keep their declared names.
            </p>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setDeleteTarget(null)} className="h-9 px-4 rounded-lg border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors">
                Cancel
              </button>
              <button onClick={confirmDelete} className="h-9 px-4 rounded-lg bg-red-500 text-white text-sm font-semibold hover:bg-red-600 transition-colors">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
