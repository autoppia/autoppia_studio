import express from "express";
import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js"
import { descopeMcpAuthRouter, descopeMcpBearerAuth } from "@descope/mcp-express";
import { z } from "zod";

import "dotenv/config";

const app = express();
// app.use(express.json());

app.use(descopeMcpAuthRouter());
app.use("/mcp", descopeMcpBearerAuth());

const transports: { [sessionId: string]: StreamableHTTPServerTransport } = {};

app.post('/mcp', async (req, res) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;

  console.log(sessionId)
  let transport: StreamableHTTPServerTransport;

  if (sessionId && transports[sessionId]) {
    transport = transports[sessionId];
  } else if (!sessionId && isInitializeRequest(req.body)) {
    transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      onsessioninitialized: (sessionId) => {
        transports[sessionId] = transport;
      },
    });

    transport.onclose = () => {
      if (transport.sessionId) {
        delete transports[transport.sessionId];
      }
    };

    const server = new McpServer({
      name: "example-server",
      version: "1.0.0"
    });

    server.registerTool(
      "calculate-bmi",
      {
        title: "BMI Calculator",
        description: "Calculate Body Mass Index",
        inputSchema: {
          weightKg: z.number(),
          heightM: z.number()
        }
      },
      async ({ weightKg, heightM }) => ({
        content: [{
          type: "text",
          text: String(weightKg / (heightM * heightM))
        }]
      })
    );

    // Async tool with external API call
    server.registerTool(
      "fetch-weather",
      {
        title: "Weather Fetcher",
        description: "Get weather data for a city",
        inputSchema: { city: z.string() }
      },
      async ({ city }) => {
        const response = await fetch(`https://api.weather.com/${city}`);
        const data = await response.text();
        return {
          content: [{ type: "text", text: data }]
        };
      }
    );

    // Tool that returns ResourceLinks
    server.registerTool(
      "list-files",
      {
        title: "List Files",
        description: "List project files",
        inputSchema: { pattern: z.string() }
      },
      async ({ pattern }) => ({
        content: [
          { type: "text", text: `Found files matching "${pattern}":` },
          // ResourceLinks let tools return references without file content
          {
            type: "resource_link",
            uri: "file:///project/README.md",
            name: "README.md",
            mimeType: "text/markdown",
            description: 'A README file'
          },
          {
            type: "resource_link",
            uri: "file:///project/src/index.ts",
            name: "index.ts",
            mimeType: "text/typescript",
            description: 'An index file'
          }
        ]
      })
    );

    await server.connect(transport);
  } else {
    res.status(400).json({
      jsonrpc: '2.0',
      error: {
        code: -32000,
        message: 'Bad Request: No valid session ID provided',
      },
      id: null,
    });
    return;
  }

  await transport.handleRequest(req, res, req.body);
});

const handleSessionRequest = async (req: express.Request, res: express.Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send('Invalid or missing session ID');
    return;
  }

  const transport = transports[sessionId];
  await transport.handleRequest(req, res);
};

app.get('/mcp', handleSessionRequest);
app.delete('/mcp', handleSessionRequest);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});  