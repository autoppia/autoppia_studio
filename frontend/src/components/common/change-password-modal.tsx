import { useState, FormEvent } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark, faEye, faEyeSlash, faSpinner } from "@fortawesome/free-solid-svg-icons";
import { useToast } from "./toast";
import { getApiUrl } from "../../utils/api-url";

const apiUrl = getApiUrl();

export default function ChangePasswordModal({ email, onClose }: { email: string; onClose: () => void }) {
  const { showToast } = useToast();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword || submitting) return;

    if (newPassword.length < 6) {
      showToast("New password must be at least 6 characters", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("Passwords do not match", "error");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${apiUrl}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, current_password: currentPassword, new_password: newPassword }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        showToast(data?.detail || "Failed to change password", "error");
        return;
      }
      showToast("Password changed successfully", "success");
      onClose();
    } catch {
      showToast("Unable to reach the server. Please try again later.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = `w-full px-4 py-2.5 pr-10 rounded-xl border border-gray-200 dark:border-zinc-800/80
    bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
    placeholder-gray-400 dark:placeholder-gray-500 outline-none
    focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm mx-4 bg-white dark:bg-zinc-900/70 rounded-2xl shadow-xl border border-gray-200 dark:border-zinc-800/80 p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">Change Password</h3>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          >
            <FontAwesomeIcon icon={faXmark} className="text-sm" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: "Current Password", value: currentPassword, setValue: setCurrentPassword, show: showCurrent, setShow: setShowCurrent, placeholder: "Enter current password", autoFocus: true },
            { label: "New Password", value: newPassword, setValue: setNewPassword, show: showNew, setShow: setShowNew, placeholder: "At least 6 characters", autoFocus: false },
            { label: "Confirm New Password", value: confirmPassword, setValue: setConfirmPassword, show: showConfirm, setShow: setShowConfirm, placeholder: "Repeat new password", autoFocus: false },
          ].map(({ label, value, setValue, show, setShow, placeholder, autoFocus }) => (
            <div key={label}>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">{label}</label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={placeholder}
                  autoFocus={autoFocus}
                  className={inputClass}
                />
                <button
                  type="button"
                  onClick={() => setShow((v: boolean) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <FontAwesomeIcon icon={show ? faEyeSlash : faEye} className="text-sm" />
                </button>
              </div>
            </div>
          ))}

          <button
            type="submit"
            disabled={!currentPassword || !newPassword || !confirmPassword || submitting}
            className="w-full h-10 rounded-xl text-sm font-medium text-white bg-gradient-primary
              disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
          >
            {submitting ? <FontAwesomeIcon icon={faSpinner} className="animate-spin" /> : "Change Password"}
          </button>
        </form>
      </div>
    </div>
  );
}
