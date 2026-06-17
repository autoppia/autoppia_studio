import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useDispatch } from "react-redux";
import Cookies from "js-cookie";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck } from "@fortawesome/free-solid-svg-icons";

import { setUser } from "../redux/userSlice";
import { useToast } from "../components/common/toast";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();
const OTP_LENGTH = 6;
const COOLDOWN_SECONDS = 60;

export default function VerifyOTP() {
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") || "";

  const [otp, setOtp] = useState<string[]>(Array(OTP_LENGTH).fill(""));
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [countdown, setCountdown] = useState(COOLDOWN_SECONDS);

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { showToast } = useToast();

  // Redirect if no email provided
  useEffect(() => {
    if (!email) {
      navigate("/signup", { replace: true });
    }
  }, [email, navigate]);

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const handleChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);

    // Auto-advance to next input
    if (value && index < OTP_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, OTP_LENGTH);
    if (!pasted) return;

    const newOtp = [...otp];
    for (let i = 0; i < pasted.length; i++) {
      newOtp[i] = pasted[i];
    }
    setOtp(newOtp);

    // Focus the next empty input or the last one
    const nextEmpty = newOtp.findIndex((d) => !d);
    inputRefs.current[nextEmpty >= 0 ? nextEmpty : OTP_LENGTH - 1]?.focus();
  };

  const handleVerify = async () => {
    const code = otp.join("");
    if (code.length !== OTP_LENGTH || submitting) return;

    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, verification_code: code }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Verification failed", "error");
        return;
      }

      const data = await res.json();
      Cookies.set("access_token", data.token, { expires: 7 });
      dispatch(setUser({ email: data.user.email, instructions: data.user.instructions }));
      showToast("Account verified successfully!", "success");
      navigate("/", { replace: true });
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (resending || countdown > 0) return;

    setResending(true);
    try {
      const res = await fetch(`${apiUrl}/auth/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Failed to resend code", "error");
        return;
      }

      showToast("New verification code sent!", "success");
      setOtp(Array(OTP_LENGTH).fill(""));
      setCountdown(COOLDOWN_SECONDS);
      inputRefs.current[0]?.focus();
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setResending(false);
    }
  };

  const isComplete = otp.every((d) => d !== "");

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
        <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-soft border border-gray-200 dark:border-dark-border p-8">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 text-center">
            Verify your email
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-6">
            We sent a 6-digit code to <span className="font-medium text-gray-700 dark:text-gray-300">{email}</span>
          </p>

          {/* OTP inputs */}
          <div className="flex justify-center gap-3 mb-6">
            {Array.from({ length: OTP_LENGTH }).map((_, i) => (
              <input
                key={i}
                ref={(el) => { inputRefs.current[i] = el; }}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={otp[i]}
                onChange={(e) => handleChange(i, e.target.value)}
                onKeyDown={(e) => handleKeyDown(i, e)}
                onPaste={i === 0 ? handlePaste : undefined}
                className="w-11 h-12 text-center text-lg font-semibold rounded-xl
                  bg-gray-50 dark:bg-dark-bg border border-gray-200 dark:border-dark-border
                  text-gray-900 dark:text-white
                  focus:border-primary focus:shadow-glow outline-none transition-all duration-300"
              />
            ))}
          </div>

          {/* Verify button */}
          <button
            onClick={handleVerify}
            disabled={!isComplete || submitting}
            className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium
              transition-all duration-300
              ${isComplete && !submitting
                ? "bg-gradient-primary text-white shadow-glow hover:shadow-glow-lg"
                : "bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed"
              }`}
          >
            {submitting ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <span>Verify</span>
                <FontAwesomeIcon icon={faCheck} className="text-xs" />
              </>
            )}
          </button>

          {/* Resend */}
          <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-4">
            {countdown > 0 ? (
              <>Resend code in <span className="font-medium">{countdown}s</span></>
            ) : (
              <button
                onClick={handleResend}
                disabled={resending}
                className="text-primary font-medium hover:underline"
              >
                {resending ? "Sending..." : "Resend code"}
              </button>
            )}
          </p>
        </div>

        {/* Back to signup */}
        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
          Wrong email?{" "}
          <button
            onClick={() => navigate("/signup")}
            className="text-primary font-medium hover:underline"
          >
            Go back
          </button>
        </p>
      </div>
    </div>
  );
}
