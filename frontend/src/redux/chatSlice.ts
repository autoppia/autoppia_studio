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
        state.chats[lastIndex] = {
          ...state.chats[lastIndex],
          thinking: action.payload.action,
          actions: [...state.chats[lastIndex].actions!, action.payload.action],
          actionResults: [
            ...state.chats[lastIndex].actionResults!,
            action.payload.previous_success,
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
              ...state.chats[lastIndex].actionResults!,
              action.payload.success,
            ],
          },
        ];
        state.completed += 1;
      }
    }
  },
});

export const { resetChat, addTask, addAction, addResult } = chatSlice.actions;
export default chatSlice.reducer;
