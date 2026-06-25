import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import ReactMarkdown from "react-markdown";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCode,
  faDownload,
  faFile,
  faFileCode,
  faFileCsv,
  faFileLines,
  faFilePdf,
  faFilePowerpoint,
  faFileWord,
  faPen,
  faPlus,
  faSave,
  faShapes,
  faSpinner,
  faTable,
  faTrash,
  faTriangleExclamation,
} from "@fortawesome/free-solid-svg-icons";
import { Artifact } from "../utils/types";
import SectionTitle from "../components/layout/section-title";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type ArtifactDraft = {
  title: string;
  artifactType: string;
  description: string;
  content: string;
  fileName: string;
};

const ARTIFACT_TYPES = [
  { value: "markdown", label: "Markdown" },
  { value: "html", label: "HTML" },
  { value: "react", label: "React" },
  { value: "svg", label: "SVG" },
  { value: "mermaid", label: "Mermaid" },
  { value: "csv", label: "CSV / Sheet" },
  { value: "json", label: "JSON" },
  { value: "javascript", label: "JavaScript" },
  { value: "python", label: "Python" },
  { value: "docx", label: "Word" },
  { value: "pdf", label: "PDF" },
  { value: "pptx", label: "PowerPoint" },
  { value: "xlsx", label: "Excel" },
  { value: "text", label: "Text" },
];

const DEFAULT_CONTENT: Record<string, string> = {
  markdown: "# New document\n\nWrite here...",
  html: "<!doctype html>\n<html>\n  <body>\n    <h1>Hello Automata</h1>\n  </body>\n</html>",
  react: "export default function Artifact() {\n  return <div>Hello Automata</div>;\n}",
  svg: '<svg width="320" height="180" viewBox="0 0 320 180" xmlns="http://www.w3.org/2000/svg">\n  <rect width="320" height="180" rx="12" fill="#f3f4f6"/>\n  <text x="24" y="96" font-size="22" fill="#111827">Automata artifact</text>\n</svg>',
  mermaid: "flowchart LR\n  User --> Automata\n  Automata --> Artifact",
  csv: "Name,Value\nExample,1",
  json: '{\n  "name": "Artifact"\n}',
  javascript: "console.log('Hello Automata');",
  python: "print('Hello Automata')",
  text: "Write here...",
};

function formatDate(value?: string) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Never";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function extensionFor(type: string) {
  const map: Record<string, string> = {
    markdown: "md",
    html: "html",
    react: "jsx",
    svg: "svg",
    mermaid: "mmd",
    csv: "csv",
    json: "json",
    javascript: "js",
    typescript: "ts",
    python: "py",
    docx: "docx",
    pdf: "pdf",
    pptx: "pptx",
    xlsx: "xlsx",
    text: "txt",
  };
  return map[type] || "txt";
}

function iconFor(type: string) {
  if (type === "markdown" || type === "text") return faFileLines;
  if (type === "html" || type === "react" || type === "javascript" || type === "typescript" || type === "python" || type === "json") return faFileCode;
  if (type === "csv" || type === "xlsx") return faFileCsv;
  if (type === "docx") return faFileWord;
  if (type === "pdf") return faFilePdf;
  if (type === "pptx") return faFilePowerpoint;
  if (type === "svg" || type === "mermaid") return faShapes;
  return faFile;
}

function normalizeContentForType(type: string) {
  return DEFAULT_CONTENT[type] || DEFAULT_CONTENT.text;
}

function csvRows(content: string) {
  return content
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(0, 12)
    .map((line) => line.split(",").map((cell) => cell.trim()));
}

