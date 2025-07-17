import React, { useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faHome,
  faUser,
} from "@fortawesome/free-solid-svg-icons";

import TitleSection from "../components/home/title-section";
import TaskSection from "../components/home/task-section";
import SliderSection from "../components/home/slider-section";
import ProfileSidebar from "../components/home/profile-sidebar";
import ToggleTheme from "../components/common/toggle-theme";
import IconButton from "../components/common/icon-button";

export default function Home(): React.ReactElement {
  const [openedDropdown, setOpenedDropdown] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [prompt, setPrompt] = useState("");
  const [initialUrl, setInitialUrl] = useState("");

  const returnHome = () => {
    window.location.href = "https://autoppia.com/";
  };

  return (
    <div className="w-[100vw] h-[100vh] flex relative overflow-auto bg-secondary">
      {openedDropdown !== null && (
        <div
          className="fixed top-0 left-0 w-full h-full bg-transparent z-10"
          onClick={() => setOpenedDropdown(null)}
        ></div>
      )}
      <div className="fixed w-full h-full hidden dark:block">
        <img
          src="./assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full"
        ></img>
      </div>
      <div className="flex flex-col px-6 md:px-12 xl:px-16 flex-grow h-full relative w-[100vw]">
        <div className="relative flex justify-between items-center mt-8 mb-8">
          <img
            src="./assets/images/logos/main_dark.webp"
            alt=""
            className="h-[16px] sm:h-[20px] dark:block hidden"
          />
          <img
            src="./assets/images/logos/main.webp"
            alt=""
            className="h-[16px] sm:h-[20px] dark:hidden block"
          />
          <div className="flex items-center ms-2 md:ms-0">
            <IconButton
              onClick={returnHome}
              icon={faHome}
              className="dark:text-white"
            />
            <ToggleTheme />
            <div
              className="flex justify-center items-center p-2 sm:p-3 rounded-full
                  transition-all duration-200 cursor-pointer text-gray-700 text-white
                  bg-gradient-primary ms-1 sm:ms-3"
              onClick={() => setSidebarOpen(true)}
            >
              <FontAwesomeIcon icon={faUser} />
            </div>
          </div>
        </div>
        <div className="flex flex-col justify-center items-center flex-grow">
          <TitleSection />

          <TaskSection
            prompt={prompt}
            setPrompt={setPrompt}
            initialUrl={initialUrl}
            setInitialUrl={setInitialUrl}
            openedDropdown={openedDropdown}
            setOpenedDropdown={setOpenedDropdown}
          />

          <SliderSection
            setPrompt={setPrompt}
            setInitialUrl={setInitialUrl}
          />
        </div>
      </div>
      <ProfileSidebar
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
      />
    </div>
  );
}
