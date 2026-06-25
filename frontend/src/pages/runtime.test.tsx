import { render, screen, within } from "@testing-library/react";
import { useSelector } from "react-redux";
import Runtime from "./runtime";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

let mockSearch = "";
const mockSetSearchParams = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
  useSearchParams: () => [new URLSearchParams(mockSearch), mockSetSearchParams],
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Runtime page", () => {
  beforeEach(() => {
    mockSearch = "";
    mockSetSearchParams.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com" } }),
    );
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        sessions: [
          {
            sessionId: "session-1",
            prompt: "Claim session",
            email: "demo@example.com",
            workItemId: "work-1",
            matchedSkillId: "skill-1",
            matchedSkillName: "Resolve claim",
            latestActivityLabel: "Read email",
            latestActivityAt: "2026-06-25T10:02:00Z",
            actionCount: 3,
            chatCount: 1,
            hasBrowserActivity: true,
            hasConnectorActivity: true,
            browserActionCount: 2,
            connectorActionCount: 1,
            pendingApprovalCount: 1,
            artifactCount: 2,
            creditsSpent: 2.5,
            runtimeLab: {
              timeline: {
                steps: 3,
                browserSteps: 2,
                toolSteps: 1,
                replayReady: false,
              },
              toolCalls: {
                total: 1,
                approved: 0,
                pendingApproval: "smtp.send_email:0:abc",
                sample: [{ action: "imap.read_email", label: "Read email", status: "ok" }],
              },
              skillMatch: {
                matched: true,
                skillId: "skill-1",
                skillName: "Resolve claim",
              },
              approvals: {
                pending: 1,
                approvedConnectorCalls: 0,
                requiredFor: ["send"],
                hasHumanBoundary: true,
              },
              outputs: {
                artifacts: 2,
                hasBusinessOutput: true,
                creditsSpent: 2.5,
              },
            },
            runtimeAuditTrail: {
              uniform: true,
              eventCount: 5,
              approvalRequiredFor: ["send"],
              hasHumanBoundary: true,
              artifactCount: 2,
              events: [
                { event: "session.started", description: "Runtime session created." },
                { event: "artifact.created", description: "2 business artifact(s) created." },
              ],
            },
          },
          {
            sessionId: "session-2",
            prompt: "Other session",
            email: "demo@example.com",
            workItemId: "work-2",
            actionCount: 2,
            chatCount: 1,
            hasConnectorActivity: true,
            connectorActionCount: 2,
          },
        ],
      }),
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("filters runtime sessions by work item scope", async () => {
    mockSearch = "workItemId=work-1";

    render(<Runtime />);

    expect(await screen.findByText("Runtime scope active")).toBeInTheDocument();
    expect(await screen.findByText("Claim session")).toBeInTheDocument();
    expect(screen.queryByText("Other session")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open skill" })).toBeInTheDocument();
  });

  it("shows latest activity summaries from the session snapshot", async () => {
    render(<Runtime />);

    expect(await screen.findByText("Latest activity:")).toBeInTheDocument();
    expect((await screen.findAllByText("Read email")).length).toBeGreaterThan(0);
  });

  it("shows runtime action totals in the summary cards", async () => {
    render(<Runtime />);

    const runtimeActionsCard = (await screen.findByText("Runtime Actions")).closest("div");
    const browserActionsCard = (await screen.findByText("Browser Actions")).closest("div");
    const connectorActionsCard = (await screen.findByText("Connector Actions")).closest("div");

    expect(runtimeActionsCard).not.toBeNull();
    expect(browserActionsCard).not.toBeNull();
    expect(connectorActionsCard).not.toBeNull();
    expect(within(runtimeActionsCard as HTMLElement).getByText("5")).toBeInTheDocument();
    expect(within(browserActionsCard as HTMLElement).getByText("2")).toBeInTheDocument();
    expect(within(connectorActionsCard as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(await screen.findByText("2 browser actions")).toBeInTheDocument();
    expect(await screen.findByText("1 connector action")).toBeInTheDocument();
  });

  it("shows Runtime Lab evidence for replay, tools, skills, approvals and outputs", async () => {
    render(<Runtime />);

    expect(await screen.findByText("Runtime Lab evidence")).toBeInTheDocument();
    expect(await screen.findByText("Replay blocked")).toBeInTheDocument();
    expect(await screen.findByText("3 steps")).toBeInTheDocument();
    expect(await screen.findByText("1 tool call")).toBeInTheDocument();
    expect(await screen.findByText("Skill matched")).toBeInTheDocument();
    expect(await screen.findByText("1 approvals")).toBeInTheDocument();
    expect(await screen.findByText("2 artifacts · 2.50 cr")).toBeInTheDocument();
  });

  it("shows the uniform runtime audit trail", async () => {
    render(<Runtime />);

    expect(await screen.findByText("Uniform audit trail")).toBeInTheDocument();
    expect(await screen.findByText("5 events")).toBeInTheDocument();
    expect(await screen.findByText("send")).toBeInTheDocument();
    expect(await screen.findByText("2 business artifact(s) created.")).toBeInTheDocument();
  });
});
