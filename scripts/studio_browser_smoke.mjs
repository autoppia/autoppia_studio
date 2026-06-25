#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createHmac } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FRONTEND_URL = process.env.STUDIO_FRONTEND_URL || "http://127.0.0.1:3000";
const API_URL = process.env.STUDIO_API_URL || "http://127.0.0.1:8080";
const EMAIL = process.env.STUDIO_SMOKE_EMAIL || "demo@autoppia.com";
const COMPANY_ID = process.env.STUDIO_SMOKE_COMPANY_ID || "deae345c-8e98-42ec-a517-267b47f1488a";
const CHROME = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const DEBUG_PORT = Number(process.env.CHROME_DEBUG_PORT || 9333);
const JWT_SECRET = process.env.JWT_SECRET || "autoppia-automata-secret-key";

function base64url(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function signedJwt(payload) {
  const header = base64url({ alg: "HS256", typ: "JWT" });
  const body = base64url(payload);
  const signature = createHmac("sha256", JWT_SECRET).update(`${header}.${body}`).digest("base64url");
  return `${header}.${body}.${signature}`;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${options.method || "GET"} ${path} failed ${response.status}: ${text.slice(0, 500)}`);
  }
  return response.json();
}

async function seedSession() {
  const sessionId = `browser-smoke-${Date.now()}`;
  await api("/sessions/save", {
    method: "POST",
    body: JSON.stringify({
      sessionId,
      email: EMAIL,
      prompt: "Busca emails recientes sin usar browser.",
      initialUrl: "",
      chatHistory: [
        { role: "user", content: "Busca emails recientes sin usar browser." },
        {
          role: "assistant",
          state: "success",
          thinking: "Runtime completed",
          content: "No emails found. Completed in 0.2s.",
          actions: ["runtime.think", "router.no_match", "imap.search_emails"],
          actionResults: [true, true, true],
          actionTimings: [{ elapsedSeconds: 0 }, { elapsedSeconds: 0.1 }, { elapsedSeconds: 0.2 }],
          actionMetadata: [
            null,
            { router: { decision: "no_safe_match", reason: "No approved trajectory matched safely.", fallbackRuntime: "local_email_agent" } },
            { tool: { output: { count: 0, folder: "INBOX" } } },
          ],
          artifacts: [],
        },
      ],
      runtimeState: {},
      agentId: "e6908921-2df5-418d-8e2e-9d4c4ea5a4ac",
      agentName: "Email Connector Runtime Benchmark Agent",
    }),
  });
  await api(`/sessions/${sessionId}/artifacts`, {
    method: "POST",
    body: JSON.stringify({
      email: EMAIL,
      companyId: COMPANY_ID,
      title: "Mailbox summary",
      artifactType: "csv",
      content: "subject,from\nInvoice,client@example.com",
      fileName: "mailbox-summary.csv",
    }),
  });
  return sessionId;
}

async function waitFor(fn, timeoutMs = 10000, intervalMs = 250) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const result = await fn();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw lastError || new Error(`Timed out after ${timeoutMs}ms`);
}

async function startChrome() {
  const userDataDir = await mkdtemp(join(tmpdir(), "studio-browser-smoke-"));
  const child = spawn(CHROME, [
    "--headless=new",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${userDataDir}`,
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  await waitFor(async () => {
    const response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/version`).catch(() => null);
    return response?.ok;
  }, 10000);
  return { child, userDataDir, stderr: () => stderr };
}

async function newTarget() {
  let response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?about:blank`, { method: "PUT" });
  if (!response.ok) response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?about:blank`);
  if (!response.ok) throw new Error(`Could not create Chrome target: ${response.status}`);
  return response.json();
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("CDP websocket timeout")), 10000);
      this.ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result || {});
        return;
      }
      if (message.method && this.events.has(message.method)) {
        for (const handler of this.events.get(message.method)) handler(message.params || {});
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }

  on(method, handler) {
    if (!this.events.has(method)) this.events.set(method, []);
    this.events.get(method).push(handler);
  }

  close() {
    this.ws?.close();
  }
}

async function main() {
  const sessionId = await seedSession();
  const chrome = await startChrome();
  const target = await newTarget();
  const cdp = new Cdp(target.webSocketDebuggerUrl);
  const checks = [];
  const consoleErrors = [];
  const requestFailures = [];
  const observedRequests = [];

  try {
    await cdp.connect();
    cdp.on("Runtime.exceptionThrown", (event) => consoleErrors.push(event.exceptionDetails?.text || "Runtime exception"));
    cdp.on("Log.entryAdded", (event) => {
      if (event.entry?.level === "error") consoleErrors.push(event.entry.text);
    });
    cdp.on("Network.loadingFailed", (event) => requestFailures.push(`${event.requestId} ${event.errorText}`));
    cdp.on("Network.requestWillBeSent", (event) => {
      if (event.request?.url?.includes("/sessions/")) observedRequests.push(`${event.request.method} ${event.request.url}`);
    });
    cdp.on("Network.responseReceived", (event) => {
      if (event.response?.status >= 500) requestFailures.push(`${event.response.status} ${event.response.url}`);
    });
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Network.enable");
    await cdp.send("Log.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 950,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send("Network.setCookie", {
      name: "access_token",
      value: signedJwt({ email: EMAIL, exp: Math.floor(Date.now() / 1000) + 3600 }),
      url: FRONTEND_URL,
      path: "/",
      expires: Math.floor(Date.now() / 1000) + 3600,
    });
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `
        localStorage.setItem("automata_company_id", ${JSON.stringify(COMPANY_ID)});
        localStorage.setItem("automata_last_email", ${JSON.stringify(EMAIL)});
      `,
    });

    async function evaluate(expression) {
      const result = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "Evaluation failed");
      return result.result?.value;
    }

    async function navigate(path) {
      await cdp.send("Page.navigate", { url: `${FRONTEND_URL}${path}` });
      await new Promise((resolve) => {
        const done = () => resolve();
        cdp.on("Page.loadEventFired", done);
        setTimeout(done, 3000);
      });
      await waitFor(() => evaluate(`document.readyState === "complete" && document.body && document.body.innerText.trim() !== "Loading..."`), 15000).catch(() => null);
    }

    async function textIncludes(text, timeout = 10000) {
      await waitFor(async () => {
        const found = await evaluate(`document.body && document.body.innerText.includes(${JSON.stringify(text)})`);
        if (!found) {
          const body = await evaluate(`document.body ? document.body.innerText.slice(0, 1600) : ""`);
          throw new Error(`Text not found: ${text}\n${body}`);
        }
        return true;
      }, timeout);
    }

    async function clickButtonMatching(pattern) {
      const ok = await evaluate(`
        (() => {
          const re = new RegExp(${JSON.stringify(pattern)}, "i");
          const button = Array.from(document.querySelectorAll("button")).find((el) => re.test(el.innerText || el.textContent || ""));
          if (!button) return false;
          button.click();
          return true;
        })()
      `);
      if (!ok) throw new Error(`Button not found: ${pattern}`);
    }

    async function check(area, fn) {
      try {
        await fn();
        checks.push({ area, result: "pass" });
      } catch (error) {
        const body = await evaluate(`document.body ? document.body.innerText.slice(0, 4000) : ""`).catch(() => "");
        checks.push({ area, result: "fail", error: String(error?.message || error), body });
      }
    }

    await check("session runtime/artifacts/no-browser", async () => {
      await navigate(`/session/${sessionId}`);
      await textIncludes("Artifacts", 20000);
      await textIncludes("Mailbox summary", 20000);
      await textIncludes("Thinking", 20000);
      await textIncludes("No trajectory match", 20000);
      await textIncludes("Search emails", 20000);
      const browserVisible = await evaluate(`
        Array.from(document.querySelectorAll("button")).some((el) => (el.innerText || "").trim() === "Browser")
      `);
      if (browserVisible) throw new Error("Browser tab is visible for a non-browser session.");
    });

    await check("approvals route", async () => {
      await navigate("/approvals");
      await textIncludes("Approvals");
      const rawJsonVisible = await evaluate(`document.body.innerText.includes('{"detail":"Not Found"}')`);
      if (rawJsonVisible) throw new Error("Raw JSON error is visible.");
    });

    await check("evals audit matrix", async () => {
      await navigate("/evals");
      await textIncludes("Connector audit matrix", 20000);
      await clickButtonMatching("Run matrix");
      await textIncludes("4 pass", 30000);
      await textIncludes("2 blocked", 30000);
      await textIncludes("0 fail", 30000);
    });

    await check("eval runs route", async () => {
      await navigate("/eval-runs");
      await textIncludes("Runs");
      const matrixVisible = await evaluate(`
        Array.from(document.querySelectorAll("button")).some((el) => /Run matrix/i.test(el.innerText || ""))
      `);
      if (matrixVisible) throw new Error("Benchmark matrix controls leaked into Runs route.");
    });
  } finally {
    cdp.close();
    chrome.child.kill();
    await new Promise((resolve) => {
      chrome.child.once("exit", resolve);
      setTimeout(resolve, 2000);
    });
    await rm(chrome.userDataDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
  }

  console.log(JSON.stringify({ checks, consoleErrors, requestFailures, observedRequests }, null, 2));
  return checks.some((item) => item.result === "fail") || requestFailures.length > 0 ? 1 : 0;
}

main().then((code) => process.exit(code)).catch((error) => {
  console.error(error);
  process.exit(1);
});
