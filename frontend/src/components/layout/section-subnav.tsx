import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { resolveActiveGroup } from "./nav-config";
import { useStudioMode } from "../../utils/studio-mode";

/**
 * Vertical sub-navigation for the active section. Renders nothing for groups
 * without sub-pages (Canvas, Settings) or for routes outside the nav (so the
 * canvas stays full-window). Dev-only items are hidden in normal mode.
 */
export default function SectionSubNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const mode = useStudioMode();
  const group = resolveActiveGroup(location.pathname);

  const items = group ? group.items.filter((item) => mode === "dev" || !item.devOnly) : [];
  if (!group || items.length === 0) return null;

  return (
    <aside className="flex h-full w-56 flex-shrink-0 flex-col gap-4 border-r border-gray-200 bg-white px-3 py-5 dark:border-dark-border dark:bg-[#080c13]">
      <div className="px-3">
        <div className="font-mono text-[10px] font-extrabold uppercase tracking-[0.16em] text-gray-400 dark:text-zinc-500">
          {group.label}
        </div>
        <p className="mt-2 text-[11px] leading-4 text-gray-500 dark:text-zinc-500">
          {group.description}
        </p>
      </div>
      <div className="flex flex-col gap-1">
        {items.map((item) => {
          const isActive =
            location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => navigate(item.path)}
              className={`group relative flex items-center gap-3 rounded-[11px] px-3.5 py-2.5 text-left font-mono text-[13px] font-bold transition-colors ${
                isActive
                  ? "bg-gray-100 text-gray-900 dark:bg-white/[0.07] dark:text-white"
                  : "text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-zinc-400 dark:hover:bg-white/[0.05] dark:hover:text-zinc-100"
              }`}
            >
              {isActive && (
                <span className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary shadow-[0_0_10px_rgba(79,143,224,0.5)]" />
              )}
              <FontAwesomeIcon
                icon={item.icon}
                className={`w-4 text-[12px] transition-transform group-hover:scale-110 ${isActive ? "text-primary" : "text-gray-400 dark:text-zinc-500 group-hover:text-primary"}`}
              />
              {item.label}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
