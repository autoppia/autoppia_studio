import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import { resetChat, addTask } from "../redux/chatSlice";
import { resetSocket, setSessionInfo, setContextId, setOperatorInfo } from "../redux/socketSlice";
import { initializeSocket } from "../utils/socket";
import { checkBackendHealth } from "../utils/health";
import { useToast } from "../components/common/toast";
import { AppDispatch } from "../redux/store";

export default function useStartSession() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const { showToast } = useToast();

  return async (
    prompt: string,
    initialUrl: string,
    contextId = "",
    extraNavState?: Record<string, any>,
    basePath = "/session",
    operatorInfo?: { operatorId?: string; operatorName?: string },
  ) => {
    const healthy = await checkBackendHealth();
    if (!healthy) {
      showToast("Unable to reach the server. Please try again later.", "error");
      return;
    }

    dispatch(resetSocket());
    dispatch(resetChat());
    dispatch(addTask(prompt));

    const sessionId = uuidv4();
    dispatch(setSessionInfo({ sessionId, prompt, initialUrl }));
    if (contextId) dispatch(setContextId(contextId));
    if (operatorInfo?.operatorId) dispatch(setOperatorInfo(operatorInfo));

    const socket = initializeSocket(dispatch, false, initialUrl);
    const task = user.instructions
      ? `${prompt}\nADDITIONAL INFO: ${user.instructions}`
      : prompt;
    socket.emit("start-task", {
      task,
      initial_url: initialUrl,
      context_id: contextId,
      operator_id: operatorInfo?.operatorId || "",
    });

    navigate(`${basePath}/${sessionId}`, { state: { activeSessionId: sessionId, ...(extraNavState || {}) } });
  };
}
