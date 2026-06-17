import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { io, Socket } from "socket.io-client";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBell,
  faBolt,
  faCheckDouble,
  faCircleCheck,
  faCircleExclamation,
  faCircleInfo,
  faSpinner,
  faTrashCan,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { ActivitySummary, AppNotification, NotificationLevel } from "../../utils/types";

const apiUrl = process.env.REACT_APP_API_URL || "http://127.0.0.1:8080";
const POLL_MS = 15000;

const levelStyles: Record<NotificationLevel, { icon: typeof faCircleInfo; color: string }> = {
  info: { icon: faCircleInfo, color: "text-blue-500" },
  success: { icon: faCircleCheck, color: "text-green-500" },
  warning: { icon: faTriangleExclamation, color: "text-amber-500" },
  error: { icon: faCircleExclamation, color: "text-red-500" },
};

function relativeTime(value?: string): string {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  if (diff < 60_000) return "now";
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

type PanelKey = "none" | "activity" | "notifications";

type StatTile = { label: string; value: number; color: string };

export default function ActivityCenter() {
  const navigate = useNavigate();
  const user = useSelector((state: any) => state.user);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [panel, setPanel] = useState<PanelKey>("none");
  const containerRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<Socket | null>(null);
  const panelRef = useRef<PanelKey>("none");
  panelRef.current = panel;

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId ?? localStorage.getItem("automata_company_id") ?? "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const loadSummary = useCallback(async () => {
    if (!user.email) return;
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/activity-summary?${params.toString()}`);
      if (!res.ok) return;
      setSummary(await res.json());
    } catch (err) {
      // Silent: the bell should never break the topbar.
    }
  }, [user.email, companyId]);

  const loadNotifications = useCallback(async () => {
    if (!user.email) return;
    try {
      const params = new URLSearchParams({ email: user.email, unreadOnly: "false", limit: "30" });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/notifications?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setNotifications(data.notifications || []);
    } catch (err) {
      // Silent.
    }
  }, [user.email, companyId]);

  // Fallback polling + initial load.
  useEffect(() => {
    if (!user.email) return;
    loadSummary();
    const timer = window.setInterval(loadSummary, POLL_MS);
    return () => window.clearInterval(timer);
  }, [user.email, companyId, loadSummary]);

  // Socket.IO: subscribe to live activity/notification events for this user + company.
  useEffect(() => {
    if (!user.email) return;
    const socket = io(apiUrl, { transports: ["websocket", "polling"] });
    socketRef.current = socket;

    const subscribe = () => socket.emit("subscribe-activity", { email: user.email, companyId });
    socket.on("connect", subscribe);

    socket.on("notification-created", (payload: { notification?: AppNotification }) => {
      const incoming = payload?.notification;
      // Optimistic insert so the badge/list update instantly.
      if (incoming?.notificationId) {
        setNotifications((prev) =>
          prev.some((item) => item.notificationId === incoming.notificationId) ? prev : [incoming, ...prev]
        );
        setSummary((prev) =>
          prev
            ? {
                ...prev,
                notifications: {
                  unreadCount: prev.notifications.unreadCount + (incoming.read ? 0 : 1),
                  recent: [incoming, ...prev.notifications.recent.filter((n) => n.notificationId !== incoming.notificationId)].slice(0, 5),
                },
              }
            : prev
        );
      }
      // Authoritative reconcile.
      loadSummary();
    });

    socket.on("activity-updated", () => {
      loadSummary();
      if (panelRef.current === "notifications") loadNotifications();
    });

    return () => {
      socket.off("connect", subscribe);
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [user.email, companyId, loadSummary, loadNotifications]);

  useEffect(() => {
    if (panel === "none") return;
    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setPanel("none");
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [panel]);

  const openNotifications = () => {
    setPanel((prev) => {
      const next = prev === "notifications" ? "none" : "notifications";
      if (next === "notifications") loadNotifications();
      return next;
    });
  };

  const handleAction = (actionUrl?: string) => {
    if (!actionUrl) return;
    setPanel("none");
    if (actionUrl.startsWith("/")) navigate(actionUrl);
    else window.open(actionUrl, "_blank", "noopener,noreferrer");
  };

  const markRead = async (notification: AppNotification) => {
    if (notification.read) return;
    setNotifications((prev) => prev.map((item) => (item.notificationId === notification.notificationId ? { ...item, read: true } : item)));
    try {
      await fetch(`${apiUrl}/notifications/${notification.notificationId}/read`, { method: "PATCH" });
    } catch (err) {
      // Silent.
    }
    loadSummary();
  };

  const markAllRead = async () => {
    if (!user.email || !(summary?.notifications.unreadCount)) return;
    setNotifications((prev) => prev.map((item) => ({ ...item, read: true })));
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      await fetch(`${apiUrl}/notifications/read-all?${params.toString()}`, { method: "POST" });
    } catch (err) {
      // Silent.
    }
    loadSummary();
    loadNotifications();
  };

  const deleteNotification = async (notification: AppNotification) => {
    setNotifications((prev) => prev.filter((item) => item.notificationId !== notification.notificationId));
    try {
      await fetch(`${apiUrl}/notifications/${notification.notificationId}`, { method: "DELETE" });
    } catch (err) {
      // Silent.
    }
    loadSummary();
  };

  const clearRead = async () => {
    if (!user.email) return;
    setNotifications((prev) => prev.filter((item) => !item.read));
    try {
      const params = new URLSearchParams({ email: user.email, readOnly: "true" });
      if (companyId) params.set("companyId", companyId);
      await fetch(`${apiUrl}/notifications?${params.toString()}`, { method: "DELETE" });
    } catch (err) {
      // Silent.
    }
    loadSummary();
    loadNotifications();
  };

  const onNotificationClick = (notification: AppNotification) => {
    markRead(notification);
    handleAction(notification.actionUrl);
  };

  if (!user.isAuthenticated) return null;

  const status = summary?.status;
  const running = status?.runningTasks || 0;
  const unreadCount = summary?.notifications.unreadCount || 0;
  const panelNotifications = panel === "notifications" && notifications.length ? notifications : summary?.notifications.recent || [];
  const hasRead = panelNotifications.some((item) => item.read);
  const runningItems = summary?.running || [];

  const taskStats: StatTile[] = [
    { label: "Review", value: status?.reviewTasks || 0, color: "text-amber-600 dark:text-amber-400" },
    { label: "Failed", value: status?.failedTasks || 0, color: "text-red-500 dark:text-red-400" },
    { label: "Queued", value: status?.queuedTasks || 0, color: "text-gray-600 dark:text-gray-300" },
    { label: "Done", value: status?.doneTasks || 0, color: "text-green-600 dark:text-green-400" },
    { label: "Due", value: status?.scheduledDue || 0, color: "text-primary" },
    { label: "Scheduled", value: status?.scheduledUpcoming || 0, color: "text-gray-600 dark:text-gray-300" },
  ];

  const runStats: StatTile[] = [
    { label: "Sessions", value: status?.activeSessions || 0, color: "text-primary" },
    { label: "Eval pending", value: status?.evalRunsPending || 0, color: "text-gray-600 dark:text-gray-300" },
    { label: "Eval failed", value: status?.evalRunsFailed || 0, color: "text-red-500 dark:text-red-400" },
    { label: "Harvest run", value: status?.harvestersRunning || 0, color: "text-primary" },
    { label: "Harvest failed", value: status?.harvestersFailed || 0, color: "text-red-500 dark:text-red-400" },
  ];

  const renderTiles = (tiles: StatTile[]) => (
    <div className="grid grid-cols-3 gap-2">
      {tiles.map((stat) => (
        <div key={stat.label} className="rounded-lg border border-gray-100 dark:border-zinc-800/80 dark:bg-zinc-950/45 px-2 py-1.5">
          <span className={`block text-base font-semibold tabular-nums leading-tight ${stat.color}`}>{stat.value}</span>
          <span className="block text-[10px] uppercase tracking-wide text-gray-400">{stat.label}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div ref={containerRef} className="flex items-center gap-2">
      {/* Activity status */}
      <div className="relative">
        <button
          onClick={() => setPanel((prev) => (prev === "activity" ? "none" : "activity"))}
          className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-gray-200 dark:border-zinc-800/80 text-xs font-medium text-gray-600 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          title="Activity"
        >
          <FontAwesomeIcon icon={running > 0 ? faSpinner : faBolt} className={`text-[11px] ${running > 0 ? "animate-spin text-primary" : "text-gray-400"}`} />
          <span className="font-semibold tabular-nums">{running}</span>
          <span className="hidden sm:inline">Running</span>
        </button>

        {panel === "activity" && (
          <div className="absolute right-0 top-10 z-[90] w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-950/95 shadow-xl dark:shadow-black/40 backdrop-blur-sm">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-zinc-800/80">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Activity</span>
              <button onClick={() => handleAction("/work")} className="text-xs font-medium text-primary hover:underline">
                View board
              </button>
            </div>

            <div className="max-h-[60vh] overflow-auto">
              <div className="px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Running now</p>
                {runningItems.length === 0 ? (
                  <p className="text-xs text-gray-400 dark:text-gray-500 py-1">No tasks running</p>
                ) : (
                  <div className="space-y-2">
                    {runningItems.map((item) => (
                      <button
                        key={item.workItemId}
                        onClick={() => handleAction("/work")}
                        className="w-full flex items-center gap-2 text-left rounded-lg px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                      >
                        <FontAwesomeIcon icon={faSpinner} className="text-[11px] text-primary animate-spin shrink-0" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-xs font-medium text-gray-800 dark:text-gray-100 truncate">{item.title}</span>
                          <span className="block text-[11px] text-gray-400 dark:text-gray-500 truncate">
                            {item.runTarget === "all" ? "All agents" : item.agentName || "Selected agent"}
                            {item.startedAt ? ` · ${relativeTime(item.startedAt)}` : ""}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="px-4 pb-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Tasks & schedule</p>
                {renderTiles(taskStats)}
              </div>

              <div className="px-4 pb-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Sessions & runs</p>
                {renderTiles(runStats)}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Notifications bell */}
      <div className="relative">
        <button
          onClick={openNotifications}
          className="relative w-8 h-8 rounded-lg border border-gray-200 dark:border-zinc-800/80 flex items-center justify-center text-gray-500 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
          title="Notifications"
        >
          <FontAwesomeIcon icon={faBell} className="text-xs" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>

        {panel === "notifications" && (
          <div className="absolute right-0 top-10 z-[90] w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-950/95 shadow-xl dark:shadow-black/40 backdrop-blur-sm">
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100 dark:border-zinc-800/80">
              <span className="text-sm font-semibold text-gray-900 dark:text-white shrink-0">
                Notifications{unreadCount > 0 ? <span className="ml-1.5 text-xs font-medium text-gray-400">{unreadCount} new</span> : null}
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={markAllRead}
                  disabled={unreadCount === 0}
                  className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline disabled:text-gray-400 disabled:no-underline"
                  title="Mark all read"
                >
                  <FontAwesomeIcon icon={faCheckDouble} className="text-[10px]" />
                  All read
                </button>
                <button
                  onClick={clearRead}
                  disabled={!hasRead}
                  className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-red-500 hover:underline disabled:text-gray-300 dark:disabled:text-gray-600 disabled:no-underline"
                  title="Clear read notifications"
                >
                  <FontAwesomeIcon icon={faTrashCan} className="text-[10px]" />
                  Clear
                </button>
              </div>
            </div>

            <div className="max-h-96 overflow-auto">
              {panelNotifications.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-500 px-4 py-8 text-center">No notifications</p>
              ) : (
                panelNotifications.map((notification) => {
                  const style = levelStyles[notification.level] || levelStyles.info;
                  return (
                    <div
                      key={notification.notificationId}
                      className={`group relative flex items-start gap-2.5 px-4 py-3 border-b border-gray-50 dark:border-zinc-800/60 last:border-0 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors ${notification.read ? "" : "bg-primary/[0.04]"}`}
                    >
                      <button
                        onClick={() => onNotificationClick(notification)}
                        className="min-w-0 flex-1 flex items-start gap-2.5 text-left"
                      >
                        <FontAwesomeIcon icon={style.icon} className={`mt-0.5 text-xs shrink-0 ${style.color}`} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center justify-between gap-2">
                            <span className={`text-xs truncate ${notification.read ? "font-medium text-gray-700 dark:text-gray-200" : "font-semibold text-gray-900 dark:text-white"}`}>
                              {notification.title}
                            </span>
                            <span className="text-[10px] text-gray-400 shrink-0">{relativeTime(notification.createdAt)}</span>
                          </span>
                          {notification.message && (
                            <span className="block text-[11px] leading-4 text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{notification.message}</span>
                          )}
                        </span>
                      </button>
                      {!notification.read && <span className="mt-1.5 w-2 h-2 rounded-full bg-primary shrink-0" />}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteNotification(notification);
                        }}
                        className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition"
                        title="Delete notification"
                      >
                        <FontAwesomeIcon icon={faXmark} className="text-[10px]" />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
