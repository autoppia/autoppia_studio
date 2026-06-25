import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircleNotch,
  faChevronDown,
  faChevronUp,
  faMousePointer,
  faKeyboard,
  faCompass,
  faArrowsUpDown,
  faMagnifyingGlass,
  faArrowLeft,
  faClock,
  faHandPointer,
  faList,
  faCode,
  faFlagCheckered,
  faGlobe,
  faBrain,
  faWandMagicSparkles,
  faEnvelope,
  faWrench,
} from "@fortawesome/free-solid-svg-icons";
import {
  faCircleCheck,
  faCircleXmark,
} from "@fortawesome/free-regular-svg-icons";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";

const ACTION_ICONS: Record<string, IconDefinition> = {
  "browser.click": faMousePointer,
  "browser.dblclick": faMousePointer,
  "browser.rightclick": faMousePointer,
  "browser.tripleclick": faMousePointer,
  "browser.middleclick": faMousePointer,
  "browser.hover": faHandPointer,
  "browser.input": faKeyboard,
  "browser.send_keys": faKeyboard,
  "browser.hold_key": faKeyboard,
  "browser.navigate": faCompass,
  "browser.go_back": faArrowLeft,
  "browser.scroll": faArrowsUpDown,
  "browser.search": faMagnifyingGlass,
  "browser.wait": faClock,
  "browser.select_dropdown": faList,
  "browser.dropdown_options": faList,
  "browser.evaluate": faCode,
  "browser.extract": faCode,
  "browser.screenshot": faGlobe,
  "browser.done": faFlagCheckered,
  "skill.use": faWandMagicSparkles,
  "runtime.think": faBrain,
  "router.matched_skill": faWandMagicSparkles,
  "router.no_match": faMagnifyingGlass,
  "router.fallback_runtime": faCompass,
  "imap.search_emails": faEnvelope,
  "imap.read_email": faEnvelope,
  "smtp.draft_email": faEnvelope,
  "smtp.send_email": faEnvelope,
  "api.human_approval": faWrench,
  "Initialize": faGlobe,
  "Continue": faCompass,
};

function getActionIcon(actionName: string): IconDefinition {
  return ACTION_ICONS[actionName] || faCircleNotch;
}

