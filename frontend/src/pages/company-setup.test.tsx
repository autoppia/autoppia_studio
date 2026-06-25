import { fireEvent, render, screen } from "@testing-library/react";
import { useSelector } from "react-redux";
import CompanySetup from "./company-setup";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

jest.mock("../components/common/toast", () => ({
  useToast: () => ({ showToast: jest.fn() }),
}));

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Company Setup page", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com" } }),
    );
    global.fetch = jest.fn().mockImplementation((url: string) => {
      if (url.includes("/companies?")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            companies: [{ companyId: "company-1", name: "Celeris", email: "demo@example.com", industry: "Insurance" }],
          }),
        });
      }
      if (url.includes("/companies/company-1/setup-contract")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            company: {
              companyId: "company-1",
              name: "Celeris",
              email: "demo@example.com",
              industry: "Insurance",
              embedSettings: { enabled: true, allowedOrigins: ["https://erp.celeris.example"], hostJwtConfigured: true, publicToken: "pk_demo" },
            },
            contract: {
              integrationContractVersion: "1",
              profile: { companyId: "company-1", name: "Celeris", industry: "Insurance", description: "Claims operations", status: "active" },
              systems: {
                summary: { totalConnectors: 4, connectedConnectors: 3, connectorsNeedingAuth: 1, customConnectors: 1 },
                categoryCoverage: [{ name: "email", count: 1 }],
                surfaceCoverage: [{ name: "api", count: 2 }],
                connectors: [],
              },
              context: { resources: 5, vectorStores: 1, entities: 4, typedTools: 8 },
              factory: {
                agents: 2,
                tools: 8,
                benchmarks: 2,
                benchmarkTasks: 6,
                evals: 6,
                evalRuns: 10,
                trajectories: 5,
                approvedTrajectories: 3,
                skills: 3,
                readySkills: 2,
              },
              runtime: {
                sessions: 7,
                runtimeKinds: [{ name: "hybrid_runtime", count: 4 }],
                artifacts: 5,
                pendingApprovals: 2,
                approvedApprovals: 4,
                workItems: 6,
                runningWorkItems: 1,
                reviewWorkItems: 2,
              },
              governance: {
                credentials: 3,
                allowedOrigins: ["https://erp.celeris.example"],
                allowedOriginHosts: ["erp.celeris.example"],
                hostJwtConfigured: true,
                discoveredDomains: ["erp.celeris.example"],
                skillPolicies: [{ name: "approval_required", count: 2 }],
              },
            },
          }),
        });
      }
      return Promise.resolve({ ok: false, text: async () => "unexpected fetch" });
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("shows the operating graph and links into factory, runtime, work and approvals", async () => {
    render(<CompanySetup />);

    expect(await screen.findByText("Operating Graph")).toBeInTheDocument();
    expect(await screen.findByText("Capability Factory")).toBeInTheDocument();
    expect(await screen.findByText("Work Orchestration")).toBeInTheDocument();
    expect(await screen.findByText("Approval Surface")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /open runtime/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /open capabilities/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/capabilities");

    fireEvent.click(screen.getByRole("button", { name: /open runtime/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/runtime");

    fireEvent.click(screen.getByRole("button", { name: /open work/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/work");

    fireEvent.click(screen.getByRole("button", { name: /open approvals/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/approvals?status=pending");
  });
});
