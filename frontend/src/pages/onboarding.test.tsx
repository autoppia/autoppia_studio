import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import Onboarding from "./onboarding";

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

const COMPANY = { companyId: "company-1", name: "Celeris", email: "demo@example.com", description: "Labor advisory" };

function mockFetch(handlers: (url: string, options?: any) => any) {
  global.fetch = jest.fn().mockImplementation((url: string, options?: any) => {
    const result = handlers(url, options);
    if (result) return result;
    if (url.includes("/companies?")) {
      return Promise.resolve({ ok: true, json: async () => ({ companies: [COMPANY] }) });
    }
    return Promise.resolve({ ok: false, status: 404, text: async () => "unexpected fetch", json: async () => ({}) });
  }) as jest.Mock;
}

function setMode(mode: "normal" | "dev") {
  localStorage.setItem("automata_studio_mode", mode);
}

describe("Company onboarding page", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    localStorage.clear();
    localStorage.setItem("automata_company_id", "company-1");
    setMode("normal");
    mockedUseSelector.mockImplementation((selector: any) => selector({ user: { email: "demo@example.com" } }));
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("renders the guided wizard and submits a company intake", async () => {
    mockFetch((url, options) => {
      if (url.includes("/company-intakes") && options?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, intake: { intakeId: "intake-1" }, harvestRun: { runId: "run-1" } }) });
      }
      if (url.includes("/company-harvest-runs/run-1/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              intakeId: "intake-1",
              companyId: "company-1",
              status: "indexing_knowledge",
              currentStep: "indexing_knowledge",
              steps: [{ key: "intaking", label: "Understand uploaded company material", status: "done" }],
              summary: { materialsReceived: 1, recommendedNextAction: "Review discovered company material." },
              delivery: {},
              questions: [],
              nextAction: { kind: "review_material" },
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Tell us about your company")).toBeInTheDocument();
    expect(await screen.findByText("Add your docs, website, API & knowledge")).toBeInTheDocument();

    // Company name is prefilled from the selected company.
    const nameInput = screen.getByPlaceholderText("Acme Inc.") as HTMLInputElement;
    expect(nameInput.value).toBe("Celeris");

    // Add a website material.
    const urlInput = screen.getByPlaceholderText("https://app.yourcompany.com");
    fireEvent.change(urlInput, { target: { value: "https://app.celeris.example" } });
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));
    expect(await screen.findByText("https://app.celeris.example")).toBeInTheDocument();

    // Start onboarding -> POST /company-intakes.
    fireEvent.click(screen.getByRole("button", { name: /Start onboarding/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      const intakeCall = calls.find((c) => String(c[0]).includes("/company-intakes") && c[1]?.method === "POST");
      expect(intakeCall).toBeTruthy();
      const body = JSON.parse(intakeCall[1].body);
      expect(body.companyId).toBe("company-1");
      expect(body.startHarvest).toBe(true);
      expect(body.materials).toHaveLength(1);
      expect(body.materials[0].kind).toBe("website");
    });

    // After starting it transitions to the progress view.
    expect(await screen.findByText("Progress")).toBeInTheDocument();
  });

  it("renders normal progress and at-a-glance counts for an active run", async () => {
    localStorage.setItem("automata_harvest_run_company-1", "run-1");
    mockFetch((url) => {
      if (url.includes("/company-harvest-runs/run-1/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              intakeId: "intake-1",
              companyId: "company-1",
              status: "solving_tasks",
              currentStep: "solving_tasks",
              steps: [
                { key: "intaking", label: "Understand uploaded company material", status: "done" },
                { key: "discovering_tasks", label: "Infer useful company tasks", status: "in_progress" },
              ],
              summary: { materialsReceived: 3, systemsFound: 2, knowledgeSourcesFound: 1, taskCandidatesFound: 4, agentsReady: 0, recommendedNextAction: "Automata is testing tasks." },
              delivery: {},
              questions: [],
              nextAction: { kind: "judge_trajectories" },
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Progress")).toBeInTheDocument();
    expect(await screen.findByText("Infer useful company tasks")).toBeInTheDocument();
    expect(await screen.findByText("Automata is testing tasks.")).toBeInTheDocument();
    expect(screen.getByText("Systems")).toBeInTheDocument();
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
  });

  it("renders the conversational questions flow and submits answers", async () => {
    localStorage.setItem("automata_harvest_run_company-1", "run-1");
    mockFetch((url, options) => {
      if (url.includes("/company-harvest-runs/run-1/answers") && options?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, harvestRun: { runId: "run-1" } }) });
      }
      if (url.includes("/company-harvest-runs/run-1/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              intakeId: "intake-1",
              companyId: "company-1",
              status: "needs_user_input",
              currentStep: "needs_user_input",
              steps: [{ key: "intaking", label: "Understand uploaded company material", status: "done" }],
              summary: { materialsReceived: 1 },
              delivery: {},
              questions: [
                { questionId: "q1", code: "website_url_required", prompt: "Provide the URL for your web app.", severity: "blocking", expectedAnswerType: "url" },
              ],
              nextAction: { kind: "answer_questions" },
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Automata needs a little more")).toBeInTheDocument();
    expect(await screen.findByText("Provide the URL for your web app.")).toBeInTheDocument();

    const answerInput = screen.getByPlaceholderText("https://…");
    fireEvent.change(answerInput, { target: { value: "https://app.celeris.example" } });
    fireEvent.click(screen.getByRole("button", { name: /Send answers/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      const answerCall = calls.find((c) => String(c[0]).includes("/answers") && c[1]?.method === "POST");
      expect(answerCall).toBeTruthy();
      const body = JSON.parse(answerCall[1].body);
      expect(body.answers[0].questionId).toBe("q1");
      expect(body.answers[0].value).toBe("https://app.celeris.example");
      expect(body.continueHarvest).toBe(true);
    });
  });

  it("shows ready delivery surfaces (chat / API / widget)", async () => {
    localStorage.setItem("automata_harvest_run_company-1", "run-1");
    mockFetch((url) => {
      if (url.includes("/company-harvest-runs/run-1/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              intakeId: "intake-1",
              companyId: "company-1",
              status: "ready",
              currentStep: "ready",
              steps: [{ key: "building_agents", label: "Build deployable agent configs", status: "done" }],
              summary: { agentsReady: 1, recommendedNextAction: "Use generated company agents." },
              delivery: {
                state: "ready",
                readyAgentCount: 1,
                agents: [
                  {
                    agentId: "company-1:model_agent",
                    name: "Celeris Agent",
                    runtimeKind: "model_agent",
                    ready: true,
                    chatAvailable: true,
                    apiEndpoint: "/runtime/agents/company-1:model_agent/step",
                    widgetAvailable: true,
                    widgetEmbedScript: "/embed/v1/widget.js",
                  },
                ],
                surfaces: { chat: true, api: true, widget: true },
              },
              questions: [],
              nextAction: { kind: "use_agents" },
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Your agents are ready")).toBeInTheDocument();
    expect(await screen.findByText("Celeris Agent")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("API endpoint")).toBeInTheDocument();
    expect(screen.getByText(/\/runtime\/agents\/company-1:model_agent\/step/)).toBeInTheDocument();
  });

  it("exposes the developer raw view in dev mode", async () => {
    setMode("dev");
    localStorage.setItem("automata_harvest_run_company-1", "run-1");
    mockFetch((url) => {
      if (url.includes("/company-harvest-runs/run-1/status") && url.includes("mode=dev")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              status: "discovering_tools",
              currentStep: "discovering_tools",
              steps: [{ key: "discovering_connectors", label: "Create connector candidates", status: "done", visibility: "dev" }],
              artifacts: [
                { artifactId: "a1", kind: "connector_candidate", title: "Company API", status: "discovered", visibility: "dev", summary: "Discovered api." },
              ],
              devSummary: { plannedPipeline: ["intaking", "discovering_tools"] },
              nextAction: { kind: "review_material" },
            },
          }),
        });
      }
      if (url.includes("/company-harvest-runs/run-1/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              runId: "run-1",
              intakeId: "intake-1",
              companyId: "company-1",
              status: "discovering_tools",
              currentStep: "discovering_tools",
              steps: [{ key: "discovering_tasks", label: "Infer useful company tasks", status: "pending" }],
              summary: { materialsReceived: 2 },
              delivery: {},
              questions: [],
              nextAction: { kind: "review_material" },
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Developer view")).toBeInTheDocument();
    expect(await screen.findByText("Company API")).toBeInTheDocument();
    expect(screen.getByText("Dev summary")).toBeInTheDocument();
  });
});
