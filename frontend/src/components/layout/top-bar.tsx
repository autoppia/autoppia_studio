import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faKey,
  faChevronDown,
  faBuilding,
  faCircleHalfStroke,
  faRightFromBracket,
  faRobot,
  faPen,
  faPlus,
  faTrash,
  faXmark,
  faUser,
  faGear,
} from "@fortawesome/free-solid-svg-icons";
import { logout } from "../../redux/userSlice";
import { Company } from "../../utils/types";
import CelerisOnboarding from "../home/celeris-onboarding";
import ConfirmModal from "../common/confirm-modal";
import { useToast } from "../common/toast";
import { apiErrorMessage } from "../../utils/api-error";
import ActivityCenter from "./activity-center";
import PrimaryNav from "./primary-nav";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

export default function TopBar() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const user = useSelector((state: any) => state.user);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [modalMode, setModalMode] = useState<"create" | "edit" | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [companyDescription, setCompanyDescription] = useState("");
  const [companyMenuOpen, setCompanyMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmDeleteCompany, setConfirmDeleteCompany] = useState(false);
  const [onboardingCompanyId, setOnboardingCompanyId] = useState(localStorage.getItem("automata_onboarding_company_id") || "");
  const [pendingOnboardingCompany, setPendingOnboardingCompany] = useState<Company | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [selectedCompanyIsEmpty, setSelectedCompanyIsEmpty] = useState(false);
  const { showToast } = useToast();

  const loadCompanies = () => {
    if (!user.email) return;
    fetch(`${apiUrl}/companies?email=${encodeURIComponent(user.email)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data) => {
        const next = data.companies || [];
        setCompanies(next);
        const selectedExists = companyId && next.some((company: Company) => company.companyId === companyId);
        if ((!companyId || !selectedExists) && next[0]?.companyId) {
          const nextId = next[0].companyId;
          setCompanyId(nextId);
          localStorage.setItem("automata_company_id", nextId);
          window.setTimeout(() => {
            window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: nextId } }));
          }, 0);
        }
      })
      .catch((err) => console.error("Failed to load companies:", err));
  };

  useEffect(() => {
    loadCompanies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email, companyId]);

  const selectedCompany = companies.find((company) => company.companyId === companyId) || companies[0] || null;
  const onboardingTargetCompany = pendingOnboardingCompany || selectedCompany;
  const canOnboardSelectedCompany = !!selectedCompany && selectedCompany.name !== "Default Company" && (selectedCompany.companyId === onboardingCompanyId || selectedCompanyIsEmpty);

  const selectCompany = (nextId: string) => {
    setCompanyId(nextId);
    localStorage.setItem("automata_company_id", nextId);
    window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: nextId } }));
    setCompanyMenuOpen(false);
  };

  const openCreate = () => {
    setCompanyName("");
    setCompanyDescription("");
    setCompanyMenuOpen(false);
    setModalMode("create");
  };

  useEffect(() => {
    const handler = () => openCreate();
    window.addEventListener("automata-open-company-onboarding", handler);
    return () => window.removeEventListener("automata-open-company-onboarding", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEdit = () => {
    if (!selectedCompany) return;
    setCompanyName(selectedCompany.name);
    setCompanyDescription(selectedCompany.description || "");
    setCompanyMenuOpen(false);
    setModalMode("edit");
  };

  const saveCompany = async () => {
    if (!user.email || saving || !companyName.trim()) return;
    setSaving(true);
    try {
      const isEdit = modalMode === "edit" && selectedCompany;
      const res = await fetch(`${apiUrl}/companies${isEdit ? `/${selectedCompany.companyId}` : ""}`, {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          name: companyName.trim(),
          description: companyDescription.trim(),
          industry: selectedCompany?.industry || "",
        }),
      });
      if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not save company. Please try again.", "this company"));
      const data = await res.json();
      const nextId = data.company?.companyId;
      if (nextId) {
        const nextCompany = data.company as Company;
        setCompanyId(nextId);
        setPendingOnboardingCompany(!isEdit ? nextCompany : null);
        localStorage.setItem("automata_company_id", nextId);
        window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: nextId } }));
        if (!isEdit) {
          setOnboardingCompanyId(nextId);
          localStorage.setItem("automata_onboarding_company_id", nextId);
          setShowOnboarding(true);
        }
      }
      setModalMode(null);
      loadCompanies();
    } catch (err) {
      console.error("Failed to save company:", err);
      showToast(err instanceof Error && err.message ? err.message : "Could not save company. Please try again.", "error");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!user.email || !selectedCompany?.companyId || selectedCompany.name === "Default Company") {
      setSelectedCompanyIsEmpty(false);
      return;
    }
    let cancelled = false;
    const checkCompanyIsEmpty = async () => {
      try {
        const params = new URLSearchParams({ email: user.email, companyId: selectedCompany.companyId });
        const [agentsRes, connectorsRes] = await Promise.all([
          fetch(`${apiUrl}/agents?${params.toString()}`),
          fetch(`${apiUrl}/connectors?${params.toString()}`),
        ]);
        if (cancelled) return;
        const agentsData = agentsRes.ok ? await agentsRes.json() : { agents: [] };
        const connectorsData = connectorsRes.ok ? await connectorsRes.json() : { connectors: [] };
        if (cancelled) return;
        setSelectedCompanyIsEmpty((agentsData.agents || []).length === 0 && (connectorsData.connectors || []).length === 0);
      } catch (err) {
        if (!cancelled) setSelectedCompanyIsEmpty(false);
      }
    };
    checkCompanyIsEmpty();
    return () => {
      cancelled = true;
    };
  }, [user.email, selectedCompany?.companyId, selectedCompany?.name]);

  if (!user.isAuthenticated) return null;

  const darkThemeHandler = () => {
    const isDark = document.documentElement.classList.toggle("dark");
    try {
      localStorage.setItem("theme", isDark ? "dark" : "light");
    } catch {
      /* ignore storage errors */
    }
  };

  const deleteCompany = async () => {
    if (!selectedCompany || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/companies/${selectedCompany.companyId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await apiErrorMessage(res, "Could not delete company. Please try again.", "this company"));
      localStorage.removeItem("automata_company_id");
      setCompanyId("");
      setCompanyMenuOpen(false);
      window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: "" } }));
      loadCompanies();
      showToast("Company deleted.", "success");
    } catch (err) {
      console.error("Failed to delete company:", err);
      showToast(err instanceof Error && err.message ? err.message : "Could not delete company. Please try again.", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <header
      className="relative flex items-center h-14 px-4 flex-shrink-0 gap-2
        border-b border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-bg"
    >
      <button
        onClick={() => navigate("/canvas")}
        className="flex h-9 flex-shrink-0 items-center gap-2 rounded-xl px-1.5 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
        title="Autoppia Studio — Canvas"
      >
        <img src="/assets/images/logos/main.webp" alt="Autoppia" className="h-6 w-6 object-contain" />
        <span className="hidden items-center gap-1.5 sm:flex">
          <span className="text-[15px] font-semibold tracking-tight text-gray-900 dark:text-white">Autoppia</span>
          <span className="rounded-md bg-primary/15 px-1.5 py-0.5 text-[9px] font-bold uppercase leading-none tracking-wider text-primary">
            Studio
          </span>
        </span>
      </button>

      <div className="mx-1 hidden h-6 w-px bg-gray-200 dark:bg-zinc-800/80 sm:block" />

      <div className="flex items-center gap-2 min-w-0">
        <div className="relative">
          <button
            onClick={() => setCompanyMenuOpen((open) => !open)}
            className="h-9 min-w-[220px] max-w-[320px] rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-gray-50 dark:bg-zinc-900/70 px-3 flex items-center gap-2 text-left hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
            title="Company"
          >
            <span className="w-6 h-6 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
              <FontAwesomeIcon icon={faBuilding} className="text-[10px]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[10px] uppercase tracking-wide text-gray-400 leading-3">Company</span>
              <span className="block text-xs font-semibold text-gray-800 dark:text-gray-100 truncate">{selectedCompany?.name || "Select company"}</span>
            </span>
            <FontAwesomeIcon icon={faChevronDown} className="text-[10px] text-gray-400" />
          </button>
          {companyMenuOpen && (
            <div className="absolute left-0 top-11 z-[90] w-[320px] max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl dark:shadow-black/40 p-2 backdrop-blur-sm">
              <div className="max-h-64 overflow-auto">
                {companies.map((company) => (
                  <button
                    key={company.companyId}
                    onClick={() => selectCompany(company.companyId)}
                    className="w-full rounded-lg px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-white/5"
                  >
                    <span className="block text-sm font-semibold text-gray-900 dark:text-white truncate">{company.name}</span>
                    <span className="block text-xs text-gray-400 dark:text-gray-500 truncate">{company.description || "No description"}</span>
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-2 border-t border-gray-100 dark:border-zinc-800/80 mt-2 pt-2">
                <button onClick={openCreate} className="h-8 rounded-lg bg-gradient-primary text-white text-xs font-semibold">
                  <FontAwesomeIcon icon={faPlus} className="mr-1.5 text-[10px]" />
                  New
                </button>
                <button onClick={openEdit} disabled={!selectedCompany} className="h-8 rounded-lg border border-gray-200 dark:border-zinc-800/80 text-xs font-semibold text-gray-600 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-white/5 disabled:opacity-40">
                  <FontAwesomeIcon icon={faPen} className="mr-1.5 text-[10px]" />
                  Edit
                </button>
                <button onClick={() => { setCompanyMenuOpen(false); setConfirmDeleteCompany(true); }} disabled={!selectedCompany || saving} className="h-8 rounded-lg border border-red-200 dark:border-red-500/30 text-xs font-semibold text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40">
                  <FontAwesomeIcon icon={faTrash} className="mr-1.5 text-[10px]" />
                  Delete
                </button>
              </div>
            </div>
          )}
        </div>
        {canOnboardSelectedCompany && (
          <button
            onClick={() => setShowOnboarding(true)}
            className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-xs font-semibold shadow-glow flex items-center gap-2"
            title="Start onboarding for this company"
          >
            <FontAwesomeIcon icon={faRobot} className="text-[10px]" />
            Onboard
          </button>
        )}
      </div>

      {/* Spacer pushes the right-side actions to the edge. */}
      <div className="min-w-0 flex-1" />

      {/* Primary navigation — centered to the header (viewport), not the free space. */}
      <div className="pointer-events-none absolute left-1/2 top-0 flex h-14 -translate-x-1/2 items-center">
        <div className="pointer-events-auto">
          <PrimaryNav />
        </div>
      </div>

      {/* New session call-to-action */}
      <button
        onClick={() => navigate("/home")}
        className="flex h-8 items-center gap-2 rounded-lg border border-white/80 bg-white px-3 text-sm font-semibold text-gray-900 shadow-sm transition-colors hover:bg-gray-100"
        title="New session"
      >
        <FontAwesomeIcon icon={faPlus} className="text-[10px]" />
        <span className="hidden sm:inline">New session</span>
      </button>

      {/* Notifications */}
      <ActivityCenter showActivity={false} />

      {/* User menu */}
      <div className="relative">
        <button
          onClick={() => setUserMenuOpen((open) => !open)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-primary text-xs font-semibold text-white shadow-sm ring-1 ring-black/5 transition-transform hover:scale-105"
          title={user.email || "Account"}
          aria-label="Account menu"
        >
          {user.email ? user.email.charAt(0).toUpperCase() : <FontAwesomeIcon icon={faUser} className="text-[11px]" />}
        </button>
        {userMenuOpen && (
          <>
            <div className="fixed inset-0 z-[80]" onClick={() => setUserMenuOpen(false)} />
            <div className="absolute right-0 top-11 z-[90] w-60 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl dark:shadow-black/40 p-1.5">
              <div className="flex items-center gap-2.5 px-2.5 py-2">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-primary text-xs font-semibold text-white">
                  {user.email ? user.email.charAt(0).toUpperCase() : <FontAwesomeIcon icon={faUser} className="text-[11px]" />}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-gray-900 dark:text-white">{user.email || "Account"}</p>
                </div>
              </div>
              <div className="my-1 h-px bg-gray-100 dark:bg-zinc-800/80" />
              <button
                onClick={darkThemeHandler}
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 dark:text-zinc-200 dark:hover:bg-white/5"
              >
                <FontAwesomeIcon icon={faCircleHalfStroke} className="w-4 text-[12px] text-gray-400" />
                Toggle theme
              </button>
              <button
                onClick={() => { setUserMenuOpen(false); navigate("/settings?tab=api-keys"); }}
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 dark:text-zinc-200 dark:hover:bg-white/5"
              >
                <FontAwesomeIcon icon={faKey} className="w-4 text-[12px] text-gray-400" />
                API Keys
              </button>
              <button
                onClick={() => { setUserMenuOpen(false); navigate("/settings"); }}
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 dark:text-zinc-200 dark:hover:bg-white/5"
              >
                <FontAwesomeIcon icon={faGear} className="w-4 text-[12px] text-gray-400" />
                Settings
              </button>
              <div className="my-1 h-px bg-gray-100 dark:bg-zinc-800/80" />
              <button
                onClick={() => { setUserMenuOpen(false); dispatch(logout()); }}
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10"
              >
                <FontAwesomeIcon icon={faRightFromBracket} className="w-4 text-[12px]" />
                Sign out
              </button>
            </div>
          </>
        )}
      </div>

      {confirmDeleteCompany && selectedCompany && (
        <ConfirmModal
          title="Delete company"
          message={`Delete "${selectedCompany.name}"? Its connectors, agents and settings will be removed. This cannot be undone.`}
          onConfirm={() => { setConfirmDeleteCompany(false); deleteCompany(); }}
          onCancel={() => setConfirmDeleteCompany(false)}
        />
      )}

      {modalMode && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setModalMode(null)} />
          <div className="relative w-full max-w-md rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl dark:shadow-black/50 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">{modalMode === "create" ? "Create company" : "Edit company"}</h3>
              <button onClick={() => setModalMode(null)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5">
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Company name"
                className="w-full h-10 rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-gray-50 dark:bg-zinc-950/70 px-3 text-sm text-gray-900 dark:text-white outline-none"
              />
              <textarea
                value={companyDescription}
                onChange={(e) => setCompanyDescription(e.target.value)}
                placeholder="What does this company do?"
                rows={3}
                className="w-full rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-gray-50 dark:bg-zinc-950/70 px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none"
              />
            </div>
            <button onClick={saveCompany} disabled={saving || !companyName.trim()} className="mt-4 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60">
              {saving ? "Saving..." : modalMode === "create" ? "Save and start onboarding" : "Save company"}
            </button>
          </div>
        </div>
      )}

      {showOnboarding && onboardingTargetCompany && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-6">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setShowOnboarding(false)} />
          <div className="relative flex w-full max-w-6xl max-h-[calc(100vh-1.5rem)] sm:max-h-[calc(100vh-3rem)] flex-col overflow-hidden rounded-2xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg shadow-2xl dark:shadow-black/60 animate-slide-up">
            <button
              onClick={() => setShowOnboarding(false)}
              title="Close"
              aria-label="Close onboarding"
              className="absolute right-4 top-4 z-20 flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-white/90 text-gray-400 shadow-sm backdrop-blur-sm transition-colors hover:bg-white hover:text-gray-900 dark:border-zinc-800/80 dark:bg-zinc-900/80 dark:hover:bg-zinc-800 dark:hover:text-white"
            >
              <FontAwesomeIcon icon={faXmark} className="text-sm" />
            </button>
            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin p-4 sm:p-6">
              <CelerisOnboarding
                companyId={onboardingTargetCompany.companyId}
                companyName={onboardingTargetCompany.name}
                companyDescription={onboardingTargetCompany.description || ""}
                onComplete={() => {
                  setShowOnboarding(false);
                  setOnboardingCompanyId("");
                  setPendingOnboardingCompany(null);
                  localStorage.removeItem("automata_onboarding_company_id");
                  loadCompanies();
                }}
              />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
