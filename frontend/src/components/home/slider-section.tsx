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
  return (
    <div className="w-full xl:w-[1000px] mx-auto my-4">
      <Slider
        ref={(slider) => {
          sliderRef.current = slider;
        }}
        {...settings}
      >
        <div className="py-2">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {bittensorPrompts.map((item, index) => (
              <div
                className="border border-gray-400 border-dashed shadow-sm px-4 py-4 rounded-2xl cursor-pointer   
                           hover:-translate-y-1 hover:shadow-lg transition-transform duration-200 dark:text-white flex items-center gap-2"
                key={`group-one-prompt-${index}`}
                onClick={() => {
                  setPrompt(item.prompt);
                  setInitialUrl(item.url);
                }}
              >
                <div className="flex items-center justify-center bg-gradient-primary p-3 rounded-full me-2">
                  <FontAwesomeIcon icon={item.icon} className="text-white" />
                </div>
                <div className="text-sm">{item.title}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="py-2">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {generalPrompts.map((item, index) => (
              <div
                className="border border-gray-400 border-dashed shadow-sm px-4 py-4 rounded-2xl cursor-pointer   
                           hover:-translate-y-1 hover:shadow-lg transition-transform duration-200 dark:text-white flex items-center gap-2"
                key={`group-two-prompt-${index}`}
                onClick={() => {
                  setPrompt(item.prompt);
                  setInitialUrl(item.url);
                }}
              >
                <div className="flex items-center justify-center bg-gradient-primary p-3 rounded-full me-2">
                  <FontAwesomeIcon icon={item.icon} className="text-white" />
                </div>
                <div className="text-sm">{item.title}</div>
              </div>
            ))}
          </div>
        </div>
      </Slider>

      <div className="flex justify-center mt-1 mb-1 w-full">
        <div className="flex justify-around w-20">
          <div
            className={
              "w-8 h-1 rounded-full hover:bg-gray-600 dark:hover:bg-gray-400 " +
              (slideIndex === 0
                ? "bg-gray-700 dark:bg-white"
                : "bg-gray-400 dark:bg-gray-600")
            }
            onClick={() => sliderRef.current?.slickGoTo(0)}
          />
          <div
            className={
              "w-8 h-1 rounded-full hover:bg-gray-600 dark:hover:bg-gray-400 " +
              (slideIndex === 1
                ? "bg-gray-700 dark:bg-white"
                : "bg-gray-400 dark:bg-gray-600")
            }
            onClick={() => sliderRef.current?.slickGoTo(1)}
          />
        </div>
      </div>
    </div>
  );
}
