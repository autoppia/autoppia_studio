import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import App from "./App";

jest.mock("react-redux", () => ({
  useDispatch: () => jest.fn(),
  useSelector: () => false,
}));

jest.mock("js-cookie", () => ({
  get: () => undefined,
  remove: jest.fn(),
}));

jest.mock("react-router-dom", () => ({
  BrowserRouter: ({ children }: { children: ReactNode }) => <>{children}</>,
  Routes: ({ children }: { children: ReactNode }) => <>{children}</>,
  Route: ({ element }: { element?: ReactNode }) => <>{element ?? null}</>,
  Navigate: () => null,
}), { virtual: true });

jest.mock("./redux/userSlice", () => ({
  setUser: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("./utils/auth-fetch", () => ({
  installAuthFetch: jest.fn(),
}));

jest.mock("./utils/api-url", () => ({
  getApiUrl: () => "http://localhost:8080",
}));

jest.mock("./pages/home", () => () => <div>Home</div>);
jest.mock("./pages/session", () => () => <div>Session</div>);
jest.mock("./pages/settings", () => () => <div>Settings</div>);
jest.mock("./pages/canvas", () => () => <div>Canvas</div>);
jest.mock("./pages/evals", () => () => <div>Evals</div>);
jest.mock("./pages/eval-detail", () => () => <div>EvalDetail</div>);
jest.mock("./pages/agents", () => () => <div>Agents</div>);
jest.mock("./pages/agent-detail", () => () => <div>AgentDetail</div>);
jest.mock("./pages/connectors", () => () => <div>Connectors</div>);
jest.mock("./pages/capabilities", () => () => <div>Capabilities</div>);
jest.mock("./pages/entities", () => () => <div>Entities</div>);
jest.mock("./pages/approvals", () => () => <div>Approvals</div>);
jest.mock("./pages/credentials", () => () => <div>Credentials</div>);
jest.mock("./pages/knowledge", () => () => <div>Knowledge</div>);
jest.mock("./pages/analytics", () => () => <div>Analytics</div>);
jest.mock("./pages/work", () => () => <div>Work</div>);
jest.mock("./pages/signin", () => () => <div>SignIn</div>);
jest.mock("./pages/signup", () => () => <div>SignUp</div>);
jest.mock("./pages/verify-otp", () => () => <div>VerifyOTP</div>);
jest.mock("./components/layout/main-layout", () => () => <div>MainLayout</div>);
jest.mock("./components/common/toast", () => ({
  ToastProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

test("renders the public sign-in route when no access token is present", () => {
  render(<App />);
  expect(screen.getByText("SignIn")).toBeInTheDocument();
});
