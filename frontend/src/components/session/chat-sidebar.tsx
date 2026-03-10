import React, { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import { useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPaperPlane } from "@fortawesome/free-solid-svg-icons";

import AgentResponse from "./agent-response";
import UserMessage from "./user-message";
import BrowserLoading from "./browser-loading";
import { addAction, addTask } from "../../redux/chatSlice";
import { setSessionId } from "../../redux/socketSlice";
import { initializeSocket } from "../../utils/socket";
import { checkBackendHealth } from "../../utils/health";
import { useToast } from "../common/toast";
import { CHAT_SIDEBAR_WIDTH } from "../../constants/layout";
import { AppDispatch } from "../../redux/store";

interface ChatSidebarProps {
  open: boolean;
  toggleSideBar: () => void;
}

export default function ChatSidebar(props: ChatSidebarProps) {
  const { open, toggleSideBar } = props;

  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const dispatch = useDispatch<AppDispatch>();
  const { id: sessionId } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const chats = useSelector((state: any) => state.chat.chats);
  const completed = useSelector((state: any) => state.chat.completed);
  const socket = useSelector((state: any) => state.socket.socket);
  const socketId = useSelector((state: any) => state.socket.socketId);
  const liveUrl = useSelector((state: any) => state.socket.liveUrl);
  const lastUrl = useSelector((state: any) => state.socket.lastUrl);
  const actionHistory = useSelector((state: any) => state.socket.actionHistory);
  const contextId = useSelector((state: any) => state.socket.contextId);
  const reduxSessionId = useSelector((state: any) => state.socket.sessionId);
  const user = useSelector((state: any) => state.user);

  const handleSubmit = async () => {
    if (!task.trim() || submitting) return;

    const taskWithInstructions = user.instructions
      ? `${task}\nADDITIONAL INFO: ${user.instructions}`
      : task;

    if (socket?.connected) {
      // Active socket — continue the task (no health check needed)
      dispatch(addTask(task));
      setTask("");
      dispatch(addAction({ action: "Continue", reasoning: "Continuing task...", previous_success: true }));
      socket.emit("continue-task", { task: taskWithInstructions });
    } else {
      // Need a new socket connection — check backend health first
      setSubmitting(true);
      const healthy = await checkBackendHealth();
      setSubmitting(false);

      if (!healthy) {
        showToast("Unable to reach the server. Please try again later.", "error");
        return;
      }

      dispatch(addTask(task));
      setTask("");

      if (sessionId && !reduxSessionId) {
        dispatch(setSessionId(sessionId));
      }

      const targetUrl = lastUrl || "https://duckduckgo.com";
      const newSocket = initializeSocket(dispatch, false, targetUrl);

      if (lastUrl) {
        // Resume session
        newSocket.emit("resume-task", {
          task: taskWithInstructions,
          lastUrl,
          actionHistory: actionHistory || [],
          context_id: contextId || "",
        });
      } else {
        // Start fresh
        newSocket.emit("start-task", {
          task: taskWithInstructions,
          initial_url: "https://duckduckgo.com",
          context_id: contextId || "",
        });
      }
    }
  };

  const handleChangeTask = (event: React.ChangeEvent<HTMLInputElement>) => {
    setTask(event.target.value);
  };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      handleSubmit();
    }
  };

  const isRunning = !!socketId && !completed;

  return (
    <>
      {/* Desktop: in-flow sidebar on the right */}
      <div
        className={`${open ? "hidden lg:flex" : "hidden"} flex-col flex-shrink-0 px-3 sm:px-4 md:px-5 z-10
          h-full pt-4 pb-1 overflow-hidden
          bg-white dark:bg-dark-bg border-l border-gray-100 dark:border-dark-border
          transition-all duration-300`}
        style={{ width: CHAT_SIDEBAR_WIDTH }}
      >
        {/* Chat messages area */}
        <div className="w-full px-1 flex flex-col flex-grow overflow-auto mb-4 scrollbar-thin">
          <div className="flex flex-col flex-grow">
            {chats.map((message: any, index: number) => {
              if (message.role === "assistant")
                return (
                  <AgentResponse key={"AgentRES" + index} {...message} />
                );
              else return <UserMessage key={"UserRES" + index} {...message} />;
            })}
          </div>
        </div>

        {/* Input area */}
        <div className="flex items-center px-1 mb-4">
          <div
            className="flex flex-grow items-center bg-gray-50 dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border
            focus-within:border-gray-300 dark:focus-within:border-gray-600 focus-within:shadow-soft transition-all duration-300 px-4 py-1"
          >
            <input
              className="border-none outline-none flex-grow bg-transparent text-gray-800 dark:text-gray-200 text-sm placeholder:text-gray-400"
              placeholder="Type here ..."
              value={task}
              disabled={isRunning || submitting}
              onChange={handleChangeTask}
              onKeyDown={handleKeyDown}
            />
            <button
              className={`flex items-center justify-center w-8 h-8 rounded-lg ml-2 transition-all duration-300
                ${
                  task
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
          h-full pt-4 pb-1 overflow-hidden
          bg-white dark:bg-dark-bg
          ${open ? "" : "hidden"}`}
      >
        {/* Chat messages + mobile browser preview */}
        <div className="w-full px-1 flex flex-col flex-grow overflow-auto mb-4 scrollbar-thin">
          <div className="flex flex-col flex-grow">
            {chats.map((message: any, index: number) => {
              if (message.role === "assistant")
                return (
                  <AgentResponse
                    key={"AgentRES_m" + index}
                    {...message}
                  />
                );
              else
                return <UserMessage key={"UserRES_m" + index} {...message} />;
            })}
          </div>

          {/* Mobile browser preview */}
          {socketId && (
            <div
              className="flex flex-col relative bg-white dark:bg-dark-surface rounded-2xl w-full self-center flex-shrink-0 mt-3 overflow-hidden shadow-soft border border-gray-200 dark:border-dark-border"
            >
              {liveUrl ? (
                <iframe
                  src={liveUrl}
                  title="Live browser session"
                  sandbox="allow-same-origin allow-scripts"
                  allow="clipboard-read; clipboard-write"
                  className="w-full border-0"
                  style={{ height: "400px", pointerEvents: "none" }}
                />
              ) : (
                <BrowserLoading minHeight="400px" />
              )}
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="flex items-center px-1 mb-4">
          <div
            className="flex flex-grow items-center bg-gray-50 dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border
            focus-within:border-gray-300 dark:focus-within:border-gray-600 focus-within:shadow-soft transition-all duration-300 px-4 py-1"
          >
            <input
              className="border-none outline-none flex-grow bg-transparent text-gray-800 dark:text-gray-200 text-sm placeholder:text-gray-400"
              placeholder="Type here ..."
              value={task}
              disabled={isRunning || submitting}
              onChange={handleChangeTask}
              onKeyDown={handleKeyDown}
            />
            <button
              className={`flex items-center justify-center w-8 h-8 rounded-lg ml-2 transition-all duration-300
                ${
                  task
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
    </>
  );
}
