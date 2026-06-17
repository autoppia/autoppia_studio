import { createSlice } from "@reduxjs/toolkit";
import Cookies from "js-cookie";

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
            Cookies.remove("access_token");
            localStorage.removeItem("automata_company_id");
            localStorage.removeItem("automata_onboarding_company_id");
            localStorage.removeItem("automata_work_board_id");
            localStorage.removeItem("automata_last_email");
            state.isAuthenticated = false;
            state.email = "";
            state.instructions = "";
        }
    }
})

export const { setUser, logout } = userSlice.actions;
export default userSlice.reducer;
