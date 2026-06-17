const SUPPORTED_BROWSER_MODES = new Set(["local", "headless", "local_headful", "headful", "headed", "browserbase", "auto"]);

export function getSessionBrowserMode(): string {
  const stored = localStorage.getItem("automataBrowserMode") || "";
  const normalized = stored.trim().toLowerCase();
  return SUPPORTED_BROWSER_MODES.has(normalized) ? normalized : "local";
}
