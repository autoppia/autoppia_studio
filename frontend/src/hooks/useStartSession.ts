import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import { resetChat, addTask } from "../redux/chatSlice";
import { resetSocket, setSessionId } from "../redux/socketSlice";
import { initializeSocket } from "../utils/socket";
import { AppDispatch } from "../redux/store";

const apiUrl = process.env.REACT_APP_API_URL;

export default function useStartSession() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);

  return async (prompt: string, initialUrl: string, provider = "autoppia", agentCount = 1) => {
    dispatch(resetSocket());
    dispatch(resetChat());
    dispatch(addTask(prompt));

    // Create session in backend to get a server-generated UUID
    // Fall back to client-side UUID if backend is unavailable
    let sessionId: string = uuidv4();
    try {
      const res = await fetch(`${apiUrl}/sessions/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          socketioPath: "",
          prompt,
          initialUrl,
          sessionPath: "",
        }),
      });
      const data = await res.json();
      if (data.session?.sessionId) {
        sessionId = data.session.sessionId;
      }
    } catch (err) {
      console.error("Failed to create session, using fallback ID:", err);
    }

    dispatch(setSessionId(sessionId));

    for (let i = 0; i < agentCount; i++) {
      const socket = initializeSocket(dispatch);
      const task = user.instructions
        ? `${prompt}\nADDITIONAL INFO: ${user.instructions}`
        : prompt;
      socket.emit("start-task", {
        task,
        initial_url: initialUrl,
        provider,
      });
    }

    navigate(`/session/${sessionId}`);
  };
}
