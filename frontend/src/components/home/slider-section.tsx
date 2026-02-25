import React, { useState, useRef } from "react";
import Slider from "react-slick";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { bittensorPrompts, generalPrompts } from "../../utils/mock/mockDB";

interface SliderSectionProps {
  setPrompt: React.Dispatch<React.SetStateAction<string>>;
  setInitialUrl: React.Dispatch<React.SetStateAction<string>>;
}

export default function SliderSection(props: SliderSectionProps) {
  const { setPrompt, setInitialUrl } = props;

  const [slideIndex, setSlideIndex] = useState<number>(0);
  let sliderRef = useRef<Slider | null>(null);

  const settings = {
    accessibility: false,
    infinite: true,
    arrows: false,
    speed: 500,
    autoplay: true,
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
      }}
    >
      <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 bg-gradient-primary rounded-xl
        shadow-glow group-hover/card:shadow-glow-lg transition-all duration-300">
        <FontAwesomeIcon icon={item.icon} className="text-white text-sm" />
      </div>
      <span className="text-sm text-gray-700 dark:text-gray-200 font-medium leading-snug">{item.title}</span>
    </div>
  );

  return (
    <div className="w-full xl:w-[900px] mx-auto mt-6 mb-4 animate-slide-up" style={{ animationDelay: "0.2s" }}>
      <Slider
        ref={(slider) => {
          sliderRef.current = slider;
        }}
        {...settings}
      >
        <div className="py-2 px-1">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {bittensorPrompts.map((item, index) => (
              <PromptCard key={index} item={item} index={index} group="group-one" />
            ))}
          </div>
        </div>

        <div className="py-2 px-1">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {generalPrompts.map((item, index) => (
              <PromptCard key={index} item={item} index={index} group="group-two" />
            ))}
          </div>
        </div>
      </Slider>

      {/* Slide indicators */}
      <div className="flex justify-center mt-3 gap-2">
        {[0, 1].map((i) => (
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
      </div>
    </div>
  );
}
