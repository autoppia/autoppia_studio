import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import Approvals from "./approvals";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

let mockSearch = "";
const mockSetSearchParams = jest.fn();
const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams(mockSearch), mockSetSearchParams],
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

function renderApprovals() {
  return render(<Approvals />);
}

describe("Approvals page", () => {
  beforeEach(() => {
    mockSearch = "";
    mockSetSearchParams.mockReset();
    mockNavigate.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com" } }),
    );
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("renders an empty state when approvals load successfully with no rows", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ approvals: [] }),
    }) as jest.Mock;

    renderApprovals();

    expect(await screen.findByText("No approvals found")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/approvals?email=demo%40example.com&companyId=company-1&status=pending&includeRuntime=true"),
    );
  });

  it("does not show raw JSON when the approvals endpoint is unavailable", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => '{"detail":"Not Found"}',
    }) as jest.Mock;

    renderApprovals();

    expect(await screen.findByText("No approvals found")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('{"detail":"Not Found"}')).not.toBeInTheDocument();
    });
  });

  it("passes the session filter through to the approvals query", async () => {
    mockSearch = "sessionId=session-42&status=pending";
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ approvals: [] }),
    }) as jest.Mock;

    renderApprovals();

    expect(await screen.findByText("Runtime filter active")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/approvals?email=demo%40example.com&companyId=company-1&status=pending&includeRuntime=true&sessionId=session-42"),
    );
  });

  it("passes the work item filter through to the approvals query", async () => {
    mockSearch = "workItemId=work-42&status=all";
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ approvals: [] }),
    }) as jest.Mock;

    renderApprovals();

    expect(await screen.findByText("Runtime filter active")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/approvals?email=demo%40example.com&companyId=company-1&status=&includeRuntime=true&workItemId=work-42"),
    );
  });

  it("stores session resume state after approving a runtime session approval", async () => {
    const approval = {
      approvalId: "approval-1",
      companyId: "company-1",
      email: "demo@example.com",
      agentId: "agent-1",
      sessionId: "session-1",
      sourceKind: "session",
      approvalKey: "smtp.send_email:0:abc",
      toolName: "smtp.send_email",
      title: "Approve send",
      proposedAction: { name: "smtp.send_email", arguments: { to: "client@example.com" } },
      status: "pending",
      metadata: { sessionId: "session-1", sourceKind: "session" },
      auditTrail: [],
    };
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ approvals: [approval] }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          statePatch: { approvedConnectorToolCalls: ["smtp.send_email:0:abc"] },
          sessionResume: {
            required: true,
            sessionId: "session-1",
            runtimeStatePatch: { approvedConnectorToolCalls: ["smtp.send_email:0:abc"] },
            socketEvent: "continue-task",
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ approvals: [] }) }) as jest.Mock;

    renderApprovals();

    fireEvent.click(await screen.findByRole("button", { name: /^approve$/i }));

    expect(await screen.findByText("Approval applied to runtime session")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open session/i })).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem("approval-session-resume:session-1") || "{}")).toEqual(
      expect.objectContaining({
        approvalId: "approval-1",
        runtimeStatePatch: { approvedConnectorToolCalls: ["smtp.send_email:0:abc"] },
      }),
    );
  });

  it("opens Runtime Lab from an approval with session context", async () => {
    const approval = {
      approvalId: "approval-2",
      companyId: "company-1",
      email: "demo@example.com",
      agentId: "agent-1",
      sessionId: "session-42",
      sourceKind: "session",
      approvalKey: "gmail.send_email:0:def",
      toolName: "gmail.send_email",
      title: "Approve send",
      proposedAction: { name: "gmail.send_email", arguments: { to: "client@example.com" } },
      status: "pending",
      metadata: { sessionId: "session-42", sourceKind: "session", workItemId: "work-42" },
      auditTrail: [],
    };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ approvals: [approval] }),
    }) as jest.Mock;

    renderApprovals();

    fireEvent.click(await screen.findByRole("button", { name: "Open Runtime Lab" }));

    expect(mockNavigate).toHaveBeenCalledWith("/runtime?sessionIds=session-42");
  });
});
