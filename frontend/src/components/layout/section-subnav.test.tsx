import { render, screen } from "@testing-library/react";
import SectionSubNav from "./section-subnav";

const mockNavigate = jest.fn();
let mockPathname = "/runtime";

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: mockPathname }),
}), { virtual: true });

describe("SectionSubNav", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockPathname = "/runtime";
  });

  it("shows the active group description and pages from nav config", () => {
    render(<SectionSubNav />);

    expect(screen.getByText("Runtime")).toBeInTheDocument();
    expect(screen.getByText("Governed sessions, approvals and artifacts from live execution.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sessions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approvals" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Artifacts" })).toBeInTheDocument();
  });
});
