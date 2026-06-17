const LOCAL_API_URL = "http://127.0.0.1:8080";

export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    const { hostname, protocol } = window.location;
    if (["localhost", "127.0.0.1", "0.0.0.0"].includes(hostname)) {
      return LOCAL_API_URL;
    }
    return process.env.REACT_APP_API_URL || `${protocol}//${hostname}:8080`;
  }
  return process.env.REACT_APP_API_URL || LOCAL_API_URL;
}
