import React, { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faEdit,
  faPaperPlane,
} from "@fortawesome/free-solid-svg-icons";

import IconButton from "../common/icon-button";
import OperatorResponse from "./operator-response";
import UserMessage from "./user-message";
import BrowserLoading from "./browser-loading";
import { addAction, addTask } from "../../redux/chatSlice";
import { setSessionId } from "../../redux/socketSlice";
import { initializeSocket } from "../../utils/socket";
import { CHAT_SIDEBAR_WIDTH } from "../../constants/layout";
import { AppDispatch } from "../../redux/store";

interface ChatSidebarProps {
  open: boolean;
  toggleSideBar: () => void;
}

export default function ChatSidebar(props: ChatSidebarProps) {
  const { open, toggleSideBar } = props;

  const [task, setTask] = useState("");
  const [dlgOpen, setDlgOpen] = useState(false);

  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { id: sessionId } = useParams<{ id: string }>();
  const chats = useSelector((state: any) => state.chat.chats);
  const completed = useSelector((state: any) => state.chat.completed);
  const sockets = useSelector((state: any) => state.socket.sockets);
  const socketIds = useSelector((state: any) => state.socket.socketIds);
  const liveUrls = useSelector((state: any) => state.socket.liveUrls);
  const lastUrl = useSelector((state: any) => state.socket.lastUrl);
  const actionHistory = useSelector((state: any) => state.socket.actionHistory);
  const reduxSessionId = useSelector((state: any) => state.socket.sessionId);
  const user = useSelector((state: any) => state.user);

  const handleSubmit = () => {
    if (!task.trim()) return;

    const hasConnectedSocket = sockets.some((s: any) => s.connected);

    if (hasConnectedSocket) {
      // Normal continue-task flow (within same browser session)
      dispatch(addTask(task));
      setTask("");
      const taskWithInstructions = user.instructions
        ? `${task}\nADDITIONAL INFO: ${user.instructions}`
        : task;
      sockets.forEach((socket: any) => {
        if (socket.connected) {
          dispatch(
            addAction({
              socketId: socket.id,
              action: "Continuing task...",
            })
          );
          socket.emit("continue-task", { task: taskWithInstructions });
        }
      });
    } else if (lastUrl) {
      // Resume flow: no active sockets, but we have a lastUrl from a saved session
      dispatch(addTask(task));
      setTask("");

      if (sessionId && !reduxSessionId) {
        dispatch(setSessionId(sessionId));
      }

      const socket = initializeSocket(dispatch);
      const taskWithInstructions = user.instructions
        ? `${task}\nADDITIONAL INFO: ${user.instructions}`
        : task;
      socket.emit("resume-task", {
        task: taskWithInstructions,
        lastUrl,
        actionHistory: actionHistory || [],
        provider: "autoppia",
      });
    } else {
      // Fallback: old session with no lastUrl — treat as start-task
      dispatch(addTask(task));
      setTask("");

      if (sessionId && !reduxSessionId) {
        dispatch(setSessionId(sessionId));
      }

      const socket = initializeSocket(dispatch);
      const taskWithInstructions = user.instructions
        ? `${task}\nADDITIONAL INFO: ${user.instructions}`
        : task;
      socket.emit("start-task", {
        task: taskWithInstructions,
        initial_url: "https://duckduckgo.com",
        provider: "autoppia",
      });
    }
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
    sockets.forEach((socket: any) => {
      socket.disconnect();
    });
    navigate("/");
  };

  return (
    <>
      {/* Desktop: in-flow sidebar on the left */}
      <div
        className={`${open ? "hidden lg:flex" : "hidden"} flex-col flex-shrink-0 px-3 sm:px-5 md:px-8 z-10
          h-full pt-1 pb-1 overflow-hidden
          bg-white dark:bg-dark-bg border-r border-gray-100 dark:border-dark-border
          transition-all duration-300`}
        style={{ width: CHAT_SIDEBAR_WIDTH }}
      >
        {/* Header */}
        <div className="flex items-center py-4 gap-2">
          <IconButton
            icon={faBars}
            onClick={toggleSideBar}
            className="dark:text-white dark:border-dark-border"
          />
          <div className="flex-grow ms-2">
            <img
              src="/assets/images/logos/main_dark.webp"
              alt="Autoppia"
              className="h-[18px] dark:block hidden"
            />
            <img
              src="/assets/images/logos/main.webp"
              alt="Autoppia"
              className="h-[18px] dark:hidden block"
            />
          </div>
          <IconButton
            icon={faEdit}
            onClick={handleNew}
            className="dark:text-white dark:border-dark-border"
          />
        </div>

        {/* Chat messages area */}
        <div className="w-full px-1 flex flex-col mt-2 flex-grow overflow-auto mb-4 scrollbar-thin">
          <div className="flex flex-col flex-grow">
            {chats.map((message: any, index: number) => {
              if (message.role === "assistant")
                return (
                  <OperatorResponse key={"OperationRES" + index} {...message} />
                );
              else return <UserMessage key={"UserRES" + index} {...message} />;
            })}
          </div>
        </div>

        {/* Input area */}
        <div className="flex items-center px-1 mb-4">
          <div className="flex flex-grow items-center bg-gray-50 dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border
            focus-within:border-gray-300 dark:focus-within:border-gray-600 focus-within:shadow-soft transition-all duration-300 px-4 py-1">
            <input
              className="border-none outline-none flex-grow bg-transparent text-gray-800 dark:text-gray-200 text-sm placeholder:text-gray-400"
              placeholder="Type here ..."
              value={task}
              disabled={completed < socketIds.length}
              onChange={handleChangeTask}
              onKeyDown={handleKeyDown}
            />
            <button
              className={`flex items-center justify-center w-8 h-8 rounded-lg ml-2 transition-all duration-300
                ${task
                  ? "text-white bg-gradient-primary shadow-glow hover:shadow-glow-lg"
                  : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
              onClick={handleSubmit}
            >
              <FontAwesomeIcon icon={faPaperPlane} className="text-sm" />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile: full-width overlay */}
      <div
        className={`lg:hidden fixed inset-0 z-10 flex flex-col px-3 sm:px-5 md:px-8
          h-full pt-1 pb-1 overflow-hidden
          bg-white dark:bg-dark-bg
          ${open ? "" : "hidden"}`}
      >
        {/* Header */}
        <div className="flex items-center py-4 gap-2">
          <IconButton
            icon={faBars}
            onClick={toggleSideBar}
            className="dark:text-white dark:border-dark-border"
          />
          <div className="flex-grow ms-2">
            <img
              src="/assets/images/logos/main_dark.webp"
              alt="Autoppia"
              className="h-[18px] dark:block hidden"
            />
            <img
              src="/assets/images/logos/main.webp"
              alt="Autoppia"
              className="h-[18px] dark:hidden block"
            />
          </div>
          <IconButton
            icon={faEdit}
            onClick={handleNew}
            className="dark:text-white dark:border-dark-border"
          />
        </div>

        {/* Chat messages + mobile browser previews */}
        <div className="w-full px-1 flex flex-col mt-2 flex-grow overflow-auto mb-4 scrollbar-thin">
          <div className="flex flex-col flex-grow">
            {chats.map((message: any, index: number) => {
              if (message.role === "assistant")
                return (
                  <OperatorResponse key={"OperationRES_m" + index} {...message} />
                );
              else return <UserMessage key={"UserRES_m" + index} {...message} />;
            })}
          </div>

          {/* Mobile browser previews */}
          {socketIds.map((socketId: any) => {
            const liveUrl = liveUrls[socketId];
            return (
              <div
                className="flex flex-col relative bg-white dark:bg-dark-surface rounded-2xl w-full self-center flex-shrink-0 mt-3 overflow-hidden shadow-soft border border-gray-200 dark:border-dark-border"
                key={`${socketId}_live_side`}
              >
                {liveUrl ? (
                  <iframe
                    src={liveUrl}
                    title={`Live browser session`}
                    sandbox="allow-same-origin allow-scripts"
                    allow="clipboard-read; clipboard-write"
                    className="w-full border-0"
                    style={{ height: "400px", pointerEvents: "none" }}
                  />
                ) : (
                  <BrowserLoading minHeight="400px" />
                )}
              </div>
            );
          })}
        </div>

        {/* Input area */}
        <div className="flex items-center px-1 mb-4">
          <div className="flex flex-grow items-center bg-gray-50 dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border
            focus-within:border-gray-300 dark:focus-within:border-gray-600 focus-within:shadow-soft transition-all duration-300 px-4 py-1">
            <input
              className="border-none outline-none flex-grow bg-transparent text-gray-800 dark:text-gray-200 text-sm placeholder:text-gray-400"
              placeholder="Type here ..."
              value={task}
              disabled={completed < socketIds.length}
              onChange={handleChangeTask}
              onKeyDown={handleKeyDown}
            />
            <button
              className={`flex items-center justify-center w-8 h-8 rounded-lg ml-2 transition-all duration-300
                ${task
                  ? "text-white bg-gradient-primary shadow-glow hover:shadow-glow-lg"
                  : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
              onClick={handleSubmit}
            >
              <FontAwesomeIcon icon={faPaperPlane} className="text-sm" />
            </button>
          </div>
        </div>
      </div>

      {/* Confirmation dialog */}
      {dlgOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center bg-black/50 backdrop-blur-sm z-50"
          onClick={() => setDlgOpen(false)}
        >
          <div
            className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft-lg p-8 w-[380px] border border-gray-100 dark:border-dark-border animate-slide-up"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="w-full text-center text-xl font-bold text-gray-800 dark:text-white mb-2">
              Are you sure?
            </h2>
            <p className="w-full text-center text-gray-500 dark:text-gray-400 mb-8">
              Do you want to start a new session?
            </p>
            <div className="flex justify-center gap-3">
              <button
                className="bg-white dark:bg-dark-bg hover:bg-gray-50 dark:hover:bg-dark-surface border border-gray-200 dark:border-dark-border
                  text-gray-700 dark:text-gray-300 px-6 py-2 rounded-xl font-medium transition-all duration-300"
                onClick={() => setDlgOpen(false)}
              >
                Cancel
              </button>
              <button
                className="bg-gradient-primary hover:shadow-glow text-white px-6 py-2 rounded-xl font-medium transition-all duration-300"
                onClick={handleYes}
              >
                Yes, start new
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
