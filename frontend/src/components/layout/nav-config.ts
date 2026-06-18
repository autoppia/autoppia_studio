import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import {
  faDiagramProject,
  faRobot,
  faWandMagicSparkles,
  faClipboardCheck,
  faListCheck,
  faBriefcase,
  faCircleCheck,
  faPlug,
  faBook,
  faCubes,
} from "@fortawesome/free-solid-svg-icons";

export interface NavItem {
  label: string;
  path: string;
  icon: IconDefinition;
}

export interface NavGroup {
  key: string;
  label: string;
  icon: IconDefinition;
  /** Direct landing path for groups with no sub-rail (e.g. Canvas, Settings). */
  path?: string;
  /** Sub-pages rendered as a vertical rail when the group is active. */
  items: NavItem[];
  /** Render this entry as a white call-to-action in the top bar. */
  cta?: boolean;
}

/**
 * Primary navigation, grouped by lifecycle. Each group is a horizontal top-bar
 * entry; groups with `items` reveal a vertical sub-rail inside the section.
 * Canvas is the home/center — it opens full-window with no rail.
 */
export const NAV_GROUPS: NavGroup[] = [
  { key: "canvas", label: "Canvas", icon: faDiagramProject, path: "/canvas", items: [] },
  {
    key: "studio",
    label: "Studio",
    icon: faPlug,
    items: [
      { label: "Connectors", path: "/connectors", icon: faPlug },
      { label: "Knowledge", path: "/knowledge", icon: faBook },
      { label: "Capabilities", path: "/capabilities", icon: faWandMagicSparkles },
      { label: "Entities", path: "/entities", icon: faCubes },
    ],
  },
  {
    key: "other",
    label: "Other",
    icon: faRobot,
    items: [
      { label: "Agents", path: "/agents", icon: faRobot },
    ],
  },
  {
    key: "eval",
    label: "Eval",
    icon: faClipboardCheck,
    items: [
      { label: "Benchmarks", path: "/evals", icon: faClipboardCheck },
    ],
  },
  {
    key: "workspace",
    label: "Workspace",
    icon: faListCheck,
    items: [
      { label: "Work", path: "/work", icon: faBriefcase },
      { label: "Approvals", path: "/approvals", icon: faCircleCheck },
    ],
  },
];

/** Path the top-bar entry navigates to when its group is clicked. */
export function groupLandingPath(group: NavGroup): string {
  return group.path || group.items[0]?.path || "/canvas";
}

/** Resolve which group owns the current pathname (null if none, e.g. /session/:id). */
export function resolveActiveGroup(pathname: string): NavGroup | null {
  // Most specific match wins: check item paths and group paths by longest first.
  const candidates: Array<{ group: NavGroup; path: string }> = [];
  for (const group of NAV_GROUPS) {
    if (group.path) candidates.push({ group, path: group.path });
    for (const item of group.items) candidates.push({ group, path: item.path });
  }
  candidates.sort((a, b) => b.path.length - a.path.length);
  for (const { group, path } of candidates) {
    if (pathname === path || pathname.startsWith(`${path}/`)) return group;
  }
  return null;
}
