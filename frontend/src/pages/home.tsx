import React, { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";

import TitleSection from "../components/home/title-section";
import TaskSection from "../components/home/task-section";
import SliderSection from "../components/home/slider-section";
import { AgentConfig, Company } from "../utils/types";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

export default function Home(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [openedDropdown, setOpenedDropdown] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [initialUrl, setInitialUrl] = useState("");
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);

  const loadAgents = useCallback(async () => {
    if (!user.email) return;
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/agents?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setAgents(data.agents || []);
    } catch (err) {
      console.error("Failed to load agents:", err);
    }
  }, [user.email, companyId]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    if (!user.email) return;
    const loadCompanies = async () => {
      try {
        const res = await fetch(`${apiUrl}/companies?email=${encodeURIComponent(user.email)}`);
        if (!res.ok) return;
        const data = await res.json();
        setCompanies(data.companies || []);
      } catch (err) {
        console.error("Failed to load companies:", err);
      }
    };
    loadCompanies();
  }, [user.email]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const hasRealCompany = companies.some((company) => company.name !== "Default Company");
  const showFirstRunSetup = companies.length > 0 && !hasRealCompany && agents.length === 0;

  const openCompanyOnboarding = () => {
    window.dispatchEvent(new CustomEvent("automata-open-company-onboarding"));
  };

  return (
    <div className="w-full h-full flex relative overflow-auto bg-secondary">
      {openedDropdown !== null && (
        <div
          className="fixed top-0 left-0 w-full h-full bg-transparent z-10"
          onClick={() => setOpenedDropdown(null)}
        ></div>
      )}
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full"
        ></img>
      </div>
      <div className="flex flex-col px-6 md:px-12 xl:px-16 flex-grow h-full relative w-full">
        <div className="flex flex-col justify-center items-center flex-grow pt-16 md:pt-20">
          <TitleSection />

          {showFirstRunSetup && (
            <div className="w-full xl:w-[900px] mb-4 animate-slide-up">
              <div className="rounded-2xl border border-primary/20 bg-white dark:bg-dark-surface shadow-soft p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Start by setting up your company agent</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Describe your company once, then Automata will draft connectors, benchmark tasks, and the first agent setup checklist.
                  </p>
                </div>
                <button
                  onClick={openCompanyOnboarding}
                  className="h-10 px-4 rounded-xl bg-gradient-primary text-white text-sm font-semibold shadow-glow flex-shrink-0"
                >
                  Start onboarding
                </button>
              </div>
            </div>
          )}

          <TaskSection
            prompt={prompt}
            setPrompt={setPrompt}
            initialUrl={initialUrl}
            setInitialUrl={setInitialUrl}
            openedDropdown={openedDropdown}
            setOpenedDropdown={setOpenedDropdown}
            agents={agents}
            selectedAgent={selectedAgent}
            setSelectedAgent={setSelectedAgent}
          />

          <SliderSection
            setPrompt={setPrompt}
            setInitialUrl={setInitialUrl}
            agents={agents}
            setSelectedAgent={setSelectedAgent}
          />
        </div>
      </div>
    </div>
  );
}
