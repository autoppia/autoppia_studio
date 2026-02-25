import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircleNotch,
  faChevronDown,
  faChevronUp,
  faCheck,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import {
  faCircleCheck,
  faCircleXmark,
} from "@fortawesome/free-regular-svg-icons";

interface OperatorResponseProps {
  role: string;
  content?: string;
  socketId?: string;
  actions?: string[];
  actionResults?: boolean[];
  thinking?: string;
  state?: string;
}

function OperatorResponse(props: OperatorResponseProps) {
  const { content, actions, actionResults, thinking, state } = props;
  const [collapse, setCollapse] = useState(false);

  const handleCollapse = () => {
    setCollapse(!collapse);
  };

  return (
    <div className="mb-4 animate-fade-in">
      <div className="w-[92%] flex flex-col items-start rounded-2xl bg-gray-50 dark:bg-dark-surface border border-gray-100 dark:border-dark-border px-4 transition-all duration-300">
        {thinking && (
          <div className="flex justify-between items-center w-full py-3">
            {state === "thinking" && (
              <div className="animate-pulse-soft text-gray-600 flex items-center dark:text-gray-300 w-full overflow-hidden">
                <FontAwesomeIcon
                  icon={faCircleNotch}
                  className="animate-spin me-3 text-primary text-lg"
                />
                <span className="truncate w-full text-sm">{thinking}</span>
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
                <span className="text-sm font-medium">Operator disconnected.</span>
              </div>
            )}
            <button
              onClick={handleCollapse}
              className="flex items-center justify-center w-7 h-7 rounded-lg hover:bg-gray-200 dark:hover:bg-dark-border transition-colors duration-200 flex-shrink-0 ml-2"
            >
              <FontAwesomeIcon
                icon={!collapse ? faChevronDown : faChevronUp}
                className="text-gray-400 text-xs"
              />
            </button>
          </div>
        )}

        <div
          className={`flex flex-col w-full items-end px-1 pb-3 ${
            collapse ? "block" : "hidden"
          }`}
        >
          {actions &&
            actions.map((action, index) => (
              <div
                key={action + index}
                className="w-full text-gray-600 dark:text-gray-300 rounded-lg p-2 text-sm transition-all duration-200 flex items-start gap-2"
              >
                <span className="flex-shrink-0 mt-0.5">
                  {actionResults && actionResults[index] === true && (
                    <FontAwesomeIcon
                      icon={faCheck}
                      className="text-emerald-500 text-xs"
                    />
                  )}
                  {actionResults && actionResults[index] === false && (
                    <FontAwesomeIcon
                      icon={faXmark}
                      className="text-red-500 text-xs"
                    />
                  )}
                  {(actionResults === undefined ||
                    (actionResults && actionResults[index] === undefined)) && (
                    <FontAwesomeIcon
                      icon={faCircleNotch}
                      className="animate-spin text-primary text-xs"
                    />
                  )}
                </span>
                <span className="break-words leading-relaxed">{action}</span>
              </div>
            ))}
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

export default OperatorResponse;
