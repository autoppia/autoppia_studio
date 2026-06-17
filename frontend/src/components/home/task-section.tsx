import React, { useState, useEffect, useCallback } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPaperPlane,
  faAngleDown,
  faGlobe,
  faUserCircle,
  faRobot,
} from "@fortawesome/free-solid-svg-icons";

import { websites } from "../../utils/mock/mockDB";
import useStartSession from "../../hooks/useStartSession";
import { AgentConfig } from "../../utils/types";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

interface Profile {
  id: string;
  name: string;
  contextId: string;
}

interface TaskSectionProps {
  prompt: string;
  setPrompt: React.Dispatch<React.SetStateAction<string>>;
  initialUrl: string;
  setInitialUrl: React.Dispatch<React.SetStateAction<string>>;
  openedDropdown: string | null;
  setOpenedDropdown: React.Dispatch<React.SetStateAction<string | null>>;
  agents: AgentConfig[];
  selectedAgent: AgentConfig | null;
  setSelectedAgent: React.Dispatch<React.SetStateAction<AgentConfig | null>>;
}

export default function TaskSection(props: TaskSectionProps) {
  const {
    prompt,
    setPrompt,
    initialUrl,
    setInitialUrl,
    openedDropdown,
    setOpenedDropdown,
    agents,
    selectedAgent,
    setSelectedAgent,
  } = props;

  const [filteredWebsites, setFilteredWebsites] = useState(websites);
  const [submitting, setSubmitting] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);

  const user = useSelector((state: any) => state.user);
  const startSession = useStartSession();

  const loadProfiles = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/profiles?email=${user.email}`);
      const data = await res.json();
      setProfiles(data.profiles || []);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    }
  }, [user.email]);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  // Auto-select first profile if available
  useEffect(() => {
    if (profiles.length > 0 && !selectedProfile) {
      setSelectedProfile(profiles[0]);
    }
  }, [profiles]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
      setPrompt("");
    }
  };

  const handlePromptChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPrompt(event.target.value);
    // Auto-resize
    event.target.style.height = "auto";
    event.target.style.height = `${event.target.scrollHeight}px`;
  };

  const handleUrlChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setInitialUrl(value);

    if (value) {
      const filtered = websites.filter((website) =>
        website.url.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredWebsites(filtered);
    } else {
      setFilteredWebsites(websites);
    }
    setOpenedDropdown("initialUrl");
  };

  const handleUrlFocus = () => {
    if (!initialUrl) {
      setFilteredWebsites(websites);
    }
    setOpenedDropdown("initialUrl");
  };

  const toggleUrlDropdown = () => {
    if (openedDropdown === "initialUrl") {
      setOpenedDropdown(null);
    } else {
      setFilteredWebsites(initialUrl
        ? websites.filter((w) => w.url.toLowerCase().includes(initialUrl.toLowerCase()))
        : websites
      );
      setOpenedDropdown("initialUrl");
    }
  };

  const handleSubmit = async () => {
    if (!prompt || submitting) return;
    setSubmitting(true);
    try {
      await startSession(
        prompt,
        initialUrl,
        selectedProfile?.contextId || "",
        selectedAgent ? { agentId: selectedAgent.agentId, agentName: selectedAgent.name } : undefined,
        "/session",
        selectedAgent ? { agentId: selectedAgent.agentId, agentName: selectedAgent.name } : undefined,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full xl:w-[900px] animate-slide-up" style={{ animationDelay: "0.1s" }}>
      {/* Main input card */}
      <div className="flex flex-col p-4 bg-white dark:bg-dark-surface rounded-2xl w-full shadow-soft
        border border-gray-200 dark:border-dark-border
        focus-within:shadow-soft-lg focus-within:border-gray-300 dark:focus-within:border-gray-600
        transition-all duration-300">
        {/* Prompt input */}
        <textarea
          className="border-none outline-none w-full resize-none text-gray-900 dark:text-white dark:bg-transparent p-2 text-base placeholder:text-gray-400 scrollbar-thin"
          placeholder="Ask me anything..."
          rows={1}
          value={prompt}
          onChange={handlePromptChange}
          onKeyDown={handleKeyDown}
          style={{ minHeight: "2.5rem", maxHeight: "8rem", overflowY: "auto" }}
        />

        {/* Bottom toolbar */}
        <div className="flex items-center mt-3 pt-3 border-t border-gray-100 dark:border-dark-border gap-2">
          {/* URL input */}
          <div className="relative w-64">
            <div className="flex items-center gap-2 px-3 h-9 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border
              focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-300">
              <FontAwesomeIcon icon={faGlobe} className="text-gray-400 text-sm" />
              <input
                type="text"
                placeholder="Website URL..."
                className="w-full outline-none bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400"
                value={initialUrl}
                onChange={handleUrlChange}
                onFocus={handleUrlFocus}
              />
              <button
                type="button"
                onClick={toggleUrlDropdown}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                <FontAwesomeIcon
                  icon={faAngleDown}
                  className="text-xs"
                />
              </button>
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

          {/* Profile selector */}
          <div className="relative text-sm font-medium flex-shrink-0">
            <button
              type="button"
              className="flex items-center gap-2 rounded-xl px-3 h-9 transition-all duration-300
                border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600"
              onClick={() => setOpenedDropdown("profile")}
            >
              <FontAwesomeIcon icon={faUserCircle} className={`text-xs ${selectedProfile ? "text-primary" : "opacity-60"}`} />
              <span className="whitespace-nowrap">{selectedProfile ? selectedProfile.name : "No Profile"}</span>
              <FontAwesomeIcon icon={faAngleDown} className="text-xs opacity-60" />
            </button>
            <div
              style={{
                display: openedDropdown === "profile" ? "block" : "none",
                width: 200,
              }}
              className="absolute right-0 z-20 mt-2 rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-100 dark:border-dark-border overflow-hidden"
            >
              <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                {profiles.map((profile) => (
                  <button
                    key={profile.id}
                    className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                    onClick={() => {
                      setSelectedProfile(profile);
                      setOpenedDropdown(null);
                    }}
                  >
                    {profile.name}
                  </button>
                ))}
                <button
                  className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                  onClick={() => {
                    setSelectedProfile(null);
                    setOpenedDropdown(null);
                  }}
                >
                  No Profile
                </button>
              </div>
            </div>
          </div>

          {/* Agent selector */}
          <div className="relative text-sm font-medium flex-shrink-0">
            <button
              type="button"
              className="flex items-center gap-2 rounded-xl px-3 h-9 transition-all duration-300
                border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600"
              onClick={() => setOpenedDropdown("agent")}
            >
              <FontAwesomeIcon icon={faRobot} className="text-xs text-primary" />
              <span className="whitespace-nowrap max-w-[150px] truncate">
                {selectedAgent ? selectedAgent.name : "Generalist Agent"}
              </span>
              <FontAwesomeIcon icon={faAngleDown} className="text-xs opacity-60" />
            </button>
            <div
              style={{
                display: openedDropdown === "agent" ? "block" : "none",
                width: 260,
              }}
              className="absolute right-0 z-20 mt-2 rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-100 dark:border-dark-border overflow-hidden"
            >
              <div className="p-1">
                <button
                  className="block w-full p-2.5 text-sm rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                  onClick={() => {
                    setSelectedAgent(null);
                    setOpenedDropdown(null);
                  }}
                >
                  <span className="block text-sm font-medium truncate">Generalist Agent</span>
                  <span className="block text-[11px] opacity-70 truncate">No company agent selected</span>
                </button>
                {agents.map((agent) => (
                  <button
                    key={agent.agentId}
                    className="block w-full p-2.5 rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                    onClick={() => {
                      setSelectedAgent(agent);
                      setOpenedDropdown(null);
                    }}
                  >
                    <span className="block text-sm font-medium truncate">{agent.name}</span>
                    <span className="block text-[11px] opacity-70 truncate">
                      {agent.tasks?.length || 0} trained tasks
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {selectedAgent && selectedAgent.tasks?.length > 0 && (
            <div className="relative text-sm font-medium flex-shrink-0">
              <button
                type="button"
                className="flex items-center gap-2 rounded-xl px-3 h-9 transition-all duration-300
                  border border-gray-100 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-700 dark:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600"
                onClick={() => setOpenedDropdown("agentTask")}
              >
                <span className="whitespace-nowrap">Trained Tasks</span>
                <FontAwesomeIcon icon={faAngleDown} className="text-xs opacity-60" />
              </button>
              <div
                style={{
                  display: openedDropdown === "agentTask" ? "block" : "none",
                  width: 280,
                }}
                className="absolute right-0 z-20 mt-2 rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-100 dark:border-dark-border overflow-hidden"
              >
                <div className="p-1 max-h-[240px] overflow-auto scrollbar-thin">
                  {selectedAgent.tasks.map((task, index) => (
                    <button
                      key={`${task.name}-${index}`}
                      className="block w-full p-2.5 rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gradient-primary hover:text-white text-left transition-colors duration-200"
                      onClick={() => {
                        setPrompt(task.prompt);
                        if (selectedAgent.websiteUrl) setInitialUrl(selectedAgent.websiteUrl);
                        setOpenedDropdown(null);
                      }}
                    >
                      <span className="block text-sm font-medium truncate">{task.name || "Task"}</span>
                      <span className="block text-[11px] opacity-70 truncate">{task.prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Submit button */}
          <button
            onClick={handleSubmit}
            disabled={!prompt || submitting}
            className={`flex items-center justify-center w-9 h-9 rounded-xl flex-shrink-0 ml-auto
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
