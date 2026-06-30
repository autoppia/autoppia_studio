import React, { useEffect, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";

export interface TabDef {
  id: string;
  label: string;
  icon?: IconDefinition;
  /** Optional small count badge rendered next to the label. */
  count?: number;
}

interface TabsProps {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  /** Optional content rendered on the right side of the tab bar (actions). */
  actions?: React.ReactNode;
  className?: string;
}

/**
 * Cockpit-styled in-section tab bar. Keeps sections shallow: one menu of
 * sub-views instead of an endless vertical scroll of stacked panels.
 */
export default function Tabs({ tabs, active, onChange, actions, className }: TabsProps): React.ReactElement {
  return (
    <div className={`flex items-center justify-between gap-3 ${className || ""}`}>
      <div className="ck-tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            onClick={() => onChange(tab.id)}
            className={`ck-tab ${tab.id === active ? "is-active" : ""}`}
          >
            {tab.icon ? <FontAwesomeIcon icon={tab.icon} className="ck-tab-icon" /> : null}
            <span>{tab.label}</span>
            {typeof tab.count === "number" ? <span className="ck-tab-count">{tab.count}</span> : null}
          </button>
        ))}
      </div>
      {actions ? <div className="flex flex-shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/**
 * Tab state synced to the URL `?tab=` query param so views are linkable and
 * survive reloads. Falls back to the first tab id when the param is absent.
 */
export function useTabState(tabIds: string[], param = "tab"): [string, (id: string) => void] {
  const read = () => {
    if (typeof window === "undefined") return tabIds[0];
    const value = new URLSearchParams(window.location.search).get(param);
    return value && tabIds.includes(value) ? value : tabIds[0];
  };
  const [active, setActive] = useState<string>(read);

  useEffect(() => {
    const handler = () => setActive(read());
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const change = (id: string) => {
    setActive(id);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set(param, id);
      window.history.replaceState(null, "", url.toString());
    }
  };

  return [active, change];
}
