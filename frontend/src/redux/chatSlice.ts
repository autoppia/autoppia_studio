import { createSlice } from "@reduxjs/toolkit";
import { ChatItem } from "../utils/types";

interface ChatState {
  chats: ChatItem[];
  completed: boolean;
}

const initialState: ChatState = {
  chats: [],
  completed: false,
};

const chatSlice = createSlice({
  name: "chat",
  initialState,
  reducers: {
    resetChat: (state) => {
      state.chats = [];
      state.completed = false;
    },
    setChats: (state, action) => {
      state.chats = action.payload;
      state.completed = action.payload.some(
        (c: ChatItem) => c.state === "success" || c.state === "error" || c.state === "disconnected"
      );
    },
    addTask: (state, action) => {
      state.chats = [
        ...state.chats,
        {
          role: "user",
          content: action.payload,
        },
      ];
      state.completed = false;
    },
    // Called before each action executes — adds action with reasoning to the chat
    addAction: (state, action) => {
      const { action: actionName, reasoning, previous_success, skill } = action.payload;
      const lastIndex = state.chats.length - 1;
      const lastChat = lastIndex >= 0 ? state.chats[lastIndex] : null;

      if (lastChat && lastChat.role === "assistant" && lastChat.state === "thinking") {
        // Mark the previous action's result based on previous_success
        const prevResults = [...(lastChat.actionResults || [])];
        if (prevResults.length > 0 && prevResults[prevResults.length - 1] === undefined) {
          prevResults[prevResults.length - 1] = previous_success !== false;
        }

        state.chats[lastIndex] = {
          ...lastChat,
          thinking: reasoning || actionName || lastChat.thinking,
          reasoning: reasoning || lastChat.reasoning,
          actions: [...(lastChat.actions || []), actionName],
          actionMetadata: [...(lastChat.actionMetadata || []), skill ? { skill } : undefined],
          actionResults: [...prevResults, undefined], // current action is pending
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            thinking: reasoning || actionName || "Thinking...",
            state: "thinking",
            actions: [actionName],
            actionMetadata: [skill ? { skill } : undefined],
            actionResults: [undefined], // pending
            screenshots: [],
            artifacts: [],
            reasoning: reasoning || undefined,
          },
        ];
      }
    },
    addResult: (state, action) => {
      const lastIndex = state.chats.length - 1;
      const lastChat = lastIndex >= 0 ? state.chats[lastIndex] : null;

      if (lastChat && lastChat.role === "assistant" && lastChat.state === "thinking") {
        // Mark the last pending action as done
        const prevResults = [...(lastChat.actionResults || [])];
        if (prevResults.length > 0 && prevResults[prevResults.length - 1] === undefined) {
          prevResults[prevResults.length - 1] = action.payload.state === "success";
        }

        state.chats[lastIndex] = {
          ...lastChat,
          content: action.payload.content,
          state: action.payload.state,
          actionResults: prevResults,
          screenshots: action.payload.screenshots || lastChat.screenshots || [],
          artifacts: action.payload.artifacts || lastChat.artifacts || [],
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            content: action.payload.content,
            state: action.payload.state,
            screenshots: action.payload.screenshots || [],
            artifacts: action.payload.artifacts || [],
          },
        ];
      }
      state.completed = true;
    },
    addScreenshot: (state, action) => {
      const screenshot = action.payload;
      if (!screenshot) return;
      const lastIndex = state.chats.length - 1;
      const lastChat = lastIndex >= 0 ? state.chats[lastIndex] : null;
      if (lastChat && lastChat.role === "assistant") {
        state.chats[lastIndex] = {
          ...lastChat,
          screenshots: [...(lastChat.screenshots || []), screenshot],
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            state: "thinking",
            screenshots: [screenshot],
          },
        ];
      }
    }
  },
});

export const { resetChat, setChats, addTask, addAction, addResult, addScreenshot } = chatSlice.actions;
export default chatSlice.reducer;
