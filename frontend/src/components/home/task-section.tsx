import React, { useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPaperPlane,
  faAngleDown,
  faGlobe,
} from "@fortawesome/free-solid-svg-icons";

import { websites } from "../../utils/mock/mockDB";
import useStartSession from "../../hooks/useStartSession";

interface TaskSectionProps {
  prompt: string;
  setPrompt: React.Dispatch<React.SetStateAction<string>>;
  initialUrl: string;
  setInitialUrl: React.Dispatch<React.SetStateAction<string>>;
  openedDropdown: string | null;
  setOpenedDropdown: React.Dispatch<React.SetStateAction<string | null>>;
}

export default function TaskSection(props: TaskSectionProps) {
  const {
    prompt,
    setPrompt,
    initialUrl,
    setInitialUrl,
    openedDropdown,
    setOpenedDropdown,
  } = props;

  const [filteredWebsites, setFilteredWebsites] = useState(websites);
  const [provider, setProvider] = useState("autoppia");
  const [submitting, setSubmitting] = useState(false);

  const startSession = useStartSession();

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      handleSubmit();
      setPrompt("");
    }
  };

  const handleUrlChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setInitialUrl(value);

    if (value) {
      const filtered = websites.filter((website) =>
        website.url.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredWebsites(filtered);
      setOpenedDropdown("initialUrl");
    } else {
      setFilteredWebsites([]);
      setOpenedDropdown(null);
    }
  };

  const handleSubmit = async () => {
    if (!prompt || submitting) return;
    setSubmitting(true);
    try {
      await startSession(prompt, initialUrl, provider);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full xl:w-[900px] animate-slide-up" style={{ animationDelay: "0.1s" }}>
      {/* Dropdowns row */}
      <div className="flex justify-end mb-3 gap-2">
        <div className="relative text-sm font-medium">
          <button
            type="button"
            className="flex items-center gap-2 rounded-full px-4 py-1.5 text-white bg-gradient-primary
              shadow-soft hover:shadow-glow transition-all duration-300"
            onClick={() => setOpenedDropdown("provider")}
          >
            <span>{provider === "autoppia" ? "Autoppia Operator" : "Browser Use"}</span>
            <FontAwesomeIcon icon={faAngleDown} className="text-xs opacity-80" />
          </button>
          <div
            style={{
              display: openedDropdown === "provider" ? "block" : "none",
              width: 190,
            }}
            className="absolute left-0 z-20 mt-2 rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-100 dark:border-dark-border overflow-hidden"
          >
            <div className="p-1">
              <button
                className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                onClick={() => {
                  setProvider("autoppia");
                  setOpenedDropdown(null);
                }}
              >
                Autoppia Operator
              </button>
              <button
                className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                onClick={() => {
                  setProvider("browser_use");
                  setOpenedDropdown(null);
                }}
              >
                Browser Use
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main input card */}
      <div className="flex flex-col p-4 bg-white dark:bg-dark-surface rounded-2xl w-full shadow-soft
        border border-gray-200 dark:border-dark-border
        focus-within:shadow-soft-lg focus-within:border-gray-300 dark:focus-within:border-gray-600
        transition-all duration-300">
        {/* Prompt input */}
        <input
          className="border-none outline-none flex-grow text-gray-900 dark:text-white dark:bg-transparent p-2 text-base placeholder:text-gray-400"
          placeholder="Ask me anything..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        {/* Bottom toolbar */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 dark:border-dark-border">
          {/* URL input */}
          <div className="relative flex-grow mr-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-300">
              <FontAwesomeIcon icon={faGlobe} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder="Website URL..."
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={initialUrl}
                onChange={handleUrlChange}
              />
              <FontAwesomeIcon
                icon={faAngleDown}
                className="text-gray-400 text-xs"
              />
            </div>
            <div
              style={{
                display: openedDropdown === "initialUrl" ? "block" : "none",
              }}
              className="absolute z-20 mt-2 w-full rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-100 dark:border-dark-border overflow-hidden"
            >
              <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                {filteredWebsites.map((website) => (
                  <div
                    key={website.url}
                    className="cursor-pointer p-2.5 rounded-lg flex items-center hover:bg-gradient-primary hover:text-white
                      text-gray-700 dark:text-gray-200 transition-colors duration-200"
                    onClick={() => {
                      setInitialUrl(website.url);
                      setFilteredWebsites([]);
                      setOpenedDropdown(null);
                    }}
                  >
                    <img
                     alt=""
                     src={website.favicon}
                     className="w-5 h-5 rounded me-2.5"
                    />
                    <span className="text-sm font-medium">{website.title}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Submit button */}
          <button
            onClick={handleSubmit}
            disabled={!prompt || submitting}
            className={`flex items-center justify-center w-10 h-10 rounded-xl
              transition-all duration-300
              ${prompt && !submitting
                ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-105 cursor-pointer"
                : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
              }`}
          >
            <FontAwesomeIcon icon={faPaperPlane} className={`text-sm ${submitting ? "animate-pulse" : ""}`} />
          </button>
        </div>
      </div>
    </div>
  );
}
