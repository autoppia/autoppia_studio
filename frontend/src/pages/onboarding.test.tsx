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

describe("Automata onboarding chat", () => {
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

  it("opens in chat mode and submits collected context to CompanyHarvester", async () => {
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
              status: "solving_tasks",
              currentStep: "solving_tasks",
              steps: [{ key: "intaking", label: "Understanding your company", status: "done" }],
              summary: { materialsReceived: 1, recommendedNextAction: "Automata is testing tasks." },
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

    expect(await screen.findByText("Onboarding chat")).toBeInTheDocument();
    expect(screen.getByText(/Hi, I'm Automata/i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/Send docs, URLs/i);
    fireEvent.change(input, { target: { value: "Our web app is https://app.celeris.example\nTasks:\n- Answer payroll questions from docs" } });
    fireEvent.click(screen.getByLabelText("Send onboarding message"));

    expect(await screen.findByText("https://app.celeris.example")).toBeInTheDocument();
    expect(await screen.findByText("Answer payroll questions from docs")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Start onboarding/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      const intakeCall = calls.find((call) => String(call[0]).includes("/company-intakes") && call[1]?.method === "POST");
      expect(intakeCall).toBeTruthy();
      const body = JSON.parse(intakeCall[1].body);
      expect(body.companyId).toBe("company-1");
      expect(body.startHarvest).toBe(true);
      expect(body.materials).toHaveLength(1);
      expect(body.materials[0].kind).toBe("website");
      expect(body.userTasks[0].prompt).toBe("Answer payroll questions from docs");
      expect(body.runtimeKinds).toEqual(["model_agent", "codex", "claude_code"]);
    });

    expect((await screen.findAllByText("Automata is testing tasks.")).length).toBeGreaterThan(0);
  });

  it("renders normal progress for an active run", async () => {
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
                { key: "intaking", label: "Understanding your company", status: "done" },
                { key: "discovering_tasks", label: "Finding useful work", status: "in_progress" },
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

    expect(await screen.findByText("Finding useful work")).toBeInTheDocument();
    expect((await screen.findAllByText("Automata is testing tasks.")).length).toBeGreaterThan(0);
    expect(screen.getByText("Systems")).toBeInTheDocument();
    expect(screen.getAllByText("Tasks").length).toBeGreaterThan(0);
  });

  it("submits backend questions as chat answers", async () => {
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
              steps: [{ key: "intaking", label: "Understanding your company", status: "done" }],
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

    expect(await screen.findByText("Provide the URL for your web app.")).toBeInTheDocument();

    const input = screen.getByPlaceholderText("Answer Automata...");
    fireEvent.change(input, { target: { value: "https://app.celeris.example" } });
    fireEvent.click(screen.getByLabelText("Send onboarding message"));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls;
      const answerCall = calls.find((call) => String(call[0]).includes("/answers") && call[1]?.method === "POST");
      expect(answerCall).toBeTruthy();
      const body = JSON.parse(answerCall[1].body);
      expect(body.answers[0].questionId).toBe("q1");
      expect(body.answers[0].value).toBe("https://app.celeris.example");
      expect(body.continueHarvest).toBe(true);
    });
  });

  it("shows ready delivery surfaces", async () => {
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
              steps: [{ key: "building_agents", label: "Preparing agents", status: "done" }],
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

    expect(await screen.findByText("Agents ready")).toBeInTheDocument();
    expect(await screen.findByText("Celeris Agent")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Widget")).toBeInTheDocument();
    expect(screen.getByText(/runtime\/agents\/company-1:model_agent\/step/)).toBeInTheDocument();
  });

  it("shows dev details only in dev mode", async () => {
    setMode("dev");
    localStorage.setItem("automata_harvest_run_company-1", "run-1");
    mockFetch((url) => {
      if (url.includes("mode=dev")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: {
              artifacts: [{ artifactId: "a1", kind: "connector_candidate", status: "ready" }],
              devSummary: { artifactKinds: ["connector_candidate"] },
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
              status: "solving_tasks",
              currentStep: "solving_tasks",
              steps: [],
              summary: {},
              delivery: {},
              questions: [],
              nextAction: {},
              errors: [],
            },
          }),
        });
      }
      return null;
    });

    render(<Onboarding />);

    expect(await screen.findByText("Dev mode details")).toBeInTheDocument();
    expect(await screen.findByText(/connector candidate/i)).toBeInTheDocument();
  });
});
