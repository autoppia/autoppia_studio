import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { jwtDecode } from "jwt-decode";
import Cookies from "js-cookie";
import "./App.css";

import Home from "./pages/home";
import Session from "./pages/session";
import Settings from "./pages/settings";
import Skills from "./pages/skills";
import CreateSkill from "./pages/create-skill";
import SkillDetail from "./pages/skill-detail";
import RecordSkill from "./pages/record-skill";
import Evals from "./pages/evals";
import EvalDetail from "./pages/eval-detail";
import Analytics from "./pages/analytics";
import SignIn from "./pages/signin";
import SignUp from "./pages/signup";
import VerifyOTP from "./pages/verify-otp";
import MainLayout from "./components/layout/main-layout";
import { ToastProvider } from "./components/common/toast";
import { setUser } from "./redux/userSlice";

const apiUrl = process.env.REACT_APP_API_URL;

function App() {
  const dispatch = useDispatch();
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "unauthenticated">("checking");
  const isAuthenticated = useSelector((state: any) => state.user.isAuthenticated);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const accessToken = Cookies.get("access_token");

        if (!accessToken) {
          setAuthState("unauthenticated");
          return;
        }

        const decodedToken = jwtDecode(accessToken) as any;

        // Check if token is expired
        if (decodedToken.exp && decodedToken.exp * 1000 < Date.now()) {
          Cookies.remove("access_token");
          setAuthState("unauthenticated");
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
          Cookies.remove("access_token");
          setAuthState("unauthenticated");
        }
      } catch (err) {
        console.error("Auth check failed:", err);
        Cookies.remove("access_token");
        setAuthState("unauthenticated");
      }
    };
    checkAuth();
  }, [dispatch]);

  // Sync authState with Redux isAuthenticated (sign-in/sign-up and logout)
  useEffect(() => {
    if (isAuthenticated && authState === "unauthenticated") {
      setAuthState("authenticated");
    } else if (!isAuthenticated && authState === "authenticated") {
      setAuthState("unauthenticated");
    }
  }, [isAuthenticated, authState]);

  if (authState === "checking") {
    return (
      <div className="flex items-center justify-center h-screen bg-white dark:bg-dark-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-[3px] border-gray-200 dark:border-dark-border border-t-orange-500 rounded-full animate-spin" />
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          {authState === "authenticated" ? (
            <>
              {/* Protected routes */}
              <Route element={<MainLayout />}>
                <Route path="/" element={<Home />} />
                <Route path="/session/:id" element={<Session />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/skills" element={<Skills />} />
                <Route path="/skills/create" element={<CreateSkill />} />
                <Route path="/skills/record" element={<RecordSkill />} />
                <Route path="/skills/:skillId" element={<SkillDetail />} />
                <Route path="/evals" element={<Evals />} />
                <Route path="/evals/:evalId" element={<EvalDetail />} />
                <Route path="/evals/:evalId/run/:id" element={<Session />} />
                <Route path="/analytics" element={<Analytics />} />
              </Route>
              {/* Redirect auth pages to home if already logged in */}
              <Route path="/signin" element={<Navigate to="/" replace />} />
              <Route path="/signup" element={<Navigate to="/" replace />} />
              <Route path="/verify-otp" element={<Navigate to="/" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </>
          ) : (
            <>
              {/* Public routes */}
              <Route path="/signin" element={<SignIn />} />
              <Route path="/signup" element={<SignUp />} />
              <Route path="/verify-otp" element={<VerifyOTP />} />
              {/* Redirect everything else to signin */}
              <Route path="*" element={<Navigate to="/signin" replace />} />
            </>
          )}
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
