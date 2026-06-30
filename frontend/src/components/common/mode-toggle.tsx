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

  const option = (value: "normal" | "dev", icon: typeof faUser, title: string) => {
    const active = mode === value;
    return (
      <button
        type="button"
        onClick={() => setStudioMode(value)}
        aria-pressed={active}
        aria-label={title}
        title={title}
        className={`flex h-7 w-9 items-center justify-center rounded-lg text-[12px] transition-all ${
          active
            ? "bg-[color:var(--panel)] text-[color:var(--accent)] shadow-sm ring-1 ring-[color:var(--accent-line)]"
            : "text-[color:var(--faint)] hover:text-[color:var(--ink)]"
        }`}
      >
        <FontAwesomeIcon icon={icon} />
      </button>
    );
  };

  return (
    <div
      className="flex h-9 items-center gap-1 rounded-xl border border-[color:var(--line)] bg-[color:var(--bg-2)] p-1"
      role="group"
      aria-label="Studio mode"
    >
      {option("normal", faUser, "Normal mode — guided onboarding")}
      {option("dev", faCode, "Dev mode — show factory internals")}
    </div>
  );
}