function formatToolName(toolName: string): string {
  if (toolName === "skill.use") return "Using Skill";
  if (toolName === "runtime.think") return "Thinking";
  if (toolName === "router.matched_skill") return "Router Matched Trajectory";
  if (toolName === "router.no_match") return "No Trajectory Match";
  if (toolName === "router.fallback_runtime") return "Runtime Fallback";
  if (toolName === "api.human_approval") return "Approval Required";
  const name = toolName.replace("browser.", "").replace("user.", "");
  return name
    .split(/[._]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

type ActionGroup =
  | { kind: "action"; index: number }
  | { kind: "router"; index: number }
  | { kind: "skill"; index: number; children: number[] };

/** Group the flat action list so that actions following a "skill.use" entry
 *  are nested as children of that skill (until the next skill.use). */
function buildActionGroups(actions: string[]): ActionGroup[] {
  const groups: ActionGroup[] = [];
  let currentSkill: { kind: "skill"; index: number; children: number[] } | null = null;
  actions.forEach((action, index) => {
    if (action === "skill.use") {
      currentSkill = { kind: "skill", index, children: [] };
      groups.push(currentSkill);
    } else if (action.startsWith("router.")) {
      groups.push({ kind: "router", index });
    } else if (currentSkill) {
      currentSkill.children.push(index);
    } else {
      groups.push({ kind: "action", index });
    }
  });
  return groups;
}

/** Get the latest action name, formatted for display. */
function getLatestActionLabel(actions: string[]): string {
  const last = actions[actions.length - 1];
  return formatToolName(last);
}

function compactValue(value: any): string {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string") return value.length > 140 ? `${value.slice(0, 140)}...` : value;
  try {
    const serialized = JSON.stringify(value);
    return serialized.length > 140 ? `${serialized.slice(0, 140)}...` : serialized;
  } catch {
    return String(value);
  }
}

interface AgentResponseProps {
  role: string;
  content?: string;
  actions?: string[];
  actionMetadata?: ({ skill?: Record<string, any>; router?: Record<string, any>; tool?: Record<string, any> } | undefined)[];
  actionResults?: (boolean | undefined)[];
  actionTimings?: ({ elapsedSeconds?: number; emittedAt?: string } | undefined)[];
  thinking?: string;
  reasoning?: string;
  state?: string;
}

function AgentResponse(props: AgentResponseProps) {
  const { content, actions, actionMetadata, actionResults, actionTimings, thinking, reasoning, state } = props;
  const [collapsed, setCollapsed] = useState(false);
  const [expandedSkills, setExpandedSkills] = useState<Record<number, boolean>>({});

  const hasActions = actions && actions.length > 0;
  const showExpanded = hasActions && !collapsed;
  const waitingForApproval = state === "success" && actions?.includes("api.human_approval");

  // Latest action icon & color for the collapsed header
  const latestAction = hasActions ? actions[actions.length - 1] : null;
  const latestIcon = latestAction ? getActionIcon(latestAction) : faCircleNotch;
  const latestResult = hasActions ? actionResults?.[actions.length - 1] : undefined;
  const latestIconColor = latestResult === true
    ? "text-emerald-500"
    : latestResult === false
      ? "text-red-500"
      : "text-primary animate-pulse";

  // Renders a single (non-skill) action row by its index in the flat list.
  const renderActionRow = (index: number) => {
    const action = actions![index];
    const icon = getActionIcon(action);
    const result = actionResults?.[index];
    const metadata = actionMetadata?.[index];
    const router = metadata?.router;
    const tool = metadata?.tool;
    const timing = actionTimings?.[index];
    const isSuccess = result === true;
    const isFailed = result === false;
    const routerConfidence = typeof router?.confidence === "number" ? `${Math.round(router.confidence * 100)}%` : "";
    const routerDetail = router
      ? [
          router.matchedSkillName
            ? `Matched: ${[router.matchedSkillName, router.matchedTaskName].filter(Boolean).join(" / ")}`
            : router.reason,
          routerConfidence ? `confidence ${routerConfidence}` : "",
          router.fallbackRuntime ? `fallback ${String(router.fallbackRuntime).replace(/_/g, " ")}` : "",
        ].filter(Boolean).join(" · ")
      : "";
    const toolDetail = tool
      ? compactValue(tool.error || tool.output || tool.arguments)
      : "";

    const iconColor = isSuccess
      ? "text-emerald-500"
      : isFailed
        ? "text-red-500"
        : "text-primary animate-pulse";

    return (
      <div
        key={action + index}
        className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm shadow-soft transition-all duration-200 dark:border-dark-border dark:bg-dark-surface"
      >
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gray-50 text-center dark:bg-white/5">
            <FontAwesomeIcon icon={icon} className={`text-xs ${iconColor}`} />
          </span>
          <span className="min-w-0 flex-1 truncate font-medium text-xs text-gray-700 dark:text-gray-200">
            {formatToolName(action)}
          </span>
          {typeof timing?.elapsedSeconds === "number" && (
            <span className="rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500 dark:bg-white/5 dark:text-gray-400">
              {timing.elapsedSeconds.toFixed(1)}s
            </span>
          )}
          <span className={`h-2 w-2 rounded-full ${isSuccess ? "bg-emerald-400" : isFailed ? "bg-red-400" : "bg-primary animate-pulse"}`} />
        </div>
        {routerDetail && (
          <div className="mt-1.5 pl-9 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
            {routerDetail}
          </div>
        )}
        {toolDetail && (
          <div className="mt-1.5 rounded-lg bg-gray-50 px-2.5 py-1.5 font-mono text-[10px] leading-relaxed text-gray-500 dark:bg-black/20 dark:text-gray-400">
            {toolDetail}
          </div>
        )}
      </div>
    );
  };

  const renderActionGroups = () =>
    actions &&
    buildActionGroups(actions).map((group) => {
      if (group.kind === "router") {
        const action = actions[group.index];
        const metadata = actionMetadata?.[group.index];
        const router = metadata?.router || {};
        const candidates = Array.isArray(router.candidates) ? router.candidates.slice(0, 3) : [];
        const matched = router.decision === "matched_skill";
        return (
          <div key={action + group.index} className={`w-full rounded-xl border px-3 py-3 text-sm shadow-soft ${
            matched
              ? "border-emerald-200 bg-emerald-50 dark:border-emerald-500/25 dark:bg-emerald-500/10"
              : "border-amber-200 bg-amber-50 dark:border-amber-500/25 dark:bg-amber-500/10"
          }`}>
            <div className="flex items-start gap-2">
              <span className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${matched ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300"}`}>
                <FontAwesomeIcon icon={getActionIcon(action)} className="text-xs" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className={`truncate text-xs font-semibold ${matched ? "text-emerald-700 dark:text-emerald-200" : "text-amber-700 dark:text-amber-200"}`}>
                    {matched ? "Router matched approved trajectory" : "Router skipped trajectory replay"}
                  </p>
                  {typeof router.confidence === "number" && (
                    <span className="rounded-md bg-white/70 px-1.5 py-0.5 text-[10px] font-semibold text-gray-500 dark:bg-black/20 dark:text-gray-300">
                      {Math.round(router.confidence * 100)}%
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-gray-600 dark:text-gray-300">
                  {matched
                    ? `${router.matchedSkillName || "Skill"}${router.matchedTaskName ? ` / ${router.matchedTaskName}` : ""}`
                    : router.reason || "No candidate passed the safe routing gate."}
                </p>
                {candidates.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {candidates.map((candidate: any, i: number) => (
                      <div key={`${candidate.skillId || candidate.name}-${i}`} className="flex items-center gap-2 text-[10px] text-gray-500 dark:text-gray-400">
                        <span className="w-4 flex-shrink-0 font-mono">{i + 1}.</span>
                        <span className="min-w-0 flex-1 truncate">{candidate.name || "Candidate"}{candidate.matchedRouteName ? ` / ${candidate.matchedRouteName}` : ""}</span>
                        <span className="flex-shrink-0 font-mono">{Math.round(Number(candidate.score || 0) * 100)}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      }
      if (group.kind === "action") {
        return renderActionRow(group.index);
      }

      const skill = actionMetadata?.[group.index]?.skill;
      const expanded = !!expandedSkills[group.index];
      const childCount = group.children.length;

      return (
        <div key={"skill" + group.index} className="w-full rounded-xl border border-primary/20 bg-primary/5 p-2 dark:bg-primary/10">
          <button
            type="button"
            onClick={() =>
              childCount > 0 &&
              setExpandedSkills((prev) => ({
                ...prev,
                [group.index]: !prev[group.index],
              }))
            }
            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-all duration-200 ${
              childCount > 0 ? "hover:bg-primary/10 dark:hover:bg-primary/15" : "cursor-default"
            }`}
          >
            <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs" />
            </span>
            <span className="min-w-0 flex-1 truncate text-left text-xs font-medium text-primary">
              {`Using skill: ${skill?.name || "Approved skill"}`}
            </span>
            {skill?.status && (
              <span className="text-[10px] font-medium uppercase tracking-wide text-primary/70">
                {String(skill.status)}
              </span>
            )}
            {childCount > 0 && (
              <span className="flex items-center gap-1.5 text-[10px] text-primary/70">
                <span>{childCount} {childCount === 1 ? "step" : "steps"}</span>
                <FontAwesomeIcon icon={expanded ? faChevronUp : faChevronDown} className="text-[10px]" />
              </span>
            )}
          </button>
          {expanded && childCount > 0 && (
            <div className="ml-5 mt-2 space-y-1.5 border-l border-primary/20 pl-3">
              {group.children.map((childIndex) => renderActionRow(childIndex))}
            </div>
          )}
        </div>
      );
    });

  return (
    <div className="mb-4 animate-fade-in">
      <div className="w-[92%] flex flex-col items-start rounded-2xl bg-gray-50 dark:bg-dark-surface border border-gray-100 dark:border-dark-border px-4 transition-all duration-300">
        {thinking && (
          <div className="flex justify-between items-center w-full py-3">
            {state === "thinking" && (
              <div className="animate-pulse-soft text-gray-600 flex items-center dark:text-gray-300 w-full overflow-hidden">
                <FontAwesomeIcon
                  icon={latestIcon}
                  className={`me-3 text-lg flex-shrink-0 ${latestIconColor}`}
                />
                <span className="truncate w-full text-sm">
                  {hasActions ? getLatestActionLabel(actions) : thinking}
                </span>
              </div>
            )}
            {state === "success" && waitingForApproval && (
              <div className="text-amber-700 flex items-center dark:text-amber-200">
                <FontAwesomeIcon
                  icon={faClock}
                  className="me-3 text-lg text-amber-500"
                />
                <span className="text-sm font-medium">Waiting for approval.</span>
              </div>
            )}
            {state === "success" && !waitingForApproval && (
              <div className="text-gray-700 flex items-center dark:text-gray-200">
                <FontAwesomeIcon
                  icon={faCircleCheck}
                  className="me-3 text-lg text-emerald-500"
                />
                <span className="text-sm font-medium">Task completed successfully.</span>
              </div>
            )}
            {state === "error" && (
              <div className="text-gray-700 flex items-center dark:text-gray-200">
                <FontAwesomeIcon
                  icon={faCircleXmark}
                  className="me-3 text-lg text-red-500"
                />
                <span className="text-sm font-medium">Task failed.</span>
              </div>
            )}
            {state === "disconnected" && (
              <div className="text-gray-700 flex items-center dark:text-gray-200">
                <FontAwesomeIcon
                  icon={faCircleXmark}
                  className="me-3 text-lg text-red-500"
                />
                <span className="text-sm font-medium">Agent disconnected.</span>
              </div>
            )}
            {hasActions && (
              <button
                onClick={() => setCollapsed(!collapsed)}
                className="flex items-center justify-center w-7 h-7 rounded-lg hover:bg-gray-200 dark:hover:bg-dark-border transition-colors duration-200 flex-shrink-0 ml-2"
              >
                <FontAwesomeIcon
                  icon={collapsed ? faChevronDown : faChevronUp}
                  className="text-gray-400 text-xs"
                />
              </button>
            )}
          </div>
        )}

        <div className="flex w-full flex-col px-1 pb-3">
          {/* Reasoning with brain icon */}
          {reasoning && (
            <div className="flex items-start gap-2 text-gray-500 dark:text-gray-400 mb-2">
              <FontAwesomeIcon
                icon={faBrain}
                className="text-xs mt-0.5 flex-shrink-0 text-purple-400"
              />
              <span className="text-xs leading-relaxed break-words">
                {reasoning}
              </span>
            </div>
          )}
        </div>
      </div>

      {showExpanded && hasActions && (
        <div className="mt-2 flex w-[92%] flex-col gap-2 px-1">
          {renderActionGroups()}
        </div>
      )}

      {content && (
        <div className="w-full text-gray-700 dark:text-gray-200 mt-2 text-sm leading-relaxed break-words px-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default AgentResponse;
