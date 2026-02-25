import { createSlice } from "@reduxjs/toolkit";
import { ChatItem } from "../utils/types";

interface ChatState {
  chats: ChatItem[];
  completed: number;
}

const initialState: ChatState = {
  chats: [],
  completed: 0,
};

const chatSlice = createSlice({
  name: "chat",
  initialState,
  reducers: {
    resetChat: (state) => {
      state.chats = [];
      state.completed = 0;
    },
    setChats: (state, action) => {
      state.chats = action.payload;
      state.completed = action.payload.filter(
        (c: ChatItem) => c.state === "success" || c.state === "error" || c.state === "disconnected"
      ).length;
    },
    addTask: (state, action) => {
      state.chats = [
        ...state.chats,
        {
          role: "user",
          content: action.payload,
        },
      ];
      state.completed = 0;
    },
    addAction: (state, action) => {
      const indexes: number[] = [];
      state.chats.forEach((chat, index) => {
        if (chat.socketId === action.payload.socketId) {
          indexes.push(index);
        }
      });
      const lastIndex = indexes.length > 0 ? indexes[indexes.length - 1] : -1;
      if (lastIndex >= 0 && state.chats[lastIndex].state === "thinking") {
        const actionLength = state.chats[lastIndex].actions?.length || 0;
        if (actionLength > 0 && state.chats[lastIndex].actions![actionLength - 1] === action.payload.action) {
          return;
        }

        state.chats[lastIndex] = {
          ...state.chats[lastIndex],
          thinking: action.payload.action,
          actions: [...state.chats[lastIndex].actions!, action.payload.action],
          actionResults: [
            ...state.chats[lastIndex].actionResults!,
            action.payload.previous_success,
          ],
          screenshots: [
            ...(state.chats[lastIndex].screenshots || []),
            ...(action.payload.screenshot ? [action.payload.screenshot] : []),
          ],
        };
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            socketId: action.payload.socketId,
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
      const indexes: number[] = [];
      state.chats.forEach((chat, index) => {
        if (chat.socketId === action.payload.socketId) {
          indexes.push(index);
        }
      });
      const lastIndex = indexes.length > 0 ? indexes[indexes.length - 1] : -1;
      if (lastIndex >= 0 && state.chats[lastIndex].state === "thinking") {
        state.chats[lastIndex] = {
          ...state.chats[lastIndex],
          content: action.payload.content,
          state: action.payload.state,
          actionResults: [
            ...state.chats[lastIndex].actionResults!,
            action.payload.success,
          ],
        };
        state.completed += 1;
      } else {
        state.chats = [
          ...state.chats,
          {
            role: "assistant",
            socketId: action.payload.socketId,
            content: action.payload.content,
            state: action.payload.state,
            actionResults: [
              action.payload.success,
            ],
          },
        ];
        state.completed += 1;
      }
    }
  },
});

export const { resetChat, setChats, addTask, addAction, addResult } = chatSlice.actions;
export default chatSlice.reducer;
