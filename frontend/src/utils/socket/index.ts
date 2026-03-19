import { io } from "socket.io-client";

import { setSocket, setSocketId, setLiveUrl, setLastUrl, setActionHistory, setTabs, setActiveTabIndex } from "../../redux/socketSlice";
import { addAction, addResult } from "../../redux/chatSlice";
import { AppDispatch } from "../../redux/store";

const apiUrl = process.env.REACT_APP_API_URL;

export const initializeSocket = (dispatch: AppDispatch, isRestore: boolean = false, initialUrl?: string) => {
  const socket = io(`${apiUrl}`, {
    timeout: 60000,
    reconnection: false,
  });

  socket.on("connect", () => {
    console.log("Connected to the agent:", socket.id);
    dispatch(setSocketId(socket.id));
    if (!isRestore) {
      dispatch(
        addAction({
          action: "Initialize",
          reasoning: "Initializing browser...",
          previous_success: true,
        })
      );
    }
  });

  socket.on("disconnect", (reason) => {
    console.log("Disconnected from the agent:", reason);
    dispatch(
      addResult({
        state: "disconnected",
      })
    );
  });

  socket.on("error", ({ message }) => {
    console.error("Socket error:", message);
    dispatch(
      addResult({
        content: message || "An error occurred",
        state: "error",
      })
    );
  });

  socket.on("live_url", ({ url }) => {
    dispatch(setLiveUrl(url));
  });

  socket.on("tabs", ({ tabs, activeIndex }) => {
    dispatch(setTabs(tabs));
    dispatch(setActiveTabIndex(activeIndex));
    if (tabs && tabs[activeIndex]) {
      dispatch(setLiveUrl(tabs[activeIndex].debugger_fullscreen_url));
    }
  });

  // Emitted before each action executes
  socket.on("action", ({ reasoning, action, previous_success }) => {
    dispatch(addAction({ action, reasoning, previous_success }));
  });

  socket.on("result", (result) => {
    dispatch(
      addResult({
        content: result.content,
        success: result.success,
        state: result.success ? "success" : "error",
        screenshots: result.screenshots || [],
      })
    );
    if (result.lastUrl) {
      dispatch(setLastUrl(result.lastUrl));
    }
    if (result.actionHistory) {
      dispatch(setActionHistory(result.actionHistory));
    }
  });

  dispatch(setSocket(socket));

  return socket;
};
