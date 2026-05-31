import React, { useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faBuilding,
  faCheck,
  faEnvelope,
  faFileLines,
  faGlobe,
  faSpinner,
} from "@fortawesome/free-solid-svg-icons";

const apiUrl = process.env.REACT_APP_API_URL;

const DEFAULT_TASKS = [
  "Leer el último BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.",
  "Buscar en Gmail una petición de un cliente y clasificarla como nómina, contrato, factura o consulta laboral.",
  "Encontrar la última factura de un cliente en Holded y preparar una respuesta por email.",
  "Revisar documentos internos de la asesoría y responder una consulta laboral básica con fuentes.",
  "Enviar por Telegram un resumen breve de una novedad laboral importante para el equipo.",
];

const DEFAULT_INTEGRATIONS = [
  { key: "gmail", label: "Gmail", icon: faEnvelope, detail: "Emails, clientes y respuestas" },
  { key: "holded", label: "Holded", icon: faFileLines, detail: "Facturas y gestión" },
  { key: "telegram", label: "Telegram", icon: faEnvelope, detail: "Avisos y asistencia" },
  { key: "bopa", label: "BOPA", icon: faGlobe, detail: "Web pública de Andorra" },
  { key: "knowledge", label: "Documentos", icon: faFileLines, detail: "Normativa y conocimiento" },
];

export default function CelerisOnboarding() {
  const user = useSelector((state: any) => state.user);
  const navigate = useNavigate();
  const [companyName, setCompanyName] = useState("Celeris");
  const [description, setDescription] = useState("Asesoría laboral en Andorra que ayuda a empresas y clientes con consultas laborales, facturas, comunicaciones y seguimiento del BOPA.");
  const [websiteUrl, setWebsiteUrl] = useState("https://www.bopa.ad/");
  const [tasks, setTasks] = useState(DEFAULT_TASKS);
  const [selected, setSelected] = useState(DEFAULT_INTEGRATIONS.map((item) => item.key));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const toggleIntegration = (key: string) => {
    setSelected((prev) => prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]);
  };

  const updateTask = (index: number, value: string) => {
    setTasks((prev) => prev.map((task, i) => i === index ? value : task));
  };

  const createDemo = async () => {
    if (!user.email || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await fetch(`${apiUrl}/demo/celeris/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });

      const companyRes = await fetch(`${apiUrl}/companies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          name: companyName.trim() || "Celeris",
          industry: "Labor advisory, Andorra",
          description: description.trim(),
        }),
      });
      if (!companyRes.ok) throw new Error(await companyRes.text());
      const companyData = await companyRes.json();
      const companyId = companyData.company?.companyId || "";
      if (companyId) {
        localStorage.setItem("automata_company_id", companyId);
        window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId } }));
      }

      const cleanTasks = tasks
        .map((prompt, index) => ({
          name: `Celeris task ${index + 1}`,
          prompt: prompt.trim(),
          successCriteria: "El usuario confirma que la respuesta es correcta, usa las fuentes adecuadas y no ejecuta acciones sensibles sin aprobación.",
        }))
        .filter((task) => task.prompt);

      const operatorRes = await fetch(`${apiUrl}/operators`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          name: `${companyName.trim() || "Celeris"} Agent`,
          websiteUrl: websiteUrl.trim(),
          apiSpecUrl: "",
          successCriteria: "Resolver tareas diarias de una asesoría laboral en Andorra usando herramientas, conocimiento y aprobación humana para acciones sensibles.",
          tasks: cleanTasks,
        }),
      });
      if (!operatorRes.ok) throw new Error(await operatorRes.text());
      const operatorData = await operatorRes.json();
      navigate(`/agents/${operatorData.operatorId}`);
    } catch (err: any) {
      setError(err?.message || "Could not create Celeris demo.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-5xl animate-slide-up">
      <div className="mb-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 h-8 rounded-full bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border text-xs font-medium text-gray-500 dark:text-gray-400 mb-4">
          <FontAwesomeIcon icon={faBuilding} className="text-primary" />
          Celeris demo
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold text-gray-900 dark:text-white mb-3">Create a company agent in minutes</h1>
        <p className="text-sm md:text-base text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">
          Automata fills the hard parts: suggested integrations, benchmark tasks, runtime defaults and an initial Celeris Agent.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_0.9fr] gap-4">
        <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Company</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="w-full h-10 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">What does it do?</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Main public web source</label>
            <input value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} className="w-full h-10 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none font-mono" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Systems Celeris uses</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {DEFAULT_INTEGRATIONS.map((item) => {
                const active = selected.includes(item.key);
                return (
                  <button key={item.key} type="button" onClick={() => toggleIntegration(item.key)} className={`flex items-center gap-3 rounded-xl border p-3 text-left transition-colors ${active ? "border-primary bg-primary/5" : "border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg"}`}>
                    <span className={`w-8 h-8 rounded-lg flex items-center justify-center ${active ? "bg-gradient-primary text-white" : "bg-white dark:bg-dark-surface text-gray-400"}`}>
                      <FontAwesomeIcon icon={item.icon} className="text-xs" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-gray-900 dark:text-white">{item.label}</span>
                      <span className="block text-xs text-gray-400 dark:text-gray-500 truncate">{item.detail}</span>
                    </span>
                    {active && <FontAwesomeIcon icon={faCheck} className="ml-auto text-primary text-xs" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gray-200 dark:border-dark-border shadow-soft p-5">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">Daily tasks</p>
            <span className="text-xs text-gray-400">{tasks.filter(Boolean).length} benchmark tasks</span>
          </div>
          <div className="space-y-2">
            {tasks.map((task, index) => (
              <textarea key={index} value={task} onChange={(e) => updateTask(index, e.target.value)} rows={2} className="w-full rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 outline-none resize-none" />
            ))}
          </div>
          {error && <p className="mt-3 text-xs text-red-500">{error}</p>}
          <button onClick={createDemo} disabled={submitting} className="mt-4 w-full h-11 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow flex items-center justify-center gap-2 disabled:opacity-60">
            <FontAwesomeIcon icon={submitting ? faSpinner : faArrowRight} className={`text-xs ${submitting ? "animate-spin" : ""}`} />
            {submitting ? "Creating Celeris..." : "Create Celeris Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
