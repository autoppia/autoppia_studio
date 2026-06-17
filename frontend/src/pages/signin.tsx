import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useDispatch } from "react-redux";
import Cookies from "js-cookie";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPaperPlane } from "@fortawesome/free-solid-svg-icons";

import { setUser } from "../redux/userSlice";
import { useToast } from "../components/common/toast";
import GoogleSignInButton from "../components/common/google-sign-in-button";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");
const demoEmail = process.env.REACT_APP_DEMO_EMAIL || "demo@autoppia.com";
const demoPassword = process.env.REACT_APP_DEMO_PASSWORD || "Passw0rd!";
const showDemoCredentialsButton =
  process.env.NODE_ENV === "development" || process.env.REACT_APP_SHOW_DEMO_CREDENTIALS === "true";

export default function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const fillDemoCredentials = () => {
    setEmail(demoEmail);
    setPassword(demoPassword);
  };

  // If the user landed here because their session expired mid-use, say so.
  useEffect(() => {
    if (sessionStorage.getItem("automata_session_expired")) {
      sessionStorage.removeItem("automata_session_expired");
      showToast("Your session expired. Please sign in again.", "info");
    }
  }, [showToast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/auth/signin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        if (res.status === 403 && data?.detail?.toLowerCase().includes("not verified")) {
          showToast("Please verify your email first", "info");
          navigate(`/verify-otp?email=${encodeURIComponent(email)}`);
          return;
        }
        showToast(data?.detail || "Invalid email or password", "error");
        return;
      }

      const data = await res.json();
      Cookies.set("access_token", data.token, { expires: 7 });
      dispatch(setUser({ email: data.user.email, instructions: data.user.instructions }));
      navigate("/", { replace: true });
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-dark-bg px-4">
      <div className="w-full max-w-md animate-slide-up" style={{ animationDelay: "0.05s" }}>
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img
            src="/assets/images/logos/autoppia-studio.webp"
            alt="Autoppia Studio"
            className="h-12 object-contain"
          />
        </div>

        {/* Card */}
        <div
          className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft border border-gray-200 dark:border-dark-border p-8"
        >
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6 text-center">
            Sign in to your account
          </h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full px-4 py-2.5 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                  text-gray-900 dark:text-white text-sm placeholder:text-gray-400
                  focus:border-gray-300 dark:focus:border-gray-600 focus:shadow-soft outline-none transition-all duration-300"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
                className="w-full px-4 py-2.5 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                  text-gray-900 dark:text-white text-sm placeholder:text-gray-400
                  focus:border-gray-300 dark:focus:border-gray-600 focus:shadow-soft outline-none transition-all duration-300"
              />
            </div>

            {showDemoCredentialsButton && (
              <button
                type="button"
                onClick={fillDemoCredentials}
                className="w-full py-2.5 rounded-xl border border-dashed border-primary/40 bg-primary/5 text-primary text-sm font-medium hover:bg-primary/10 transition-colors"
              >
                Fill demo credentials
              </button>
            )}

            <button
              type="submit"
              disabled={!email || !password || submitting}
              className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium
                transition-all duration-300 mt-2
                ${email && password && !submitting
                  ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg"
                  : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                }`}
            >
              {submitting ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign In</span>
                  <FontAwesomeIcon icon={faPaperPlane} className="text-xs" />
                </>
              )}
            </button>
          </form>

          {/* Google sign-in */}
          {process.env.REACT_APP_GOOGLE_CLIENT_ID && (
            <>
              <div className="flex items-center gap-3 mt-5">
                <div className="flex-grow h-px bg-gray-200 dark:bg-dark-border" />
                <span className="text-xs text-gray-400">or</span>
                <div className="flex-grow h-px bg-gray-200 dark:bg-dark-border" />
              </div>
              <div className="mt-4">
                <GoogleSignInButton />
              </div>
            </>
          )}
        </div>

        {/* Footer link */}
        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
          Don't have an account?{" "}
          <Link to="/signup" className="text-primary font-medium hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
