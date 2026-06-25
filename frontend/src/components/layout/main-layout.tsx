import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useSelector } from "react-redux";
import TopBar from "./top-bar";
import SectionSubNav from "./section-subnav";
import ChatHistoryRail from "./chat-history-rail";
import AutomataAssistant from "../assistant/automata-assistant";
import { getApiUrl } from "../../utils/api-url";
import type { HistoryItem } from "../../utils/types";

const apiUrl = getApiUrl();

export default function MainLayout() {
  const user = useSelector((state: any) => state.user);
  const location = useLocation();
  const [histories, setHistories] = useState<HistoryItem[]>([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");

  const addHistoryItem = useCallback((item: HistoryItem) => {
    setHistories((prev) => [item, ...prev.filter((h) => h.sessionId !== item.sessionId)]);
  }, []);

  const loadHistories = useCallback(async () => {
    if (!user.email) return;
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const res = await fetch(`${apiUrl}/sessions?${params.toString()}`);
      const data = await res.json();
      setHistories(data.sessions || []);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, [user.email, companyId]);

  useEffect(() => {
    loadHistories();
  }, [loadHistories]);

  useEffect(() => {
    const onCleared = () => setHistories([]);
    window.addEventListener("automata-chats-cleared", onCleared);
    return () => window.removeEventListener("automata-chats-cleared", onCleared);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      setCompanyId((event as CustomEvent).detail?.companyId ?? localStorage.getItem("automata_company_id") ?? "");
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const isChatSurface =
    location.pathname === "/home" || location.pathname.startsWith("/session/");

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <TopBar />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {isChatSurface ? <ChatHistoryRail histories={histories} /> : <SectionSubNav />}
        <div className="min-w-0 flex-1 overflow-hidden">
          <Outlet context={{ sidebarExpanded: false, addHistoryItem }} />
        </div>
      </div>
      <AutomataAssistant />
    </div>
  );
}
