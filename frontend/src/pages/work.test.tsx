import { render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import Work from "./work";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

jest.mock("../components/common/toast", () => ({
  useToast: () => ({ showToast: jest.fn() }),
}));

let mockSearch = "";
const mockSetSearchParams = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
  useSearchParams: () => [new URLSearchParams(mockSearch), mockSetSearchParams],
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Work page", () => {
  beforeEach(() => {
    mockSearch = "";
    mockSetSearchParams.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com" } }),
    );
    global.fetch = jest.fn().mockImplementation((url: string) => {
      if (url.includes("/work-boards?")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ boards: [{ boardId: "board-1", name: "Default", email: "demo@example.com", companyId: "company-1" }] }),
        });
      }
      if (url.includes("/work-items?")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            workItems: [
              {
                workItemId: "work-1",
                title: "Claim follow-up",
                prompt: "Follow up a claim",
                sourceBenchmarkId: "benchmark-1",
                sourceTaskId: "task-1",
                runTarget: "selected",
                browserEnabled: false,
                browserMode: "headless",
                maxCreditsPerRun: 1,
                status: "REVIEW",
                operational: {
                  pendingApprovalCount: 1,
                  latestArtifactCount: 2,
                  persistedArtifactCount: 2,
                  latestToolCallCount: 3,
                  latestCreditsSpent: 1.5,
                  latestMatchedSkillIds: ["skill-1"],
                  latestMatchedSkillNames: ["Resolve claim"],
                  latestMatchedTrajectoryIds: ["trajectory-1"],
                  latestToolIds: ["tool-1"],
                  latestSessionIds: ["session-1", "session-1b"],
                  orchestration: {
                    sla: { state: "blocked", deadlineState: "overdue", dueAt: "2026-01-01T00:00:00+00:00", overdueMinutes: 42, needsAttention: true },
                    schedule: { deadlineState: "overdue" },
                    budget: { remainingCredits: 0, exhausted: true },
                    automationGate: {
                      state: "blocked",
                      canRunUnattended: false,
                      blockers: ["pending_approval"],
                      nextActions: ["Resolve pending approvals before allowing unattended execution."],
                    },
                  },
                },
              },
              {
                workItemId: "work-2",
                title: "Other workflow",
                prompt: "Other task",
                runTarget: "selected",
                browserEnabled: false,
                browserMode: "headless",
                maxCreditsPerRun: 1,
                status: "TODO",
                operational: {
                  latestArtifactCount: 1,
                  persistedArtifactCount: 1,
                  latestToolCallCount: 2,
                  latestMatchedSkillIds: ["skill-2"],
                  latestMatchedTrajectoryIds: ["trajectory-2"],
                  latestToolIds: ["tool-2"],
                  latestSessionIds: ["session-2"],
                },
              },
            ],
          }),
        });
      }
      if (url.includes("/agents?")) {
        return Promise.resolve({ ok: true, json: async () => ({ agents: [] }) });
      }
      if (url.includes("/evals?")) {
        return Promise.resolve({ ok: true, json: async () => ({ evals: [] }) });
      }
      if (url.includes("/work-judges")) {
        return Promise.resolve({ ok: true, json: async () => ({ judges: [] }) });
      }
      return Promise.resolve({ ok: false, text: async () => "unexpected fetch" });
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("filters visible jobs by capability scope from query params", async () => {
    mockSearch = "skillId=skill-1";

    render(<Work />);

    expect(await screen.findByText("Runtime filter active")).toBeInTheDocument();
    expect((await screen.findAllByText("Claim follow-up")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.queryByText("Other workflow")).not.toBeInTheDocument();
    });
  });

  it("shows reverse capability links from the selected work item", async () => {
    mockSearch = "item=work-1";

    render(<Work />);

    expect((await screen.findAllByText("Claim follow-up")).length).toBeGreaterThan(0);
    expect(await screen.findByRole("button", { name: "Open skill" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open tool" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open benchmark" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open recent runs" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open Runtime Lab" })).toBeInTheDocument();
  });

  it("surfaces runtime evidence in orchestration summaries and job cards", async () => {
    render(<Work />);

    expect(await screen.findByText("Runtime sessions")).toBeInTheDocument();
    expect(await screen.findByText("Pending approvals")).toBeInTheDocument();
    expect(await screen.findByText("Artifacts")).toBeInTheDocument();
    expect(await screen.findByText("Tool calls")).toBeInTheDocument();
    expect(await screen.findByText("Overdue SLA")).toBeInTheDocument();
    expect(await screen.findByText("2 runtime sessions")).toBeInTheDocument();
    expect(await screen.findByText("3 tool calls")).toBeInTheDocument();
    expect(await screen.findByText("1 pending approvals")).toBeInTheDocument();
    expect(await screen.findByText("2 artifacts")).toBeInTheDocument();
    expect(await screen.findByText("42 min overdue")).toBeInTheDocument();
    expect(await screen.findByText("gate blocked")).toBeInTheDocument();
  });
});
