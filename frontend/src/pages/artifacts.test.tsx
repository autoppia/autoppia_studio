import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { useSelector } from "react-redux";
import Artifacts from "./artifacts";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

jest.mock("react-markdown", () => ({ children }: { children: ReactNode }) => <div>{children}</div>);

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Artifacts page", () => {
  beforeEach(() => {
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
});
