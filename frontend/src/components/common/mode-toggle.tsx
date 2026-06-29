import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUser, faCode } from "@fortawesome/free-solid-svg-icons";
import { setStudioMode, useStudioMode } from "../../utils/studio-mode";

/**
 * Segmented Normal / Dev switch. Normal keeps the experience simple for
 * non-technical users; Dev reveals raw factory artifacts and run internals.
 */
export default function ModeToggle() {
  const mode = useStudioMode();

  const option = (value: "normal" | "dev", label: string, icon: typeof faUser) => {
    const active = mode === value;
    return (
      <button
        type="button"
        onClick={() => setStudioMode(value)}
        aria-pressed={active}
        title={value === "normal" ? "Normal mode — guided onboarding" : "Dev mode — show factory internals"}
        className={`flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[11px] font-semibold transition-colors ${
          active
            ? "bg-white text-gray-900 shadow-sm dark:bg-white dark:text-gray-900"
            : "text-gray-500 hover:text-gray-700 dark:text-zinc-400 dark:hover:text-zinc-200"
        }`}
      >
        <FontAwesomeIcon icon={icon} className="text-[10px]" />
        <span className="hidden sm:inline">{label}</span>
      </button>
    );
  };

  return (
    <div
      className="flex h-9 items-center rounded-xl border border-gray-200 bg-gray-50 p-1 dark:border-zinc-800/80 dark:bg-zinc-900/70"
      role="group"
      aria-label="Studio mode"
    >
      {option("normal", "Normal", faUser)}
      {option("dev", "Dev", faCode)}
    </div>
  );
}
