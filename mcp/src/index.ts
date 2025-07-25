import dotenv from "dotenv";
import express, { Request, Response } from "express";
import cors from "cors";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { AuthInfo } from "@modelcontextprotocol/sdk/server/auth/types.js";
import { descopeMcpAuthRouter, descopeMcpBearerAuth, DescopeMcpProvider } from "@descope/mcp-express";
import { createServer } from "./create-server";

// Type declarations
declare global {
  namespace Express {
    interface Request {
      auth?: AuthInfo;
    }
  }
}

// Environment setup
dotenv.config();
const PORT = process.env.PORT || 5000;

// Initialize Express app
const app = express();

// CORS Middleware
app.use(cors({
  origin: true,
  methods: '*',
  allowedHeaders: 'Authorization, Origin, Content-Type, Accept, *',
}));

// Auth middleware
const provider = new DescopeMcpProvider({
  // Project credentials
  projectId: process.env.DESCOPE_PROJECT_ID,
  managementKey: process.env.DESCOPE_MANAGEMENT_KEY,
  serverUrl: process.env.SERVER_URL,

  // Dynamic client registration options
  dynamicClientRegistrationOptions: {
    authPageUrl: `https://api.descope.com/login/${process.env.DESCOPE_PROJECT_ID}?flow=inbound-apps-user-consent`,
    permissionScopes: [],
    isDisabled: false // Set to true to disable dynamic registration
  },
});

app.use(descopeMcpAuthRouter());
app.use(["/mcp"], descopeMcpBearerAuth(provider));

// Initialize transport
const transport = new StreamableHTTPServerTransport({
  sessionIdGenerator: undefined, // set to undefined for stateless servers
});

// MCP endpoint
app.post('/mcp', async (req: Request, res: Response) => {
  console.log('Received MCP request:', req.body);
  try {
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error('Error handling MCP request:', error);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: '2.0',
        error: {
          code: -32603,
          message: 'Internal server error',
        },
        id: null,
      });
    }
  }
});

// Method not allowed handlers
const methodNotAllowed = (req: Request, res: Response) => {
  console.log(`Received ${req.method} MCP request`);
  res.status(405).json({
    jsonrpc: "2.0",
    error: {
      code: -32000,
      message: "Method not allowed."
    },
    id: null
  });
};

app.get('/mcp', methodNotAllowed);
app.delete('/mcp', methodNotAllowed);

const { server } = createServer();

// Server setup
const setupServer = async () => {
  try {
    await server.connect(transport);
    console.log('Server connected successfully');
  } catch (error) {
    console.error('Failed to set up the server:', error);
    throw error;
  }
};

// Start server
setupServer()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`MCP Streamable HTTP Server listening on port ${PORT}`);
    });
  })
  .catch(error => {
    console.error('Failed to start server:', error);
    process.exit(1);
  });

// Handle server shutdown
process.on('SIGINT', async () => {
  console.log('Shutting down server...');
  try {
    console.log(`Closing transport`);
    await transport.close();
  } catch (error) {
    console.error(`Error closing transport:`, error);
  }

  try {
    await server.close();
    console.log('Server shutdown complete');
  } catch (error) {
    console.error('Error closing server:', error);
  }
  process.exit(0);
});