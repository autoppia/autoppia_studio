import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faClock } from "@fortawesome/free-solid-svg-icons";
import type { HistoryItem } from "../../utils/types";

/**
 * Chat / session history rail — the old sidebar history list, shown on the
 * chat surfaces (home + active session).
 */
export default function ChatHistoryRail({ histories }: { histories: HistoryItem[] }) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside className="flex h-full w-60 flex-shrink-0 flex-col border-r border-gray-200 bg-white dark:border-dark-border dark:bg-dark-bg">
      <div className="px-4 pb-1 pt-4">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-zinc-500">
          History
        </span>
      </div>

      <div className="scrollbar-thin flex-grow overflow-y-auto px-2 pb-2">
        {histories.length === 0 ? (
          <div className="px-3 py-4 text-xs text-gray-400 dark:text-zinc-500">No sessions yet</div>
        ) : (
          histories.map((item) => {
            const isActive = location.pathname === `/session/${item.sessionId}`;
            return (
              <button
                key={`history_${item.sessionId}`}
                onClick={() => item.sessionId && navigate(`/session/${item.sessionId}`)}
                className={`group mb-0.5 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors duration-200 ${
                  isActive
                    ? "bg-gray-100 text-gray-900 dark:bg-zinc-900/70 dark:text-white"
                    : "text-gray-600 hover:bg-gray-50 dark:text-zinc-400 dark:hover:bg-zinc-900/60"
                }`}
              >
                <FontAwesomeIcon icon={faClock} className="flex-shrink-0 text-[10px] opacity-50" />
                <div className="min-w-0 flex-grow">
                  <p className="truncate text-xs font-medium">{item.prompt || "Untitled session"}</p>
                  {item.initialUrl ? (
                    <p className="truncate text-[10px] opacity-60">{item.initialUrl}</p>
                  ) : null}
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}
