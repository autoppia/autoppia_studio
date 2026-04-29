import { configureStore } from "@reduxjs/toolkit";
import socketReducer from "./socketSlice";
import chatReducer from "./chatSlice";
import userReducer from "./userSlice";
import walletReducer from "./walletSlice";

const store = configureStore({
  reducer: {
    socket: socketReducer,
    chat: chatReducer,
    user: userReducer,
    wallet: walletReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: false,
    }),
  devTools: process.env.NODE_ENV !== "production",
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
