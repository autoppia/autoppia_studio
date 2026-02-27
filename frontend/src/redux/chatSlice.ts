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
    addAction: (state, action) => {
      const lastIndex = state.chats.length - 1;
      const lastChat = lastIndex >= 0 ? state.chats[lastIndex] : null;

      if (lastChat && lastChat.role === "assistant" && lastChat.state === "thinking") {
        const actionLength = lastChat.actions?.length || 0;
        if (actionLength > 0 && lastChat.actions![actionLength - 1] === action.payload.action) {
          return;
        }

        state.chats[lastIndex] = {
          ...lastChat,
          thinking: action.payload.action,
          actions: [...lastChat.actions!, action.payload.action],
          actionResults: [
            ...lastChat.actionResults!,
            action.payload.previous_success,
          ],
          screenshots: [
            ...(lastChat.screenshots || []),
            ...(action.payload.screenshot ? [action.payload.screenshot] : []),
          ],
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            thinking: action.payload.action,
            state: "thinking",
            actions: [action.payload.action],
            actionResults: [],
            screenshots: action.payload.screenshot ? [action.payload.screenshot] : [],
          },
        ];
      }
    },
    addResult: (state, action) => {
      const lastIndex = state.chats.length - 1;
      const lastChat = lastIndex >= 0 ? state.chats[lastIndex] : null;

      if (lastChat && lastChat.role === "assistant" && lastChat.state === "thinking") {
        state.chats[lastIndex] = {
          ...lastChat,
          content: action.payload.content,
          state: action.payload.state,
          actionResults: [
            ...lastChat.actionResults!,
            action.payload.success,
          ],
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            content: action.payload.content,
            state: action.payload.state,
            actionResults: [
              action.payload.success,
            ],
          },
        ];
      }
      state.completed = true;
    }
  },
});

export const { resetChat, setChats, addTask, addAction, addResult } = chatSlice.actions;
export default chatSlice.reducer;
