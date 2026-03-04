import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPaperPlane } from "@fortawesome/free-solid-svg-icons";

import { useToast } from "../components/common/toast";
import GoogleSignInButton from "../components/common/google-sign-in-button";

const apiUrl = process.env.REACT_APP_API_URL;

export default function SignUp() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const navigate = useNavigate();
  const { showToast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !confirmPassword || submitting) return;

    if (password.length < 6) {
      showToast("Password must be at least 6 characters", "error");
      return;
    }

    if (password !== confirmPassword) {
      showToast("Passwords do not match", "error");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Failed to create account", "error");
        return;
      }

      showToast("Verification code sent to your email!", "success");
      navigate(`/verify-otp?email=${encodeURIComponent(email)}`);
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const isValid = email && password && confirmPassword;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-dark-bg px-4">
      <div className="w-full max-w-md animate-slide-up" style={{ animationDelay: "0.05s" }}>
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img
            src="/assets/images/logos/main.webp"
            alt="Autoppia"
            className="h-12 mb-3"
          />
          <div className="flex items-center gap-1">
            <img
              src="/assets/images/logos/automata.webp"
              alt="Automata"
              className="h-5 dark:hidden"
            />
            <img
              src="/assets/images/logos/automata_dark.webp"
              alt="Automata"
              className="h-5 hidden dark:block"
            />
          </div>
        </div>

        {/* Card */}
        <div
          className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft border border-gray-200 dark:border-dark-border p-8"
        >
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6 text-center">
            Create your account
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
                placeholder="At least 6 characters"
                required
                className="w-full px-4 py-2.5 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                  text-gray-900 dark:text-white text-sm placeholder:text-gray-400
                  focus:border-gray-300 dark:focus:border-gray-600 focus:shadow-soft outline-none transition-all duration-300"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Confirm Password
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                required
                className="w-full px-4 py-2.5 rounded-xl bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                  text-gray-900 dark:text-white text-sm placeholder:text-gray-400
                  focus:border-gray-300 dark:focus:border-gray-600 focus:shadow-soft outline-none transition-all duration-300"
              />
            </div>

            <button
              type="submit"
              disabled={!isValid || submitting}
              className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium
                transition-all duration-300 mt-2
                ${isValid && !submitting
                  ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg"
                  : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
                }`}
            >
              {submitting ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign Up</span>
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
          Already have an account?{" "}
          <Link to="/signin" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
