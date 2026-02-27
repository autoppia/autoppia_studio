import React, { useRef, useState, useCallback } from "react";

interface ScreenshotStripProps {
  screenshots: string[];
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
}

export default function ScreenshotStrip({ screenshots, selectedIndex, onSelect }: ScreenshotStripProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragState = useRef({ startX: 0, scrollLeft: 0, hasMoved: false });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;
    setIsDragging(true);
    dragState.current = {
      startX: e.pageX - container.offsetLeft,
      scrollLeft: container.scrollLeft,
      hasMoved: false,
    };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return;
    const container = containerRef.current;
    if (!container) return;
    e.preventDefault();
    const x = e.pageX - container.offsetLeft;
    const walk = x - dragState.current.startX;
    if (Math.abs(walk) > 3) {
      dragState.current.hasMoved = true;
    }
    container.scrollLeft = dragState.current.scrollLeft - walk;
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleClick = useCallback((i: number) => {
    if (dragState.current.hasMoved) return;
    onSelect(selectedIndex === i ? null : i);
  }, [onSelect, selectedIndex]);

  if (!screenshots || screenshots.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className={`flex gap-2 overflow-x-auto pb-2 scrollbar-thin w-full mt-2 select-none ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {screenshots.map((src, i) => (
        <img
          key={i}
          src={`data:image/png;base64,${src}`}
          alt={`Step ${i + 1}`}
          draggable={false}
          className={`h-24 rounded-lg border-2 cursor-pointer flex-shrink-0 transition-all duration-200
            ${selectedIndex === i
              ? "border-primary shadow-glow"
              : "border-gray-200 dark:border-dark-border hover:border-gray-400"
            }`}
          onClick={() => handleClick(i)}
        />
      ))}
    </div>
  );
}
