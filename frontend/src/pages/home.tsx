import React, { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";

import TitleSection from "../components/home/title-section";
import TaskSection from "../components/home/task-section";
import SliderSection from "../components/home/slider-section";
import { Operator } from "../utils/types";

const apiUrl = process.env.REACT_APP_API_URL;

export default function Home(): React.ReactElement {
  const user = useSelector((state: any) => state.user);
  const [openedDropdown, setOpenedDropdown] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [initialUrl, setInitialUrl] = useState("");
  const [operators, setOperators] = useState<Operator[]>([]);
  const [selectedOperator, setSelectedOperator] = useState<Operator | null>(null);

  const loadOperators = useCallback(async () => {
    if (!user.email) return;
    try {
      const res = await fetch(`${apiUrl}/operators?email=${encodeURIComponent(user.email)}`);
      if (!res.ok) return;
      const data = await res.json();
      setOperators(data.operators || []);
    } catch (err) {
      console.error("Failed to load operators:", err);
    }
  }, [user.email]);

  useEffect(() => {
    loadOperators();
  }, [loadOperators]);

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

          <SliderSection
            setPrompt={setPrompt}
            setInitialUrl={setInitialUrl}
            operators={operators}
            setSelectedOperator={setSelectedOperator}
          />
        </div>
      </div>
    </div>
  );
}
