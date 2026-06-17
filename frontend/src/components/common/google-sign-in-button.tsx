import { useGoogleLogin } from "@react-oauth/google";
import { useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import Cookies from "js-cookie";

import { setUser } from "../../redux/userSlice";
import { useToast } from "./toast";

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48">
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
    <path fill="#FBBC05" d="M10.53 28.59a14.5 14.5 0 0 1 0-9.18l-7.98-6.19a24.01 24.01 0 0 0 0 21.56l7.98-6.19z"/>
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
  </svg>
);


const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");
const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || "";

function GoogleSignInButtonInner() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { showToast } = useToast();

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        const res = await fetch(`${apiUrl}/auth/google`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ access_token: tokenResponse.access_token }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          showToast(data?.detail || "Google sign-in failed", "error");
          return;
        }

        const data = await res.json();
        Cookies.set("access_token", data.token, { expires: 7 });
        dispatch(setUser({ email: data.user.email, instructions: data.user.instructions }));
        navigate("/", { replace: true });
      } catch {
        showToast("Unable to reach the server", "error");
      }
    },
    onError: () => {
      showToast("Google sign-in failed", "error");
    },
  });

  return (
    <button
      type="button"
      onClick={() => googleLogin()}
      className="flex items-center justify-center gap-3 w-full py-2.5 rounded-xl text-sm font-medium
        border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg
        text-gray-700 dark:text-gray-200
        hover:bg-gray-50 dark:hover:bg-dark-surface hover:shadow-soft
        transition-all duration-300"
    >
      <GoogleIcon />
      <span>Continue with Google</span>
    </button>
  );
}

export default function GoogleSignInButton() {
  if (!GOOGLE_CLIENT_ID) return null;
  return <GoogleSignInButtonInner />;
}
