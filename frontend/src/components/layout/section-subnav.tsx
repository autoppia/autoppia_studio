import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { resolveActiveGroup } from "./nav-config";

/**
 * Vertical sub-navigation for the active section. Renders nothing for groups
 * without sub-pages (Canvas, Settings) or for routes outside the nav (so the
 * canvas stays full-window).
 */
export default function SectionSubNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const group = resolveActiveGroup(location.pathname);

  if (!group || group.items.length === 0) return null;

  return (
    <aside className="flex h-full w-52 flex-shrink-0 flex-col border-r border-gray-200 bg-white px-3 py-4 dark:border-dark-border dark:bg-dark-bg">
      <div className="mb-3 px-2">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-zinc-500">
          <FontAwesomeIcon icon={group.icon} className="text-[11px]" />
          {group.label}
        </div>
        <p className="mt-2 text-[11px] leading-4 text-gray-500 dark:text-zinc-400">
          {group.description}
        </p>
      </div>
      <div className="flex flex-col gap-0.5">
        {group.items.map((item) => {
          const isActive =
            location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => navigate(item.path)}
              className={`flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-gray-600 hover:bg-gray-100 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-200"
              }`}
            >
              <FontAwesomeIcon icon={item.icon} className="w-4 text-[12px]" />
              {item.label}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
