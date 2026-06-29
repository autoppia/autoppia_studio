import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { groupLandingPath, visibleNavGroups, type NavGroup, type NavItem } from "./nav-config";
import { useStudioMode } from "../../utils/studio-mode";

function isActivePath(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

/**
 * Single left navigation rail (cockpit style, ported from the AHF UI). Replaces
 * the old top center-nav + per-section sub-rail with one calm, grouped sidebar.
 */
export default function CockpitSidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const mode = useStudioMode();
  const groups = visibleNavGroups(mode);

  // Path-only groups (Canvas, Onboarding) become direct "Workspace" entries;
  // groups with items render as labelled sections.
  const workspace = groups.filter((g) => g.path && g.items.length === 0);
  const sections = groups.filter((g) => g.items.length > 0);

  const renderItem = (key: string, label: string, path: string, icon: NavItem["icon"], active: boolean) => (
    <button key={key} type="button" onClick={() => navigate(path)} className={`ck-nav-item${active ? " is-active" : ""}`} title={label}>
      <FontAwesomeIcon icon={icon} className="ck-nav-icon" />
      <span>{label}</span>
    </button>
  );

  return (
    <aside className="ck-sidebar">
      <button type="button" onClick={() => navigate("/")} className="ck-brand" title="Autoppia Studio">
        <img src="/assets/images/logos/main.webp" alt="Autoppia" />
        <span className="ck-brand-word">
          <span className="ck-brand-main">Autoppia</span>
          <span className="ck-brand-sub">Studio</span>
        </span>
      </button>

      <nav className="ck-nav">
        {workspace.length > 0 && (
          <div className="ck-nav-group">
            <span className="ck-nav-label">Workspace</span>
            {workspace.map((g: NavGroup) =>
              renderItem(g.key, g.label, groupLandingPath(g), g.icon, isActivePath(location.pathname, g.path || groupLandingPath(g))),
            )}
          </div>
        )}
        {sections.map((g: NavGroup) => (
          <div key={g.key} className="ck-nav-group">
            <span className="ck-nav-label">{g.label}</span>
            {g.items.map((item) => renderItem(item.path, item.label, item.path, item.icon, isActivePath(location.pathname, item.path)))}
          </div>
        ))}
      </nav>

      <div className="ck-side-foot">
        <span className="ck-eyebrow" style={{ letterSpacing: "0.14em" }}>
          {mode === "dev" ? "Dev mode" : "Guided mode"}
        </span>
        <span className="ck-mono" style={{ fontSize: 11, color: "var(--muted)" }}>
          Autoppia Studio
        </span>
      </div>
    </aside>
  );
}
