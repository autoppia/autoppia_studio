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
              resourceMap: {
                documents: {
                  total: 5,
                  indexed: 4,
                  withResourceContract: 5,
                  withVectorStore: 4,
                  acl: {
                    withAcl: 5,
                    companyVisible: 5,
                    restricted: 0,
                    visibility: [{ name: "company", count: 5 }],
                    roles: ["claims"],
                    users: [],
                  },
                  status: [{ name: "indexed", count: 4 }],
                  readTools: ["knowledge.claims.search", "knowledge.claims.read_document"],
                  runtimeGate: {
                    ready: 4,
                    blocked: 1,
                    states: [{ name: "ready", count: 4 }, { name: "blocked", count: 1 }],
                    blockers: [{ name: "acl", count: 1 }],
                  },
                  sample: [
                    {
                      documentId: "doc-1",
                      resourceId: "resource-1",
                      name: "claims-policy.pdf",
                      resourceKind: "document",
                      status: "indexed",
                      vectorDatabaseId: "vec-1",
                      aclVisibility: "company",
                      readTools: ["knowledge.claims.search"],
                      runtimeGate: { state: "ready", readyForRuntime: true, blockers: [] },
                    },
                  ],
                },
                vectorStores: {
                  total: 1,
                  linked: 1,
                  collections: ["claims-knowledge"],
                },
                gaps: [],
              },
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
                sessionContracts: {
                  total: 7,
                  withContract: 5,
                  selectedSkill: 3,
                  pendingApprovals: 2,
                  artifactOutputs: 4,
                  traceIds: 9,
                  replayReady: 2,
                  creditsSpent: 6.5,
                  runtimeKinds: [{ name: "hybrid", count: 4 }],
                },
                artifacts: 5,
                pendingApprovals: 2,
                approvedApprovals: 4,
                workItems: 6,
                runningWorkItems: 1,
                reviewWorkItems: 2,
              },
              runtimePolicyMap: {
                defaultBrowserUse: "exception",
                browserRestrictedByDomain: true,
                runtimeClasses: {
                  declared: [{ name: "hybrid", count: 2 }],
                  observed: [{ name: "hybrid_runtime", count: 4 }],
                  apiCapabilities: 6,
                  browserCapabilities: 2,
                  browserSessions: 4,
                },
                approvalBoundaries: {
                  skills: [{ name: "write", count: 2 }],
                  tools: [{ name: "write", count: 4 }],
                  all: [{ name: "write", count: 6 }],
                },
                humanApproval: {
                  pending: 2,
                  approved: 4,
                  writesProtected: true,
                  sendsProtected: true,
                },
                gaps: [],
              },
              workOrchestration: {
                queues: {
                  total: 6,
                  byStatus: [{ name: "REVIEW", count: 2 }],
                  running: 1,
                  review: 2,
                  blockedByApproval: 2,
                },
                triggers: {
                  manual: 4,
                  scheduled: 2,
                  due: 1,
                  upcoming: 1,
                  frequencies: [{ name: "daily", count: 2 }],
                },
                budgets: {
                  budgetedItems: 5,
                  exhaustedItems: 1,
                  totalMaxBudgetCredits: 12,
                  latestCreditsSpent: 3.5,
                },
                retries: {
                  itemsRetried: 1,
                  maxRetryCount: 2,
                  totalRetryCount: 2,
                },
                approvalBoundary: {
                  pendingApprovals: 2,
                  workItemsBlocked: 2,
                  linkedApprovalWorkItems: 1,
                },
                sla: {
                  reviewBlocked: 2,
                  scheduledDue: 1,
                  budgetExhausted: 1,
                  needsAttention: 4,
                },
              },
              governance: {
                credentials: 3,
                allowedOrigins: ["https://erp.celeris.example"],
                allowedOriginHosts: ["erp.celeris.example"],
                hostJwtConfigured: true,
                discoveredDomains: ["erp.celeris.example"],
                skillPolicies: [{ name: "approval_required", count: 2 }],
                resourceAcl: {
                  documents: 5,
                  withAcl: 5,
                  companyVisible: 5,
                  restricted: 0,
                  visibility: [{ name: "company", count: 5 }],
                },
              },
              capabilityMap: {
                taskContracts: {
                  total: 2,
                  ready: 1,
                  coverageRatio: 0.5,
                  businessIntents: [{ name: "Respond to claim status", count: 1 }],
                  allowedSystems: ["email", "insurance_erp", "knowledge"],
                  expectedArtifacts: ["draft_email", "claim_summary"],
                  riskClasses: [{ name: "draft", count: 1 }],
                },
                benchmarks: {
                  total: 1,
                  verticals: [{ name: "insurance", count: 1 }],
                  tasks: 2,
                  evalRuns: 10,
                },
                tools: {
                  total: 8,
                  typed: 6,
                  typedRatio: 0.75,
                  sideEffects: [{ name: "read", count: 4 }],
                  mappedEntities: ["Claim", "Policy"],
                },
                skills: {
                  total: 3,
                  ready: 2,
                  hardened: 1,
                  hardenedRatio: 0.333,
                  expectedArtifacts: ["draft_email"],
                  policies: [{ name: "human_approval_for_writes", count: 1 }],
                },
                gaps: [],
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
    expect(await screen.findByText("Capability map")).toBeInTheDocument();
    expect(await screen.findByText("Resource map")).toBeInTheDocument();
    expect(await screen.findByText("Runtime policy map")).toBeInTheDocument();
    expect(await screen.findByText("Session contracts")).toBeInTheDocument();
    expect(await screen.findByText("5/7")).toBeInTheDocument();
    expect(await screen.findByText("6.5 credits")).toBeInTheDocument();
    expect(await screen.findByText("Domain restricted · 4 browser sessions")).toBeInTheDocument();
    expect(await screen.findByText("Runtime gate")).toBeInTheDocument();
    expect((await screen.findAllByText("4/5")).length).toBeGreaterThan(0);
    expect(await screen.findByText("acl 1")).toBeInTheDocument();
    expect(await screen.findByText("knowledge.claims.search, knowledge.claims.read_document")).toBeInTheDocument();
    expect(await screen.findByText("email, insurance_erp, knowledge")).toBeInTheDocument();
    expect(await screen.findByText("Work orchestration contract")).toBeInTheDocument();
    expect(await screen.findByText("1 due now")).toBeInTheDocument();
    expect(await screen.findByText("Capability Factory")).toBeInTheDocument();
    expect(await screen.findByText("Work Orchestration")).toBeInTheDocument();
    expect(await screen.findByText("Approval Surface")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /open runtime/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /open capabilities/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/capabilities");

    fireEvent.click(screen.getByRole("button", { name: /open runtime/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/runtime");

    fireEvent.click(screen.getAllByRole("button", { name: /open work/i })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/work");

    fireEvent.click(screen.getByRole("button", { name: /open approvals/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/approvals?status=pending");
  });
});
