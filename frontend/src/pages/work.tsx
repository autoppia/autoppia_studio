import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBolt,
  faCheck,
  faCalendarDays,
  faCircleNodes,
  faClockRotateLeft,
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
  faLayerGroup,
  faScaleBalanced,
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

function parseDate(value?: string) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatRunCount(item: WorkItem) {
  const count = item.runHistory?.length || 0;
  if (count === 0) return "No runs yet";
  return `${count} ${count === 1 ? "run" : "runs"}`;
}

function matchedSkillSummary(item: WorkItem) {
  const names = item.operational?.latestMatchedSkillNames || [];
  if (names.length === 0) return "";
  if (names.length === 1) return names[0];
  return `${names[0]} +${names.length - 1}`;
}

function latestWorkSessionId(item: WorkItem) {
  return item.operational?.latestSessionIds?.[0] || "";
}

function firstMatchedSkillId(item: WorkItem) {
  return item.operational?.latestMatchedSkillIds?.[0] || "";
}

function firstMatchedTrajectoryId(item: WorkItem) {
  return item.operational?.latestMatchedTrajectoryIds?.[0] || "";
}

function firstMatchedToolId(item: WorkItem) {
  return item.operational?.latestToolIds?.[0] || "";
}

export default function Work() {
  const user = useSelector((state: any) => state.user);
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
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
  const sessionFilter = searchParams.get("sessionId") || "";
  const skillFilter = searchParams.get("skillId") || "";
  const trajectoryFilter = searchParams.get("trajectoryId") || "";
  const toolFilter = searchParams.get("toolId") || "";

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
      const operational = item.operational || {};
      const sessionMatch = !sessionFilter || (operational.latestSessionIds || []).includes(sessionFilter);
      const skillScopeMatch = !skillFilter || (operational.latestMatchedSkillIds || []).includes(skillFilter);
      const trajectoryScopeMatch = !trajectoryFilter || (operational.latestMatchedTrajectoryIds || []).includes(trajectoryFilter);
      const toolScopeMatch = !toolFilter || (operational.latestToolIds || []).includes(toolFilter);
      const textMatch = !q || [item.title, item.prompt, item.successCriteria || "", item.agentName || ""].join(" ").toLowerCase().includes(q);
      const agentMatch = !agentFilter || item.agentId === agentFilter || (agentFilter === "all" && item.runTarget === "all");
      const scheduleMatch = scheduleFilter === "all" || (scheduleFilter === "scheduled" ? item.triggerType === "scheduled" : item.triggerType !== "scheduled");
      return sessionMatch && skillScopeMatch && trajectoryScopeMatch && toolScopeMatch && textMatch && agentMatch && scheduleMatch;
    });
  }, [items, search, agentFilter, scheduleFilter, sessionFilter, skillFilter, trajectoryFilter, toolFilter]);

  const grouped = useMemo(() => {
    const result: Record<WorkStatus, WorkItem[]> = { TODO: [], RUNNING: [], REVIEW: [], DONE: [], FAILED: [] };
    filteredItems.forEach((item) => result[item.status]?.push(item));
    return result;
  }, [filteredItems]);

  const selectedItem = items.find((item) => item.workItemId === selectedItemId) || null;

  useEffect(() => {
    const requestedItemId = searchParams.get("item") || "";
    if (requestedItemId && requestedItemId !== selectedItemId) {
      setSelectedItemId(requestedItemId);
      return;
    }
    if (!requestedItemId && selectedItemId) {
      setSelectedItemId("");
    }
  }, [searchParams, selectedItemId]);

  useEffect(() => {
    if (selectedItem) setDrawerDraft(selectedItem);
  }, [selectedItemId, selectedItem]);

  const orchestrationSummary = useMemo(() => {
    const now = new Date();
    const scheduledItems = items.filter((item) => item.triggerType === "scheduled");
    const dueScheduledItems = scheduledItems.filter((item) => {
      const next = parseDate(item.nextRunAt);
      return Boolean(next && next <= now && item.status !== "RUNNING");
    });
    const upcomingScheduledItems = scheduledItems
      .filter((item) => {
        const next = parseDate(item.nextRunAt);
        return Boolean(next && next > now);
      })
      .sort((left, right) => (parseDate(left.nextRunAt)?.getTime() || 0) - (parseDate(right.nextRunAt)?.getTime() || 0));
    const reviewItems = items.filter((item) => item.status === "REVIEW");
    const runningItems = items.filter((item) => item.status === "RUNNING");
    const failedItems = items.filter((item) => item.status === "FAILED");
    const totalBudget = items.reduce((sum, item) => sum + Number(item.maxBudgetCredits || item.maxCreditsPerRun || 0), 0);

    return {
      scheduledItems,
      dueScheduledItems,
      upcomingScheduledItems,
      reviewItems,
      runningItems,
      failedItems,
      totalBudget,
    };
  }, [items]);

  const openItem = (workItemId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("item", workItemId);
    setSearchParams(next);
  };

  const closeDrawer = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("item");
    setSearchParams(next);
  };

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
        <div className="flex min-h-16 items-center justify-between gap-3 border-b border-gray-200 bg-white/80 px-6 py-3 backdrop-blur-sm dark:border-dark-border dark:bg-dark-bg/80 sm:px-8 flex-shrink-0">
          <SectionTitle
            icon={faBriefcase}
            title="Work Orchestration"
            subtitle="Queue recurring work, control budgets and review runtime outcomes across your agent fleet."
          />
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setShowCreate(true)}
              className="h-9 px-3 rounded-xl bg-gradient-primary text-white text-sm font-medium shadow-glow whitespace-nowrap"
            >
              <FontAwesomeIcon icon={faPlus} className="mr-2 text-xs" />
              New Job
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-4 sm:px-6 py-5">
          {(sessionFilter || skillFilter || trajectoryFilter || toolFilter) && (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Runtime filter active</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {sessionFilter ? <>Session <span className="font-mono text-gray-700 dark:text-gray-200">{sessionFilter}</span></> : null}
                  {skillFilter ? <> {sessionFilter ? "· " : ""}Skill <span className="font-mono text-gray-700 dark:text-gray-200">{skillFilter}</span></> : null}
                  {trajectoryFilter ? <> {(sessionFilter || skillFilter) ? "· " : ""}Trajectory <span className="font-mono text-gray-700 dark:text-gray-200">{trajectoryFilter}</span></> : null}
                  {toolFilter ? <> {(sessionFilter || skillFilter || trajectoryFilter) ? "· " : ""}Tool <span className="font-mono text-gray-700 dark:text-gray-200">{toolFilter}</span></> : null}
                </p>
              </div>
              <button
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.delete("sessionId");
                  next.delete("skillId");
                  next.delete("trajectoryId");
                  next.delete("toolId");
                  setSearchParams(next);
                }}
                className="h-8 rounded-lg border border-gray-200 px-3 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:text-gray-300 dark:hover:bg-dark-bg"
              >
                Clear filter
              </button>
            </div>
          )}
          <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            {[
              {
                label: "Active jobs",
                value: orchestrationSummary.runningItems.length,
                hint: "Runs currently executing in the runtime queue.",
                icon: faBolt,
                tone: "text-primary",
              },
              {
                label: "Needs review",
                value: orchestrationSummary.reviewItems.length,
                hint: "Jobs blocked on human review or waiting approval.",
                icon: faClipboardList,
                tone: "text-amber-600 dark:text-amber-400",
              },
              {
                label: "Scheduled",
                value: orchestrationSummary.scheduledItems.length,
                hint: "Recurring jobs with an active trigger.",
                icon: faCalendarDays,
                tone: "text-gray-700 dark:text-gray-200",
              },
              {
                label: "Due now",
                value: orchestrationSummary.dueScheduledItems.length,
                hint: "Scheduled jobs whose next run window has arrived.",
                icon: faClockRotateLeft,
                tone: "text-red-500 dark:text-red-400",
              },
              {
                label: "Budget envelope",
                value: `${orchestrationSummary.totalBudget.toFixed(1)} cr`,
                hint: "Configured max budget across visible jobs.",
                icon: faScaleBalanced,
                tone: "text-gray-700 dark:text-gray-200",
              },
            ].map((card) => (
              <div key={card.label} className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">{card.label}</p>
                    <p className={`mt-2 text-2xl font-semibold ${card.tone}`}>{card.value}</p>
                    <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{card.hint}</p>
                  </div>
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gray-50 text-gray-500 dark:bg-dark-bg dark:text-gray-300">
                    <FontAwesomeIcon icon={card.icon} className="text-sm" />
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
            <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Schedule queue</p>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Recurring jobs ordered by next run time. Due jobs should start from the worker loop without manual intervention.
                  </p>
                </div>
                <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 px-2 text-xs font-semibold text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  {orchestrationSummary.scheduledItems.length}
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {orchestrationSummary.scheduledItems.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                    No recurring jobs configured yet.
                  </div>
                ) : orchestrationSummary.upcomingScheduledItems.slice(0, 4).map((item) => (
                  <button
                    key={item.workItemId}
                    onClick={() => openItem(item.workItemId)}
                    className="w-full rounded-xl border border-gray-200 bg-gray-50 p-4 text-left transition-colors hover:border-primary/30 dark:border-dark-border dark:bg-dark-bg"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{item.title}</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {item.scheduleFrequency} at {item.scheduleTime || "09:00"} UTC
                        </p>
                      </div>
                      <StatusBadge status={item.status} />
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      <span className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                        next {formatDate(item.nextRunAt)}
                      </span>
                      <span className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300">
                        {item.maxBudgetCredits || item.maxCreditsPerRun} cr
                      </span>
                    </div>
                  </button>
                ))}
                {orchestrationSummary.dueScheduledItems.length > 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10">
                    <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
                      {orchestrationSummary.dueScheduledItems.length} due {orchestrationSummary.dueScheduledItems.length === 1 ? "job" : "jobs"}
                    </p>
                    <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                      These jobs are ready for the scheduled worker tick or need attention if they stay idle.
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Review queue</p>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Jobs that need human judgement, approval follow-up or failure triage before they can be trusted.
                  </p>
                </div>
                <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 px-2 text-xs font-semibold text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                  {orchestrationSummary.reviewItems.length + orchestrationSummary.failedItems.length}
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {[...orchestrationSummary.reviewItems, ...orchestrationSummary.failedItems].slice(0, 5).map((item) => (
                  <button
                    key={item.workItemId}
                    onClick={() => openItem(item.workItemId)}
                    className="w-full rounded-xl border border-gray-200 bg-gray-50 p-4 text-left transition-colors hover:border-primary/30 dark:border-dark-border dark:bg-dark-bg"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{item.title}</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                          {item.judge?.reason || item.report?.summary || "No report summary yet."}
                        </p>
                      </div>
                      <StatusBadge status={item.status} />
                    </div>
                  </button>
                ))}
                {orchestrationSummary.reviewItems.length === 0 && orchestrationSummary.failedItems.length === 0 && (
                  <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-sm text-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-gray-400">
                    No open review blockers.
                  </div>
                )}
              </div>
            </div>
          </div>

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
                          onClick={() => openItem(item.workItemId)}
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
                            {item.sourceBenchmarkId && (
                              <span className="inline-flex items-center gap-1 max-w-full px-2 py-0.5 rounded-md text-[11px] border border-gray-200 dark:border-dark-border text-gray-500 dark:text-gray-400">
                                <FontAwesomeIcon icon={faLayerGroup} className="text-[10px] shrink-0" />
                                <span className="truncate">benchmarked</span>
                              </span>
                            )}
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

                          <div className="mt-2.5 flex items-center justify-between gap-2 text-[11px] text-gray-400 dark:text-gray-500">
                            <span>{formatRunCount(item)}</span>
                            <span>{formatDate(item.updatedAt || item.createdAt)}</span>
                          </div>

                          {((item.operational?.pendingApprovalCount || 0) > 0 || (item.operational?.latestArtifactCount || 0) > 0 || matchedSkillSummary(item)) && (
                            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                              {(item.operational?.pendingApprovalCount || 0) > 0 && (
                                <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                                  {item.operational?.pendingApprovalCount} pending approvals
                                </span>
                              )}
                              {(item.operational?.latestArtifactCount || 0) > 0 && (
                                <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
                                  {item.operational?.persistedArtifactCount || item.operational?.latestArtifactCount} artifacts
                                </span>
                              )}
                              {(item.operational?.latestCreditsSpent || 0) > 0 && (
                                <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-600 dark:border-dark-border dark:bg-dark-bg dark:text-gray-300">
                                  {(item.operational?.latestCreditsSpent || 0).toFixed(2)} cr spent
                                </span>
                              )}
                              {matchedSkillSummary(item) && (
                                <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] font-medium text-primary">
                                  matched {matchedSkillSummary(item)}
                                </span>
                              )}
                              {latestWorkSessionId(item) && (
                                <button
                                  onClick={(event) => { event.stopPropagation(); navigate(`/session/${latestWorkSessionId(item)}`); }}
                                  className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-300 dark:hover:bg-dark-bg"
                                >
                                  Open runtime
                                </button>
                              )}
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
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Create a governed job for one agent or an all-agent race.</p>
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
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm" onClick={closeDrawer}>
          <div
            className="w-full max-w-xl h-full bg-white dark:bg-dark-surface border-l border-gray-200 dark:border-dark-border shadow-soft-lg overflow-auto"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 dark:border-dark-border bg-white/90 dark:bg-dark-surface/90 backdrop-blur-sm">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{selectedItem.title}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">{selectedItem.workItemId}</p>
              </div>
              <button onClick={closeDrawer} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-dark-border">
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

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Execution policy</p>
                  <div className="mt-2 space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                    <p>Target: {selectedItem.runTarget === "all" ? "All agents" : selectedItem.agentName || "Selected agent"}</p>
                    <p>Runtime: {selectedItem.browserEnabled ? selectedItem.browserMode : "API-only / browser off"}</p>
                    <p>Budget: {selectedItem.maxBudgetCredits || selectedItem.maxCreditsPerRun} credits</p>
                    <p>Judge: {selectedItem.judgeImplementation || "llm"}</p>
                  </div>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Orchestration</p>
                  <div className="mt-2 space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                    <p>Trigger: {selectedItem.triggerType || "manual"}</p>
                    <p>Next run: {selectedItem.nextRunAt ? formatDate(selectedItem.nextRunAt) : "Not scheduled"}</p>
                    <p>Last run: {selectedItem.startedAt ? formatDate(selectedItem.startedAt) : "Never"}</p>
                    <p>Status: {selectedItem.status.toLowerCase()}</p>
                  </div>
                </div>
              </div>

              {(selectedItem.sourceBenchmarkId || selectedItem.sourceTaskId) && (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Benchmark lineage</p>
                  <div className="space-y-1.5 text-xs text-gray-500 dark:text-gray-400">
                    {selectedItem.sourceBenchmarkId && <p>Benchmark: <span className="font-mono text-[11px] text-gray-700 dark:text-gray-200">{selectedItem.sourceBenchmarkId}</span></p>}
                    {selectedItem.sourceTaskId && <p>Task: <span className="font-mono text-[11px] text-gray-700 dark:text-gray-200">{selectedItem.sourceTaskId}</span></p>}
                  </div>
                  {selectedItem.sourceBenchmarkId && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => navigate(`/evals?benchmark=${encodeURIComponent(selectedItem.sourceBenchmarkId || "")}`)}
                        className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
                      >
                        Open benchmark
                      </button>
                      <button
                        onClick={() => navigate(`/eval-runs?benchmark=${encodeURIComponent(selectedItem.sourceBenchmarkId || "")}`)}
                        className="h-8 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                      >
                        Open recent runs
                      </button>
                    </div>
                  )}
                </div>
              )}

              {selectedItem.operational && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Runtime evidence</p>
                    <div className="mt-2 space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                      <p>Tool calls: {selectedItem.operational.latestToolCallCount || 0}</p>
                      <p>Artifacts: {selectedItem.operational.persistedArtifactCount || selectedItem.operational.latestArtifactCount || 0}</p>
                      <p>Approvals: {selectedItem.operational.approvalCount || 0}</p>
                      <p>Pending approvals: {selectedItem.operational.pendingApprovalCount || 0}</p>
                      <p>Credits spent: {(selectedItem.operational.latestCreditsSpent || 0).toFixed(2)}</p>
                    </div>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Matched capabilities</p>
                    <div className="mt-2 space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                      {(selectedItem.operational.latestMatchedSkillNames || []).length > 0 ? (
                        (selectedItem.operational.latestMatchedSkillNames || []).slice(0, 3).map((name) => (
                          <p key={name}>{name}</p>
                        ))
                      ) : (
                        <p>No matched skills recorded in the latest report.</p>
                      )}
                    </div>
                    {(firstMatchedSkillId(selectedItem) || firstMatchedTrajectoryId(selectedItem) || firstMatchedToolId(selectedItem)) && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {firstMatchedSkillId(selectedItem) && (
                          <button
                            onClick={() => navigate(`/capabilities/skill/${firstMatchedSkillId(selectedItem)}`)}
                            className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
                          >
                            Open skill
                          </button>
                        )}
                        {!firstMatchedSkillId(selectedItem) && firstMatchedTrajectoryId(selectedItem) && (
                          <button
                            onClick={() => navigate(`/capabilities/trajectory/${firstMatchedTrajectoryId(selectedItem)}`)}
                            className="h-8 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
                          >
                            Open trajectory
                          </button>
                        )}
                        {firstMatchedToolId(selectedItem) && (
                          <button
                            onClick={() => navigate(`/capabilities/tool/${firstMatchedToolId(selectedItem)}`)}
                            className="h-8 rounded-lg border border-gray-200 bg-white px-3 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                          >
                            Open tool
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

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

              {(selectedItem.operational?.approvalCount || 0) > 0 && (
                <button
                  onClick={() => navigate(`/approvals?status=all&workItemId=${selectedItem.workItemId}`)}
                  className="w-full h-10 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                >
                  Open approvals for this job
                </button>
              )}

              {latestWorkSessionId(selectedItem) && (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <button
                    onClick={() => navigate(`/session/${latestWorkSessionId(selectedItem)}`)}
                    className="h-10 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                  >
                    Open latest runtime session
                  </button>
                  <button
                    onClick={() => navigate(`/runtime?sessionIds=${encodeURIComponent((selectedItem.operational?.latestSessionIds || []).join(","))}`)}
                    className="h-10 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                  >
                    Open Runtime Lab
                  </button>
                  <button
                    onClick={() => navigate(`/artifacts?sessionId=${encodeURIComponent(latestWorkSessionId(selectedItem))}`)}
                    className="h-10 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-dark-border dark:bg-dark-surface dark:text-gray-200 dark:hover:bg-dark-bg"
                  >
                    Open runtime artifacts
                  </button>
                </div>
              )}

              {selectedItem.judge?.label && (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Judge</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{selectedItem.judge.label} · {selectedItem.judge.judgeType}</p>
                  <p className="text-xs leading-5 text-gray-600 dark:text-gray-300 mt-2">{selectedItem.judge.reason}</p>
                </div>
              )}

              {selectedItem.report?.summary && (
                <div className="rounded-xl border border-gray-200 dark:border-dark-border p-4">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Latest outcome</p>
                  <p className="text-xs leading-5 text-gray-600 dark:text-gray-300">{selectedItem.report.summary}</p>
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
