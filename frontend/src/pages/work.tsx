import React, { useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBolt,
  faCheck,
  faCalendarDays,
  faCircleNodes,
  faClipboardList,
  faHouse,
  faMagnifyingGlass,
  faPlus,
  faRobot,
  faRotateRight,
  faSpinner,
  faTrash,
  faTriangleExclamation,
  faXmark,
  faBriefcase,
} from "@fortawesome/free-solid-svg-icons";
import { AgentConfig, EvalItem, WorkBoard, WorkItem, WorkRunTarget, WorkStatus } from "../utils/types";
import SectionTitle from "../components/layout/section-title";
import { useToast } from "../components/common/toast";
import { apiErrorMessage } from "../utils/api-error";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

const columns: Array<{ status: WorkStatus; label: string; tone: string }> = [
  { status: "TODO", label: "Backlog", tone: "text-gray-500" },
  { status: "RUNNING", label: "Running", tone: "text-primary" },
  { status: "REVIEW", label: "Review", tone: "text-amber-600 dark:text-amber-400" },
  { status: "DONE", label: "Done", tone: "text-green-600 dark:text-green-400" },
  { status: "FAILED", label: "Failed", tone: "text-red-500 dark:text-red-400" },
];

function StatusBadge({ status }: { status: WorkStatus | string }) {
  const styles: Record<string, string> = {
    TODO: "bg-gray-100 dark:bg-dark-border text-gray-500 border-gray-200 dark:border-dark-border",
    RUNNING: "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/30",
    REVIEW: "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/30",
    DONE: "bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/30",
    FAILED: "bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 border-red-200 dark:border-red-500/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border ${styles[status] || styles.TODO}`}>
      {status.toLowerCase().replace("_", " ")}
    </span>
  );
}

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const emptyDraft = {
  title: "",
  prompt: "",
  successCriteria: "",
  agentId: "",
  runTarget: "all" as WorkRunTarget,
  browserEnabled: true,
  browserMode: "headless" as "visible" | "headless",
  maxCreditsPerRun: 5,
  maxBudgetCredits: 5,
  triggerType: "manual" as "manual" | "scheduled",
  scheduleFrequency: "none" as "none" | "daily" | "weekly",
  scheduleTime: "09:00",
  scheduleDayOfWeek: 1,
  sourceTaskId: "",
  sourceBenchmarkId: "",
  judgeImplementation: "llm",
};

