/**
 * Build a user-facing message from a failed API Response.
 *
 * The backend now fails closed: invalid/expired JWTs return 401 (handled
 * globally by the auth-fetch wrapper, which signs the user out) and path-only
 * mutations on resources the caller doesn't own return 403. This gives both
 * cases clear copy instead of a raw status or empty body, while still
 * preferring an explicit `detail`/`message` from the server when present.
 */
export async function apiErrorMessage(res: Response, fallback: string, subject = "this resource"): Promise<string> {
  const text = await res.text().catch(() => "");
  const authFallback = res.status === 403
    ? `You don't have access to ${subject}. It may belong to another account.`
    : res.status === 401
      ? "Your session expired. Please sign in again."
      : fallback;
  if (!text) return authFallback;
  try {
    const data = JSON.parse(text);
    return data?.detail || data?.message || authFallback;
  } catch {
    return text.slice(0, 180);
  }
}
