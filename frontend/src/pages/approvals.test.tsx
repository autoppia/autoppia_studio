import { render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import Approvals from "./approvals";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Approvals page", () => {
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

  it("renders an empty state when approvals load successfully with no rows", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ approvals: [] }),
    }) as jest.Mock;

    render(<Approvals />);

    expect(await screen.findByText("No approvals found")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/approvals?email=demo%40example.com&companyId=company-1&status=pending"),
    );
  });

  it("does not show raw JSON when the approvals endpoint is unavailable", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => '{"detail":"Not Found"}',
    }) as jest.Mock;

    render(<Approvals />);

    expect(await screen.findByText("No approvals found")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('{"detail":"Not Found"}')).not.toBeInTheDocument();
    });
  });
});
