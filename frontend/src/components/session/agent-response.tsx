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
  "Initialize": faGlobe,
  "Continue": faCompass,
};

function getActionIcon(actionName: string): IconDefinition {
  return ACTION_ICONS[actionName] || faCircleNotch;
}

function formatToolName(toolName: string): string {
  if (toolName === "skill.use") return "Using Skill";
  const name = toolName.replace("browser.", "").replace("user.", "");
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

type ActionGroup =
  | { kind: "action"; index: number }
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
  if (last.startsWith("browser.") || last.startsWith("user.")) {
    return formatToolName(last);
  }
  return last;
}

interface AgentResponseProps {
  role: string;
  content?: string;
  actions?: string[];
  actionMetadata?: ({ skill?: Record<string, any> } | undefined)[];
  actionResults?: (boolean | undefined)[];
  thinking?: string;
  reasoning?: string;
  state?: string;
}

function AgentResponse(props: AgentResponseProps) {
  const { content, actions, actionMetadata, actionResults, thinking, reasoning, state } = props;
  const [collapsed, setCollapsed] = useState(false);
  const [expandedSkills, setExpandedSkills] = useState<Record<number, boolean>>({});

  const hasActions = actions && actions.length > 0;
  const showExpanded = hasActions && !collapsed;

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
    const isSuccess = result === true;
    const isFailed = result === false;

    const iconColor = isSuccess
      ? "text-emerald-500"
      : isFailed
        ? "text-red-500"
        : "text-primary animate-pulse";

    return (
      <div
        key={action + index}
        className="w-full rounded-lg p-2 text-sm transition-all duration-200 text-gray-600 dark:text-gray-300"
      >
        <div className="flex items-center gap-2">
          <span className="flex-shrink-0 w-4 text-center">
            <FontAwesomeIcon icon={icon} className={`text-xs ${iconColor}`} />
          </span>
          <span className="font-medium text-xs text-gray-500 dark:text-gray-400">
            {action.startsWith("browser.") || action.startsWith("user.")
              ? formatToolName(action)
              : action}
          </span>
        </div>
      </div>
    );
  };

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
            {state === "success" && (
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

        <div
          className={`flex flex-col w-full px-1 pb-3 ${
            showExpanded ? "block" : "hidden"
          }`}
        >
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

          {/* Separator */}
          {reasoning && hasActions && (
            <div className="border-t border-gray-200 dark:border-dark-border mb-1" />
          )}

          {/* Action list — actions following a "skill.use" belong to that skill
              and are nested under it, hidden until the skill row is expanded. */}
          {actions &&
            buildActionGroups(actions).map((group) => {
              // Plain (non-skill) action row
              if (group.kind === "action") {
                return renderActionRow(group.index);
              }

              // Skill group: collapsible header + nested inner actions
              const skill = actionMetadata?.[group.index]?.skill;
              const expanded = !!expandedSkills[group.index];
              const childCount = group.children.length;

              return (
                <div key={"skill" + group.index} className="w-full">
                  <button
                    type="button"
                    onClick={() =>
                      childCount > 0 &&
                      setExpandedSkills((prev) => ({
                        ...prev,
                        [group.index]: !prev[group.index],
                      }))
                    }
                    className={`w-full rounded-lg p-2 text-sm transition-all duration-200 bg-primary/5 dark:bg-primary/10 ${
                      childCount > 0 ? "hover:bg-primary/10 dark:hover:bg-primary/15" : "cursor-default"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="flex-shrink-0 w-4 text-center">
                        <FontAwesomeIcon icon={faWandMagicSparkles} className="text-xs text-primary" />
                      </span>
                      <span className="font-medium text-xs text-primary">
                        {`Using skill: ${skill?.name || "Approved skill"}`}
                      </span>
                      {skill?.status && (
                        <span className="text-[10px] font-medium uppercase tracking-wide text-primary/70">
                          {String(skill.status)}
                        </span>
                      )}
                      {childCount > 0 && (
                        <span className="ml-auto flex items-center gap-1.5 text-[10px] text-primary/70">
                          <span>{childCount} {childCount === 1 ? "step" : "steps"}</span>
                          <FontAwesomeIcon
                            icon={expanded ? faChevronUp : faChevronDown}
                            className="text-[10px]"
                          />
                        </span>
                      )}
                    </div>
                  </button>
                  {expanded && childCount > 0 && (
                    <div className="ml-3 mt-0.5 border-l border-primary/20 pl-2">
                      {group.children.map((childIndex) => renderActionRow(childIndex))}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </div>

      {content && (
        <div className="w-full text-gray-700 dark:text-gray-200 mt-2 text-sm leading-relaxed break-words px-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default AgentResponse;
