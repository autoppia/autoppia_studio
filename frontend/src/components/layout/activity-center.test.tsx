import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import ActivityCenter from "./activity-center";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

const mockNavigate = jest.fn();
const mockIo = jest.fn();
const mockSocket = {
  on: jest.fn(),
  off: jest.fn(),
  emit: jest.fn(),
  removeAllListeners: jest.fn(),
  disconnect: jest.fn(),
};

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

jest.mock("socket.io-client", () => ({
  io: (...args: any[]) => mockIo(...args),
}));

const mockedUseSelector = useSelector as unknown as jest.Mock;

function jsonResponse(data: any) {
  return Promise.resolve({
    ok: true,
    json: async () => data,
  });
}

describe("ActivityCenter", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockIo.mockReset();
    mockIo.mockReturnValue(mockSocket);
    mockSocket.on.mockReset();
    mockSocket.off.mockReset();
    mockSocket.emit.mockReset();
    mockSocket.removeAllListeners.mockReset();
    mockSocket.disconnect.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com", isAuthenticated: true } }),
    );
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("opens Runtime Lab from a running work item using the derived runtime session", async () => {
    global.fetch = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/activity-summary?")) {
        return jsonResponse({
          status: {
            runningTasks: 1,
            queuedTasks: 0,
            reviewTasks: 0,
            doneTasks: 0,
            failedTasks: 0,
            scheduledDue: 0,
            scheduledUpcoming: 0,
            activeSessions: 1,
            evalRunsPending: 0,
            evalRunsPassed: 0,
            evalRunsFailed: 0,
            harvestersRunning: 0,
            harvestersCompleted: 0,
            harvestersFailed: 0,
          },
          running: [
            {
              workItemId: "work-42",
              title: "Handle claim",
              agentName: "Claims Agent",
              runTarget: "selected",
              startedAt: new Date().toISOString(),
              lastRunId: "run-7",
            },
          ],
          notifications: { unreadCount: 0, recent: [] },
        });
      }
      return jsonResponse({ notifications: [], unreadCount: 0 });
    }) as jest.Mock;

    render(<ActivityCenter />);

    fireEvent.click(await screen.findByTitle("Activity"));
    fireEvent.click(await screen.findByText("Handle claim"));

    expect(mockNavigate).toHaveBeenCalledWith("/runtime?sessionIds=work-work-42-run-7");
  });

  it("prefers operational runtime links over generic notification action urls", async () => {
    global.fetch = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/activity-summary?")) {
        return jsonResponse({
          status: {
            runningTasks: 0,
            queuedTasks: 0,
            reviewTasks: 0,
            doneTasks: 0,
            failedTasks: 0,
            scheduledDue: 0,
            scheduledUpcoming: 0,
            activeSessions: 1,
            evalRunsPending: 0,
            evalRunsPassed: 0,
            evalRunsFailed: 0,
            harvestersRunning: 0,
            harvestersCompleted: 0,
            harvestersFailed: 0,
          },
          running: [],
          notifications: {
            unreadCount: 1,
            recent: [
              {
                notificationId: "notif-1",
                title: "Claim run completed",
                message: "The asynchronous run finished.",
                level: "success",
                source: "work",
                entityType: "work_item",
                entityId: "work-42",
                actionUrl: "/work?item=work-42",
                metadata: { runId: "run-7" },
                read: false,
                createdAt: new Date().toISOString(),
              },
            ],
          },
        });
      }
      if (url.includes("/notifications?")) {
        return jsonResponse({
          notifications: [
            {
              notificationId: "notif-1",
              title: "Claim run completed",
              message: "The asynchronous run finished.",
              level: "success",
              source: "work",
              entityType: "work_item",
              entityId: "work-42",
              actionUrl: "/work?item=work-42",
              metadata: { runId: "run-7" },
              read: false,
              createdAt: new Date().toISOString(),
            },
          ],
          unreadCount: 1,
        });
      }
      if (url.includes("/notifications/notif-1/read")) {
        return jsonResponse({ success: true });
      }
      return jsonResponse({});
    }) as jest.Mock;

    render(<ActivityCenter />);

    fireEvent.click(await screen.findByTitle("Notifications"));
    fireEvent.click(await screen.findByText("Claim run completed"));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/runtime?sessionIds=work-work-42-run-7");
    });
  });

  it("keeps scoped approval notifications on the approvals surface", async () => {
    global.fetch = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/activity-summary?")) {
        return jsonResponse({
          status: {
            runningTasks: 0,
            queuedTasks: 0,
            reviewTasks: 0,
            doneTasks: 0,
            failedTasks: 0,
            scheduledDue: 0,
            scheduledUpcoming: 0,
            activeSessions: 1,
            evalRunsPending: 0,
            evalRunsPassed: 0,
            evalRunsFailed: 0,
            harvestersRunning: 0,
            harvestersCompleted: 0,
            harvestersFailed: 0,
          },
          running: [],
          notifications: {
            unreadCount: 1,
            recent: [
              {
                notificationId: "notif-approval-1",
                title: "Approve send",
                message: "Confirm send.",
                level: "warning",
                source: "approval",
                entityType: "approval",
                entityId: "approval-1",
                actionUrl: "/approvals?status=pending&sessionId=session-42",
                metadata: { sessionId: "session-42", runId: "run-9", sourceKind: "session" },
                read: false,
                createdAt: new Date().toISOString(),
              },
            ],
          },
        });
      }
      if (url.includes("/notifications?")) {
        return jsonResponse({
          notifications: [
            {
              notificationId: "notif-approval-1",
              title: "Approve send",
              message: "Confirm send.",
              level: "warning",
              source: "approval",
              entityType: "approval",
              entityId: "approval-1",
              actionUrl: "/approvals?status=pending&sessionId=session-42",
              metadata: { sessionId: "session-42", runId: "run-9", sourceKind: "session" },
              read: false,
              createdAt: new Date().toISOString(),
            },
          ],
          unreadCount: 1,
        });
      }
      if (url.includes("/notifications/notif-approval-1/read")) {
        return jsonResponse({ success: true });
      }
      return jsonResponse({});
    }) as jest.Mock;

    render(<ActivityCenter />);

    fireEvent.click(await screen.findByTitle("Notifications"));
    fireEvent.click(await screen.findByText("Approve send"));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/approvals?status=pending&sessionId=session-42");
    });
  });

  it("surfaces lifecycle navigation shortcuts inside activity", async () => {
    global.fetch = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/activity-summary?")) {
        return jsonResponse({
          status: {
            runningTasks: 1,
            queuedTasks: 2,
            reviewTasks: 3,
            doneTasks: 0,
            failedTasks: 1,
            scheduledDue: 1,
            scheduledUpcoming: 2,
            activeSessions: 4,
            evalRunsPending: 2,
            evalRunsPassed: 0,
            evalRunsFailed: 1,
            harvestersRunning: 1,
            harvestersCompleted: 0,
            harvestersFailed: 0,
          },
          running: [],
          notifications: { unreadCount: 0, recent: [] },
        });
      }
      return jsonResponse({});
    }) as jest.Mock;

    render(<ActivityCenter />);

    fireEvent.click(await screen.findByTitle("Activity"));
    expect(await screen.findByText("Operating surfaces")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Capability Factory/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/capabilities");

    fireEvent.click(await screen.findByTitle("Activity"));
    fireEvent.click(screen.getByRole("button", { name: /Company Setup/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/setup/company");
  });
});
