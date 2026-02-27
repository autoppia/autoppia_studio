import { useRef, useState, useCallback } from "react";
import { Outlet } from "react-router-dom";
import AppSidebar, { COLLAPSED_WIDTH, EXPANDED_WIDTH } from "./app-sidebar";
import type { AppSidebarHandle } from "./app-sidebar";
import type { HistoryItem } from "../../utils/types";

export default function MainLayout() {
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const sidebarRef = useRef<AppSidebarHandle>(null);

  const addHistoryItem = useCallback((item: HistoryItem) => {
    sidebarRef.current?.addHistoryItem(item);
  }, []);

  return (
    <div className="w-screen h-screen flex overflow-hidden">
      <AppSidebar ref={sidebarRef} onExpandChange={setSidebarExpanded} />
      <div
        className="flex-grow h-full transition-all duration-300 overflow-hidden"
        style={{ marginLeft: sidebarExpanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH }}
      >
        <Outlet context={{ sidebarExpanded, addHistoryItem }} />
      </div>
    </div>
  );
}
