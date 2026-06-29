import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { groupLandingPath, resolveActiveGroup, visibleNavGroups } from "./nav-config";
import { useStudioMode } from "../../utils/studio-mode";

/** Horizontal primary navigation rendered in the top bar. */
export default function PrimaryNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const mode = useStudioMode();
  const active = resolveActiveGroup(location.pathname);
  const groups = visibleNavGroups(mode);

  return (
    <nav className="flex items-center gap-1">
      {groups.map((group) => {
        const isActive = active?.key === group.key;
        return (
          <button
            key={group.key}
            type="button"
            onClick={() => navigate(groupLandingPath(group))}
            className={`flex h-8 items-center gap-2 rounded-lg px-3 font-mono text-[12px] font-bold uppercase tracking-[0.04em] transition-colors ${
              isActive
                ? "bg-gray-100 text-gray-900 dark:bg-white/[0.08] dark:text-white"
                : "text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-zinc-400 dark:hover:bg-white/[0.05] dark:hover:text-zinc-100"
            }`}
            title={group.label}
          >
            <FontAwesomeIcon icon={group.icon} className={`text-[12px] ${isActive ? "text-primary" : ""}`} />
            <span className="hidden lg:inline">{group.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
