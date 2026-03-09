import { createSlice } from '@reduxjs/toolkit';
import type { RootState, AppDispatch } from './store';

interface SocketState {
    sessionId: string;
    prompt: string;
    initialUrl: string;
    socket: any;
    socketId: string;
    liveUrl: string;
    lastUrl: string;
    actionHistory: any[];
    contextId: string;
    provider: string;
}

const initialState: SocketState = {
    sessionId: '',
    prompt: '',
    initialUrl: '',
    socket: null,
    socketId: '',
    liveUrl: '',
    lastUrl: '',
    actionHistory: [],
    contextId: '',
    provider: 'autoppia',
};

const socketSlice = createSlice({
    name: 'socket',
    initialState,
    reducers: {
        clearSocketState: (state) => {
            state.sessionId = '';
            state.prompt = '';
            state.initialUrl = '';
            state.socket = null;
            state.socketId = '';
            state.liveUrl = '';
            state.lastUrl = '';
            state.actionHistory = [];
            state.contextId = '';
            state.provider = 'autoppia';
        },
        setSessionId: (state, action) => {
            state.sessionId = action.payload;
        },
        setSessionInfo: (state, action) => {
            state.sessionId = action.payload.sessionId;
            state.prompt = action.payload.prompt;
            state.initialUrl = action.payload.initialUrl;
        },
        setSocket: (state, action) => {
            state.socket = action.payload;
        },
        setSocketId: (state, action) => {
            state.socketId = action.payload;
        },
        setLiveUrl: (state, action) => {
            state.liveUrl = action.payload;
        },
        setLastUrl: (state, action) => {
            state.lastUrl = action.payload;
        },
        setActionHistory: (state, action) => {
            state.actionHistory = action.payload;
        },
        setContextId: (state, action) => {
            state.contextId = action.payload;
        },
        setProvider: (state, action) => {
            state.provider = action.payload;
        },
        clearBrowserState: (state) => {
            // Clear socket/liveUrl but preserve lastUrl, actionHistory, sessionId, prompt, initialUrl
            // so the resume flow still works after idle disconnect
            state.socket = null;
            state.socketId = '';
            state.liveUrl = '';
        },
    },
});

// Thunk: disconnect socket outside the reducer, then clear state
export const resetSocket = () => (dispatch: AppDispatch, getState: () => RootState) => {
    const { socket } = getState();
    if (socket.socket) {
        socket.socket.removeAllListeners();
        socket.socket.disconnect();
    }
    dispatch(clearSocketState());
};

// Thunk: disconnect browser but preserve lastUrl/actionHistory for resume
export const disconnectBrowser = () => (dispatch: AppDispatch, getState: () => RootState) => {
    const { socket } = getState();
    if (socket.socket) {
        socket.socket.removeAllListeners();
        socket.socket.disconnect();
    }
    dispatch(clearBrowserState());
};

export const { clearSocketState, clearBrowserState, setSessionId, setSessionInfo, setSocket, setSocketId, setLiveUrl, setLastUrl, setActionHistory, setContextId, setProvider } = socketSlice.actions;
export default socketSlice.reducer;
