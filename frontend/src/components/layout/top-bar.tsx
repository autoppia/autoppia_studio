import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faKey,
  faArrowUp,
  faCoins,
  faBookOpen,
} from "@fortawesome/free-solid-svg-icons";

const DOCS_URL = "https://docs.autoppia.com";

const WALLET_PLACEHOLDER = { balance: "0.00", currency: "EUR" };

export default function TopBar() {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);

  if (!user.isAuthenticated) return null;

  const wallet = WALLET_PLACEHOLDER;
  const currencySymbol = wallet.currency === "EUR" ? "€" : "$";

  return (
    <header
      className="flex items-center justify-end h-12 px-4 flex-shrink-0 gap-2
        border-b border-gray-200 dark:border-dark-border
        bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm"
    >
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
        <span>
          {currencySymbol}
          {parseFloat(wallet.balance).toFixed(2)}
        </span>
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

      {/* Docs */}
      <a
        href={DOCS_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center w-8 h-8 rounded-lg
          text-gray-500 dark:text-gray-400
          hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors"
        title="Docs"
      >
        <FontAwesomeIcon icon={faBookOpen} className="text-xs" />
      </a>
    </header>
  );
}
