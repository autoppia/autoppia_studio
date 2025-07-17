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
    <div className="mb-3">
      <div className="w-[90%] flex flex-col items-start border rounded-[20px] bg-white dark:bg-transparent px-4">
        {thinking && (
          <div className="flex justify-between items-center w-full py-2">
            {state === "thinking" && (
              <div className="animate-pulse text-gray-600 flex items-center dark:text-gray-100 w-full overflow-hidden">
                <FontAwesomeIcon
                  icon={faCircleNotch}
                  className="animate-spin me-2 text-xl"
                />
                <span className="truncate w-full">{thinking}</span>
              </div>
            )}
            {state === "success" && (
              <div className="text-gray-600 flex items-center dark:text-gray-100">
                <FontAwesomeIcon
                  icon={faCircleCheck}
                  color="green"
                  className="me-2 text-xl"
                />
                <span>{"Task completed successfully."}</span>
              </div>
            )}
            {state === "error" && (
              <div className="text-gray-600 flex items-center dark:text-gray-100">
                <FontAwesomeIcon
                  icon={faCircleXmark}
                  color="red"
                  className="me-2 text-xl"
                />
                <span>{"Task failed."}</span>
              </div>
            )}
            {state === "disconnected" && (
              <div className="text-gray-600 flex items-center dark:text-gray-100">
                <FontAwesomeIcon
                  icon={faCircleXmark}
                  color="red"
                  className="me-2 text-xl"
                />
                <span>{"Operator disconnected."}</span>
              </div>
            )}
            <FontAwesomeIcon
              icon={!collapse ? faChevronDown : faChevronUp}
              color="gray"
              onClick={handleCollapse}
              className="cursor-pointer"
            />
          </div>
        )}

        <div
          className={`flex flex-col w-full items-end px-2 pb-4 ${
            collapse ? "block" : "hidden"
          }`}
        >
          {actions &&
            actions.map((action, index) => (
              <div
                key={action + index}
                className="w-full text-gray-700 rounded-md shadow-sm p-1 text-sm cursor-pointer transition-all duration-200 dark:text-gray-100"
              >
                {actionResults && actionResults[index] === true && (
                  <FontAwesomeIcon
                    icon={faCheck}
                    color="green"
                    className="me-2"
                  />
                )}
                {actionResults && actionResults[index] === false && (
                  <FontAwesomeIcon
                    icon={faXmark}
                    color="red"
                    className="me-2"
                  />
                )}
                {(actionResults === undefined ||
                  (actionResults && actionResults[index] === undefined)) && (
                  <FontAwesomeIcon
                    icon={faCircleNotch}
                    className="animate-spin me-2"
                  />
                )}
                <span className="w-full break-words">{action}</span>
              </div>
            ))}
        </div>
      </div>

      {content && (
        <div className="w-full text-gray-700 mt-2 dark:text-white break-words">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default OperatorResponse;