function Preview({ artifact }: { artifact: ArtifactDraft }) {
  const type = artifact.artifactType;
  const content = artifact.content || "";

  if (type === "markdown") {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface p-5">
        <ReactMarkdown>{content || "Nothing to preview yet."}</ReactMarkdown>
      </div>
    );
  }

  if (type === "html" || type === "svg") {
    return (
      <iframe
        title="Artifact preview"
        sandbox=""
        srcDoc={content}
        className="h-[420px] w-full rounded-xl border border-gray-200 dark:border-dark-border bg-white"
      />
    );
  }

  if (type === "csv" || type === "xlsx") {
    const rows = csvRows(content);
    return (
      <div className="overflow-auto rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface">
        <table className="min-w-full text-left text-xs">
          <tbody>
            {rows.length ? rows.map((row, rowIndex) => (
              <tr key={`${rowIndex}-${row.join("-")}`} className={rowIndex === 0 ? "bg-gray-50 dark:bg-white/5" : ""}>
                {row.map((cell, cellIndex) => (
                  <td key={`${rowIndex}-${cellIndex}`} className="border-b border-r border-gray-100 dark:border-dark-border px-3 py-2 text-gray-700 dark:text-gray-200">
                    {cell}
                  </td>
                ))}
              </tr>
            )) : (
              <tr>
                <td className="px-3 py-2 text-gray-400">Nothing to preview yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }

  if (["docx", "pdf", "pptx"].includes(type)) {
    return (
      <div className="flex h-[260px] flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 dark:border-dark-border bg-white dark:bg-dark-surface text-center">
        <FontAwesomeIcon icon={iconFor(type)} className="mb-3 text-3xl text-primary" />
        <p className="text-sm font-semibold text-gray-900 dark:text-white">{artifact.fileName || artifact.title}</p>
        <p className="mt-1 max-w-sm text-xs text-gray-500 dark:text-gray-400">
          Binary rendering is handled through download in this MVP. The artifact content remains editable as source text or generation metadata.
        </p>
      </div>
    );
  }

  return (
    <pre className="min-h-[260px] overflow-auto rounded-xl border border-gray-200 dark:border-dark-border bg-gray-950 p-4 text-xs leading-relaxed text-gray-100">
      <code>{content || "Nothing to preview yet."}</code>
    </pre>
  );
}

export default function Artifacts(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<ArtifactDraft>({
    title: "New artifact",
    artifactType: "markdown",
    description: "",
    content: normalizeContentForType("markdown"),
    fileName: "new-artifact.md",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(() => artifacts.find((artifact) => artifact.artifactId === selectedId), [artifacts, selectedId]);

  const loadArtifacts = useCallback(async () => {
    if (!user.email || !companyId) {
      setArtifacts([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ email: user.email });
      const res = await fetch(`${apiUrl}/companies/${companyId}/artifacts?${params.toString()}`);
      if (res.status === 404) {
        setArtifacts([]);
        return;
      }
      if (!res.ok) throw new Error("Could not load artifacts.");
      const data = await res.json();
      const items = data.artifacts || [];
      setArtifacts(items);
      if (!selectedId && items.length) {
        const first = items[0];
        setSelectedId(first.artifactId);
        setDraft({
          title: first.title || "",
          artifactType: first.artifactType || "text",
          description: first.description || "",
          content: first.content || "",
          fileName: first.fileName || "",
        });
      }
    } catch (err: any) {
      console.error("Failed to load artifacts:", err);
      setError(err?.message || "Could not load artifacts.");
    } finally {
      setLoading(false);
    }
  }, [companyId, selectedId, user.email]);

  useEffect(() => {
    loadArtifacts();
  }, [loadArtifacts]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
      setSelectedId("");
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const createNew = () => {
    setSelectedId("");
    setDraft({
      title: "New artifact",
      artifactType: "markdown",
      description: "",
      content: normalizeContentForType("markdown"),
      fileName: "new-artifact.md",
    });
    setError("");
  };

  const selectArtifact = (artifact: Artifact) => {
    setSelectedId(artifact.artifactId);
    setDraft({
      title: artifact.title || "",
      artifactType: artifact.artifactType || "text",
      description: artifact.description || "",
      content: artifact.content || "",
      fileName: artifact.fileName || "",
    });
    setError("");
  };

  const updateType = (artifactType: string) => {
    setDraft((current) => {
      const nextExt = extensionFor(artifactType);
      const base = (current.fileName || current.title || "artifact").replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "artifact";
      return {
        ...current,
        artifactType,
        content: current.content === normalizeContentForType(current.artifactType) ? normalizeContentForType(artifactType) : current.content,
        fileName: `${base}.${nextExt}`,
      };
    });
  };

  const saveArtifact = async () => {
    if (!user.email || !companyId || saving) return;
    if (!draft.title.trim()) {
      setError("Add a title before saving.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = { ...draft, email: user.email };
      const url = selectedId ? `${apiUrl}/artifacts/${selectedId}` : `${apiUrl}/companies/${companyId}/artifacts`;
      const res = await fetch(url, {
        method: selectedId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const saved = data.artifact;
      setSelectedId(saved.artifactId);
      await loadArtifacts();
    } catch (err: any) {
      console.error("Failed to save artifact:", err);
      setError(err?.message || "Could not save artifact.");
    } finally {
      setSaving(false);
    }
  };

  const deleteArtifact = async (artifactId: string) => {
    if (!window.confirm("Delete this artifact?")) return;
    setError("");
    try {
      const res = await fetch(`${apiUrl}/artifacts/${artifactId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      if (selectedId === artifactId) createNew();
      await loadArtifacts();
    } catch (err: any) {
      console.error("Failed to delete artifact:", err);
      setError(err?.message || "Could not delete artifact.");
    }
  };

  const downloadArtifact = () => {
    if (!selectedId || !user.email) return;
    const params = new URLSearchParams({ email: user.email });
    window.open(`${apiUrl}/artifacts/${selectedId}/download?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const counts = useMemo(() => {
    const interactive = artifacts.filter((artifact) => ["html", "react", "svg", "mermaid"].includes(artifact.artifactType)).length;
    return { total: artifacts.length, interactive };
  }, [artifacts]);

  return (
    <div className="relative flex h-full w-full overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden pointer-events-none dark:block">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="h-full w-full object-cover" />
      </div>
      <div className="relative flex h-full w-full flex-col">
        <div className="flex min-h-16 flex-shrink-0 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-8 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80">
          <SectionTitle icon={faShapes} title="Artifacts" subtitle="Generated files and outputs" />
          <div className="flex items-center gap-2">
            <button onClick={createNew} className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-surface">
              <FontAwesomeIcon icon={faPlus} className="mr-2 text-[10px]" />
              New
            </button>
            <button onClick={saveArtifact} disabled={saving || !companyId} className="h-8 rounded-lg bg-gradient-primary px-3 text-xs font-semibold text-white transition-opacity disabled:opacity-60">
              <FontAwesomeIcon icon={saving ? faSpinner : faSave} className={`mr-2 text-[10px] ${saving ? "animate-spin" : ""}`} />
              Save
            </button>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-auto p-6 xl:grid-cols-[320px_1fr]">
          <aside className="flex min-h-[280px] flex-col rounded-xl border border-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
            <div className="border-b border-gray-200 p-4 dark:border-dark-border">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Workspace artifacts</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-gray-50 p-3 dark:bg-white/5">
                  <p className="text-[10px] uppercase text-gray-400">Total</p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{counts.total}</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-3 dark:bg-white/5">
                  <p className="text-[10px] uppercase text-gray-400">Interactive</p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{counts.interactive}</p>
                </div>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-2">
              {loading ? (
                <div className="flex h-32 items-center justify-center text-sm text-gray-400">
                  <FontAwesomeIcon icon={faSpinner} className="mr-2 animate-spin" />
                  Loading artifacts
                </div>
              ) : artifacts.length ? artifacts.map((artifact) => (
                <button
                  key={artifact.artifactId}
                  onClick={() => selectArtifact(artifact)}
                  className={`mb-2 flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors ${
                    artifact.artifactId === selectedId ? "bg-primary/10" : "hover:bg-gray-50 dark:hover:bg-white/5"
                  }`}
                >
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100 text-primary dark:bg-white/5">
                    <FontAwesomeIcon icon={iconFor(artifact.artifactType)} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-gray-900 dark:text-white">{artifact.title}</span>
                    <span className="mt-0.5 block truncate text-xs text-gray-500 dark:text-gray-400">{artifact.artifactType} · {formatDate(artifact.updatedAt || artifact.createdAt)}</span>
                  </span>
                </button>
              )) : (
                <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-gray-200 px-4 text-center dark:border-dark-border">
                  <FontAwesomeIcon icon={faShapes} className="mb-2 text-xl text-gray-300" />
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">No artifacts yet</p>
                  <p className="mt-1 text-xs text-gray-400">Create a document, page, diagram or interactive asset.</p>
                </div>
              )}
            </div>
          </aside>

          <main className="min-w-0 space-y-4">
            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
                <FontAwesomeIcon icon={faTriangleExclamation} className="mt-0.5" />
                <span className="break-all">{error}</span>
              </div>
            )}

            {!companyId && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                Select or create a company before saving artifacts.
              </div>
            )}

            <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{selected ? "Edit artifact" : "Create artifact"}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Artifacts are company-scoped and persist between sessions.</p>
                </div>
                <div className="flex items-center gap-2">
                  {selectedId && (
                    <>
                      <button onClick={downloadArtifact} className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-white/5">
                        <FontAwesomeIcon icon={faDownload} className="mr-2 text-[10px]" />
                        Download
                      </button>
                      <button onClick={() => deleteArtifact(selectedId)} className="h-8 rounded-lg border border-red-200 px-3 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-red-500/30 dark:text-red-400 dark:hover:bg-red-500/10">
                        <FontAwesomeIcon icon={faTrash} className="mr-2 text-[10px]" />
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_180px_220px]">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Title</span>
                  <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-primary dark:border-dark-border dark:bg-dark-bg dark:text-white" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Type</span>
                  <select value={draft.artifactType} onChange={(event) => updateType(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-primary dark:border-dark-border dark:bg-dark-bg dark:text-white">
                    {ARTIFACT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">File name</span>
                  <input value={draft.fileName} onChange={(event) => setDraft({ ...draft, fileName: event.target.value })} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-primary dark:border-dark-border dark:bg-dark-bg dark:text-white" />
                </label>
              </div>
              <label className="mt-3 block">
                <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Description</span>
                <input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-primary dark:border-dark-border dark:bg-dark-bg dark:text-white" />
              </label>
            </section>

            <section className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
                <div className="mb-3 flex items-center gap-2">
                  <FontAwesomeIcon icon={faPen} className="text-xs text-primary" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Source</p>
                </div>
                <textarea
                  value={draft.content}
                  onChange={(event) => setDraft({ ...draft, content: event.target.value })}
                  spellCheck={false}
                  className="h-[420px] w-full resize-none rounded-xl border border-gray-200 bg-gray-950 p-4 font-mono text-xs leading-relaxed text-gray-100 outline-none focus:border-primary dark:border-dark-border"
                />
              </div>
              <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
                <div className="mb-3 flex items-center gap-2">
                  <FontAwesomeIcon icon={draft.artifactType === "csv" || draft.artifactType === "xlsx" ? faTable : draft.artifactType.includes("script") ? faCode : iconFor(draft.artifactType)} className="text-xs text-primary" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Preview</p>
                </div>
                <Preview artifact={draft} />
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}
