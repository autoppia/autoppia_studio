import Cookies from "js-cookie";

const apiUrl = process.env.REACT_APP_API_URL;

export interface WalletData {
  balance: string;
  currency: string;
  updated_at: string | null;
}

export interface TransactionData {
  id: string;
  type: string;
  amount: string;
  currency: string;
  status: string;
  provider: string;
  provider_payment_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface TransactionList {
  transactions: TransactionData[];
  total: number;
  page: number;
  limit: number;
}

export interface TopUpResult {
  mode: "stripe" | "mock";
  transaction_id?: string;
  // Stripe-specific
  client_secret?: string;
  payment_intent_id?: string;
  publishable_key?: string;
  // Mock — already completed
  status?: string;
  balance?: string;
}

function authHeaders(): Record<string, string> {
  const token = Cookies.get("access_token");
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

export async function fetchWallet(): Promise<WalletData> {
  const res = await fetch(`${apiUrl}/wallet`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch wallet: ${res.status}`);
  return res.json();
}

export async function fetchTransactions(
  page = 1,
  limit = 20
): Promise<TransactionList> {
  const res = await fetch(
    `${apiUrl}/wallet/transactions?page=${page}&limit=${limit}`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error(`Failed to fetch transactions: ${res.status}`);
  return res.json();
}

export async function createTopUp(amount: number): Promise<TopUpResult> {
  const res = await fetch(`${apiUrl}/wallet/topup`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ amount }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail ?? `Top-up failed: ${res.status}`);
  }
  return res.json();
}
