import { createSlice } from "@reduxjs/toolkit";

interface UserState {
    isAuthenticated: boolean;
    email: string;
    instructions: string;
}

const initialState: UserState = {
    isAuthenticated: false,
    email: "",
    instructions: ""
}

const userSlice = createSlice({
    name: "user",
    initialState,
    reducers: {
        setUser: (state, action) => {
            state.isAuthenticated = true;
            state.email = action.payload.email;
            state.instructions = action.payload.instructions;
        },
        logout: (state) => {
            state.isAuthenticated = false;
            state.email = "";
            state.instructions = "";
        }
    }
})

export const { setUser, logout } = userSlice.actions;
export default userSlice.reducer;

