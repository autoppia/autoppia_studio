import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faKey,
  faChevronDown,
  faBuilding,
  faCircleHalfStroke,
  faRightFromBracket,
  faPen,
  faPlus,
  faTrash,
  faXmark,
  faUser,
  faGear,
} from "@fortawesome/free-solid-svg-icons";
import { logout } from "../../redux/userSlice";
import { Company } from "../../utils/types";
import OnboardingWindow from "../onboarding/onboarding-window";
import ConfirmModal from "../common/confirm-modal";
import { useToast } from "../common/toast";
import { apiErrorMessage } from "../../utils/api-error";
import ActivityCenter from "./activity-center";
import { getApiUrl } from "../../utils/api-url";
import { groupLandingPath, resolveActiveGroup, visibleNavGroups } from "./nav-config";
import { useStudioMode } from "../../utils/studio-mode";
import ThemeCustomizer from "./theme-customizer";

const apiUrl = getApiUrl();

export default function TopBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const user = useSelector((state: any) => state.user);
  const mode = useStudioMode();
  const navGroups = visibleNavGroups(mode);
  const activeGroup = resolveActiveGroup(location.pathname);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [modalMode, setModalMode] = useState<"create" | "edit" | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [companyDescription, setCompanyDescription] = useState("");
  const [companyMenuOpen, setCompanyMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const companyMenuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDeleteCompany, setConfirmDeleteCompany] = useState(false);
  const [pendingOnboardingCompany, setPendingOnboardingCompany] = useState<Company | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
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

  // Close the company / account dropdowns on any click outside them. A plain
  // `fixed inset-0` overlay does not work here because the top bar uses
  // backdrop-filter, which contains fixed-positioned children to the bar.
  useEffect(() => {
    if (!companyMenuOpen && !userMenuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (companyMenuOpen && companyMenuRef.current && !companyMenuRef.current.contains(target)) {
        setCompanyMenuOpen(false);
      }
      if (userMenuOpen && userMenuRef.current && !userMenuRef.current.contains(target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [companyMenuOpen, userMenuOpen]);

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
    <header className="ck-topbar">
      <div className="ck-topbar-left">
        <button
          className="ck-brand-top"
          onClick={() => navigate("/agents")}
          title="Autoppia Studio"
          aria-label="Autoppia Studio"
        >
          <img src="/assets/images/logos/main.webp" alt="Autoppia" />
          <span className="ck-brand-top-word">Autoppia</span>
          <span className="ck-brand-pill">Studio</span>
        </button>
        <span className="ck-topbar-sep" aria-hidden="true" />
        <div className="flex items-center gap-2 flex-shrink-0">
        <div className="relative" ref={companyMenuRef}>
          <button
            onClick={() => setCompanyMenuOpen((open) => !open)}
            className="group flex h-9 w-[180px] max-w-[200px] items-center gap-2 rounded-lg border border-[color:var(--line)] bg-[color:var(--bg-2)] pl-1.5 pr-2.5 text-left transition-colors hover:border-[color:var(--accent-line)] hover:bg-[color:var(--hover-strong)]"
            title="Company"
          >
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
              <FontAwesomeIcon icon={faBuilding} className="text-[10px]" />
            </span>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block font-sans text-[8px] font-bold uppercase tracking-[0.16em] text-[color:var(--faint)]">Company</span>
              <span className="block truncate text-[13px] font-semibold text-[color:var(--ink)]">{selectedCompany?.name || "Select company"}</span>
            </span>
            <FontAwesomeIcon
              icon={faChevronDown}
              className="flex-shrink-0 text-[9px] text-[color:var(--faint)] transition-transform duration-200 group-hover:text-[color:var(--accent)]"
              style={{ transform: companyMenuOpen ? "rotate(180deg)" : "none" }}
            />
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
      </div>

      <nav className="ck-topbar-nav" aria-label="Primary navigation">
        {navGroups.map((group) => {
          const active = activeGroup?.key === group.key;
          return (
            <button
              key={group.key}
              type="button"
              onClick={() => navigate(groupLandingPath(group))}
              className={`ck-topbar-nav-item${active ? " is-active" : ""}`}
              title={group.description}
            >
              <FontAwesomeIcon icon={group.icon} className="ck-topbar-nav-icon" />
              <span>{group.label}</span>
            </button>
          );
        })}
      </nav>
      </div>

      <div className="ck-topbar-actions">
      <ThemeCustomizer />

      {/* Quick access to settings */}
      <button
        onClick={() => navigate("/settings")}
        className="relative flex h-8 w-8 flex-none items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors hover:bg-gray-100 hover:text-[color:var(--accent)] dark:border-zinc-800/80 dark:text-zinc-300 dark:hover:bg-white/5"
        title="Settings"
        aria-label="Settings"
      >
        <FontAwesomeIcon icon={faGear} className="text-xs" />
      </button>

      {/* New session call-to-action */}
      <button
        onClick={() => navigate("/home")}
        className="ck-newsession-btn"
        title="New session"
        aria-label="New session"
      >
        <FontAwesomeIcon icon={faPlus} className="text-[11px]" />
        <span>New session</span>
      </button>

      {/* Notifications */}
      <ActivityCenter showActivity={false} />

      {/* User menu */}
      <div className="relative" ref={userMenuRef}>
        <button
          onClick={() => setUserMenuOpen((open) => !open)}
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-primary text-[13px] font-bold text-white shadow-sm ring-1 ring-[color:var(--accent-line)] transition-transform hover:scale-105"
          title={user.email || "Account"}
          aria-label="Account menu"
        >
          {user.email ? user.email.charAt(0).toUpperCase() : <FontAwesomeIcon icon={faUser} className="text-[12px]" />}
        </button>
        {userMenuOpen && (
          <>
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
        <OnboardingWindow
          companyId={onboardingTargetCompany.companyId}
          companyName={onboardingTargetCompany.name}
          companyDescription={onboardingTargetCompany.description || ""}
          onClose={() => setShowOnboarding(false)}
          onComplete={() => {
            setShowOnboarding(false);
            setPendingOnboardingCompany(null);
            localStorage.removeItem("automata_onboarding_company_id");
            loadCompanies();
          }}
        />
      )}
    </header>
  );
}
