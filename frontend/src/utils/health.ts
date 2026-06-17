const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

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
