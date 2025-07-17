import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPaperPlane,
  faAngleDown,
  faPaperclip,
} from "@fortawesome/free-solid-svg-icons";

import IconButton from "../common/icon-button";
import { initializeSocket } from "../../utils/socket";
import { websites } from "../../utils/mock/mockDB";
import { resetChat, addTask } from "../../redux/chatSlice";
import { resetSocket } from "../../redux/socketSlice";

const apiUrl = process.env.REACT_APP_API_URL;

interface TaskSectionProps {
  prompt: string;
  setPrompt: React.Dispatch<React.SetStateAction<string>>;
  initialUrl: string;
  setInitialUrl: React.Dispatch<React.SetStateAction<string>>;
  openedDropdown: string | null;
  setOpenedDropdown: React.Dispatch<React.SetStateAction<string | null>>;
}

export default function TaskSection(props: TaskSectionProps) {
  const {
    prompt,
    setPrompt,
    initialUrl,
    setInitialUrl,
    openedDropdown,
    setOpenedDropdown,
  } = props;

  const [filteredWebsites, setFilteredWebsites] = useState(websites);
  const [agentCount, setAgentCount] = useState(1);

  const navigate = useNavigate();
  const dispatch = useDispatch();

  const user = useSelector((state: any) => state.user);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      handleSubmit();
      setPrompt("");
    }
  };

  const handleUrlChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setInitialUrl(value);

    if (value) {
      const filtered = websites.filter((website) =>
        website.url.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredWebsites(filtered);
      setOpenedDropdown("initialUrl");
    } else {
      setFilteredWebsites([]);
      setOpenedDropdown(null);
    }
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch(`${apiUrl}/operator`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          agentCount: agentCount,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        dispatch(resetSocket());
        dispatch(resetChat());
        dispatch(addTask(prompt));
        data.socketioPaths.forEach((socketioPath: string) => {
          const socket = initializeSocket(dispatch, socketioPath);
          const task = user.isAuthenticated ? `${prompt}\nADDITIONAL INFO: ${user.instructions}` : prompt;
          socket.emit("new-task", {
            task: task,
            url: initialUrl,
            storageState: data.storageState,
          });
        });
        navigate("/operator");
      } else {
        const errorData = await response.json();
        console.log(errorData);
      }
    } catch (error) {
      console.log(error);
    }
  };

  return (
    <>
      <div className="flex justify-end w-[100%] xl:w-[1000px] mb-4 md:me-2 mt-12">
        <label className="ms-2">
          <div className="relative w-full text-sm font-medium">
            <button
              type="button"
              className="w-[175px] text-left rounded-full shadow-sm py-1 ps-3 text-white bg-gradient-primary outline-none appearance-none -webkit-appearance-none -moz-appearance-none"
              onClick={() => setOpenedDropdown("network")}
            >
              Autoppia Validator
              <span className="absolute inset-y-0 right-2 flex items-center pointer-events-none">
                <FontAwesomeIcon icon={faAngleDown} />
              </span>
            </button>
            <div
              style={{
                display: openedDropdown === "network" ? "block" : "none",
              }}
              className="absolute z-20 mt-1 w-full rounded-lg bg-white shadow-lg"
            >
              <div className="p-1">
                <button
                  className="block p-2 text-sm rounded-lg text-gray-700 hover:bg-gradient-primary hover:text-white w-full text-left"
                  onClick={() => setOpenedDropdown(null)}
                >
                  Autoppia Validator
                </button>
              </div>
            </div>
          </div>
        </label>
        <label className="ms-2">
          <div className="relative w-full text-sm font-medium">
            <button
              type="button"
              className="w-[105px] text-left rounded-full shadow-sm py-1 ps-3 text-white bg-gradient-primary outline-none appearance-none -webkit-appearance-none -moz-appearance-none"
              onClick={() => setOpenedDropdown("agentCount")}
            >
              {`${agentCount} x Agent`}
              <span className="absolute inset-y-0 right-2 flex items-center pointer-events-none">
                <FontAwesomeIcon icon={faAngleDown} />
              </span>
            </button>
            <div
              style={{
                display: openedDropdown === "agentCount" ? "block" : "none",
              }}
              className="absolute z-20 mt-1 w-full rounded-lg bg-white shadow-lg"
            >
              <div className="p-1">
                {[1, 2, 4].map((option) => (
                  <button
                    key={option}
                    className="block p-2 text-sm rounded-lg text-gray-700 hover:bg-gradient-primary hover:text-white w-full text-left"
                    onClick={() => {
                      setAgentCount(option);
                      setOpenedDropdown(null);
                    }}
                  >
                    {`${option} x Agent`}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </label>
      </div>
      <div className="flex flex-col p-3 bg-white rounded-2xl w-[100%] xl:w-[1000px] self-center shadow-md border border-gray-300 group focus-within:shadow-lg focus-within:border-gray-500">
        <div className="flex items-start flex-grow">
          {" "}
          <input
            className="border-none outline-none flex-grow text-gray-900 p-2"
            placeholder="Ask me anything..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>

        <div className="flex flex-col md:flex-row justify-between mt-3 items-center gap-2">
          <label className="relative w-full">
            <div className="flex items-center gap-2">
              <IconButton icon={faPaperclip} className="dark:text-gray-700" />
              <div className="flex flex-grow px-4 py-2 grow items-center rounded-full border-gray-300 border-[1px] shadow-sm">
                {" "}
                <input
                  type="text"
                  placeholder="Website URL..."
                  className="w-full outline-none bg-none"
                  value={initialUrl}
                  onChange={handleUrlChange}
                />
                <div className="inset-y-0 right-3 flex items-center pointer-events-none">
                  <FontAwesomeIcon
                    icon={faAngleDown}
                    className="text-gray-500"
                  />
                </div>
              </div>
              <IconButton
                icon={faPaperPlane}
                onClick={handleSubmit}
                disabled={!prompt}
                className="dark:text-gray-700"
              />
            </div>
            <div
              style={{
                display: openedDropdown === "initialUrl" ? "block" : "none",
              }}
              className="absolute z-20 mt-1 w-[calc(100%-100px)] mx-[50px] rounded-lg bg-white shadow-lg"
            >
              <div className="p-1">
                {filteredWebsites.map((website) => (
                  <div
                    key={website.url}
                    className="cursor-pointer p-2 rounded-lg flex items-center hover:bg-gradient-primary hover:text-white"
                    onClick={() => {
                      setInitialUrl(website.url);
                      setFilteredWebsites([]);
                      setOpenedDropdown(null);
                    }}
                  >
                    <img
                     alt=""
                     src={website.favicon}
                     className="w-5 me-2"
                    />
                    <span className="text-sm">{website.title}</span>
                  </div>
                ))}
              </div>
            </div>
          </label>
        </div>
      </div>
    </>
  );
}
