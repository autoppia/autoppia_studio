import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { NAV_GROUPS, groupLandingPath, resolveActiveGroup } from "./nav-config";

/** Horizontal primary navigation rendered in the top bar. */
export default function PrimaryNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const active = resolveActiveGroup(location.pathname);

  return (
    <nav className="flex items-center gap-2.5">
      {NAV_GROUPS.map((group) => {
        const isActive = active?.key === group.key;
        const className = group.cta
          ? `flex h-9 items-center gap-2 rounded-lg px-3.5 text-sm font-semibold transition-colors border ${
              isActive
                ? "bg-white text-gray-900 border-white shadow-sm"
                : "bg-white text-gray-900 border-white/80 hover:bg-gray-100 shadow-sm"
            }`
          : `flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors ${
              isActive
                ? "bg-primary/10 text-primary"
                : "text-gray-600 hover:bg-gray-100 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-200"
            }`;
        return (
          <button
            key={group.key}
            type="button"
            onClick={() => navigate(groupLandingPath(group))}
            className={className}
            title={group.label}
          >
            <FontAwesomeIcon icon={group.icon} className="text-[12px]" />
            <span className="hidden lg:inline">{group.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
