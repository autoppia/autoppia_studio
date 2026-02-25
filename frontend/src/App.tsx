import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useDispatch } from "react-redux";
import { jwtDecode } from "jwt-decode";
import Cookies from "js-cookie";
import "./App.css";

import Home from "./pages/home";
import Session from "./pages/session";
import { setUser } from "./redux/userSlice";

const apiUrl = process.env.REACT_APP_API_URL;
const isDev = process.env.NODE_ENV === "development";
const devEmail = process.env.REACT_APP_DEV_EMAIL || "dev@autoppia.com";

function redirectToLogin() {
  // Preserve the current path + search so the user lands back on the same page
  const returnUrl = window.location.origin + window.location.pathname + window.location.search;
  const url = new URL("https://app.autoppia.com/auth/sign-in");
  url.searchParams.append("redirectURL", returnUrl);
  window.location.href = url.href;
}

function getTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("access_token");
}

function cleanTokenFromUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete("access_token");
  window.history.replaceState({}, "", url.pathname + (url.search || ""));
}

function App() {
  const dispatch = useDispatch();
  const [authState, setAuthState] = useState<"checking" | "authenticated">("checking");

  useEffect(() => {
    const checkAuth = async () => {
      try {
        // 1. Check if token was returned in URL (redirect from Autoppia)
        const urlToken = getTokenFromUrl();
        if (urlToken) {
          Cookies.set("access_token", urlToken, { expires: 7 });
          cleanTokenFromUrl();
        }

        const accessToken = urlToken || Cookies.get("access_token");

        // In development, skip auth redirect and use a dev user
        if (!accessToken && isDev) {
          const response = await fetch(`${apiUrl}/user?email=${devEmail}`);
          if (response.ok) {
            const data = await response.json();
            dispatch(setUser({ email: data.user.email, instructions: data.user.instructions }));
          } else {
            dispatch(setUser({ email: devEmail, instructions: "" }));
          }
          setAuthState("authenticated");
          return;
        }

        if (!accessToken) {
          redirectToLogin();
          return;
        }

        const decodedToken = jwtDecode(accessToken) as any;

        // Check if token is expired
        if (decodedToken.exp && decodedToken.exp * 1000 < Date.now()) {
          Cookies.remove("access_token");
          if (isDev) {
            const response = await fetch(`${apiUrl}/user?email=${devEmail}`);
            if (response.ok) {
              const data = await response.json();
              dispatch(setUser({ email: data.user.email, instructions: data.user.instructions }));
            } else {
              dispatch(setUser({ email: devEmail, instructions: "" }));
            }
            setAuthState("authenticated");
            return;
          }
          redirectToLogin();
          return;
        }

        const email = decodedToken.email;
        const response = await fetch(`${apiUrl}/user?email=${email}`);
        if (response.ok) {
          const data = await response.json();
          dispatch(
            setUser({
              email: data.user.email,
              instructions: data.user.instructions,
            })
          );
          setAuthState("authenticated");
        } else {
          if (isDev) {
            dispatch(setUser({ email, instructions: "" }));
            setAuthState("authenticated");
            return;
          }
          redirectToLogin();
        }
      } catch (err) {
        console.error("Auth check failed:", err);
        if (isDev) {
          dispatch(setUser({ email: devEmail, instructions: "" }));
          setAuthState("authenticated");
          return;
        }
        Cookies.remove("access_token");
        redirectToLogin();
      }
    };
    checkAuth();
  }, [dispatch]);

  if (authState === "checking") {
    return (
      <div className="flex items-center justify-center h-screen bg-white dark:bg-dark-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-[3px] border-gray-200 dark:border-dark-border border-t-orange-500 rounded-full animate-spin" />
          <p className="text-sm text-gray-500 dark:text-gray-400">Authenticating...</p>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/session/:id" element={<Session />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
