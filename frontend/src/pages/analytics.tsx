import { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCoins,
  faClock,
  faChartLine,
  faGauge,
  faHashtag,
  faStopwatch,
  faGift,
  faSpinner,
  faTriangleExclamation,
} from "@fortawesome/free-solid-svg-icons";

const apiUrl = process.env.REACT_APP_API_URL;

type RangeKey = "24h" | "7d" | "30d" | "90d";

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "24h", label: "Last 24 hours" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
];

interface OverTimePoint {
  bucket: string;
  with_tasks: number;
  no_tasks: number;
}

interface AnalyticsResponse {
  range: RangeKey;
  credits: {
    total_usage: number;
    runway: number | null;
    breakdown_by_source: { source: string; usage: number }[];
    usage_over_time: { bucket: string; usage: number }[];
    available: boolean;
  };
  sessions: {
    total: number;
    with_no_tasks: number;
    avg_tasks_per_session: number;
    avg_duration_seconds: number | null;
    free_tier: number;
    over_time: OverTimePoint[];
    available: boolean;
  };
}

export default function Analytics() {
  const user = useSelector((state: any) => state.user);
  const [range, setRange] = useState<RangeKey>("30d");
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user.email) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`${apiUrl}/analytics?email=${encodeURIComponent(user.email)}&range=${range}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json();
      })
      .then((json: AnalyticsResponse) => {
        if (!cancelled) setData(json);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load analytics");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user.email, range]);

  const sessions = data?.sessions;
  const credits = data?.credits;

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img
          src="/assets/images/bg/dark-bg.webp"
          alt=""
          className="w-full h-full object-cover"
        />
      </div>

      <div className="flex flex-col w-full h-full relative">
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-6 border-b border-gray-200 dark:border-dark-border
          bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Analytics</h1>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {sessions ? `${sessions.total} sessions` : "—"}
            </span>
          </div>

          <div className="flex items-center gap-1 p-1 rounded-xl bg-white dark:bg-dark-surface
            border border-gray-200 dark:border-dark-border">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200
                  ${range === r.key
                    ? "bg-gradient-primary text-white shadow-glow"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-bg"}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-6 space-y-8">
          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl
              bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20
              text-sm text-red-600 dark:text-red-400">
              <FontAwesomeIcon icon={faTriangleExclamation} className="text-xs" />
              <span>Failed to load analytics: {error}</span>
            </div>
          )}

          {loading && !data ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <FontAwesomeIcon icon={faSpinner} className="text-primary text-2xl animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading analytics…</p>
            </div>
          ) : (
            <>
              {/* API Credits Usage */}
              <section>
                <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-4">
                  API Credits Usage
                </h2>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-1 bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft p-5 space-y-5">
                    <StatRow
                      icon={faCoins}
                      label="Total Usage"
                      value={`$${(credits?.total_usage ?? 0).toFixed(4)}`}
                    />
                    <StatRow
                      icon={faClock}
                      label="Runway"
                      value={credits?.runway != null ? `${credits.runway}` : "—"}
                    />

                    <div className="pt-4 border-t border-gray-100 dark:border-dark-border">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                        Breakdown by Source
                      </p>
                      <p className="text-sm text-gray-400 dark:text-gray-500">
                        {credits?.available ? "No data available" : "Billing telemetry not available yet"}
                      </p>
                    </div>
                  </div>

                  <div className="lg:col-span-2 bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft p-5">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                      Usage Over Time
                    </p>
                    <ChartPlaceholder
                      icon={faChartLine}
                      label={credits?.available
                        ? "No usage in this range"
                        : "Billing telemetry not available yet"}
                    />
                  </div>
                </div>
              </section>

              {/* Agent Sessions */}
              <section>
                <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-4">
                  Agent Sessions
                </h2>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-1 bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft p-5 space-y-5">
                    <StatRow
                      icon={faGauge}
                      label="Total Sessions"
                      value={sessions?.total ?? 0}
                    />
                    <StatRow
                      icon={faHashtag}
                      label="Sessions with No Tasks"
                      value={sessions?.with_no_tasks ?? 0}
                    />
                    <StatRow
                      icon={faChartLine}
                      label="Avg Tasks per Session"
                      value={(sessions?.avg_tasks_per_session ?? 0).toFixed(2)}
                    />
                    <StatRow
                      icon={faStopwatch}
                      label="Avg Duration"
                      value={
                        sessions?.avg_duration_seconds != null
                          ? formatDuration(sessions.avg_duration_seconds)
                          : "—"
                      }
                    />
                    <StatRow
                      icon={faGift}
                      label="Free Tier Sessions"
                      value={sessions?.free_tier ?? 0}
                    />
                  </div>

                  <div className="lg:col-span-2 bg-white dark:bg-dark-surface rounded-xl
                    border border-gray-200 dark:border-dark-border shadow-soft p-5">
                    <div className="flex items-center justify-between mb-4">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Sessions Over Time
                      </p>
                      <div className="flex items-center gap-3 text-[10px]">
                        <span className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                          <span className="w-2.5 h-2.5 rounded-sm bg-gradient-primary" />
                          With Tasks
                        </span>
                        <span className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                          <span className="w-2.5 h-2.5 rounded-sm bg-gray-300 dark:bg-gray-600" />
                          No Tasks
                        </span>
                      </div>
                    </div>
                    {sessions && sessions.over_time.length > 0 && sessions.total > 0 ? (
                      <SessionsBarChart points={sessions.over_time} range={range} />
                    ) : (
                      <ChartPlaceholder icon={faChartLine} label="No sessions in this range" />
                    )}
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function StatRow({
  icon,
  label,
  value,
}: {
  icon: typeof faCoins;
  label: string;
  value: string | number;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <FontAwesomeIcon icon={icon} className="text-gray-400 text-xs" />
        <span className="text-sm text-gray-600 dark:text-gray-400 truncate">{label}</span>
      </div>
      <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 flex-shrink-0">
        {value}
      </span>
    </div>
  );
}

function ChartPlaceholder({ icon, label }: { icon: typeof faChartLine; label: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 rounded-lg
      bg-gray-50 dark:bg-dark-bg border border-dashed border-gray-200 dark:border-dark-border
      text-gray-400 dark:text-gray-500 gap-2">
      <FontAwesomeIcon icon={icon} className="text-2xl opacity-60" />
      <p className="text-xs">{label}</p>
    </div>
  );
}

function SessionsBarChart({ points, range }: { points: OverTimePoint[]; range: RangeKey }) {
  const max = Math.max(1, ...points.map((p) => p.with_tasks + p.no_tasks));
  const showLabel = (idx: number) => {
    if (range === "24h") return idx % 4 === 0;
    if (range === "7d") return true;
    if (range === "30d") return idx % 5 === 0;
    return idx % 15 === 0;
  };

  return (
    <div className="h-64 flex flex-col">
      <div className="flex-1 flex items-end gap-[2px] px-1">
        {points.map((p) => {
          const totalH = ((p.with_tasks + p.no_tasks) / max) * 100;
          const withH = p.with_tasks + p.no_tasks > 0
            ? (p.with_tasks / (p.with_tasks + p.no_tasks)) * totalH
            : 0;
          const noH = totalH - withH;
          return (
            <div
              key={p.bucket}
              className="flex-1 flex flex-col-reverse min-w-0 group relative"
              title={`${p.bucket}: ${p.with_tasks} with tasks, ${p.no_tasks} no tasks`}
            >
              {p.with_tasks > 0 && (
                <div
                  className="bg-gradient-primary rounded-t-sm transition-all duration-200"
                  style={{ height: `${withH}%` }}
                />
              )}
              {p.no_tasks > 0 && (
                <div
                  className="bg-gray-300 dark:bg-gray-600 transition-all duration-200"
                  style={{ height: `${noH}%` }}
                />
              )}
            </div>
          );
        })}
      </div>
      <div className="flex gap-[2px] px-1 pt-2 text-[9px] text-gray-400 dark:text-gray-500">
        {points.map((p, idx) => (
          <div key={`${p.bucket}-label`} className="flex-1 text-center truncate">
            {showLabel(idx) ? formatBucket(p.bucket, range) : ""}
          </div>
        ))}
      </div>
    </div>
  );
}

function formatBucket(bucket: string, range: RangeKey): string {
  if (range === "24h") {
    return bucket.slice(11, 13) + "h";
  }
  return bucket.slice(5);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}
