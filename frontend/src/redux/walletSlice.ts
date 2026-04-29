import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface WalletState {
  balance: string;
  currency: string;
  loading: boolean;
  lastUpdated: string | null;
}

const initialState: WalletState = {
  balance: "0.00",
  currency: "EUR",
  loading: false,
  lastUpdated: null,
};

const walletSlice = createSlice({
  name: "wallet",
  initialState,
  reducers: {
    setWallet: (
      state,
      action: PayloadAction<{ balance: string; currency: string; updated_at?: string | null }>
    ) => {
      state.balance = action.payload.balance;
      state.currency = action.payload.currency;
      state.lastUpdated = action.payload.updated_at ?? null;
      state.loading = false;
    },
    setWalletLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    resetWallet: () => initialState,
  },
});

export const { setWallet, setWalletLoading, resetWallet } = walletSlice.actions;
export default walletSlice.reducer;
