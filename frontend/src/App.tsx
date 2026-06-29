import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { jwtDecode } from "jwt-decode";
import Cookies from "js-cookie";
import "./App.css";

import Home from "./pages/home";
import Session from "./pages/session";
import Settings from "./pages/settings";
import Canvas from "./pages/canvas";
import Evals from "./pages/evals";
import EvalDetail from "./pages/eval-detail";
import Agents from "./pages/agents";
import AgentDetail from "./pages/agent-detail";
import Connectors from "./pages/connectors";
import Capabilities from "./pages/capabilities";
import Entities from "./pages/entities";
import Approvals from "./pages/approvals";
import Artifacts from "./pages/artifacts";
import Credentials from "./pages/credentials";
import Knowledge from "./pages/knowledge";
import Analytics from "./pages/analytics";
import Runtime from "./pages/runtime";
import Work from "./pages/work";
import CompanySetup from "./pages/company-setup";
import Onboarding from "./pages/onboarding";
import SignIn from "./pages/signin";
import SignUp from "./pages/signup";
import VerifyOTP from "./pages/verify-otp";
import MainLayout from "./components/layout/main-layout";
import { ToastProvider } from "./components/common/toast";
import { setUser, logout } from "./redux/userSlice";
import { installAuthFetch } from "./utils/auth-fetch";
import { getApiUrl } from "./utils/api-url";
import { useStudioMode } from "./utils/studio-mode";

const apiUrl = getApiUrl();
installAuthFetch(apiUrl);

/**
 * Studio's landing target depends on the experience mode: normal users land on
 * company onboarding (the center of the product); dev users land on the canvas.
 */
function RootRedirect() {
  const mode = useStudioMode();
  return <Navigate to={mode === "dev" ? "/canvas" : "/onboarding"} replace />;
}

function resetUserScopedStorage(email: string) {
  const previous = localStorage.getItem("automata_last_email") || "";
  if (previous !== email) {
    localStorage.removeItem("automata_company_id");
    localStorage.removeItem("automata_onboarding_company_id");
    localStorage.removeItem("automata_work_board_id");
  }
  if (email) localStorage.setItem("automata_last_email", email);
}

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
        resetUserScopedStorage(email);
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

  // The auth-fetch wrapper fires this when a token-bearing request is rejected
  // (401) — the JWT is invalid/expired. Tear down the session and redirect.
  useEffect(() => {
    const onExpired = () => {
      dispatch(logout());
      setAuthState("unauthenticated");
    };
    window.addEventListener("automata-auth-expired", onExpired);
    return () => window.removeEventListener("automata-auth-expired", onExpired);
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
          <div className="w-10 h-10 border-[3px] border-gray-200 dark:border-dark-border border-t-primary rounded-full animate-spin" />
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
                {/* Landing depends on mode: onboarding (normal) or canvas (dev) */}
                <Route path="/" element={<RootRedirect />} />
                <Route path="/onboarding" element={<Onboarding />} />
                <Route path="/home" element={<Home />} />
                <Route path="/session/:id" element={<Session />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/canvas" element={<Canvas />} />
                {/* Skills are no longer a separate section — they live under Capabilities. */}
                <Route path="/skills" element={<Navigate to="/capabilities?view=skills" replace />} />
                <Route path="/trajectories" element={<Navigate to="/capabilities?view=trajectories" replace />} />
                <Route path="/skills/create" element={<Navigate to="/capabilities?view=skills" replace />} />
                <Route path="/skills/record" element={<Navigate to="/capabilities?view=skills" replace />} />
                <Route path="/skills/:skillId" element={<Navigate to="/capabilities?view=skills" replace />} />
                <Route path="/evals" element={<Evals mode="benchmarks" />} />
                <Route path="/eval-runs" element={<Evals mode="runs" />} />
                <Route path="/evals/:evalId" element={<EvalDetail />} />
                <Route path="/evals/:evalId/run/:id" element={<Session />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/agents/:agentId" element={<AgentDetail />} />
                <Route path="/work" element={<Work />} />
                <Route path="/connectors" element={<Connectors />} />
                <Route path="/capabilities" element={<Capabilities />} />
                <Route path="/capabilities/:kind/:id" element={<Capabilities />} />
                <Route path="/entities" element={<Entities />} />
                <Route path="/runtime" element={<Runtime />} />
                <Route path="/approvals" element={<Approvals />} />
                <Route path="/artifacts" element={<Artifacts />} />
                <Route path="/setup/company" element={<CompanySetup />} />
                <Route path="/credentials" element={<Credentials />} />
                <Route path="/knowledge" element={<Knowledge />} />
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
