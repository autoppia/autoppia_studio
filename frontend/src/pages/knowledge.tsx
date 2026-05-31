import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faFileLines, faPlus, faRotate, faSpinner, faTrash } from "@fortawesome/free-solid-svg-icons";
import { KnowledgeDocument } from "../utils/types";
import InfoIcon from "../components/common/info-icon";

const apiUrl = process.env.REACT_APP_API_URL;

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export default function Knowledge(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const loadDocuments = useCallback(async () => {
    if (!user.email || !companyId) {
      setDocuments([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email, companyId });
      const res = await fetch(`${apiUrl}/knowledge/documents?${params.toString()}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setDocuments(data.documents || []);
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
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const uploadFiles = async (files: FileList | null) => {
    if (!files?.length || !user.email || !companyId || uploading) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("email", user.email);
        body.append("companyId", companyId);
        body.append("source", "knowledge_page");
        body.append("file", file);
        const res = await fetch(`${apiUrl}/knowledge/documents`, { method: "POST", body });
        if (!res.ok) throw new Error(await res.text());
      }
      await loadDocuments();
    } catch (err) {
      console.error("Failed to upload knowledge document:", err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const deleteDocument = async (documentId: string) => {
    try {
      const res = await fetch(`${apiUrl}/knowledge/documents/${documentId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      await loadDocuments();
    } catch (err) {
      console.error("Failed to delete knowledge document:", err);
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
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Knowledge</h1>
            <InfoIcon title="Knowledge">
              <div className="space-y-3">
                <p>Knowledge documents belong to the selected company and feed the Knowledge connector.</p>
                <p>Agents can use these documents through knowledge search tools once indexing/vector search is connected.</p>
              </div>
            </InfoIcon>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadDocuments} className="h-8 px-3 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-surface">
              <FontAwesomeIcon icon={faRotate} className="mr-2 text-[10px]" />
              Refresh
            </button>
            <button onClick={() => fileInputRef.current?.click()} disabled={uploading || !companyId} className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold disabled:opacity-60">
              <FontAwesomeIcon icon={uploading ? faSpinner : faPlus} className={`mr-2 text-[10px] ${uploading ? "animate-spin" : ""}`} />
              Upload
            </button>
            <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(event) => uploadFiles(event.target.files)} />
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
            </div>
          ) : documents.length === 0 ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center text-sm text-gray-500 dark:text-gray-400">
              No documents yet. Upload PDFs, markdown, text, CSV, JSON, DOC or DOCX files for this company.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {documents.map((document) => (
                <div key={document.documentId} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <div className="flex items-start gap-3">
                    <span className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                      <FontAwesomeIcon icon={faFileLines} className="text-sm" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{document.filename}</p>
                      <p className="text-xs text-gray-400 mt-1">{formatSize(document.size)} · {document.status}</p>
                    </div>
                    <button onClick={() => deleteDocument(document.documentId)} className="w-8 h-8 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10">
                      <FontAwesomeIcon icon={faTrash} className="text-xs" />
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 truncate">{document.contentType || "Unknown type"}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
