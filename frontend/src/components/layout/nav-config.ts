import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import {
  faDiagramProject,
  faRobot,
  faWandMagicSparkles,
  faClipboardCheck,
  faClockRotateLeft,
  faListCheck,
  faBriefcase,
  faCircleCheck,
  faPlug,
  faBook,
  faCubes,
  faBolt,
  faGear,
  faKey,
  faShapes,
  faBuilding,
} from "@fortawesome/free-solid-svg-icons";

export interface NavItem {
  label: string;
  path: string;
  icon: IconDefinition;
}

export interface NavGroup {
  key: string;
  label: string;
  description: string;
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
  { key: "canvas", label: "Canvas", description: "Visual operating surface for live sessions and control flows.", icon: faDiagramProject, path: "/canvas", items: [] },
  {
    key: "factory",
    label: "Capability Factory",
    description: "Connectors, resources, entities, tasks, benchmarks, trajectories and skills become reusable business capabilities here.",
    icon: faWandMagicSparkles,
    items: [
      { label: "Agents", path: "/agents", icon: faRobot },
      { label: "Connectors", path: "/connectors", icon: faPlug },
      { label: "Resources", path: "/knowledge", icon: faBook },
      { label: "Capabilities", path: "/capabilities", icon: faWandMagicSparkles },
      { label: "Entities", path: "/entities", icon: faCubes },
      { label: "Benchmarks", path: "/evals", icon: faClipboardCheck },
      { label: "Runs", path: "/eval-runs", icon: faClockRotateLeft },
    ],
  },
  {
    key: "runtime",
    label: "Runtime Lab",
    description: "Governed sessions, traces, skill routing, approvals, artifacts, cost and replay from live execution.",
    icon: faBolt,
    items: [
      { label: "Sessions", path: "/runtime", icon: faClockRotateLeft },
      { label: "Approvals", path: "/approvals", icon: faCircleCheck },
      { label: "Artifacts", path: "/artifacts", icon: faShapes },
    ],
  },
  {
    key: "operations",
    label: "Work Orchestration",
    description: "Queues, schedules, recurring jobs and operational follow-through.",
    icon: faListCheck,
    items: [
      { label: "Work Orchestration", path: "/work", icon: faBriefcase },
    ],
  },
  {
    key: "setup",
    label: "Company Setup",
    description: "Company contract, credentials, embed controls and governance.",
    icon: faGear,
    items: [
      { label: "Company Setup", path: "/setup/company", icon: faBuilding },
      { label: "Credentials", path: "/credentials", icon: faKey },
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
