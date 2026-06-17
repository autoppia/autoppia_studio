import React, { useEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faChevronDown } from "@fortawesome/free-solid-svg-icons";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";

export interface SelectOption {
  value: string;
  label: string;
  /** Optional secondary text shown after the label. */
  hint?: string;
  /** Optional leading icon. */
  icon?: IconDefinition;
}

interface SelectDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Min width of the popup list (defaults to the trigger width). */
  menuMinWidth?: string;
}

/**
 * Styled dropdown matching the connectors "Type" selector — a button trigger
 * with a popup list, click-outside-to-close, a check on the selected option,
 * and a chevron that rotates while open. A drop-in replacement for native
 * <select> across the app.
 */
export default function SelectDropdown({
  value,
  onChange,
  options,
  placeholder = "Select...",
  disabled = false,
  className = "",
  menuMinWidth,
}: SelectDropdownProps): React.ReactElement {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = options.find((item) => item.value === value);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className="w-full h-10 rounded-lg border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg px-3 flex items-center gap-2 text-sm text-gray-800 dark:text-gray-100 outline-none hover:border-primary/50 transition-colors disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:border-gray-200"
      >
        {current?.icon && <FontAwesomeIcon icon={current.icon} className="text-xs text-gray-400 flex-shrink-0" />}
        <span className={`flex-1 text-left truncate ${current ? "" : "text-gray-400 dark:text-gray-500"}`}>
          {current ? current.label : placeholder}
          {current?.hint && <span className="text-gray-400 dark:text-gray-500"> · {current.hint}</span>}
        </span>
        <FontAwesomeIcon
          icon={faChevronDown}
          className={`text-[10px] text-gray-400 transition-transform flex-shrink-0 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          className="absolute z-30 mt-1 w-full max-h-72 overflow-auto rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-soft-lg py-1"
          style={menuMinWidth ? { minWidth: menuMinWidth } : undefined}
        >
          {options.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => { onChange(item.value); setOpen(false); }}
              className={`w-full px-3 py-1.5 flex items-center gap-2 text-sm text-left hover:bg-gray-100 dark:hover:bg-dark-border transition-colors ${item.value === value ? "text-primary font-semibold" : "text-gray-700 dark:text-gray-200"}`}
            >
              {item.icon && <FontAwesomeIcon icon={item.icon} className="text-xs flex-shrink-0" />}
              <span className="flex-1 truncate">
                {item.label}
                {item.hint && <span className="text-gray-400 dark:text-gray-500 font-normal"> · {item.hint}</span>}
              </span>
              {item.value === value && <FontAwesomeIcon icon={faCheck} className="text-[10px] text-primary flex-shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
