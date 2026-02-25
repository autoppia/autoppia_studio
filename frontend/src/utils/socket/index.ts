import { io } from "socket.io-client";

import { addSocket, addSocketId, setLiveUrl, setLastUrl, setActionHistory } from "../../redux/socketSlice";
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
    dispatch(addSocketId(socket.id));
    if (!isRestore) {
      dispatch(
        addAction({
          socketId: socket.id,
          action: "Initializing browser...",
        })
      );
    }
  });

  socket.on("disconnect", (reason) => {
    console.log("Disconnected from the agent:", reason);
    dispatch(
      addResult({
        socketId: socket.id,
        state: "disconnected",
      })
    );
  });

  socket.on("error", ({ error }) => {
    console.error("Socket error:", error);
  });

  socket.on("live_url", ({ url }) => {
    dispatch(
      setLiveUrl({
        socketId: socket.id,
        url,
      })
    );
  });

  socket.on("action", (action) => {
    dispatch(addAction({ socketId: socket.id, ...action }));
  });

  socket.on("result", (result) => {
    dispatch(
      addResult({
        socketId: socket.id,
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

  dispatch(addSocket(socket));

  return socket;
};
