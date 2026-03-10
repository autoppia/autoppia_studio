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
  "Initialize": faGlobe,
  "Continue": faCompass,
};

function getActionIcon(actionName: string): IconDefinition {
  return ACTION_ICONS[actionName] || faCircleNotch;
}

function formatToolName(toolName: string): string {
  const name = toolName.replace("browser.", "").replace("user.", "");
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

interface AgentResponseProps {
  role: string;
  content?: string;
  actions?: string[];
  actionResults?: (boolean | undefined)[];
  thinking?: string;
  reasoning?: string;
  state?: string;
}

function AgentResponse(props: AgentResponseProps) {
  const { content, actions, actionResults, thinking, reasoning, state } = props;
  const [collapsed, setCollapsed] = useState(false);

  const hasActions = actions && actions.length > 0;
  const showActions = hasActions && !collapsed;

  return (
    <div className="mb-4 animate-fade-in">
      <div className="w-[92%] flex flex-col items-start rounded-2xl bg-gray-50 dark:bg-dark-surface border border-gray-100 dark:border-dark-border px-4 transition-all duration-300">
        {thinking && (
          <div className="flex justify-between items-center w-full py-3">
            {state === "thinking" && (
              <div className="animate-pulse-soft text-gray-600 flex items-center dark:text-gray-300 w-full overflow-hidden">
                <FontAwesomeIcon
                  icon={faCircleNotch}
                  className="me-3 text-primary text-lg flex-shrink-0 animate-spin"
                />
                <span className="w-full text-sm break-words">
                  {reasoning || thinking}
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
          className={`flex flex-col w-full items-end px-1 pb-3 ${
            showActions ? "block" : "hidden"
          }`}
        >
          {actions &&
            actions.map((action, index) => {
              const icon = getActionIcon(action);
              const result = actionResults?.[index];
              const isPending = result === undefined;
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
                  className="w-full text-gray-600 dark:text-gray-300 rounded-lg p-2 text-sm transition-all duration-200"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex-shrink-0 w-4 text-center">
                      <FontAwesomeIcon
                        icon={icon}
                        className={`text-xs ${iconColor}`}
                      />
                    </span>
                    <span className="font-medium text-xs text-gray-500 dark:text-gray-400">
                      {action.startsWith("browser.") || action.startsWith("user.")
                        ? formatToolName(action)
                        : action}
                    </span>
                  </div>
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
