import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import AgentResponse from "./agent-response";

jest.mock("react-markdown", () => ({ children }: { children: ReactNode }) => <div>{children}</div>);
jest.mock("remark-gfm", () => () => null);

test("shows approval pending header for human approval runs", () => {
  render(
    <AgentResponse
      role="assistant"
      state="success"
      thinking="Runtime completed"
      content="Waiting for human approval before executing smtp.send_email."
      actions={["runtime.think", "router.no_match", "api.human_approval"]}
      actionResults={[true, true, true]}
    />,
  );

  expect(screen.getByText("Waiting for approval.")).toBeInTheDocument();
  expect(screen.queryByText("Task completed successfully.")).not.toBeInTheDocument();
  expect(screen.getByText("Approval Required")).toBeInTheDocument();
});

test("shows elapsed time for runtime actions when provided", () => {
  render(
    <AgentResponse
      role="assistant"
      state="thinking"
      thinking="Running"
      actions={["runtime.think", "imap.search_emails"]}
      actionResults={[true, undefined]}
      actionTimings={[{ elapsedSeconds: 0 }, { elapsedSeconds: 1.247 }]}
      actionMetadata={[undefined, { tool: { output: { count: 0 } } }]}
    />,
  );

  expect(screen.getByText("0.0s")).toBeInTheDocument();
  expect(screen.getByText("1.2s")).toBeInTheDocument();
  expect(screen.getByText(/count/)).toBeInTheDocument();
});
