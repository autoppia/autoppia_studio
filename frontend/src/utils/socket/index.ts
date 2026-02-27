import { io } from "socket.io-client";

import { setSocket, setSocketId, setLiveUrl, setLastUrl, setActionHistory } from "../../redux/socketSlice";
import { addAction, addResult } from "../../redux/chatSlice";
import { AppDispatch } from "../../redux/store";

const apiUrl = process.env.REACT_APP_API_URL;

export const initializeSocket = (dispatch: AppDispatch, isRestore: boolean = false) => {
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
          action: "Initializing browser...",
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

  socket.on("error", ({ error }) => {
    console.error("Socket error:", error);
  });

  socket.on("live_url", ({ url }) => {
    dispatch(setLiveUrl(url));
  });

  socket.on("action", (action) => {
    dispatch(addAction(action));
  });

  socket.on("result", (result) => {
    dispatch(
      addResult({
        content: result.content,
        success: result.success,
        state: result.success ? "success" : "error",
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
