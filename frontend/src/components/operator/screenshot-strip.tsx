import React from "react";

interface ScreenshotStripProps {
  screenshots: string[];
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
}

export default function ScreenshotStrip({ screenshots, selectedIndex, onSelect }: ScreenshotStripProps) {
  if (!screenshots || screenshots.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin w-full mt-2">
      {screenshots.map((src, i) => (
        <img
          key={i}
          src={`data:image/png;base64,${src}`}
          alt={`Step ${i + 1}`}
          className={`h-24 rounded-lg border-2 cursor-pointer flex-shrink-0 transition-all duration-200
            ${selectedIndex === i
              ? "border-primary shadow-glow"
              : "border-gray-200 dark:border-dark-border hover:border-gray-400"
            }`}
          onClick={() => onSelect(selectedIndex === i ? null : i)}
        />
      ))}
    </div>
  );
}
