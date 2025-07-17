import React, { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faCompressAlt,
  faSave,
} from "@fortawesome/free-solid-svg-icons";
import { faShareFromSquare } from "@fortawesome/free-regular-svg-icons";

import ChatSidebar from "../components/operator/chat-sidebar";
import IconButton from "../components/common/icon-button";

function Operator(): React.ReactElement {
  const imageRef = useRef<HTMLImageElement | null>(null);

  const [showSideBar, setShowSideBar] = useState(window.screen.width >= 1024);

  const navigate = useNavigate();

  const chats = useSelector((state: any) => state.chat.chats);
  const socketIds = useSelector((state: any) => state.socket.socketIds);
  const screenshots = useSelector((state: any) => state.socket.screenshots);

  useEffect(() => {
    if (chats.length === 0) {
      navigate("/")
    }
  }, [chats.length, navigate])

  const handleFullScreen = () => {
    if (imageRef.current) {
      imageRef.current.requestFullscreen?.();
    }
  };

  const toggleSideBar = () => {
    setShowSideBar(!showSideBar);
  };

  const generateClassName = (parent: boolean) => {
    if (parent) {
      if (socketIds.length > 1) {
        return "flex flex-col xl:grid xl:grid-cols-2 gap-4 w-full flex-grow relative overflow-auto p-5 mt-5";
      } else {
        return "flex w-full flex-grow relative overflow-auto p-5 mt-5";
      }
    }

    let className =
      "flex flex-shrink-0 relative bg-white rounded-2xl w-full self-center shadow-md flex-grow overflow-y-scroll dark:border-2 dark:border-gray-100";

    if (socketIds.length > 1) {
      return className + " h-auto xl:h-full";
    } else {
      return className + " max-h-full";
    }
  };
  return (
    <div className="bg-gray-100 w-[100%] h-[100vh] flex z-0">
      <div className="fixed w-full h-full hidden dark:block">
        <img
          src="./assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full"
        />
      </div>
      <ChatSidebar
        open={showSideBar}
        toggleSideBar={toggleSideBar}
      />
      <div
        className={`hidden lg:flex flex-col px-5 py-5 h-full hidden relative items-center ${showSideBar ? "lg:w-[calc(100%-500px)] lg:ms-[500px]" : "w-full"
          }`}
      >
        <div className="flex justify-between w-full">
          <div className="flex items-center">
            {!showSideBar && (
              <IconButton icon={faBars} onClick={toggleSideBar} className="dark:text-white" />
            )}
            <div
              className="ms-2 flex hover:bg-gray-300 rounded-full justify-center items-center p-3 cursor-pointer transition-all duration-300 text-gray-500 dark:text-white"
              onClick={handleFullScreen}
            >
              <FontAwesomeIcon icon={faCompressAlt} />
            </div>
          </div>
          <div className="flex">
            <div className="flex rounded-full justify-center items-center px-3 me-3 cursor-not-allowed transition-all duration-300 font-semibold text-gray-600 dark:text-white">
              <FontAwesomeIcon icon={faShareFromSquare} />
              <span className="ms-2">Share</span>
            </div>
            <div className="flex rounded-full justify-center items-center px-3 border-[1px] border-gray-400 cursor-not-allowed transition-all duration-300 font-semibold text-gray-600 dark:text-white">
              <FontAwesomeIcon icon={faSave} />
              <span className="ms-2">Save Task</span>
            </div>
          </div>
        </div>
        <div className={generateClassName(true)}>
          {socketIds.map((socketId: string, index: Number) => {
            const screenshot = screenshots[socketId]
            return (
              <div
                key={`${index}_screenshot_main`}
                className={generateClassName(false) + " items-start"}
                style={{
                  scrollbarWidth: "none",
                  msOverflowStyle: "none",
                }}
              >
                <img
                  ref={imageRef}
                  alt=""
                  src={screenshot ? screenshot : "/assets/images/screenshot/blank.webp"}
                  className="w-full h-auto screenshot my-auto object-contain max-h-none self-center"
                />
                {!screenshot && <div className="absolute w-full h-full flex flex-col justify-center items-center">
                  <img
                    src="./assets/images/logos/main_dark.webp"
                    alt=""
                    className="h-6 mb-6"
                  />
                  <img
                    alt=""
                    src="/assets/images/screenshot/loading.gif"
                    className="h-12"
                  />
                </div>}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  );
}

export default Operator;
