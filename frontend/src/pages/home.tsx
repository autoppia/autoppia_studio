import React, { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";

import TitleSection from "../components/home/title-section";
import TaskSection from "../components/home/task-section";
import SliderSection from "../components/home/slider-section";
import { Company, Operator } from "../utils/types";
import CelerisOnboarding from "../components/home/celeris-onboarding";

const apiUrl = process.env.REACT_APP_API_URL;

export default function Home(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [openedDropdown, setOpenedDropdown] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [initialUrl, setInitialUrl] = useState("");
  const [operators, setOperators] = useState<Operator[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [selectedOperator, setSelectedOperator] = useState<Operator | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  const loadOperators = useCallback(async () => {
    if (!user.email) return;
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/operators?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setOperators(data.operators || []);
    } catch (err) {
      console.error("Failed to load operators:", err);
    }
  }, [user.email, companyId]);

  useEffect(() => {
    loadOperators();
  }, [loadOperators]);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const loadCompanies = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/companies?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) return;
      const data = await res.json();
      const next = data.companies || [];
      setCompanies(next);
      const hasConfiguredCompany = next.some((company: Company) => company.name !== "Default Company");
      if (!hasConfiguredCompany && operators.length === 0) setShowOnboarding(true);
    } catch (err) {
      console.error("Failed to load companies:", err);
    }
  }, [user.email, operators.length]);

  useEffect(() => {
    loadCompanies();
  }, [loadCompanies]);

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

          <TaskSection
            prompt={prompt}
            setPrompt={setPrompt}
            initialUrl={initialUrl}
            setInitialUrl={setInitialUrl}
            openedDropdown={openedDropdown}
            setOpenedDropdown={setOpenedDropdown}
            operators={operators}
            selectedOperator={selectedOperator}
            setSelectedOperator={setSelectedOperator}
          />

          <div className="mt-5 flex items-center gap-3">
            <button
              onClick={() => setShowOnboarding(true)}
              className="text-xs font-medium text-gray-400 dark:text-gray-500 hover:text-primary transition-colors"
            >
              Create a company agent
            </button>
            {companies.length > 0 && <span className="text-xs text-gray-300 dark:text-gray-600">/</span>}
            <button
              onClick={loadCompanies}
              className="text-xs font-medium text-gray-400 dark:text-gray-500 hover:text-primary transition-colors"
            >
              Refresh companies
            </button>
          </div>

          <SliderSection
            setPrompt={setPrompt}
            setInitialUrl={setInitialUrl}
            operators={operators}
            setSelectedOperator={setSelectedOperator}
          />
        </div>
      </div>
      {showOnboarding && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center px-4 py-6">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowOnboarding(false)} />
          <div className="relative max-h-full overflow-auto scrollbar-thin">
            <button
              onClick={() => setShowOnboarding(false)}
              className="absolute right-3 top-3 z-10 h-8 px-3 rounded-lg bg-white/90 dark:bg-dark-surface/90 text-xs font-medium text-gray-500 hover:text-gray-900 dark:hover:text-white"
            >
              Close
            </button>
            <CelerisOnboarding />
          </div>
        </div>
      )}
    </div>
  );
}
