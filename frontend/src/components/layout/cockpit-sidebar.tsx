import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faAnglesLeft, faAnglesRight } from "@fortawesome/free-solid-svg-icons";
import { groupLandingPath, resolveActiveGroup, visibleNavGroups, type NavItem } from "./nav-config";
import { useStudioMode } from "../../utils/studio-mode";

const COLLAPSE_KEY = "automata_sidebar_collapsed";

function isActivePath(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

/**
 * Single left navigation rail (cockpit style, ported from the AHF UI). Replaces
 * the old top center-nav + per-section sub-rail with one calm, grouped sidebar.
 * Collapsible to an icon-only rail; the choice is persisted in localStorage.
 */
export default function CockpitSidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const mode = useStudioMode();
  const groups = visibleNavGroups(mode);
  const routeGroup = resolveActiveGroup(location.pathname);
  const activeGroup = groups.find((group) => group.key === routeGroup?.key) || groups[0] || null;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore storage errors */
    }
  }, [collapsed]);

  const activeItems = activeGroup
    ? activeGroup.items.length > 0
      ? activeGroup.items
      : [{ label: activeGroup.label, path: groupLandingPath(activeGroup), icon: activeGroup.icon }]
    : [];

  const renderItem = (key: string, label: string, path: string, icon: NavItem["icon"], active: boolean) => (
    <button key={key} type="button" onClick={() => navigate(path)} className={`ck-nav-item${active ? " is-active" : ""}`} title={label}>
      <FontAwesomeIcon icon={icon} className="ck-nav-icon" />
      <span>{label}</span>
    </button>
  );

  return (
    <aside className={`ck-sidebar${collapsed ? " ck-sidebar--collapsed" : ""}`}>
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="ck-side-collapse"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <FontAwesomeIcon icon={collapsed ? faAnglesRight : faAnglesLeft} />
      </button>

      <nav className="ck-nav">
        {activeGroup && (
          <div className="ck-nav-group">
            <span className="ck-nav-label">{activeGroup.label}</span>
            {activeItems.map((item) => renderItem(item.path, item.label, item.path, item.icon, isActivePath(location.pathname, item.path)))}
          </div>
        )}
      </nav>
    </aside>
  );
}
