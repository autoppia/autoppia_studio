import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faChevronDown,
  faCloud,
  faCodeBranch,
  faComments,
  faDatabase,
  faEnvelope,
  faFileLines,
  faFlask,
  faGlobe,
  faKey,
  faPlus,
  faSearch,
  faSpinner,
  faTrash,
  faWandMagicSparkles,
  faWrench,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { Connector } from "../utils/types";
import InfoIcon from "../components/common/info-icon";
import SelectDropdown from "../components/common/select-dropdown";
import ConfirmModal from "../components/common/confirm-modal";
import { useToast } from "../components/common/toast";
import { apiErrorMessage } from "../utils/api-error";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

const CONNECTOR_TYPES = [
  { value: "gmail", label: "Gmail", category: "email", icon: faEnvelope, logo: "/assets/images/connectors/gmail.svg" },
  { value: "smtp", label: "SMTP", category: "email", icon: faEnvelope, logo: "/assets/images/connectors/mail.png" },
  { value: "holded", label: "Holded", category: "software", icon: faFileLines, logo: "/assets/images/connectors/holded.png" },
  { value: "telegram", label: "Telegram", category: "communication", icon: faEnvelope, logo: "/assets/images/connectors/telegram.png" },
  { value: "slack", label: "Slack", category: "communication", icon: faComments, logo: "/assets/images/connectors/slack.png" },
  { value: "discord", label: "Discord", category: "communication", icon: faComments, logo: "/assets/images/connectors/discord.png" },
  { value: "whatsapp", label: "WhatsApp Cloud", category: "communication", icon: faComments, logo: "/assets/images/connectors/whatsapp.png" },
  { value: "teams", label: "Microsoft Teams", category: "communication", icon: faComments, logo: "/assets/images/connectors/teams.png" },
  { value: "matrix", label: "Matrix", category: "communication", icon: faComments, logo: "/assets/images/connectors/matrix.svg" },
  { value: "signal", label: "Signal", category: "communication", icon: faComments, logo: "/assets/images/connectors/signal.svg" },
  { value: "github", label: "GitHub", category: "development", icon: faCodeBranch, logo: "/assets/images/connectors/github.svg" },
  { value: "gitlab", label: "GitLab", category: "development", icon: faCodeBranch, logo: "/assets/images/connectors/gitlab.svg" },
  { value: "jira", label: "Jira", category: "development", icon: faCodeBranch, logo: "/assets/images/connectors/jira.svg" },
  { value: "linear", label: "Linear", category: "software", icon: faFileLines, logo: "/assets/images/connectors/linear.svg" },
  { value: "notion", label: "Notion", category: "software", icon: faFileLines, logo: "/assets/images/connectors/notion.svg" },
  { value: "trello", label: "Trello", category: "software", icon: faFileLines, logo: "/assets/images/connectors/trello.svg" },
  { value: "asana", label: "Asana", category: "software", icon: faFileLines, logo: "/assets/images/connectors/asana.svg" },
  { value: "confluence", label: "Confluence", category: "software", icon: faFileLines, logo: "/assets/images/connectors/confluence.svg" },
  { value: "google_calendar", label: "Google Calendar", category: "software", icon: faFileLines, logo: "/assets/images/connectors/google-calendar.svg" },
  { value: "google_drive", label: "Google Drive", category: "software", icon: faFileLines, logo: "/assets/images/connectors/google-drive.svg" },
  { value: "aws", label: "AWS", category: "cloud", icon: faCloud, logo: "/assets/images/connectors/aws.png" },
  { value: "runpod", label: "RunPod", category: "cloud", icon: faCloud, logo: "/assets/images/connectors/runpod.png" },
  { value: "contabo", label: "Contabo", category: "cloud", icon: faCloud, logo: "/assets/images/connectors/contabo.svg" },
  { value: "cloudflare", label: "Cloudflare", category: "cloud", icon: faCloud, logo: "/assets/images/connectors/cloudflare.svg" },
  { value: "kubernetes", label: "Kubernetes", category: "cloud", icon: faCloud, logo: "/assets/images/connectors/kubernetes.svg" },
  { value: "postgres", label: "PostgreSQL", category: "data", icon: faDatabase, logo: "/assets/images/connectors/postgres.svg" },
  { value: "mongodb", label: "MongoDB", category: "data", icon: faDatabase, logo: "/assets/images/connectors/mongodb.svg" },
  { value: "openai", label: "OpenAI", category: "api", icon: faWrench, logo: "/assets/images/connectors/openai.png" },
  { value: "weather", label: "Weather", category: "api", icon: faGlobe, logo: "/assets/images/connectors/weather.png" },
  { value: "google", label: "Google Search", category: "api", icon: faSearch, logo: "/assets/images/connectors/google.svg" },
  { value: "taostats", label: "TaoStats", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/taostats.png" },
  { value: "twitter", label: "Twitter/X", category: "social", icon: faComments, logo: "/assets/images/connectors/x.svg" },
  { value: "twitterapi", label: "twitterapi.io", category: "social", icon: faComments, logo: "/assets/images/connectors/twitterapi.png" },
  { value: "bittensor_directory", label: "Bittensor Directory", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor.png" },
  { value: "bittensor_subnet_vendor", label: "Bittensor Vendor API", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor.png" },
  { value: "bittensor_desearch", label: "Bittensor Desearch", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor-desearch.png" },
  { value: "bittensor_datauniverse", label: "Bittensor DataUniverse", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor-datauniverse.png" },
  { value: "bittensor_chutes", label: "Bittensor Chutes", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor-chutes.png" },
  { value: "bittensor_computehorde", label: "Bittensor ComputeHorde", category: "bittensor", icon: faDatabase, logo: "/assets/images/connectors/bittensor.png" },
  { value: "web", label: "Web / Browser", category: "web", icon: faGlobe, logo: "/assets/images/connectors/web.svg" },
  { value: "knowledge", label: "Knowledge", category: "knowledge", icon: faFileLines, logo: "/assets/images/connectors/knowledge.svg" },
  { value: "api", label: "OpenAPI / API", category: "api", icon: faWrench, logo: "/assets/images/connectors/openapi.svg" },
];
const OFFICIAL_CONNECTOR_TYPES = CONNECTOR_TYPES.filter((item) => !["api", "web"].includes(item.value));
const CUSTOM_CONNECTOR_TYPES = CONNECTOR_TYPES.filter((item) => ["api", "web"].includes(item.value));

const STATUS_COPY: Record<string, string> = {
  connected: "Connected",
  needs_auth: "Needs auth",
  not_connected: "Not connected",
};

const PROVIDER_COPY: Record<string, string> = {
  official: "Autoppia official",
  custom: "Custom generated",
};

function tone(status: string) {
  if (status === "connected") return "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30";
  if (status === "needs_auth") return "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function providerTone(provider?: string) {
  if (provider === "custom") return "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30";
  return "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border";
}

function typeMeta(type: string) {
  return CONNECTOR_TYPES.find((item) => item.value === type) || CONNECTOR_TYPES[CONNECTOR_TYPES.length - 1];
}

function toolCount(n: number) {
  return `${n} ${n === 1 ? "tool" : "tools"}`;
}

function useLogoPresentation(src?: string): { tone: "light" | "dark"; scale: number } {
  const [presentation, setPresentation] = useState<{ tone: "light" | "dark"; scale: number }>({ tone: "light", scale: 1 });

  useEffect(() => {
    if (!src) {
      setPresentation({ tone: "light", scale: 1 });
      return;
    }

    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      try {
        const size = 48;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const context = canvas.getContext("2d");
        if (!context) return;

        context.drawImage(image, 0, 0, size, size);
        const pixels = context.getImageData(0, 0, size, size).data;
        let weightedLuminance = 0;
        let weight = 0;
        let minX = size;
        let minY = size;
        let maxX = -1;
        let maxY = -1;
        const cornerIndexes = [
          0,
          (size - 1) * 4,
          (size * (size - 1)) * 4,
          ((size * size) - 1) * 4,
        ];
        const background = cornerIndexes.reduce(
          (acc, index) => {
            acc.r += pixels[index];
            acc.g += pixels[index + 1];
            acc.b += pixels[index + 2];
            acc.a += pixels[index + 3];
            return acc;
          },
          { r: 0, g: 0, b: 0, a: 0 },
        );
        background.r /= cornerIndexes.length;
        background.g /= cornerIndexes.length;
        background.b /= cornerIndexes.length;
        background.a /= cornerIndexes.length;

        for (let index = 0; index < pixels.length; index += 4) {
          const alpha = pixels[index + 3];
          if (alpha < 16) continue;
          const pixel = index / 4;
          const x = pixel % size;
          const y = Math.floor(pixel / size);
          const colorDistance = Math.abs(pixels[index] - background.r)
            + Math.abs(pixels[index + 1] - background.g)
            + Math.abs(pixels[index + 2] - background.b)
            + Math.abs(alpha - background.a);
          const isVisibleMark = alpha < 245 || colorDistance > 42;
          if (isVisibleMark) {
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
          }
          const pixelWeight = alpha / 255;
          weightedLuminance += (0.2126 * pixels[index] + 0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2]) * pixelWeight;
          weight += pixelWeight;
        }

        const visibleWidth = maxX >= minX ? maxX - minX + 1 : size;
        const visibleHeight = maxY >= minY ? maxY - minY + 1 : size;
        const visibleRatio = Math.max(visibleWidth, visibleHeight) / size;
        const scale = Math.min(1.9, Math.max(1, 0.78 / Math.max(visibleRatio, 0.1)));

        if (!cancelled) {
          setPresentation({
            tone: weight > 0 && weightedLuminance / weight > 185 ? "dark" : "light",
            scale: Number(scale.toFixed(2)),
          });
        }
      } catch {
        if (!cancelled) setPresentation({ tone: "light", scale: 1 });
      }
    };
    image.onerror = () => {
      if (!cancelled) setPresentation({ tone: "light", scale: 1 });
    };
    image.src = src;

    return () => {
      cancelled = true;
    };
  }, [src]);

  return presentation;
}

function ConnectorLogo({ type, className = "w-9 h-9" }: { type: string; className?: string }) {
  const meta = typeMeta(type);
  const logoPresentation = useLogoPresentation(meta.logo);

  if (meta.logo) {
    const tileClass = logoPresentation.tone === "dark"
      ? "bg-gray-950 border-gray-700"
      : "bg-white border-gray-200 dark:border-dark-border";

    return (
      <span className={`${className} rounded-lg ${tileClass} border flex items-center justify-center flex-shrink-0 overflow-hidden`}>
        <img src={meta.logo} alt="" className="w-full h-full object-contain p-1" style={{ transform: `scale(${logoPresentation.scale})` }} />
      </span>
    );
  }

  return (
    <span className={`${className} rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0`}>
      <FontAwesomeIcon icon={meta.icon} className="text-sm" />
    </span>
  );
}

function ConnectorTypeSelect({
  value,
  onChange,
  options,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  options: typeof CONNECTOR_TYPES;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = options.find((item) => item.value === value) || options[0];

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg pl-2 pr-3 flex items-center gap-2 text-sm text-gray-800 dark:text-gray-100 outline-none hover:border-primary/50 transition-colors"
      >
        <ConnectorLogo type={current?.value || ""} className="w-6 h-6" />
        <span className="flex-1 text-left truncate">{current?.label}</span>
        <FontAwesomeIcon icon={faChevronDown} className={`text-[10px] text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-full min-w-[15rem] max-h-72 overflow-auto rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-soft-lg py-1">
          {options.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => { onChange(item.value); setOpen(false); }}
              className={`w-full px-2 py-1.5 flex items-center gap-2 text-sm text-left hover:bg-gray-100 dark:hover:bg-dark-border transition-colors ${item.value === value ? "text-primary font-semibold" : "text-gray-700 dark:text-gray-200"}`}
            >
              <ConnectorLogo type={item.value} className="w-6 h-6" />
              <span className="flex-1 truncate">{item.label}</span>
              {item.value === value && <FontAwesomeIcon icon={faCheck} className="text-[10px] text-primary" />}
            </button>
          ))}
        </div>
      )}
    </div>
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
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const { showToast } = useToast();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState("");
  const [connectorMode, setConnectorMode] = useState<"official" | "custom">("official");
  const [showAddConnector, setShowAddConnector] = useState(false);
  const [connectorFilter, setConnectorFilter] = useState<"all" | "official" | "custom">("all");
  const [name, setName] = useState("");
  const [type, setType] = useState("gmail");
  const [customType, setCustomType] = useState("api");
  const [selectedId, setSelectedId] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [draft, setDraft] = useState({ name: "", type: "gmail", description: "", config: {} as Record<string, string> });

  const selected = useMemo(() => connectors.find((connector) => connector.connectorId === selectedId) || null, [connectors, selectedId]);
  const needsAuthCount = useMemo(() => connectors.filter((connector) => connector.status === "needs_auth" || connector.status === "not_connected").length, [connectors]);
  const connectedCount = useMemo(() => connectors.filter((connector) => connector.status === "connected").length, [connectors]);

  const responseMessage = (res: Response, fallback: string) => apiErrorMessage(res, fallback, "this connector");

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
      showToast("Could not load connectors.", "error");
    } finally {
      setLoading(false);
    }
  }, [companyId, showToast, user.email]);

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
    const connectorType = connectorMode === "custom" ? customType : type;
    const selectedType = typeMeta(connectorType);
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: name.trim() || selectedType.label,
          type: connectorType,
          category: selectedType.category,
          description: `${selectedType.label} connector for this company.`,
          status: connectorMode === "custom" ? "not_connected" : connectorType === "knowledge" ? "connected" : "not_connected",
          provider: connectorMode,
          generationStatus: connectorMode === "custom" && connectorType === "api" ? "needs_swagger" : connectorMode === "custom" ? "needs_start_url" : "autoppia_supported",
          surface: connectorType === "web" ? "webapp" : connectorType === "api" ? "api" : "",
          authRequired: false,
          discoveryStatus: connectorMode === "custom" ? "pending" : "ready",
          discoveryMode: "task_scoped",
          runtimeRequirements: connectorType === "web" ? ["browser", "network"] : connectorType === "api" ? ["network"] : [],
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not create connector."));
      setName("");
      setShowAddConnector(false);
      await loadConnectors();
      showToast("Connector added.", "success");
    } catch (err) {
      console.error("Failed to create connector:", err);
      showToast(err instanceof Error ? err.message : "Could not create connector.", "error");
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
      if (!res.ok) throw new Error(await responseMessage(res, "Could not save connector."));
      await loadConnectors();
      showToast("Connector saved.", "success");
    } catch (err) {
      console.error("Failed to update connector:", err);
      showToast(err instanceof Error ? err.message : "Could not save connector.", "error");
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
      if (!res.ok) throw new Error(await responseMessage(res, "Could not test connector."));
      const data = await res.json();
      setConnectors((prev) => prev.map((item) => item.connectorId === connector.connectorId ? data.connector : item));
      showToast(data.success ? "Connector test passed." : data.message || "Connector needs attention.", data.success ? "success" : "error");
    } catch (err) {
      console.error("Failed to test connector:", err);
      showToast(err instanceof Error ? err.message : "Could not test connector.", "error");
    } finally {
      setTestingId("");
    }
  };

  const deleteConnector = async (connectorId: string) => {
    if (saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/connectors/${connectorId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not delete connector."));
      if (selectedId === connectorId) setSelectedId("");
      await loadConnectors();
      showToast("Connector deleted.", "success");
    } catch (err) {
      console.error("Failed to delete connector:", err);
      showToast(err instanceof Error ? err.message : "Could not delete connector.", "error");
    } finally {
      setSaving(false);
    }
  };

  const configFields = selected ? [...(selected.toolkit.authFields || []), ...(selected.toolkit.configFields || [])] : [];

  const officialConnectors = useMemo(() => connectors.filter((connector) => (connector.provider || "official") !== "custom"), [connectors]);
  const customConnectors = useMemo(() => connectors.filter((connector) => connector.provider === "custom"), [connectors]);
  const filteredConnectors = useMemo(
    () => connectors.filter((connector) => {
      if (connectorFilter === "all") return true;
      if (connectorFilter === "custom") return connector.provider === "custom";
      return (connector.provider || "official") !== "custom";
    }),
    [connectorFilter, connectors],
  );

  const renderConnectorCard = (connector: Connector) => {
    const testing = testingId === connector.connectorId;
    return (
      <button
        key={connector.connectorId}
        onClick={() => setSelectedId(connector.connectorId)}
        className="group flex flex-col text-left bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-4 hover:border-primary/50 hover:shadow-soft hover:-translate-y-0.5 transition-all duration-200"
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
        <div className="flex items-center gap-1.5 mt-3">
          <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${providerTone(connector.provider)}`}>
            {PROVIDER_COPY[connector.provider || "official"] || connector.provider}
          </span>
          {connector.discoveryStatus && (
            <span className="px-2 py-0.5 rounded-md text-[11px] font-medium border bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-500/30">
              discovery {connector.discoveryStatus}
            </span>
          )}
          {connector.generationStatus && (
            <span className="px-2 py-0.5 rounded-md text-[11px] font-medium border bg-gray-50 dark:bg-dark-bg text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
              {connector.generationStatus.replace(/_/g, " ")}
            </span>
          )}
        </div>
        <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400 mt-3 line-clamp-2 min-h-[2rem]">{connector.description || "No description."}</p>
        {connector.type === "knowledge" && connector.vectorIndex && (
          <div className="mt-2 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border px-2 py-1.5">
            <p className="text-[10px] uppercase tracking-wide text-gray-400">Vector DB</p>
            <p className="text-[11px] font-medium text-gray-700 dark:text-gray-200 truncate">
              {connector.vectorIndex.provider} / {connector.vectorIndex.collectionName}
            </p>
          </div>
        )}
        {(connector.runtimeRequirements || []).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {(connector.runtimeRequirements || []).slice(0, 3).map((requirement) => (
              <span key={requirement} className="px-1.5 py-0.5 rounded-md bg-gray-100 dark:bg-dark-bg text-[10px] font-semibold text-gray-500 dark:text-gray-300">
                {requirement}
              </span>
            ))}
          </div>
        )}
        <div className="flex items-center justify-between mt-auto pt-3 border-t border-gray-100 dark:border-dark-border">
          <span className="text-xs font-medium text-gray-400 dark:text-gray-500">{toolCount(connector.toolkit.tools.length)}</span>
          <span
            onClick={(event) => {
              event.stopPropagation();
              testConnector(connector);
            }}
            className="inline-flex items-center h-7 px-2.5 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border hover:border-gray-300 dark:hover:border-dark-border transition-colors"
          >
            <FontAwesomeIcon icon={testing ? faSpinner : faFlask} className={`mr-1.5 text-[10px] ${testing ? "animate-spin" : ""}`} />
            Test
          </span>
        </div>
      </button>
    );
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
              <div className="space-y-3">
                <p><strong>Connector</strong> belongs to the Company and can be reused by multiple agents.</p>
                <p><strong>Toolkit</strong> is generated from the connector and is what agents actually call: Gmail tools, Holded tools, browser tools, API tools, or knowledge search.</p>
                <p>Configure auth, test the connector, then agents in this company can use its toolkit.</p>
              </div>
            </InfoIcon>
          </div>
          <div className="flex items-center gap-2">
            {companyId && (
              <button
                onClick={() => setShowAddConnector(true)}
                className="h-8 px-3 rounded-lg bg-gradient-primary text-white text-xs font-semibold inline-flex items-center gap-2 shadow-glow"
                title="Add connector"
              >
                <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
                Add connector
              </button>
            )}
            {companyId && connectors.length > 0 && (
              <>
                <span
                  className="px-2.5 h-8 rounded-lg border border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 text-xs font-semibold inline-flex items-center"
                  title="Connectors ready for agent setup"
                >
                  {connectedCount} ready
                </span>
                {needsAuthCount > 0 && (
                  <span
                    className="px-2.5 h-8 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs font-semibold inline-flex items-center"
                    title="Connectors that need credentials or a successful test"
                  >
                    {needsAuthCount} need setup
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          {!companyId && (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-amber-200 dark:border-amber-500/30 p-5 mb-5 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Create a company first</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Connectors belong to a company so agents can reuse them safely.</p>
              </div>
              <button
                onClick={() => window.dispatchEvent(new CustomEvent("automata-open-company-onboarding"))}
                className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow flex-shrink-0"
              >
                Start onboarding
              </button>
            </div>
          )}

          {showAddConnector && (
          <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowAddConnector(false)} />
            <div className="relative w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-5">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex items-start gap-2.5 min-w-0">
                <span className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                  <FontAwesomeIcon icon={faPlus} className="text-xs" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Add connector</p>
                  <p className="text-[11px] leading-4 text-gray-400 dark:text-gray-500">
                    Official connectors come with supported toolkits. Custom API/Web connectors are harvested from benchmarks.
                  </p>
                </div>
              </div>
              <button onClick={() => setShowAddConnector(false)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border flex-shrink-0">
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Kind</span>
              <SelectDropdown
                value={connectorMode}
                onChange={(next) => setConnectorMode(next as "official" | "custom")}
                options={[
                  { value: "official", label: "Official" },
                  { value: "custom", label: "Custom API/Web" },
                ]}
              />
            </label>
            <label className="block">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={connectorMode === "custom" ? "Connector name, e.g. Internal CRM API or BOPA Portal" : "Connector name, e.g. Gmail, Holded, Telegram"}
              className="h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-800 dark:text-gray-100 outline-none"
            />
            </label>
            <label className="block">
              <span className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Type</span>
            <ConnectorTypeSelect
              value={connectorMode === "custom" ? customType : type}
              onChange={(next) => connectorMode === "custom" ? setCustomType(next) : setType(next)}
              options={connectorMode === "custom" ? CUSTOM_CONNECTOR_TYPES : OFFICIAL_CONNECTOR_TYPES}
            />
            </label>
            <button onClick={createConnector} disabled={saving || !companyId} className="h-10 px-4 rounded-lg bg-gradient-primary text-white text-sm font-medium disabled:opacity-60 self-end">
              <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
              Add connector
            </button>
            </div>
            {connectorMode === "custom" && (
              <p className="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">
                Custom connectors are currently API or Web only. APIs need a Swagger/OpenAPI URL. Web apps need start URL, optional login URL, username and password. Harvesting custom connectors requires a benchmark.
              </p>
            )}
            </div>
          </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
            </div>
          ) : connectors.length === 0 ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">No connectors yet. Add Gmail, Holded, Telegram, BOPA, or Knowledge for this company.</p>
              <button
                onClick={() => setShowAddConnector(true)}
                className="h-9 px-4 rounded-lg bg-gradient-primary text-white text-sm font-semibold inline-flex items-center gap-2"
              >
                <FontAwesomeIcon icon={faPlus} className="text-xs" />
                Add connector
              </button>
            </div>
          ) : (
            <div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Company connectors</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    {connectors.length} total · {officialConnectors.length} official · {customConnectors.length} custom
                  </p>
                </div>
                <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-thin">
                  {[
                    { key: "all" as const, label: "All", count: connectors.length },
                    { key: "official" as const, label: "Official", count: officialConnectors.length },
                    { key: "custom" as const, label: "Custom", count: customConnectors.length },
                  ].map((item) => (
                    <button
                      key={item.key}
                      onClick={() => setConnectorFilter(item.key)}
                      className={`h-8 px-3 rounded-lg text-xs font-semibold border whitespace-nowrap transition-colors ${
                        connectorFilter === item.key
                          ? "bg-white dark:bg-dark-surface text-primary border-primary/30 shadow-sm"
                          : "bg-white/70 dark:bg-dark-surface/70 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border hover:bg-white dark:hover:bg-dark-surface"
                      }`}
                    >
                      {item.label}
                      <span className={`ml-1.5 px-1.5 rounded-md text-[10px] ${connectorFilter === item.key ? "bg-primary/10 text-primary" : "bg-gray-100 dark:bg-dark-border text-gray-500 dark:text-gray-400"}`}>{item.count}</span>
                    </button>
                  ))}
                </div>
              </div>
              {filteredConnectors.length === 0 ? (
                <div className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-10 text-center text-sm text-gray-500 dark:text-gray-400">
                  No connectors match this filter.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
                  {filteredConnectors.map((connector) => renderConnectorCard(connector))}
                </div>
              )}
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
                  <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${providerTone(selected.provider)}`}>{PROVIDER_COPY[selected.provider || "official"] || selected.provider}</span>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  {selected.provider === "custom"
                    ? "Custom connector generated for this company. Add API docs/auth so Automata can draft a richer toolkit."
                    : "Official Autoppia connector. Its toolkit can be reused by agents in this company."}
                </p>
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
                    <ConnectorTypeSelect
                      value={draft.type}
                      onChange={(next) => setDraft((prev) => ({ ...prev, type: next }))}
                      options={selected.provider === "custom" ? CUSTOM_CONNECTOR_TYPES : OFFICIAL_CONNECTOR_TYPES}
                    />
                    <textarea value={draft.description} onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))} rows={3} className="sm:col-span-2 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" placeholder="Description" />
                  </div>
                </div>

                <div className="rounded-xl border border-gray-100 dark:border-dark-border p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FontAwesomeIcon icon={faKey} className="text-primary text-xs" />
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">Auth and config</p>
                  </div>
                  {selected.type === "knowledge" && selected.vectorIndex && (
                    <div className="mb-4 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <FontAwesomeIcon icon={faDatabase} className="text-primary text-xs" />
                        <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">Vector database target</p>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="block text-gray-400">Provider</span>
                          <span className="font-medium text-gray-800 dark:text-gray-100">{selected.vectorIndex.provider}</span>
                        </div>
                        <div>
                          <span className="block text-gray-400">Collection</span>
                          <span className="font-mono text-[11px] text-gray-800 dark:text-gray-100 break-all">{selected.vectorIndex.collectionName}</span>
                        </div>
                        <div>
                          <span className="block text-gray-400">Embeddings</span>
                          <span className="font-medium text-gray-800 dark:text-gray-100">{selected.vectorIndex.embeddingProvider || "hash"}</span>
                        </div>
                        <div>
                          <span className="block text-gray-400">Model</span>
                          <span className="font-medium text-gray-800 dark:text-gray-100">{selected.vectorIndex.embeddingModel || "hash-256"}</span>
                        </div>
                      </div>
                    </div>
                  )}
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
                  {selected.provider === "custom" && selected.type === "api" && (
                    <p className="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">
                      For a custom API connector, provide `openApiUrl` or `docsUrl`. The API harvester uses that spec plus a benchmark to generate task-scoped tools and skills.
                    </p>
                  )}
                  {selected.provider === "custom" && selected.type === "web" && (
                    <p className="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">
                      For a custom web connector, provide `startUrl`, optional `loginUrl`, and auth if needed. The web harvester uses benchmark tasks to create skills, not generic browser tools.
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
                  <span className="text-xs text-gray-400">{toolCount(selected.toolkit.tools.length)}</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {selected.toolkit.runtimeRequirements.map((requirement) => (
                    <span key={requirement} className="px-2 py-0.5 rounded-md text-[11px] font-medium border bg-white dark:bg-dark-surface text-gray-500 dark:text-gray-400 border-gray-200 dark:border-dark-border">
                      {requirement.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>

                <button
                  onClick={() => navigate(`/capabilities?connectorId=${encodeURIComponent(selected.connectorId)}`)}
                  className="w-full mb-3 h-9 rounded-lg border border-primary/40 text-primary text-xs font-semibold hover:bg-primary/5 transition-colors flex items-center justify-center gap-2"
                  title="Publish tools or run harvesters from Capabilities"
                >
                  <FontAwesomeIcon icon={faWandMagicSparkles} className="text-[11px]" />
                  Generate capabilities
                </button>
                <p className="text-[11px] leading-4 text-gray-400 dark:text-gray-500 mb-3">
                  Official connectors publish default tools. Custom APIs/Web apps generate task-scoped capabilities from benchmarks. Manage all generation runs under Capabilities.
                </p>

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
              <button onClick={() => setConfirmDelete(true)} disabled={saving} className="h-9 px-3 rounded-lg border border-red-200 dark:border-red-500/30 text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-60">
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

      {selected && confirmDelete && (
        <ConfirmModal
          title="Delete connector"
          message={`Delete "${selected.name}"? Agents in this company will lose access to its toolkit. This cannot be undone.`}
          onConfirm={() => { setConfirmDelete(false); deleteConnector(selected.connectorId); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
}
