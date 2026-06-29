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
  faRocket,
} from "@fortawesome/free-solid-svg-icons";
import type { StudioMode } from "../../utils/studio-mode";

export interface NavItem {
  label: string;
  path: string;
  icon: IconDefinition;
  /** Hidden from non-technical (normal) users. */
  devOnly?: boolean;
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
  /** Hidden from non-technical (normal) users. */
  devOnly?: boolean;
}

/**
 * Primary navigation, grouped by lifecycle. Each group is a horizontal top-bar
 * entry; groups with `items` reveal a vertical sub-rail inside the section.
 * Canvas is the home/center — it opens full-window with no rail.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    key: "onboarding",
    label: "Onboarding",
    description: "Tell Automata about your company and it will discover systems, build and test tasks, and prepare agents.",
    icon: faRocket,
    path: "/onboarding",
    items: [],
  },
  { key: "canvas", label: "Canvas", description: "Visual operating surface for live sessions and control flows.", icon: faDiagramProject, path: "/canvas", items: [], devOnly: true },
  {
    key: "factory",
    label: "Capability Factory",
    description: "Connectors, resources, entities, tasks, benchmarks, trajectories and skills become reusable business capabilities here.",
    icon: faWandMagicSparkles,
    items: [
      // Agents stay accessible in normal mode; the rest are factory internals.
      { label: "Agents", path: "/agents", icon: faRobot },
      { label: "Connectors", path: "/connectors", icon: faPlug, devOnly: true },
      { label: "Resources", path: "/knowledge", icon: faBook, devOnly: true },
      { label: "Capabilities", path: "/capabilities", icon: faWandMagicSparkles, devOnly: true },
      { label: "Entities", path: "/entities", icon: faCubes, devOnly: true },
      { label: "Benchmarks", path: "/evals", icon: faClipboardCheck, devOnly: true },
      { label: "Runs", path: "/eval-runs", icon: faClockRotateLeft, devOnly: true },
    ],
  },
  {
    key: "runtime",
    label: "Runtime Lab",
    description: "Governed sessions, traces, skill routing, approvals, artifacts, cost and replay from live execution.",
    icon: faBolt,
    devOnly: true,
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
    devOnly: true,
    items: [
      { label: "Company Setup", path: "/setup/company", icon: faBuilding },
      { label: "Credentials", path: "/credentials", icon: faKey },
    ],
  },
];

/**
 * Groups (and items within them) visible for a given experience mode. Normal
 * users see only the guided surface; dev mode reveals factory internals.
 */
export function visibleNavGroups(mode: StudioMode): NavGroup[] {
  if (mode === "dev") return NAV_GROUPS;
  return NAV_GROUPS.filter((group) => !group.devOnly)
    .map((group) => ({ ...group, items: group.items.filter((item) => !item.devOnly) }))
    // Drop groups that have a sub-rail but no longer have any visible items.
    .filter((group) => Boolean(group.path) || group.items.length > 0);
}

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

/** Eyebrow + title for the top bar, derived from the active route. */
export function resolvePageMeta(pathname: string): { eyebrow: string; title: string } {
  const group = resolveActiveGroup(pathname);
  if (!group) return { eyebrow: "Autoppia Studio", title: "Workspace" };
  // Find the most specific owning item within the group.
  let item: NavItem | undefined;
  let best = -1;
  for (const candidate of group.items) {
    if ((pathname === candidate.path || pathname.startsWith(`${candidate.path}/`)) && candidate.path.length > best) {
      item = candidate;
      best = candidate.path.length;
    }
  }
  if (item) return { eyebrow: group.label, title: item.label };
  // Path-only group (Canvas, Onboarding): the group is the page.
  return { eyebrow: "Autoppia Studio", title: group.label };
}
