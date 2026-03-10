import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlus, faGlobe, faXmark, faExpand, faCompress } from "@fortawesome/free-solid-svg-icons";
import type { BrowserTab } from "../../redux/socketSlice";

interface BrowserTabsProps {
  tabs: BrowserTab[];
  activeIndex: number;
  onSelectTab: (index: number) => void;
  onNewTab?: () => void;
  onCloseTab?: (index: number) => void;
  isFullscreen?: boolean;
  onFullscreen?: () => void;
  compact?: boolean;
}

function extractDomain(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname;
  } catch {
    return url;
  }
}

export default function BrowserTabs({
  tabs,
  activeIndex,
  onSelectTab,
  onNewTab,
  onCloseTab,
  isFullscreen,
  onFullscreen,
  compact,
}: BrowserTabsProps) {
  if (tabs.length === 0 && !onFullscreen) return null;

  return (
    <div className={`flex items-center px-2 ${compact ? "pt-0.5" : "pt-1"} pb-0 bg-gray-100 dark:bg-dark-surface border-b border-gray-200 dark:border-dark-border rounded-t-xl`}>
      {/* Tabs area — aligned to bottom */}
      <div className={`flex items-end gap-0.5 flex-1 min-w-0 overflow-x-auto scrollbar-thin ${compact ? "pt-0.5" : "pt-2"}`}>
        {tabs.map((tab, index) => {
          const isActive = index === activeIndex;
          const title = tab.title || extractDomain(tab.url) || `Tab ${index + 1}`;

          return (
            <div
              key={tab.id}
              className={`group flex items-center gap-1.5 px-3 py-1.5 mb-0.5 rounded-lg text-xs font-medium transition-all duration-200 max-w-[200px] flex-shrink-0 cursor-pointer
                ${
                  isActive
                    ? "bg-white dark:bg-dark-bg text-gray-800 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-dark-border"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-dark-border/50"
                }`}
              onClick={() => onSelectTab(index)}
            >
              {tab.favicon_url ? (
                <img
                  src={tab.favicon_url}
                  alt=""
                  className="w-3.5 h-3.5 rounded-sm flex-shrink-0"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <FontAwesomeIcon
                  icon={faGlobe}
                  className="text-[10px] flex-shrink-0 opacity-60"
                />
              )}
              <span className="truncate">{title}</span>
              {onCloseTab && tabs.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onCloseTab(index);
                  }}
                  className="flex items-center justify-center w-4 h-4 rounded flex-shrink-0 ml-auto
                    opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500
                    hover:bg-red-50 dark:hover:bg-red-500/10 transition-all duration-150"
                  title="Close tab"
                >
                  <FontAwesomeIcon icon={faXmark} className="text-[9px]" />
                </button>
              )}
            </div>
          );
        })}
        {onNewTab && (
          <button
            onClick={onNewTab}
            className="flex items-center justify-center w-7 h-7 mb-0.5 rounded-lg text-gray-400 dark:text-gray-500
              hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-dark-border/50
              transition-all duration-200 flex-shrink-0 ml-1"
            title="New tab"
          >
            <FontAwesomeIcon icon={faPlus} className="text-xs" />
          </button>
        )}
      </div>
      {/* Fullscreen button — vertically centered in the full bar */}
      {onFullscreen && (
        <button
          onClick={onFullscreen}
          className="flex items-center justify-center w-7 h-7 rounded-lg text-gray-400 dark:text-gray-500
            hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-200/50 dark:hover:bg-dark-border/50
            transition-all duration-200 flex-shrink-0 ml-2 mr-1"
          title="Fullscreen"
        >
          <FontAwesomeIcon icon={isFullscreen ? faCompress : faExpand} className="text-xs" />
        </button>
      )}
    </div>
  );
}
