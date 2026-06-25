import { render, screen } from "@testing-library/react";
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
            actionCount: 1,
            chatCount: 1,
          },
          {
            sessionId: "session-2",
            prompt: "Other session",
            email: "demo@example.com",
            workItemId: "work-2",
            actionCount: 1,
            chatCount: 1,
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
    expect(await screen.findByText("Read email")).toBeInTheDocument();
  });
});
