import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRightLong,
  faBuilding,
  faCube,
  faDiagramProject,
  faKey,
  faList,
  faPenToSquare,
  faPlus,
  faRotate,
  faShareNodes,
  faSpinner,
  faTrash,
  faTriangleExclamation,
  faWandMagicSparkles,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { EntityField, EntityModel, EntityRelationship } from "../utils/types";
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
  sourceUrl,
  onSourceUrlChange,
  onPreview,
  onApply,
  onClose,
}: {
  saving: boolean;
  preview: EntityModel[];
  sourceUrl: string;
  onSourceUrlChange: (value: string) => void;
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
            <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">OpenAPI or Swagger docs URL</span>
            <input value={sourceUrl} onChange={(e) => onSourceUrlChange(e.target.value)} className={inputClass} placeholder="https://app.celeris.ad/openapi.json" autoFocus />
          </label>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Preview first, then create the proposed entity models in this company.
            </p>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button onClick={onPreview} disabled={saving || !sourceUrl.trim()} className="h-9 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60">
                {saving ? <FontAwesomeIcon icon={faSpinner} className="animate-spin mr-2 text-[10px]" /> : null}
                Preview
              </button>
              <button onClick={onApply} disabled={saving || !sourceUrl.trim()} className="h-9 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold shadow-glow disabled:opacity-60">
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
}: {
  entity: EntityModel;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const fields = entity.fields || [];
  const relationships = entity.relationships || [];
  return (
    <div className="group flex flex-col bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 hover:border-primary/40 hover:shadow-soft transition-all duration-200">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
            <FontAwesomeIcon icon={faCube} className="text-xs" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{entity.name}</p>
            <p className="text-[10px] text-gray-400">{formatDate(entity.createdAt)}</p>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onEdit} className="w-8 h-8 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/10 flex items-center justify-center" title="Edit entity">
            <FontAwesomeIcon icon={faPenToSquare} className="text-xs" />
          </button>
          <button onClick={onDelete} className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center justify-center" title="Delete entity">
            <FontAwesomeIcon icon={faTrash} className="text-xs" />
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 line-clamp-2 min-h-[2rem]">{entity.description || "No description."}</p>

      <div className="flex flex-wrap items-center gap-1.5 mt-3">
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
          <FontAwesomeIcon icon={faList} className="mr-1 text-[9px]" />{fields.length} {fields.length === 1 ? "field" : "fields"}
        </span>
        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
          <FontAwesomeIcon icon={faShareNodes} className="mr-1 text-[9px]" />{relationships.length} {relationships.length === 1 ? "relationship" : "relationships"}
        </span>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${sourceTone(entity.source)}`}>{(entity.source || "manual").replace(/_/g, " ")}</span>
      </div>

      {fields.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-3 border-t border-gray-100 dark:border-dark-border">
          {fields.slice(0, 6).map((field) => (
            <span key={field.name} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono border bg-gray-50 dark:bg-dark-bg text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border" title={field.description || field.type}>
              {(field.role === "identifier") && <FontAwesomeIcon icon={faKey} className="text-[8px] text-amber-500" />}
              {field.name}
              {field.type && <span className="text-gray-400">:{field.type}</span>}
            </span>
          ))}
          {fields.length > 6 && <span className="text-[10px] text-gray-400">+{fields.length - 6} more</span>}
        </div>
      )}

      {relationships.length > 0 && (
        <div className="mt-3 space-y-1">
          {relationships.map((rel, index) => (
            <div key={`${rel.name}-${index}`} className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-600 dark:text-gray-300">{rel.name || rel.kind || "rel"}</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400">{rel.kind || "references"}</span>
              <FontAwesomeIcon icon={faArrowRightLong} className="text-[9px] text-gray-300 dark:text-gray-600" />
              <span className="font-medium text-primary truncate">{rel.target}</span>
              {rel.via && <span className="text-gray-400 truncate">via {rel.via}</span>}
            </div>
          ))}
        </div>
      )}
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
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [entities, setEntities] = useState<EntityModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<EntitiesTab>("list");
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<EntityModel | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EntityModel | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateUrl, setGenerateUrl] = useState("");
  const [generatePreview, setGeneratePreview] = useState<EntityModel[]>([]);
  const [generating, setGenerating] = useState(false);

  const loadEntities = useCallback(async () => {
    if (!user.email || !companyId) {
      setEntities([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      const res = await fetch(`${apiUrl}/companies/${companyId}/entities?${params.toString()}`);
      if (res.status === 404) {
        setEntities([]);
        return;
      }
      if (!res.ok) throw new Error(await responseErrorMessage(res, "Could not load entities."));
      const data = await res.json();
      setEntities(data.entities || []);
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
    if (!companyId || !user.email || generating || !generateUrl.trim()) return;
    setGenerating(true);
    setError("");
    try {
      const res = await fetch(`${apiUrl}/companies/${companyId}/entities/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          sourceUrl: generateUrl.trim(),
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

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>
      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-2.5">
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
            <button onClick={loadEntities} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors">
              <FontAwesomeIcon icon={faRotate} className="mr-2 text-[10px]" />
              Refresh
            </button>
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
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {entities.map((entity) => (
                    <EntityCard key={entity.entityId} entity={entity} onEdit={() => openEdit(entity)} onDelete={() => setDeleteTarget(entity)} />
                  ))}
                </div>
              ) : (
                <EntityGraphView entities={entities} />
              )}
            </>
          )}
        </div>
      </div>

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
          sourceUrl={generateUrl}
          onSourceUrlChange={setGenerateUrl}
          onPreview={() => generateEntities(false)}
          onApply={() => generateEntities(true)}
          onClose={() => {
            setGenerateOpen(false);
            setGeneratePreview([]);
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
