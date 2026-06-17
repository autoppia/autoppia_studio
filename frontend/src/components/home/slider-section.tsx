import React, { useMemo, useRef, useState } from "react";
import Slider from "react-slick";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faFilm, faListCheck, faMagnifyingGlass, faRightToBracket, faRobot } from "@fortawesome/free-solid-svg-icons";
import { AgentConfig } from "../../utils/types";

interface SliderSectionProps {
  setPrompt: React.Dispatch<React.SetStateAction<string>>;
  setInitialUrl: React.Dispatch<React.SetStateAction<string>>;
  agents: AgentConfig[];
  setSelectedAgent: React.Dispatch<React.SetStateAction<AgentConfig | null>>;
}

export default function SliderSection(props: SliderSectionProps) {
  const { setPrompt, setInitialUrl, agents, setSelectedAgent } = props;

  const [slideIndex, setSlideIndex] = useState<number>(0);
  let sliderRef = useRef<Slider | null>(null);

  const agentPrompts = useMemo(() => {
    const trainedTasks = agents.flatMap((agent) =>
      (agent.tasks || []).map((task, index) => ({
        title: task.name || `${agent.name} Task ${index + 1}`,
        prompt: task.prompt,
        url: agent.websiteUrl,
        agentName: agent.name,
        agent,
        icon: index === 0 ? faRightToBracket : index === 1 ? faMagnifyingGlass : index === 2 ? faFilm : faRobot,
      }))
    ).filter((item) => item.prompt);

    if (trainedTasks.length > 0) return trainedTasks.slice(0, 8);

    return [
      {
        title: "Autocinema Login",
        prompt: "Log in to Autocinema with username user1 and password Passw0rd!",
        url: "http://84.247.180.192:8000",
        agentName: "Autocinema",
        agent: null,
        icon: faRightToBracket,
      },
      {
        title: "Autocinema Search",
        prompt: "Search for The Matrix in Autocinema",
        url: "http://84.247.180.192:8000",
        agentName: "Autocinema",
        agent: null,
        icon: faMagnifyingGlass,
      },
      {
        title: "Autocinema Film Detail",
        prompt: "Open a film detail page in Autocinema",
        url: "http://84.247.180.192:8000",
        agentName: "Autocinema",
        agent: null,
        icon: faFilm,
      },
    ];
  }, [agents]);

  const promptSlides = useMemo(() => {
    const slides = [];
    for (let i = 0; i < agentPrompts.length; i += 4) {
      slides.push(agentPrompts.slice(i, i + 4));
    }
    return slides.length > 0 ? slides : [agentPrompts];
  }, [agentPrompts]);

  const settings = {
    accessibility: false,
    infinite: promptSlides.length > 1,
    arrows: false,
    speed: 500,
    autoplay: promptSlides.length > 1,
    autoplaySpeed: 5000,
    slidesToShow: 1,
    slidesToScroll: 1,
    beforeChange: (current: number, next: number) => {
      setSlideIndex(next);
    },
  };

  const PromptCard = ({ item, index, group }: { item: any; index: number; group: string }) => (
    <div
      className="group/card border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface
        px-4 py-4 rounded-2xl cursor-pointer
        hover:-translate-y-1 hover:shadow-soft-lg hover:border-gray-300 dark:hover:border-gray-600
        transition-all duration-300 flex items-center gap-3"
      key={`${group}-prompt-${index}`}
      onClick={() => {
        setPrompt(item.prompt);
        setInitialUrl(item.url);
        if (item.agent) setSelectedAgent(item.agent);
      }}
    >
      <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 bg-gradient-primary rounded-lg
        shadow-glow group-hover/card:shadow-glow-lg transition-all duration-300">
        <FontAwesomeIcon icon={item.icon} className="text-white text-sm" />
      </div>
      <div className="min-w-0">
        <span className="block text-sm text-gray-700 dark:text-gray-200 font-medium leading-snug truncate">{item.title}</span>
        <span className="block text-[11px] text-gray-400 dark:text-gray-500 truncate">
          {item.agentName || "Agent trained task"}
        </span>
      </div>
    </div>
  );

  const renderSlide = (slide: any[], slideNumber: number) => (
    <div className="py-2 px-1" key={`agent-examples-${slideNumber}`}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {slide.map((item, index) => (
          <PromptCard key={`${item.title}-${index}`} item={item} index={index} group={`agent-${slideNumber}`} />
        ))}
        {slide.length < 4 && Array.from({ length: 4 - slide.length }).map((_, index) => (
          <div
            key={`placeholder-${index}`}
            className="hidden lg:flex border border-dashed border-gray-200 dark:border-dark-border bg-white/50 dark:bg-dark-surface/50
              px-4 py-4 rounded-2xl items-center gap-3 text-gray-400 dark:text-gray-500"
          >
            <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-lg bg-gray-100 dark:bg-dark-border">
              <FontAwesomeIcon icon={faListCheck} className="text-sm" />
            </div>
            <span className="text-sm font-medium">Train more tasks</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="w-full xl:w-[900px] mx-auto mt-6 mb-4 animate-slide-up" style={{ animationDelay: "0.2s" }}>
      {promptSlides.length === 1 ? (
        renderSlide(promptSlides[0], 0)
      ) : (
        <Slider
          ref={(slider) => {
            sliderRef.current = slider;
          }}
          {...settings}
        >
          {promptSlides.map((slide, slideNumber) => renderSlide(slide, slideNumber))}
        </Slider>
      )}

      {/* Slide indicators */}
      {promptSlides.length > 1 && <div className="flex justify-center mt-3 gap-2">
        {promptSlides.map((_, i) => (
          <button
            key={i}
            className={`h-1.5 rounded-full transition-all duration-300 cursor-pointer
              ${slideIndex === i
                ? "w-8 bg-primary"
                : "w-4 bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500"
              }`}
            onClick={() => sliderRef.current?.slickGoTo(i)}
          />
        ))}
      </div>}
    </div>
  );
}
