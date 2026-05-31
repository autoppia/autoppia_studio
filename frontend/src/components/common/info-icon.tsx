import { useState } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCircleInfo, faXmark } from "@fortawesome/free-solid-svg-icons";

interface InfoIconProps {
  title: string;
  children: React.ReactNode;
}

export default function InfoIcon({ title, children }: InfoIconProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
        className="inline-flex items-center justify-center w-5 h-5 rounded-full text-gray-400 hover:text-primary hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
        title={title}
      >
        <FontAwesomeIcon icon={faCircleInfo} className="text-xs" />
      </button>
      {open && createPortal(
        <div
          className="fixed inset-0 z-[2147483647] flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
          onClick={() => setOpen(false)}
        >
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
          <div
            className="relative my-auto w-full max-w-lg max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-3rem)] rounded-2xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-xl flex flex-col"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-dark-border"
              >
                <FontAwesomeIcon icon={faXmark} className="text-sm" />
              </button>
            </div>
            <div className="px-5 py-4 text-sm leading-6 text-gray-600 dark:text-gray-300 overflow-y-auto scrollbar-thin">
              {children}
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
