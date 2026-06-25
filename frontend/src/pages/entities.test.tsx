import { render, screen, waitFor } from "@testing-library/react";
import { useSelector } from "react-redux";
import Entities from "./entities";

jest.mock("react-redux", () => ({
  useSelector: jest.fn(),
}));
jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

const mockedUseSelector = useSelector as unknown as jest.Mock;

describe("Entities page", () => {
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

  it("renders an empty state when the company has no entities", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ entities: [] }),
    }) as jest.Mock;

    render(<Entities />);

    expect(await screen.findByText("No entities yet")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/companies/company-1/entities?email=demo%40example.com"),
    );
  });

  it("does not show raw JSON when the entities endpoint returns 404", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => '{"detail":"Not Found"}',
    }) as jest.Mock;

    render(<Entities />);

    expect(await screen.findByText("No entities yet")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('{"detail":"Not Found"}')).not.toBeInTheDocument();
    });
  });
});
