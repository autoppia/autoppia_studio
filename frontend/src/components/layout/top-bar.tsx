import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faKey,
  faArrowUp,
  faChevronDown,
  faCoins,
  faBuilding,
  faPen,
  faPlus,
  faTrash,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { Company } from "../../utils/types";

const WALLET_PLACEHOLDER = { balance: "0.00", currency: "EUR" };

export default function TopBar() {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [modalMode, setModalMode] = useState<"create" | "edit" | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [companyDescription, setCompanyDescription] = useState("");
  const [companyMenuOpen, setCompanyMenuOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const wallet = WALLET_PLACEHOLDER;

  const loadCompanies = () => {
    if (!user.email) return;
    fetch(`${process.env.REACT_APP_API_URL}/companies?email=${encodeURIComponent(user.email)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data) => {
        const next = data.companies || [];
        setCompanies(next);
        if (!companyId && next[0]?.companyId) {
          setCompanyId(next[0].companyId);
          localStorage.setItem("automata_company_id", next[0].companyId);
        }
      })
      .catch((err) => console.error("Failed to load companies:", err));
  };

  useEffect(() => {
    loadCompanies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email, companyId]);

  if (!user.isAuthenticated) return null;

  const selectedCompany = companies.find((company) => company.companyId === companyId) || companies[0] || null;

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
      const res = await fetch(`${process.env.REACT_APP_API_URL}/companies${isEdit ? `/${selectedCompany.companyId}` : ""}`, {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          name: companyName.trim(),
          description: companyDescription.trim(),
          industry: selectedCompany?.industry || "",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const nextId = data.company?.companyId;
      if (nextId) {
        setCompanyId(nextId);
        localStorage.setItem("automata_company_id", nextId);
        window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: nextId } }));
      }
      setModalMode(null);
      loadCompanies();
    } catch (err) {
      console.error("Failed to save company:", err);
    } finally {
      setSaving(false);
    }
  };

  const deleteCompany = async () => {
    if (!selectedCompany || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL}/companies/${selectedCompany.companyId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      localStorage.removeItem("automata_company_id");
      setCompanyId("");
      setCompanyMenuOpen(false);
      window.dispatchEvent(new CustomEvent("automata-company-changed", { detail: { companyId: "" } }));
      loadCompanies();
    } catch (err) {
      console.error("Failed to delete company:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <header
      className="flex items-center justify-end h-12 px-4 flex-shrink-0 gap-2
        border-b border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-bg"
    >
      <div className="mr-auto flex items-center gap-2 min-w-0">
        <div className="relative">
          <button
            onClick={() => setCompanyMenuOpen((open) => !open)}
            className="h-9 min-w-[220px] max-w-[320px] rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-surface px-3 flex items-center gap-2 text-left hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
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
            <div className="absolute left-0 top-11 z-[90] w-[320px] max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-2">
              <div className="max-h-64 overflow-auto">
                {companies.map((company) => (
                  <button
                    key={company.companyId}
                    onClick={() => selectCompany(company.companyId)}
                    className={`w-full rounded-lg px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-dark-border ${company.companyId === selectedCompany?.companyId ? "bg-primary/5" : ""}`}
                  >
                    <span className="block text-sm font-semibold text-gray-900 dark:text-white truncate">{company.name}</span>
                    <span className="block text-xs text-gray-400 dark:text-gray-500 truncate">{company.description || "No description"}</span>
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-2 border-t border-gray-100 dark:border-dark-border mt-2 pt-2">
                <button onClick={openCreate} className="h-8 rounded-lg bg-gradient-primary text-white text-xs font-semibold">
                  <FontAwesomeIcon icon={faPlus} className="mr-1.5 text-[10px]" />
                  New
                </button>
                <button onClick={openEdit} disabled={!selectedCompany} className="h-8 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-40">
                  <FontAwesomeIcon icon={faPen} className="mr-1.5 text-[10px]" />
                  Edit
                </button>
                <button onClick={deleteCompany} disabled={!selectedCompany || saving} className="h-8 rounded-lg border border-red-200 dark:border-red-500/30 text-xs font-semibold text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40">
                  <FontAwesomeIcon icon={faTrash} className="mr-1.5 text-[10px]" />
                  Delete
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Credit balance — clickable shortcut to billing */}
      <button
        onClick={() => navigate("/settings?tab=credit")}
        className="hidden sm:flex items-center gap-1.5 h-8 px-2.5 rounded-lg
          border border-gray-200 dark:border-dark-border
          text-xs font-medium text-gray-600 dark:text-gray-300
          hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
        title="Available credit"
      >
        <FontAwesomeIcon icon={faCoins} className="text-[10px] text-[#FF7E5F]" />
        <span>{parseFloat(wallet.balance).toFixed(2)} Credits</span>
      </button>

      {/* API Key shortcut */}
      <button
        onClick={() => navigate("/settings?tab=api-keys")}
        className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg
          border border-gray-200 dark:border-dark-border
          text-xs font-medium text-gray-600 dark:text-gray-300
          hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
        title="API Keys"
      >
        <FontAwesomeIcon icon={faKey} className="text-[10px]" />
        <span className="hidden md:inline">API Key</span>
      </button>

      {/* Upgrade CTA */}
      <button
        onClick={() => navigate("/settings?tab=credit")}
        className="hidden sm:flex items-center gap-1.5 h-8 px-3 rounded-lg
          bg-gradient-primary text-white text-xs font-semibold
          shadow-glow hover:shadow-glow-lg transition-all"
      >
        <FontAwesomeIcon icon={faArrowUp} className="text-[10px]" />
        <span>Upgrade</span>
      </button>

      {modalMode && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setModalMode(null)} />
          <div className="relative w-full max-w-md rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">{modalMode === "create" ? "Create Company" : "Edit Company"}</h3>
              <button onClick={() => setModalMode(null)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border">
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Company name"
                className="w-full h-10 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 text-sm text-gray-900 dark:text-white outline-none"
              />
              <textarea
                value={companyDescription}
                onChange={(e) => setCompanyDescription(e.target.value)}
                placeholder="What does this company do?"
                rows={3}
                className="w-full rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 py-2 text-sm text-gray-900 dark:text-white outline-none resize-none"
              />
            </div>
            <button onClick={saveCompany} disabled={saving || !companyName.trim()} className="mt-4 w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-semibold disabled:opacity-60">
              {saving ? "Saving..." : "Save Company"}
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
