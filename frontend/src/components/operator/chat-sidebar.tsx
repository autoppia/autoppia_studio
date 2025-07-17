import React, { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faEdit,
  faPaperPlane,
} from "@fortawesome/free-solid-svg-icons";

import ToggleTheme from "../common/toggle-theme";
import IconButton from "../common/icon-button";
import OperatorResponse from "./operator-response";
import UserMessage from "./user-message";
import { addAction, addTask } from "../../redux/chatSlice";

interface ChatSidebarProps {
  open: boolean;
  toggleSideBar: () => void;
}

export default function ChatSidebar(props: ChatSidebarProps) {
  const { open, toggleSideBar } = props;

  const [task, setTask] = useState("");
  const [dlgOpen, setDlgOpen] = useState(false);

  const navigate = useNavigate();
  const dispatch = useDispatch();
  const chats = useSelector((state: any) => state.chat.chats);
  const completed = useSelector((state: any) => state.chat.completed);
  const sockets = useSelector((state: any) => state.socket.sockets);
  const socketIds = useSelector((state: any) => state.socket.socketIds);
  const screenshots = useSelector((state: any) => state.socket.screenshots);

  const handleSubmit = () => {
    dispatch(addTask(task));
    setTask("");
    sockets.forEach((socket: any) => {
      if (socket.connected) {
        dispatch(
          addAction({
            socketId: socket.id,
            action: "Continuing task...",
          })
        );
        socket.emit("continue-task", {
          task: task,
        });
      } 
    });
  };
  const handleChangeTask = (event: React.ChangeEvent<HTMLInputElement>) => {
    setTask(event.target.value);
  };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      handleSubmit();
      setTask("");
    }
  };
  const handleNew = () => {
    setDlgOpen(true);
  };
  const handleYes = () => {
    navigate("/");
  };

  return (
    <div
      className={`fixed left-0 w-full lg:w-[500px] px-2 sm:px-4 md:px-8 z-10 
        transition-all duration-300 h-full pt-1 pb-1 flex flex-col overflow-hidden 
        bg-secondary shadow-md dark:bg-transparent dark:shadow-gray-100
        ${open ? "" : "lg:-left-[500px]"}`}
    >
      <div className="flex items-center py-4">
        <IconButton
          icon={faBars}
          onClick={toggleSideBar}
          className="dark:text-white"
        />
        <div className="flex-grow ms-2 sm:ms-4">
          <img
            src="./assets/images/logos/main_dark.webp"
            alt=""
            className="h-[18px] dark:block hidden"
          />
          <img
            src="./assets/images/logos/main.webp"
            alt=""
            className="h-[18px] dark:hidden block"
          />
        </div>
        <IconButton
          icon={faEdit}
          onClick={handleNew}
          className="dark:text-white"
        />
        <ToggleTheme />
      </div>
      <div
        className="w-full px-2 flex flex-col mt-2 flex-grow overflow-auto mb-5 
                  [&::-webkit-scrollbar]:w-2
                  [&::-webkit-scrollbar-track]:rounded-full
                  [&::-webkit-scrollbar-track]:bg-gray-100/20
                  [&::-webkit-scrollbar-thumb]:rounded-full
                  [&::-webkit-scrollbar-thumb]:bg-gray-300/40
                  dark:[&::-webkit-scrollbar-track]:bg-neutral-700
                  dark:[&::-webkit-scrollbar-thumb]:bg-neutral-500"
      >
        <div className="flex flex-col flex-grow">
          {chats.map((message: any, index: number) => {
            if (message.role === "assistant")
              return (
                <OperatorResponse key={"OperationRES" + index} {...message} />
              );
            else return <UserMessage key={"UserRES" + index} {...message} />;
          })}
        </div>
        {socketIds.map((socketId: any) => {
          const screenshot = screenshots[socketId];
          return (
            <div
              className="flex flex-col relative bg-white rounded-xl w-full self-center flex-shrink-0 h-auto mt-2 overflow-auto lg:hidden shadow-lg border-2 border-gray-300"
              key={`${socketId}_screenshot_side`}
              style={{
                scrollbarWidth: "none",
                msOverflowStyle: "none",
              }}
            >
              <img
                alt=""
                src={
                  screenshot
                    ? screenshot
                    : "/assets/images/screenshot/blank.webp"
                }
                className="w-full h-auto screenshot"
                style={{ objectFit: "cover", objectPosition: "top" }}
              />
              {!screenshot && (
                <div className="absolute w-full h-full flex flex-col justify-center items-center">
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
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex items-center px-1 mb-4">
        <div className="ps-4 pe-1 flex flex-grow bg-white rounded-full relative border border-gray-300">
          <input
            className="border-none outline-none flex-grow"
            placeholder="Type here ..."
            value={task}
            disabled={completed < socketIds.length}
            onChange={handleChangeTask}
            onKeyDown={handleKeyDown}
          ></input>
          <div
            className="hover:bg-gray-100 text-gray-700 rounded-full w-[35px] h-[35px] flex justify-center items-center transition-all duration-200 cursor-pointer"
            onClick={handleSubmit}
          >
            <FontAwesomeIcon icon={faPaperPlane} />
          </div>
        </div>
      </div>
      {dlgOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center bg-gray-900 bg-opacity-50"
          onClick={() => setDlgOpen(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-lg p-6 w-[360px]"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="w-full text-center text-xl font-semibold mb-2">
              Are you sure?
            </h2>
            <p className="w-full text-center mb-6">
              Do you want to start new task?
            </p>
            <div className="flex justify-center">
              <button
                className="bg-white hover:bg-gray-100 border border-primary text-gray-800 px-4 py-1 rounded-full w-24"
                onClick={() => setDlgOpen(false)}
              >
                No
              </button>
              <button
                className="bg-gradient-primary hover:opacity-90 text-white px-4 py-1 rounded-full w-24 ms-4"
                onClick={handleYes}
              >
                Yes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
