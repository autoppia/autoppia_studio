import { getApiUrl } from "./api-url";

const apiUrl = getApiUrl();

/**
 * Check if the backend is reachable.
 * Returns true if healthy, false otherwise.
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}
