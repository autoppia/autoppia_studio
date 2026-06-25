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
                runTarget: "selected",
                browserEnabled: false,
                browserMode: "headless",
                maxCreditsPerRun: 1,
                status: "REVIEW",
                operational: {
                  latestMatchedSkillIds: ["skill-1"],
                  latestMatchedTrajectoryIds: ["trajectory-1"],
                  latestToolIds: ["tool-1"],
                  latestSessionIds: ["session-1"],
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
});
