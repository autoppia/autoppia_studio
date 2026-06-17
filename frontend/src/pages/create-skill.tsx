import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import useStartSession from "../hooks/useStartSession";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faRobot,
  faHand,
  faArrowLeft,
  faChevronDown,
  faGlobe,
  faAngleDown,
  faUserCircle,
} from "@fortawesome/free-solid-svg-icons";
import { websites } from "../utils/mock/mockDB";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

type GenerationMode = "agent" | "record";

interface Profile {
  id: string;
  name: string;
  contextId: string;
}

const GOAL_EXAMPLES = [
  "Log into my account",
  "Add item to cart",
  "Fill out a contact form",
  "Search for a product",
  "Submit a job application",
];

export default function CreateSkill() {
  const navigate = useNavigate();
  const startSession = useStartSession();
  const user = useSelector((state: any) => state.user);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<GenerationMode>("agent");
  const [agentInstructions, setAgentInstructions] = useState("");
  const [initialUrl, setInitialUrl] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [urlDropdownOpen, setUrlDropdownOpen] = useState(false);
  const [filteredWebsites, setFilteredWebsites] = useState(websites);
  const [, setAgent] = useState("autoppia");
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false);
  const goalRef = useRef<HTMLTextAreaElement>(null);
  const instructionsRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!user.email) return;
    fetch(`${apiUrl}/profiles?email=${encodeURIComponent(user.email)}`)
      .then((r) => r.json())
      .then((d) => setProfiles(d.profiles || []))
      .catch(() => {});
  }, [user.email]);

  // Auto-select first profile
  const autoSelected = useRef(false);
  useEffect(() => {
    if (profiles.length > 0 && !autoSelected.current) {
      setSelectedProfileId(profiles[0].id);
      autoSelected.current = true;
    }
  }, [profiles]);

  const handleGoalChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setGoal(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${e.target.scrollHeight}px`;
  };

  const handleInstructionsChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setAgentInstructions(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${e.target.scrollHeight}px`;
  };

  const handleUrlChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInitialUrl(value);
    if (value) {
      setFilteredWebsites(websites.filter((w) => w.url.toLowerCase().includes(value.toLowerCase())));
    } else {
      setFilteredWebsites(websites);
    }
    setUrlDropdownOpen(true);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;

    const profile = profiles.find((p) => p.id === selectedProfileId);
    const contextId = profile?.contextId || "";

    if (mode === "agent") {
      if (!agentInstructions.trim()) return;
      await startSession(agentInstructions.trim(), initialUrl.trim(), contextId, {
        skillMode: true,
        skillName: name.trim(),
        skillGoal: goal.trim(),
        skillInstructions: agentInstructions.trim(),
      });
    } else {
      navigate("/skills/record", {
        state: {
          skillName: name.trim(),
          skillGoal: goal.trim(),
          initialUrl: initialUrl.trim(),
          contextId,
        },
      });
    }
  };

  // Close dropdowns when clicking outside
  const closeDropdowns = () => {
    setUrlDropdownOpen(false);
    setProfileDropdownOpen(false);
    setAgentDropdownOpen(false);
  };

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full object-cover"
        />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/skills")}
              className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400
                hover:bg-gray-100 dark:hover:bg-dark-surface transition-colors duration-200"
            >
              <FontAwesomeIcon icon={faArrowLeft} className="text-sm" />
            </button>
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Create Skill</h1>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-8" onClick={closeDropdowns}>
          <div className="max-w-2xl mx-auto">
            <form onSubmit={handleSubmit} className="space-y-8">

              {/* Skill Name */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Skill Name <span className="text-gray-400 dark:text-gray-500 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g., Login Automation"
                  className="w-full h-10 px-3 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                    text-sm text-gray-900 dark:text-white placeholder:text-gray-400
                    outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors duration-200"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              {/* Skill Goal */}
              <div className="space-y-4">
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white">What should this skill do?</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Describe the repeatable action you want to automate</p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Skill Goal <span className="text-red-500 ml-0.5">*</span>
                  </label>
                  <textarea
                    ref={goalRef}
                    placeholder="e.g., Log into my account, navigate to the orders page, and extract the latest order status"
                    className="w-full px-3 py-2.5 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                      text-sm text-gray-900 dark:text-white placeholder:text-gray-400 resize-none overflow-hidden
                      outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors duration-200"
                    rows={3}
                    style={{ minHeight: "100px" }}
                    value={goal}
                    onChange={handleGoalChange}
                  />
                  {/* Example chips */}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {GOAL_EXAMPLES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => setGoal(example)}
                        className="px-3 h-7 rounded-lg text-xs font-medium border border-gray-200 dark:border-dark-border
                          bg-gray-50 dark:bg-dark-surface text-gray-500 dark:text-gray-400
                          hover:text-gray-800 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-gray-500
                          transition-colors duration-200"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Generation Mode */}
              <div className="space-y-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Generation Mode <span className="text-red-500 ml-0.5">*</span>
                </label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Agent */}
                  <div
                    onClick={() => setMode("agent")}
                    className={`cursor-pointer rounded-xl border-2 p-4 flex flex-col gap-2 transition-all duration-200
                      ${mode === "agent"
                        ? "border-primary bg-primary/5 dark:bg-primary/10 shadow-glow"
                        : "border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface hover:border-gray-300 dark:hover:border-gray-600"
                      }`}
                  >
                    <div className={`flex items-center gap-2 font-medium text-sm
                      ${mode === "agent" ? "text-primary" : "text-gray-700 dark:text-gray-300"}`}>
                      <FontAwesomeIcon icon={faRobot} className="text-sm" />
                      Agent
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                      The AI agent handles everything automatically based on your goal description.
                    </p>
                  </div>

                  {/* Record yourself */}
                  <div
                    onClick={() => setMode("record")}
                    className={`cursor-pointer rounded-xl border-2 p-4 flex flex-col gap-2 transition-all duration-200
                      ${mode === "record"
                        ? "border-primary bg-primary/5 dark:bg-primary/10 shadow-glow"
                        : "border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface hover:border-gray-300 dark:hover:border-gray-600"
                      }`}
                  >
                    <div className={`flex items-center gap-2 font-medium text-sm
                      ${mode === "record" ? "text-primary" : "text-gray-700 dark:text-gray-300"}`}>
                      <FontAwesomeIcon icon={faHand} className="text-sm" />
                      Record Yourself
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                      You control the browser and perform the actions — we record and replay them.
                    </p>
                  </div>
                </div>
              </div>

              {mode === "agent" && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Agent Instructions <span className="text-red-500 ml-0.5">*</span>
                  </label>
                  <textarea
                    ref={instructionsRef}
                    placeholder="Any specific instructions for the agent, e.g., 'Use the email field for login, skip cookie banners'"
                    className="w-full px-3 py-2.5 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                      text-sm text-gray-900 dark:text-white placeholder:text-gray-400 resize-none
                      outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors duration-200"
                    style={{ minHeight: "113px", overflowY: "hidden" }}
                    value={agentInstructions}
                    onChange={handleInstructionsChange}
                  />
                </div>
              )}

              {/* Website URL — shared by both modes */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Website URL <span className="text-gray-400 dark:text-gray-500 font-normal">(optional)</span>
                </label>
                <div className="relative" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center gap-2 px-3 h-10 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                    focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-all duration-200">
                    <FontAwesomeIcon icon={faGlobe} className="text-gray-400 text-sm flex-shrink-0" />
                    <input
                      type="text"
                      placeholder="https://google.com"
                      className="w-full outline-none bg-transparent text-sm text-gray-900 dark:text-white placeholder:text-gray-400 font-mono"
                      value={initialUrl}
                      onChange={handleUrlChange}
                      onFocus={() => {
                        if (!initialUrl) setFilteredWebsites(websites);
                        setUrlDropdownOpen(true);
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setFilteredWebsites(initialUrl
                          ? websites.filter((w) => w.url.toLowerCase().includes(initialUrl.toLowerCase()))
                          : websites
                        );
                        setUrlDropdownOpen((v) => !v);
                      }}
                      className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    >
                      <FontAwesomeIcon icon={faAngleDown} className="text-xs" />
                    </button>
                  </div>
                  {urlDropdownOpen && filteredWebsites.length > 0 && (
                    <div className="absolute z-20 mt-1 w-full rounded-xl bg-white dark:bg-dark-surface shadow-soft-lg border border-gray-200 dark:border-dark-border overflow-hidden">
                      <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                        {filteredWebsites.map((website) => (
                          <div
                            key={website.url}
                            className="cursor-pointer p-2.5 rounded-lg flex items-center hover:bg-gradient-primary hover:text-white
                              text-gray-700 dark:text-gray-200 transition-colors duration-200"
                            onClick={() => {
                              setInitialUrl(website.url);
                              setUrlDropdownOpen(false);
                            }}
                          >
                            <img alt="" src={website.favicon} className="w-5 h-5 rounded me-2.5" />
                            <span className="text-sm font-medium">{website.title}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Profile & Agent — inline row */}
              <div className="flex items-start gap-4">
                {/* Profile selector */}
                <div className="flex-1 space-y-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Profile <span className="text-gray-400 dark:text-gray-500 font-normal">(optional)</span>
                  </label>
                  <div className="relative" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      onClick={() => setProfileDropdownOpen((v) => !v)}
                      className="w-full h-10 px-3 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                        text-sm text-left flex items-center gap-2
                        outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors duration-200 cursor-pointer"
                    >
                      <FontAwesomeIcon icon={faUserCircle} className={`text-xs flex-shrink-0 ${selectedProfileId ? "text-primary" : "text-gray-400"}`} />
                      <span className={`flex-1 truncate ${selectedProfileId ? "text-gray-900 dark:text-white" : "text-gray-400"}`}>
                        {selectedProfileId
                          ? profiles.find((p) => p.id === selectedProfileId)?.name || "Unknown"
                          : "No profile"}
                      </span>
                      <FontAwesomeIcon
                        icon={faChevronDown}
                        className={`text-[10px] text-gray-400 transition-transform duration-200 flex-shrink-0 ${profileDropdownOpen ? "rotate-180" : ""}`}
                      />
                    </button>
                    {profileDropdownOpen && (
                      <>
                        <div className="fixed inset-0 z-10" onClick={() => setProfileDropdownOpen(false)} />
                        <div className="absolute top-full left-0 right-0 mt-1 z-20 rounded-xl bg-white dark:bg-dark-surface
                          border border-gray-200 dark:border-dark-border shadow-lg overflow-hidden">
                          <div className="p-1 max-h-[200px] overflow-auto scrollbar-thin">
                            <button
                              type="button"
                              onClick={() => { setSelectedProfileId(""); setProfileDropdownOpen(false); }}
                              className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors
                                ${!selectedProfileId
                                  ? "bg-primary/5 text-primary font-medium"
                                  : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                            >
                              No profile (fresh session)
                            </button>
                            {profiles.map((p) => (
                              <button
                                key={p.id}
                                type="button"
                                onClick={() => { setSelectedProfileId(p.id); setProfileDropdownOpen(false); }}
                                className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors
                                  ${selectedProfileId === p.id
                                    ? "bg-primary/5 text-primary font-medium"
                                    : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                              >
                                {p.name}
                              </button>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {/* Agent selector */}
                {mode === "agent" && (
                  <div className="flex-1 space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Agent
                    </label>
                    <div className="relative" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => setAgentDropdownOpen((v) => !v)}
                        className="w-full h-10 px-3 rounded-xl bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border
                          text-sm text-left flex items-center gap-2
                          outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors duration-200 cursor-pointer"
                      >
                        <FontAwesomeIcon icon={faRobot} className="text-xs text-primary flex-shrink-0" />
                        <span className="flex-1 truncate text-gray-900 dark:text-white">Generalist Agent</span>
                        <FontAwesomeIcon
                          icon={faChevronDown}
                          className={`text-[10px] text-gray-400 transition-transform duration-200 flex-shrink-0 ${agentDropdownOpen ? "rotate-180" : ""}`}
                        />
                      </button>
                      {agentDropdownOpen && (
                        <>
                          <div className="fixed inset-0 z-10" onClick={() => setAgentDropdownOpen(false)} />
                          <div className="absolute top-full left-0 right-0 mt-1 z-20 rounded-xl bg-white dark:bg-dark-surface
                            border border-gray-200 dark:border-dark-border shadow-lg overflow-hidden">
                            <div className="p-1">
                              <button
                                type="button"
                                onClick={() => { setAgent("autoppia"); setAgentDropdownOpen(false); }}
                                className="w-full text-left px-3 py-2 text-sm rounded-lg bg-primary/5 text-primary font-medium"
                              >
                                Generalist Agent
                              </button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={!goal.trim() || (mode === "agent" && !agentInstructions.trim())}
                className={`w-full h-11 rounded-xl text-sm font-medium transition-all duration-200
                  ${goal.trim() && (mode === "record" || agentInstructions.trim())
                    ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg hover:scale-[1.01] cursor-pointer"
                    : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                  }`}
              >
                {mode === "record" ? "Start Recording" : "Create Skill"}
              </button>

            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
