import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTriangleExclamation } from "@fortawesome/free-solid-svg-icons";

interface ConfirmModalProps {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({ title, message, confirmLabel = "Delete", onConfirm, onCancel }: ConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative w-full max-w-sm mx-4 bg-white dark:bg-dark-surface rounded-2xl shadow-xl border border-gray-200 dark:border-dark-border p-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-red-50 dark:bg-red-500/10">
            <FontAwesomeIcon icon={faTriangleExclamation} className="text-red-500 text-lg" />
          </div>
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{message}</p>
        </div>
        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel}
            className="flex-1 h-10 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-300
              bg-gray-100 dark:bg-dark-border hover:bg-gray-200 dark:hover:bg-dark-border/80 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 h-10 rounded-xl text-sm font-medium text-white
              bg-red-500 hover:bg-red-600 transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
