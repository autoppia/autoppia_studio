import Cookies from "js-cookie";

let installed = false;

function sameApi(url: string, apiUrl: string): boolean {
  const normalized = apiUrl.replace(/\/$/, "");
  return url.startsWith(normalized) || url.startsWith("/");
}

function withAuthHeaders(headers: HeadersInit | undefined): Headers {
  const next = new Headers(headers || {});
  const token = Cookies.get("access_token");
  if (token && !next.has("Authorization")) {
    next.set("Authorization", `Bearer ${token}`);
  }
  return next;
}

/**
 * The backend now fails closed for invalid/expired JWTs. When a request that
 * carried our token comes back 401, the session is no longer valid — clear it
 * once and let the app redirect to sign-in. Login/signup carry no token, so a
 * wrong-password 401 never trips this. Coalesced so a burst of parallel 401s
 * only produces a single logout, while still allowing a fresh session to expire
 * again later.
 */
let expiryBroadcast = false;
function handleAuthExpiry(): void {
  if (expiryBroadcast || !Cookies.get("access_token")) return;
  expiryBroadcast = true;
  Cookies.remove("access_token");
  try {
    sessionStorage.setItem("automata_session_expired", "1");
  } catch {
    /* ignore storage errors */
  }
  window.dispatchEvent(new Event("automata-auth-expired"));
  window.setTimeout(() => {
    expiryBroadcast = false;
  }, 1000);
}

export function installAuthFetch(apiUrl: string): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (!sameApi(url, apiUrl)) {
      return originalFetch(input, init);
    }

    // Capture before the call so we know whether *we* presented a token.
    const sentToken = Boolean(Cookies.get("access_token"));

    let response: Response;
    if (input instanceof Request) {
      const headers = withAuthHeaders(init?.headers || input.headers);
      response = await originalFetch(input, { ...init, headers });
    } else {
      response = await originalFetch(input, { ...init, headers: withAuthHeaders(init?.headers) });
    }

    // Only treat as a session expiry when we presented a token and it was rejected.
    if (response.status === 401 && sentToken) {
      handleAuthExpiry();
    }
    return response;
  };
}
