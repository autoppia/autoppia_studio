import { createSlice } from '@reduxjs/toolkit';

interface SocketState {
    sockets: any[];
    socketIds: string[];
    screenshots: {
        [key: string]: string | undefined;
    };
}

const initialState: SocketState = {
    sockets: [],
    socketIds: [],
    screenshots: {},
};

const socketSlice = createSlice({
    name: 'socket',
    initialState,
    reducers: {
        resetSocket: (state) => {
            state.sockets.forEach((socket) => {
                socket.close();
            });
            state.sockets = [];
            state.socketIds = [];
        },
        addSocket: (state, action) => {
            state.sockets = [...state.sockets, action.payload];
        },
        addSocketId: (state, action) => {
            state.socketIds = [...state.socketIds, action.payload];
        },
        setScreenshot: (state, action) => {
            state.screenshots = {
                ...state.screenshots,
                [action.payload.socketId]: action.payload.screenshot
            };
        }
    },
});

export const { resetSocket, addSocket, addSocketId, setScreenshot } = socketSlice.actions;
export default socketSlice.reducer;