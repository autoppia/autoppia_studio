import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";

/**
 * Standard section header title block: a gradient icon badge + title (+ optional
 * subtitle and info popover). Shared across all section pages so margins, icon
 * and text are identical everywhere.
 */
export default function SectionTitle({
  icon,
  title,
  subtitle,
  info,
}: {
  icon: IconDefinition;
  title: string;
  subtitle?: string;
  info?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px] border border-[color:var(--accent-line)] bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
        <FontAwesomeIcon icon={icon} className="text-sm" />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="font-display truncate text-[20px] font-extrabold leading-tight tracking-[-0.01em] text-gray-900 dark:text-white">{title}</h1>
          {info}
        </div>
        {subtitle && (
          <p className="truncate text-[12px] leading-tight text-[color:var(--muted)]">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
