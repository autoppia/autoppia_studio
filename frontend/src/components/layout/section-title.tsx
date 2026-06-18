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
      <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-primary text-white shadow-glow">
        <FontAwesomeIcon icon={icon} className="text-sm" />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold leading-tight text-gray-800 dark:text-gray-100">{title}</h1>
          {info}
        </div>
        {subtitle && (
          <p className="text-[11px] leading-tight text-gray-400 dark:text-gray-500">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
