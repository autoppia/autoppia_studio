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
        }
    }
})

export const { setUser } = userSlice.actions;
export default userSlice.reducer;