export default function Work() {
  const user = useSelector((state: any) => state.user);
  const { showToast } = useToast();
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");
  const [boards, setBoards] = useState<WorkBoard[]>([]);
  const [activeBoardId, setActiveBoardId] = useState(localStorage.getItem("automata_work_board_id") || "");
  const [items, setItems] = useState<WorkItem[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [benchmarkTasks, setBenchmarkTasks] = useState<EvalItem[]>([]);
  const [judges, setJudges] = useState<Array<{ name: string; label?: string; description?: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [expandedReportId, setExpandedReportId] = useState("");
  const [newBoardName, setNewBoardName] = useState("");
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [scheduleFilter, setScheduleFilter] = useState("all");
  const [draggedItemId, setDraggedItemId] = useState("");
  const [dragOverStatus, setDragOverStatus] = useState<WorkStatus | "">("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [drawerDraft, setDrawerDraft] = useState<Partial<WorkItem>>({});
  const [draft, setDraft] = useState(emptyDraft);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.companyId || localStorage.getItem("automata_company_id") || "";
      setCompanyId(next);
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  const loadData = async () => {
    if (!user.email) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ email: user.email });
      if (companyId) params.set("companyId", companyId);
      const boardsRes = await fetch(`${apiUrl}/work-boards?${params.toString()}`);
      if (!boardsRes.ok) throw new Error(await boardsRes.text());
      const boardsData = await boardsRes.json();
      const loadedBoards: WorkBoard[] = boardsData.boards || [];
      const nextBoardId = activeBoardId && loadedBoards.some((board) => board.boardId === activeBoardId)
        ? activeBoardId
        : loadedBoards[0]?.boardId || "";
      if (nextBoardId && nextBoardId !== activeBoardId) {
        setActiveBoardId(nextBoardId);
        localStorage.setItem("automata_work_board_id", nextBoardId);
      }
      const itemParams = new URLSearchParams(params);
      if (nextBoardId) itemParams.set("boardId", nextBoardId);
      const [itemsRes, agentsRes, evalsRes, judgesRes] = await Promise.all([
        fetch(`${apiUrl}/work-items?${itemParams.toString()}`),
        fetch(`${apiUrl}/agents?${params.toString()}`),
        fetch(`${apiUrl}/evals?${params.toString()}`),
        fetch(`${apiUrl}/work-judges`),
      ]);
      if (!itemsRes.ok) throw new Error(await itemsRes.text());
      const itemsData = await itemsRes.json();
      const agentsData = agentsRes.ok ? await agentsRes.json() : { agents: [] };
      const evalsData = evalsRes.ok ? await evalsRes.json() : { evals: [] };
      const judgesData = judgesRes.ok ? await judgesRes.json() : { judges: [] };
      setBoards(loadedBoards);
      setItems(itemsData.workItems || []);
      setAgents(agentsData.agents || []);
      setBenchmarkTasks(evalsData.evals || []);
      setJudges(judgesData.judges || []);
    } catch (err) {
      console.error("Failed to load work board:", err);
      showToast("Could not load work board.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.email, companyId, activeBoardId]);

  useEffect(() => {
    if (!items.some((item) => item.status === "RUNNING")) return;
    const timer = window.setInterval(loadData, 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      const textMatch = !q || [item.title, item.prompt, item.successCriteria || "", item.agentName || ""].join(" ").toLowerCase().includes(q);
      const agentMatch = !agentFilter || item.agentId === agentFilter || (agentFilter === "all" && item.runTarget === "all");
      const scheduleMatch = scheduleFilter === "all" || (scheduleFilter === "scheduled" ? item.triggerType === "scheduled" : item.triggerType !== "scheduled");
      return textMatch && agentMatch && scheduleMatch;
    });
  }, [items, search, agentFilter, scheduleFilter]);

  const grouped = useMemo(() => {
    const result: Record<WorkStatus, WorkItem[]> = { TODO: [], RUNNING: [], REVIEW: [], DONE: [], FAILED: [] };
    filteredItems.forEach((item) => result[item.status]?.push(item));
    return result;
  }, [filteredItems]);

  const selectedItem = items.find((item) => item.workItemId === selectedItemId) || null;

  useEffect(() => {
    if (selectedItem) setDrawerDraft(selectedItem);
  }, [selectedItemId, selectedItem]);

  const responseMessage = (res: Response, fallback: string) => apiErrorMessage(res, fallback, "this work item");

  const createItem = async () => {
    if (!draft.title.trim() || !draft.prompt.trim() || saving) return;
    setSaving(true);
    try {
      const agent = agents.find((item) => item.agentId === draft.agentId);
      const res = await fetch(`${apiUrl}/work-items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          companyId,
          boardId: activeBoardId,
          title: draft.title.trim(),
          prompt: draft.prompt.trim(),
          successCriteria: draft.successCriteria.trim(),
          agentId: draft.runTarget === "selected" ? draft.agentId : "",
          agentName: draft.runTarget === "selected" ? agent?.name || "" : "",
          runTarget: draft.runTarget,
          browserEnabled: draft.browserEnabled,
          browserMode: draft.browserMode,
          maxCreditsPerRun: draft.maxCreditsPerRun,
          maxBudgetCredits: draft.maxBudgetCredits,
          triggerType: draft.triggerType,
          scheduleFrequency: draft.triggerType === "scheduled" ? draft.scheduleFrequency : "none",
          scheduleTime: draft.scheduleTime,
          scheduleDayOfWeek: draft.scheduleDayOfWeek,
          sourceTaskId: draft.sourceTaskId,
          sourceBenchmarkId: draft.sourceBenchmarkId,
          judgeImplementation: draft.judgeImplementation,
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not create work item."));
      setDraft(emptyDraft);
      setShowCreate(false);
      await loadData();
      showToast("Work item created.", "success");
    } catch (err) {
      console.error("Failed to create work item:", err);
      showToast(err instanceof Error ? err.message : "Could not create work item.", "error");
    } finally {
      setSaving(false);
    }
  };

  const patchItem = async (item: WorkItem, updates: Partial<WorkItem>) => {
    try {
      const res = await fetch(`${apiUrl}/work-items/${item.workItemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not update work item."));
      const data = await res.json();
      setItems((prev) => prev.map((entry) => (entry.workItemId === item.workItemId ? data.workItem : entry)));
      if (selectedItemId === item.workItemId) setDrawerDraft(data.workItem);
    } catch (err) {
      console.error("Failed to update work item:", err);
      showToast(err instanceof Error ? err.message : "Could not update work item.", "error");
    }
  };

  const rejudgeItem = async (item: WorkItem) => {
    try {
      const res = await fetch(`${apiUrl}/work-items/${item.workItemId}/rejudge`, { method: "POST" });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not rejudge work item."));
      const data = await res.json();
      setItems((prev) => prev.map((entry) => (entry.workItemId === item.workItemId ? data.workItem : entry)));
      setDrawerDraft(data.workItem);
      showToast("Work item judged again.", "success");
    } catch (err) {
      console.error("Failed to rejudge work item:", err);
      showToast(err instanceof Error ? err.message : "Could not rejudge work item.", "error");
    }
  };

  const runItem = async (item: WorkItem) => {
    if (runningId || item.status === "RUNNING") return;
    setRunningId(item.workItemId);
    try {
      const res = await fetch(`${apiUrl}/work-items/${item.workItemId}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          browserEnabled: item.browserEnabled,
          browserMode: item.browserMode,
          maxCreditsPerRun: item.maxCreditsPerRun,
        }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not run work item."));
      const data = await res.json();
      setItems((prev) => prev.map((entry) => (entry.workItemId === item.workItemId ? data.workItem : entry)));
      showToast("Work item is running.", "success");
      window.setTimeout(loadData, 1800);
    } catch (err) {
      console.error("Failed to run work item:", err);
      showToast(err instanceof Error ? err.message : "Could not run work item.", "error");
    } finally {
      setRunningId("");
    }
  };

  const createBoard = async () => {
    if (!newBoardName.trim() || saving) return;
    setSaving(true);
    try {
      const res = await fetch(`${apiUrl}/work-boards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, companyId, name: newBoardName.trim() }),
      });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not create board."));
      const data = await res.json();
      setNewBoardName("");
      setActiveBoardId(data.board.boardId);
      localStorage.setItem("automata_work_board_id", data.board.boardId);
      await loadData();
      showToast("Board created.", "success");
    } catch (err) {
      console.error("Failed to create board:", err);
      showToast(err instanceof Error ? err.message : "Could not create board.", "error");
    } finally {
      setSaving(false);
    }
  };

  const selectBenchmarkTask = (taskId: string) => {
    const task = benchmarkTasks.find((item) => item.evalId === taskId || item.taskId === taskId);
    if (!task) {
      setDraft((prev) => ({ ...prev, sourceTaskId: "", sourceBenchmarkId: "" }));
      return;
    }
    setDraft((prev) => ({
      ...prev,
      sourceTaskId: task.taskId || task.evalId,
      sourceBenchmarkId: task.benchmarkId || "",
      title: task.agentTaskName || task.prompt.slice(0, 80),
      prompt: task.prompt,
      successCriteria: task.successCriteria || prev.successCriteria,
      agentId: task.agentId || prev.agentId,
      runTarget: task.agentId ? "selected" : prev.runTarget,
    }));
  };

  const deleteItem = async (item: WorkItem) => {
    try {
      const res = await fetch(`${apiUrl}/work-items/${item.workItemId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await responseMessage(res, "Could not delete work item."));
      setItems((prev) => prev.filter((entry) => entry.workItemId !== item.workItemId));
      showToast("Work item deleted.", "success");
    } catch (err) {
      console.error("Failed to delete work item:", err);
      showToast(err instanceof Error ? err.message : "Could not delete work item.", "error");
    }
  };

  const inputClass = `w-full px-3 h-10 rounded-xl border border-gray-200 dark:border-dark-border
    bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100
    placeholder:text-gray-400 outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors`;

  const filterClass = `px-3 h-9 rounded-xl border border-gray-200 dark:border-dark-border
    bg-white dark:bg-dark-surface text-sm text-gray-700 dark:text-gray-200
    outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors`;

  const drawerLabelClass = "text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1";

  return (
    <div className="w-full h-full flex relative overflow-auto bg-gray-100 dark:bg-dark-bg">
      <div className="absolute inset-0 hidden dark:block pointer-events-none">
        <img src="/assets/images/bg/dark-bg.webp" alt="" className="w-full h-full object-cover" />
      </div>

      <div className="flex flex-col w-full h-full relative">
        <div className="flex items-center justify-between gap-3 h-14 px-4 sm:px-6 border-b border-gray-200 dark:border-dark-border bg-white/80 dark:bg-dark-bg/80 backdrop-blur-sm flex-shrink-0">
          <SectionTitle
            icon={faBriefcase}
            title={boards.find((board) => board.boardId === activeBoardId)?.name || "Work Board"}
            subtitle="Assign work to one agent or race all agents, then review the report."
          />
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setShowCreate(true)}
              className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow whitespace-nowrap"
            >
              <FontAwesomeIcon icon={faPlus} className="mr-2 text-xs" />
              New Work
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-4 sm:px-6 py-5">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-5">
            <div className="flex flex-wrap items-center gap-2">
              {boards.map((board) => (
                <button
                  key={board.boardId}
                  onClick={() => {
                    setActiveBoardId(board.boardId);
                    localStorage.setItem("automata_work_board_id", board.boardId);
                  }}
                  className={`h-9 px-3 rounded-xl text-sm font-medium border transition-colors inline-flex items-center gap-2 ${activeBoardId === board.boardId ? "bg-gradient-primary text-white border-transparent shadow-glow" : "bg-white dark:bg-dark-surface text-gray-600 dark:text-gray-300 border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-border"}`}
                >
                  {board.name === "Default" && <FontAwesomeIcon icon={faHouse} className="text-[11px]" />}
                  {board.name}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={newBoardName}
                onChange={(event) => setNewBoardName(event.target.value)}
                placeholder="New board"
                className="w-40 px-3 h-9 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-sm text-gray-800 dark:text-gray-100 outline-none"
              />
              <button
                onClick={createBoard}
                disabled={!newBoardName.trim() || saving}
                className="h-9 px-3 rounded-xl border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-dark-surface hover:bg-gray-100 dark:hover:bg-dark-border disabled:opacity-60"
              >
                <FontAwesomeIcon icon={faPlus} className="mr-2 text-xs" />
                Board
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-5">
            <div className="relative flex-1 min-w-[180px] max-w-sm">
              <FontAwesomeIcon icon={faMagnifyingGlass} className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search cards"
                className="w-full pl-9 pr-3 h-9 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface text-sm text-gray-800 dark:text-gray-100 outline-none focus:border-gray-300 dark:focus:border-gray-600 transition-colors"
              />
            </div>
            <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)} className={`${filterClass} w-40`}>
              <option value="">All assignees</option>
              <option value="all">All agents cards</option>
              {agents.map((agent) => (
                <option key={agent.agentId} value={agent.agentId}>{agent.name}</option>
              ))}
            </select>
            <select value={scheduleFilter} onChange={(event) => setScheduleFilter(event.target.value)} className={`${filterClass} w-36`}>
              <option value="all">All triggers</option>
              <option value="manual">Manual</option>
              <option value="scheduled">Scheduled</option>
            </select>
            {(search || agentFilter || scheduleFilter !== "all") && (
              <button
                onClick={() => { setSearch(""); setAgentFilter(""); setScheduleFilter("all"); }}
                className="h-9 px-3 rounded-xl text-xs font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-border transition-colors"
              >
                <FontAwesomeIcon icon={faXmark} className="mr-1.5 text-[10px]" />
                Clear
              </button>
            )}
          </div>

          {loading ? (
            <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
              <FontAwesomeIcon icon={faSpinner} className="mr-2 animate-spin" />
              Loading work board
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3 items-start">
              {columns.map((column) => {
                const isDragOver = dragOverStatus === column.status;
                const draggedItem = items.find((entry) => entry.workItemId === draggedItemId);
                const canDrop = Boolean(draggedItem) && draggedItem?.status !== "RUNNING" && draggedItem?.status !== column.status;
                return (
                <div
                  key={column.status}
                  className={`flex flex-col rounded-2xl p-2 transition-colors ${isDragOver && canDrop ? "bg-primary/5 ring-2 ring-primary/40" : "bg-gray-200/40 dark:bg-dark-surface/30"}`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (dragOverStatus !== column.status) setDragOverStatus(column.status);
                  }}
                  onDragLeave={(event) => {
                    if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragOverStatus("");
                  }}
                  onDrop={() => {
                    const item = items.find((entry) => entry.workItemId === draggedItemId);
                    if (item && item.status !== "RUNNING" && item.status !== column.status) {
                      patchItem(item, { status: column.status });
                    }
                    setDraggedItemId("");
                    setDragOverStatus("");
                  }}
                >
                  <div className="flex items-center gap-2 px-1.5 py-1 mb-1">
                    <span className={`text-sm font-semibold ${column.tone}`}>{column.label}</span>
                    <span className="min-w-[20px] h-5 px-1.5 inline-flex items-center justify-center rounded-full bg-gray-100 dark:bg-dark-border text-[11px] font-medium text-gray-500 dark:text-gray-400">{grouped[column.status].length}</span>
                  </div>

                  <div className="space-y-2.5 min-h-[60px]">
                    {grouped[column.status].map((item) => {
                      const reportOpen = expandedReportId === item.workItemId;
                      const reportResults = item.report?.results || [];
                      const isRunning = runningId === item.workItemId || item.status === "RUNNING";
                      return (
                        <div
                          key={item.workItemId}
                          draggable={item.status !== "RUNNING"}
                          onDragStart={() => setDraggedItemId(item.workItemId)}
                          onDragEnd={() => { setDraggedItemId(""); setDragOverStatus(""); }}
                          onClick={() => setSelectedItemId(item.workItemId)}
                          className={`group bg-white dark:bg-dark-surface rounded-xl border border-gray-200 dark:border-dark-border p-3 shadow-soft hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-soft-lg transition-all ${item.status === "RUNNING" ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"} ${draggedItemId === item.workItemId ? "opacity-40" : ""}`}
                        >
                          <div className="flex items-start justify-between gap-2 mb-1.5">
                            <p className="text-sm font-semibold leading-snug text-gray-900 dark:text-white line-clamp-2 break-words">{item.title}</p>
                            <StatusBadge status={item.status} />
                          </div>

                          <p className="text-xs leading-5 text-gray-600 dark:text-gray-300 line-clamp-2">{item.prompt}</p>

                          <div className="flex flex-wrap gap-1.5 mt-2.5">
                            <span className="inline-flex items-center gap-1 max-w-full px-2 py-0.5 rounded-md text-[11px] border border-gray-200 dark:border-dark-border text-gray-500 dark:text-gray-400">
                              <FontAwesomeIcon icon={item.runTarget === "all" ? faCircleNodes : faRobot} className="text-[10px] shrink-0" />
                              <span className="truncate">{item.runTarget === "all" ? "all agents" : item.agentName || "selected agent"}</span>
                            </span>
                            <span className="px-2 py-0.5 rounded-md text-[11px] border border-gray-200 dark:border-dark-border text-gray-500 dark:text-gray-400">
                              {item.browserEnabled ? item.browserMode : "browser off"}
                            </span>
                            <span className="px-2 py-0.5 rounded-md text-[11px] border border-gray-200 dark:border-dark-border text-gray-500 dark:text-gray-400">
                              {item.maxBudgetCredits || item.maxCreditsPerRun} cr
                            </span>
                            {item.triggerType === "scheduled" && (
                              <span className="inline-flex items-center gap-1 max-w-full px-2 py-0.5 rounded-md text-[11px] border border-gray-200 dark:border-dark-border text-gray-500 dark:text-gray-400">
                                <FontAwesomeIcon icon={faCalendarDays} className="text-[10px] shrink-0" />
                                <span className="truncate">{item.scheduleFrequency}{item.nextRunAt ? ` · ${formatDate(item.nextRunAt)}` : ""}</span>
                              </span>
                            )}
                          </div>

                          {item.judge?.label && (
                            <div className="mt-2.5 rounded-lg bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border p-2.5">
                              <div className="flex items-center gap-1.5 mb-1">
                                <FontAwesomeIcon
                                  icon={item.judge.label === "success" ? faCheck : item.judge.label === "failed" ? faTriangleExclamation : faClipboardList}
                                  className={`text-xs shrink-0 ${item.judge.label === "success" ? "text-green-600" : item.judge.label === "failed" ? "text-red-500" : "text-amber-600"}`}
                                />
                                <p className="text-[11px] font-semibold text-gray-900 dark:text-white capitalize">{item.judge.label.replace("_", " ")}</p>
                              </div>
                              <p className="text-[11px] leading-4 text-gray-500 dark:text-gray-400 line-clamp-2">{item.judge.reason}</p>
                            </div>
                          )}

                          {reportResults.length > 0 && (
                            <button
                              onClick={(event) => { event.stopPropagation(); setExpandedReportId(reportOpen ? "" : item.workItemId); }}
                              className="mt-2.5 w-full h-7 rounded-lg border border-gray-200 dark:border-dark-border text-[11px] font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors"
                            >
                              {reportOpen ? "Hide report" : `View report (${reportResults.length})`}
                            </button>
                          )}

                          {reportOpen && (
                            <div className="mt-2.5 space-y-2" onClick={(event) => event.stopPropagation()}>
                              {reportResults.map((result) => (
                                <div key={`${item.workItemId}-${result.agentId}`} className="rounded-lg border border-gray-100 dark:border-dark-border p-2">
                                  <div className="flex items-center justify-between gap-2 mb-1">
                                    <p className="text-[11px] font-semibold text-gray-800 dark:text-gray-100 truncate">{result.agentName || result.agentId}</p>
                                    <span className={`text-[11px] shrink-0 ${result.status === "ok" ? "text-green-600" : "text-red-500"}`}>{result.status}</span>
                                  </div>
                                  <p className="text-[11px] leading-4 text-gray-500 dark:text-gray-400 break-words line-clamp-4">
                                    {result.error || result.result?.content || result.result?.reasoning || (Array.isArray(result.result?.tool_calls) ? result.result?.tool_calls.map((call: any) => call.name || call.action || "tool").join(", ") : "No details")}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}

                          <div className="flex items-center justify-between gap-2 mt-2.5 pt-2.5 border-t border-gray-100 dark:border-dark-border">
                            <select
                              value={item.status}
                              disabled={item.status === "RUNNING"}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => { event.stopPropagation(); patchItem(item, { status: event.target.value as WorkStatus }); }}
                              title="Move to column"
                              className="h-8 max-w-[8rem] px-2 rounded-lg border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg text-[11px] font-medium text-gray-600 dark:text-gray-300 outline-none cursor-pointer disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-dark-border transition-colors"
                            >
                              {columns.map((target) => (
                                <option key={`${item.workItemId}-${target.status}`} value={target.status}>{target.label}</option>
                              ))}
                            </select>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={(event) => { event.stopPropagation(); runItem(item); }}
                                disabled={runningId !== "" || item.status === "RUNNING" || (item.runTarget === "selected" && !item.agentId)}
                                className="w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-primary text-white disabled:opacity-50"
                                title="Run"
                              >
                                <FontAwesomeIcon icon={isRunning ? faSpinner : faBolt} className={`text-xs ${isRunning ? "animate-spin" : ""}`} />
                              </button>
                              <button
                                onClick={(event) => { event.stopPropagation(); deleteItem(item); }}
                                disabled={item.status === "RUNNING"}
                                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                                title="Delete"
                              >
                                <FontAwesomeIcon icon={faTrash} className="text-xs" />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    <button
                      onClick={() => setShowCreate(true)}
                      className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left text-[13px] font-medium text-gray-400 dark:text-gray-500 hover:bg-white/70 dark:hover:bg-dark-surface/60 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    >
                      <FontAwesomeIcon icon={faPlus} className="text-[11px]" />
                      Add a card
                    </button>
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-auto rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface shadow-soft-lg">
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">New Work Item</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Create a background task for one agent or all agents.</p>
              </div>
              <button onClick={() => setShowCreate(false)} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-border">
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <select className={inputClass} value={draft.sourceTaskId} onChange={(e) => selectBenchmarkTask(e.target.value)}>
                <option value="">Use a saved benchmark task...</option>
                {benchmarkTasks.map((task) => (
                  <option key={task.evalId} value={task.taskId || task.evalId}>
                    {(task.benchmarkName || "Benchmark") + " / " + (task.agentTaskName || task.prompt.slice(0, 80))}
                  </option>
                ))}
              </select>

              <input className={inputClass} placeholder="Title" value={draft.title} onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))} />
              <textarea
                className="w-full min-h-28 p-3 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100 outline-none resize-y"
                placeholder="Task prompt"
                value={draft.prompt}
                onChange={(e) => setDraft((prev) => ({ ...prev, prompt: e.target.value }))}
              />
              <textarea
                className="w-full min-h-20 p-3 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100 outline-none resize-y"
                placeholder="Success criteria"
                value={draft.successCriteria}
                onChange={(e) => setDraft((prev) => ({ ...prev, successCriteria: e.target.value }))}
              />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {[
                  { key: "selected" as WorkRunTarget, label: "Selected agent", desc: "Run this card with one agent." },
                  { key: "all" as WorkRunTarget, label: "All agents", desc: "Race all matching agents and compare." },
                ].map((option) => (
                  <button
                    key={option.key}
                    onClick={() => setDraft((prev) => ({ ...prev, runTarget: option.key }))}
                    className={`text-left rounded-xl border p-4 transition-colors ${draft.runTarget === option.key ? "border-primary bg-primary/5 dark:bg-primary/10" : "border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-bg"}`}
                  >
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{option.label}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{option.desc}</p>
                  </button>
                ))}
              </div>

              {draft.runTarget === "selected" && (
                <select className={inputClass} value={draft.agentId} onChange={(e) => setDraft((prev) => ({ ...prev, agentId: e.target.value }))}>
                  <option value="">Select an agent</option>
                  {agents.map((agent) => (
                    <option key={agent.agentId} value={agent.agentId}>{agent.name}</option>
                  ))}
                </select>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <label className="rounded-xl border border-gray-100 dark:border-dark-border p-4 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">Browser</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Expose browser tools.</p>
                  </div>
                  <input type="checkbox" checked={draft.browserEnabled} onChange={(e) => setDraft((prev) => ({ ...prev, browserEnabled: e.target.checked }))} className="w-4 h-4 accent-primary" />
                </label>
                <select className={inputClass} value={draft.browserMode} onChange={(e) => setDraft((prev) => ({ ...prev, browserMode: e.target.value === "visible" ? "visible" : "headless" }))}>
                  <option value="headless">Headless</option>
                  <option value="visible">Visible</option>
                </select>
                <input className={inputClass} type="number" min="0" step="0.25" value={draft.maxCreditsPerRun} onChange={(e) => setDraft((prev) => ({ ...prev, maxCreditsPerRun: Number(e.target.value) }))} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <div>
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Max task budget</p>
                  <input className={inputClass} type="number" min="0" step="0.25" value={draft.maxBudgetCredits} onChange={(e) => setDraft((prev) => ({ ...prev, maxBudgetCredits: Number(e.target.value), maxCreditsPerRun: Number(e.target.value) }))} />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Judge</p>
                  <select className={inputClass} value={draft.judgeImplementation} onChange={(e) => setDraft((prev) => ({ ...prev, judgeImplementation: e.target.value }))}>
                    {(judges.length ? judges : [{ name: "llm", label: "LLMJudge" }, { name: "deterministic_runtime_result", label: "Deterministic" }]).map((judge) => (
                      <option key={judge.name} value={judge.name}>{judge.label || judge.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Trigger</p>
                  <select className={inputClass} value={draft.triggerType} onChange={(e) => setDraft((prev) => ({ ...prev, triggerType: e.target.value === "scheduled" ? "scheduled" : "manual", scheduleFrequency: e.target.value === "scheduled" ? "daily" : "none" }))}>
                    <option value="manual">Manual</option>
                    <option value="scheduled">Scheduled</option>
                  </select>
                </div>
              </div>

              {draft.triggerType === "scheduled" && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Schedule</p>
                    <select className={inputClass} value={draft.scheduleFrequency} onChange={(e) => setDraft((prev) => ({ ...prev, scheduleFrequency: e.target.value === "weekly" ? "weekly" : "daily" }))}>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">UTC time</p>
                    <input className={inputClass} type="time" value={draft.scheduleTime} onChange={(e) => setDraft((prev) => ({ ...prev, scheduleTime: e.target.value }))} />
                  </div>
                  {draft.scheduleFrequency === "weekly" && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Day</p>
                      <select className={inputClass} value={draft.scheduleDayOfWeek} onChange={(e) => setDraft((prev) => ({ ...prev, scheduleDayOfWeek: Number(e.target.value) }))}>
                        <option value={0}>Monday</option>
                        <option value={1}>Tuesday</option>
                        <option value={2}>Wednesday</option>
                        <option value={3}>Thursday</option>
                        <option value={4}>Friday</option>
                        <option value={5}>Saturday</option>
                        <option value={6}>Sunday</option>
                      </select>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button onClick={() => setShowCreate(false)} className="h-9 px-3 rounded-xl border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-border">
                  Cancel
                </button>
                <button onClick={createItem} disabled={saving || !draft.title.trim() || !draft.prompt.trim() || (draft.runTarget === "selected" && !draft.agentId)} className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow disabled:opacity-60">
                  <FontAwesomeIcon icon={saving ? faSpinner : faPlus} className={`mr-2 text-xs ${saving ? "animate-spin" : ""}`} />
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {selectedItem && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm" onClick={() => setSelectedItemId("")}>
          <div
            className="w-full max-w-xl h-full bg-white dark:bg-dark-surface border-l border-gray-200 dark:border-dark-border shadow-soft-lg overflow-auto"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border bg-white/90 dark:bg-dark-surface/90 backdrop-blur-sm">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{selectedItem.title}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">{selectedItem.workItemId}</p>
              </div>
              <button onClick={() => setSelectedItemId("")} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-border">
                <FontAwesomeIcon icon={faXmark} className="text-xs" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <button onClick={() => runItem(selectedItem)} disabled={selectedItem.status === "RUNNING" || runningId !== ""} className="h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium disabled:opacity-60">
                  <FontAwesomeIcon icon={selectedItem.status === "RUNNING" ? faSpinner : faBolt} className={`mr-2 text-xs ${selectedItem.status === "RUNNING" ? "animate-spin" : ""}`} />
                  Run
                </button>
                <button onClick={() => rejudgeItem(selectedItem)} disabled={!selectedItem.report?.results?.length} className="h-10 rounded-xl border border-gray-200 dark:border-dark-border text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-dark-bg disabled:opacity-60">
                  <FontAwesomeIcon icon={faRotateRight} className="mr-2 text-xs" />
                  Rejudge
                </button>
              </div>

              <div>
                <p className={drawerLabelClass}>Title</p>
                <input className={inputClass} value={String(drawerDraft.title || "")} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, title: e.target.value }))} />
              </div>
              <div>
                <p className={drawerLabelClass}>Task prompt</p>
                <textarea className="w-full min-h-32 p-3 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100 outline-none resize-y" value={String(drawerDraft.prompt || "")} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, prompt: e.target.value }))} />
              </div>
              <div>
                <p className={drawerLabelClass}>Success criteria</p>
                <textarea className="w-full min-h-20 p-3 rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-sm text-gray-800 dark:text-gray-100 outline-none resize-y" placeholder="Optional" value={String(drawerDraft.successCriteria || "")} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, successCriteria: e.target.value }))} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <div>
                  <p className={drawerLabelClass}>Status</p>
                  <select className={inputClass} value={drawerDraft.status || selectedItem.status} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, status: e.target.value as WorkStatus }))}>
                    {columns.map((column) => <option key={column.status} value={column.status}>{column.label}</option>)}
                  </select>
                </div>
                <div>
                  <p className={drawerLabelClass}>Assignee</p>
                  <select className={inputClass} value={drawerDraft.runTarget || selectedItem.runTarget} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, runTarget: e.target.value as WorkRunTarget }))}>
                    <option value="all">All agents</option>
                    <option value="selected">Selected agent</option>
                  </select>
                </div>
                {(drawerDraft.runTarget || selectedItem.runTarget) === "selected" && (
                  <div>
                    <p className={drawerLabelClass}>Agent</p>
                    <select className={inputClass} value={drawerDraft.agentId || ""} onChange={(e) => {
                      const agent = agents.find((item) => item.agentId === e.target.value);
                      setDrawerDraft((prev) => ({ ...prev, agentId: e.target.value, agentName: agent?.name || "" }));
                    }}>
                      <option value="">Select an agent</option>
                      {agents.map((agent) => <option key={agent.agentId} value={agent.agentId}>{agent.name}</option>)}
                    </select>
                  </div>
                )}
                <div>
                  <p className={drawerLabelClass}>Judge</p>
                  <select className={inputClass} value={drawerDraft.judgeImplementation || selectedItem.judgeImplementation || "llm"} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, judgeImplementation: e.target.value }))}>
                    {(judges.length ? judges : [{ name: "llm", label: "LLMJudge" }]).map((judge) => <option key={judge.name} value={judge.name}>{judge.label || judge.name}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <label className="rounded-xl border border-gray-200 dark:border-dark-border px-3 h-10 flex items-center justify-between gap-3 cursor-pointer">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-200">Browser</span>
                  <input type="checkbox" checked={Boolean(drawerDraft.browserEnabled ?? selectedItem.browserEnabled)} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, browserEnabled: e.target.checked }))} className="w-4 h-4 accent-primary" />
                </label>
                <div>
                  <p className={drawerLabelClass}>Max budget (cr)</p>
                  <input className={inputClass} type="number" min="0" step="0.25" value={Number(drawerDraft.maxBudgetCredits ?? selectedItem.maxBudgetCredits ?? selectedItem.maxCreditsPerRun)} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, maxBudgetCredits: Number(e.target.value), maxCreditsPerRun: Number(e.target.value) }))} />
                </div>
                <div>
                  <p className={drawerLabelClass}>Max steps</p>
                  <input className={inputClass} type="number" min="1" max="30" value={Number(drawerDraft.maxSteps ?? selectedItem.maxSteps ?? 8)} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, maxSteps: Number(e.target.value) } as Partial<WorkItem>))} />
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <div>
                  <p className={drawerLabelClass}>Trigger</p>
                  <select className={inputClass} value={drawerDraft.triggerType || selectedItem.triggerType || "manual"} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, triggerType: e.target.value as "manual" | "scheduled", scheduleFrequency: e.target.value === "scheduled" ? (prev.scheduleFrequency || "daily") : "none" }))}>
                    <option value="manual">Manual</option>
                    <option value="scheduled">Scheduled</option>
                  </select>
                </div>
                {(drawerDraft.triggerType || selectedItem.triggerType) === "scheduled" && (
                  <>
                    <div>
                      <p className={drawerLabelClass}>Schedule</p>
                      <select className={inputClass} value={drawerDraft.scheduleFrequency || selectedItem.scheduleFrequency || "daily"} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, scheduleFrequency: e.target.value as "daily" | "weekly" }))}>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                      </select>
                    </div>
                    <div>
                      <p className={drawerLabelClass}>UTC time</p>
                      <input className={inputClass} type="time" value={drawerDraft.scheduleTime || selectedItem.scheduleTime || "09:00"} onChange={(e) => setDrawerDraft((prev) => ({ ...prev, scheduleTime: e.target.value }))} />
                    </div>
                  </>
                )}
              </div>

              <button onClick={() => patchItem(selectedItem, drawerDraft)} className="w-full h-10 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow">
                Save Changes
              </button>

              {selectedItem.judge?.label && (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Judge</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{selectedItem.judge.label} · {selectedItem.judge.judgeType}</p>
                  <p className="text-xs leading-5 text-gray-600 dark:text-gray-300 mt-2">{selectedItem.judge.reason}</p>
                </div>
              )}

              {selectedItem.report?.results?.length ? (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Report</p>
                  <div className="space-y-2">
                    {selectedItem.report.results.map((result) => (
                      <div key={`${selectedItem.workItemId}-drawer-${result.agentId}`} className="rounded-lg bg-gray-50 dark:bg-dark-bg p-3">
                        <p className="text-xs font-semibold text-gray-800 dark:text-gray-100">{result.agentName || result.agentId} · {result.status}</p>
                        <p className="text-[11px] leading-4 text-gray-500 dark:text-gray-400 mt-1">{result.error || result.result?.content || result.result?.reasoning || `${result.stepCount || 0} steps`}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {selectedItem.runHistory?.length ? (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Run History</p>
                  <div className="space-y-2">
                    {selectedItem.runHistory.slice().reverse().map((run: any, index: number) => (
                      <p key={`${run.runId}-${index}`} className="text-xs text-gray-500 dark:text-gray-400">{formatDate(run.createdAt)} · {run.status} · {run.judge?.label || ""}</p>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
