import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faGlobe } from "@fortawesome/free-solid-svg-icons";

interface BrowserLoadingProps {
  minHeight?: string;
}

export default function BrowserLoading({ minHeight = "600px" }: BrowserLoadingProps) {
  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden"
      style={{ minHeight }}
    >
      {/* Browser chrome bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-dark-bg border-b border-gray-200 dark:border-dark-border">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-300 dark:bg-red-400/40" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-300 dark:bg-yellow-400/40" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-300 dark:bg-green-400/40" />
        </div>
        <div className="flex items-center flex-grow max-w-lg h-7 bg-gray-100 dark:bg-dark-surface rounded-md px-3 border border-gray-150 dark:border-dark-border">
          <div className="w-3 h-3 rounded-full bg-gray-300 dark:bg-gray-600 mr-2 flex-shrink-0" />
          <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded w-40 shimmer" />
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-grow relative bg-gradient-to-b from-gray-50 to-gray-100 dark:from-dark-surface dark:to-dark-bg">

        {/* Subtle dot grid background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            opacity: 0.4,
            backgroundImage: "radial-gradient(circle, #d1d5db 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
        />
        <div
          className="dark:block hidden absolute inset-0 pointer-events-none"
          style={{
            opacity: 0.15,
            backgroundImage: "radial-gradient(circle, #4b5563 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
        />

        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {/* Animated rings */}
          <div className="relative w-28 h-28 mb-6">
            <div className="absolute inset-0 rounded-full border border-primary/20 orbit-ring" />
            <div className="absolute inset-[-8px] rounded-full border border-primary/10 orbit-ring-2" />
            <div className="absolute inset-[-16px] rounded-full border border-primary/5 orbit-ring" style={{ animationDelay: "1s" }} />

            {/* Spinning track */}
            <div className="absolute inset-2 rounded-full border-2 border-gray-200 dark:border-dark-border" />
            <div
              className="absolute inset-2 rounded-full border-2 border-transparent animate-spin"
              style={{
                borderTopColor: "#4F8FE0",
                borderRightColor: "rgba(79,143,224,0.3)",
                animationDuration: "1.5s",
              }}
            />

            {/* Center icon */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-gradient-primary flex items-center justify-center shadow-glow">
                <FontAwesomeIcon icon={faGlobe} className="text-white text-lg" />
              </div>
            </div>
          </div>

          {/* Text */}
          <div className="flex flex-col items-center gap-2 float-up" style={{ animationDelay: "0.2s" }}>
            <span className="text-base font-semibold text-gray-700 dark:text-gray-200">
              Starting browser session
            </span>
            <span className="text-sm text-gray-400 dark:text-gray-500">
              Connecting to agent
            </span>
          </div>

          {/* Bouncing dots */}
          <div className="flex gap-1.5 mt-4 float-up" style={{ animationDelay: "0.4s" }}>
            <div className="w-1.5 h-1.5 rounded-full bg-primary loading-dot" />
            <div className="w-1.5 h-1.5 rounded-full bg-primary loading-dot" />
            <div className="w-1.5 h-1.5 rounded-full bg-primary loading-dot" />
          </div>
        </div>
      </div>
    </div>
  );
}
