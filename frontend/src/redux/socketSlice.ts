import { createSlice } from '@reduxjs/toolkit';
import type { RootState, AppDispatch } from './store';

export interface BrowserTab {
    id: string;
    url: string;
    title: string;
    favicon_url: string;
    debugger_fullscreen_url: string;
}

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
    tabs: BrowserTab[];
    activeTabIndex: number;
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
    tabs: [],
    activeTabIndex: 0,
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
            state.tabs = [];
            state.activeTabIndex = 0;
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
        setTabs: (state, action) => {
            state.tabs = action.payload;
        },
        setActiveTabIndex: (state, action) => {
            state.activeTabIndex = action.payload;
        },
        clearBrowserState: (state) => {
            state.socket = null;
            state.socketId = '';
            state.liveUrl = '';
            state.tabs = [];
            state.activeTabIndex = 0;
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

export const { clearSocketState, clearBrowserState, setSessionId, setSessionInfo, setSocket, setSocketId, setLiveUrl, setLastUrl, setActionHistory, setContextId, setTabs, setActiveTabIndex } = socketSlice.actions;
export default socketSlice.reducer;
