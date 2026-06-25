import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { useSelector } from "react-redux";
import Artifacts from "./artifacts";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

jest.mock("react-markdown", () => ({ children }: { children: ReactNode }) => <div>{children}</div>);

let mockSearch = "";
const mockSetSearchParams = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
  useSearchParams: () => [new URLSearchParams(mockSearch), mockSetSearchParams],
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Artifacts page", () => {
  beforeEach(() => {
    mockSearch = "";
    mockSetSearchParams.mockReset();
    localStorage.setItem("automata_company_id", "company-1");
    mockedUseSelector.mockImplementation((selector: any) =>
      selector({ user: { email: "demo@example.com" } }),
    );
  });

  afterEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  it("renders an empty state when the company has no artifacts", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ artifacts: [] }),
    }) as jest.Mock;

    render(<Artifacts />);

    expect(await screen.findByText("No artifacts yet")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/companies/company-1/artifacts?email=demo%40example.com"),
    );
  });

  it("creates a new artifact from the default draft", async () => {
    const saved = {
      artifactId: "artifact-1",
      companyId: "company-1",
      email: "demo@example.com",
      title: "New artifact",
      artifactType: "markdown",
      description: "",
      content: "# New document",
      fileName: "new-artifact.md",
    };
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ artifacts: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ artifact: saved }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ artifacts: [saved] }) }) as jest.Mock;

    render(<Artifacts />);

    expect(await screen.findByText("No artifacts yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/companies/company-1/artifacts"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("passes the session filter through to the artifacts query", async () => {
    mockSearch = "sessionId=session-7";
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ artifacts: [] }),
    }) as jest.Mock;

    render(<Artifacts />);

    expect(await screen.findByText("Runtime filter active")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/companies/company-1/artifacts?email=demo%40example.com&sessionId=session-7"),
    );
  });

  it("passes capability filters through to the artifacts query", async () => {
    mockSearch = "skillId=skill-9&trajectoryId=trajectory-4&toolId=tool-2";
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ artifacts: [] }),
    }) as jest.Mock;

    render(<Artifacts />);

    expect(await screen.findByText("Runtime filter active")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/companies/company-1/artifacts?email=demo%40example.com&skillId=skill-9&trajectoryId=trajectory-4&toolId=tool-2"),
    );
  });

  it("shows runtime and work links for a persisted artifact with operational metadata", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        artifacts: [
          {
            artifactId: "artifact-1",
            companyId: "company-1",
            email: "demo@example.com",
            title: "Draft reply",
            artifactType: "markdown",
            description: "",
            content: "# Draft",
            fileName: "draft-reply.md",
            sessionId: "session-1",
            metadata: {
              workItemId: "work-1",
              skillId: "skill-1",
            },
          },
        ],
      }),
    }) as jest.Mock;

    render(<Artifacts />);

    expect(await screen.findByRole("button", { name: "Open session" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open Runtime Lab" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open job" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Open skill" })).toBeInTheDocument();
  });
});
