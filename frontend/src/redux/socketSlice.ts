import { createSlice } from '@reduxjs/toolkit';
import type { RootState, AppDispatch } from './store';

interface SocketState {
    sessionId: string;
    sockets: any[];
    socketIds: string[];
    liveUrls: {
        [key: string]: string | undefined;
    };
    lastUrl: string;
    actionHistory: any[];
}

const initialState: SocketState = {
    sessionId: '',
    sockets: [],
    socketIds: [],
    liveUrls: {},
    lastUrl: '',
    actionHistory: [],
};

const socketSlice = createSlice({
    name: 'socket',
    initialState,
    reducers: {
        clearSocketState: (state) => {
            state.sessionId = '';
            state.sockets = [];
            state.socketIds = [];
            state.liveUrls = {};
            state.lastUrl = '';
            state.actionHistory = [];
        },
        setSessionId: (state, action) => {
            state.sessionId = action.payload;
        },
        addSocket: (state, action) => {
            state.sockets = [...state.sockets, action.payload];
        },
        addSocketId: (state, action) => {
            state.socketIds = [...state.socketIds, action.payload];
        },
        setLiveUrl: (state, action) => {
            state.liveUrls = {
                ...state.liveUrls,
                [action.payload.socketId]: action.payload.url
            };
        },
        setLastUrl: (state, action) => {
            state.lastUrl = action.payload;
        },
        setActionHistory: (state, action) => {
            state.actionHistory = action.payload;
        },
        clearBrowserState: (state) => {
            // Clear sockets/liveUrls but preserve lastUrl, actionHistory, sessionId
            // so the resume flow still works after idle disconnect
            state.sockets = [];
            state.socketIds = [];
            state.liveUrls = {};
        },
    },
});

// Thunk: disconnect sockets outside the reducer, then clear state
export const resetSocket = () => (dispatch: AppDispatch, getState: () => RootState) => {
    const { socket } = getState();
    socket.sockets.forEach((s: any) => {
        s.removeAllListeners();
        s.disconnect();
    });
    dispatch(clearSocketState());
};

// Thunk: disconnect browser but preserve lastUrl/actionHistory for resume
export const disconnectBrowser = () => (dispatch: AppDispatch, getState: () => RootState) => {
    const { socket } = getState();
    socket.sockets.forEach((s: any) => {
        s.removeAllListeners();
        s.disconnect();
    });
    dispatch(clearBrowserState());
};

export const { clearSocketState, clearBrowserState, setSessionId, addSocket, addSocketId, setLiveUrl, setLastUrl, setActionHistory } = socketSlice.actions;
export default socketSlice.reducer;
