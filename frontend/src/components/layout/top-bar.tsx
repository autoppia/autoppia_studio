import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faKey,
  faArrowUp,
  faCoins,
  faBuilding,
} from "@fortawesome/free-solid-svg-icons";
import { Company } from "../../utils/types";

const WALLET_PLACEHOLDER = { balance: "0.00", currency: "EUR" };

export default function TopBar() {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");

  const wallet = WALLET_PLACEHOLDER;

  useEffect(() => {
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
  }, [user.email, companyId]);

  if (!user.isAuthenticated) return null;

  return (
    <header
      className="flex items-center justify-end h-12 px-4 flex-shrink-0 gap-2
        border-b border-gray-200 dark:border-dark-border
        bg-white dark:bg-dark-bg"
    >
      <div className="mr-auto flex items-center gap-2 min-w-0">
        <FontAwesomeIcon icon={faBuilding} className="text-xs text-gray-400" />
        <select
          value={companyId}
          onChange={(event) => {
            setCompanyId(event.target.value);
            localStorage.setItem("automata_company_id", event.target.value);
          }}
          className="h-8 max-w-[220px] rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface px-2 text-xs font-medium text-gray-700 dark:text-gray-200 outline-none"
          title="Company"
        >
          {companies.map((company) => (
            <option key={company.companyId} value={company.companyId}>{company.name}</option>
          ))}
        </select>
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
    </header>
  );
}
