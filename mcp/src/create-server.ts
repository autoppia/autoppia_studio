import dotenv from "dotenv";
import fetch, { RequestInit } from "node-fetch"
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

// Environment setup
dotenv.config();
const AUTOMATA_API_BASE_URL = process.env.AUTOMATA_API_BASE_URL || "http://localhost:8000/api/v1";
const AUTOPPIA_API_KEY = process.env.AUTOPPIA_API_KEY

// Interface
interface TaskResponse {
    task_id: string;
};

interface TaskDetails {
    id: string;
    task: string;
    initial_url?: string | null;
    provider: "browser_use" | "openai";
    status: string;
    steps: Array<Record<string, any>>;
    output?: string | null;
}

interface TaskStatus {
    status: string;
};

interface TaskScreenshots {
    screenshots: Array<string>;
};

interface TaskGif {
    gif: string;
};

// Helper function for make Automata API requests
async function makeAutomataRequest<T>(path: string, init?: RequestInit): Promise<T | null> {
    init = init || {};

    init.headers = {
        "x-api-key": AUTOPPIA_API_KEY as string
    };

    try {
        const response = await fetch(`${AUTOMATA_API_BASE_URL}${path}`, init);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return (await response.json()) as T;
    } catch (err) {
        console.error("Error making Automata Request:", err);
        return null;
    }
}

export const createServer = () => {
    const server = new McpServer({
        name: "Automata MCP Server",
        version: "1.0.0"
    });

    server.registerTool(
        "run-task",
        {
            title: "Run Task",
            description: "Runs a new automation task",
            inputSchema: {
                task: z.string(),
                initial_url: z.string().url().optional(),
                provider: z.enum(["browser_use", "openai"]).optional(),
            }
        },
        async (input) => {
            const response = await makeAutomataRequest<TaskResponse>("/run-task", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(input),
            });

            if (response) {
                return {
                    content: [{ type: "text", text: response.task_id }]
                }
            } else {
                return {
                    content: [{ type: "text", text: "Failed to run task." }]
                }
            }
        }
    )

    server.registerTool(
        "get-task-details",
        {
            title: "Get Task Details",
            description: "Gets details of the specified task",
            inputSchema: {
                task_id: z.string()
            }
        },
        async ({ task_id }) => {
            const response = await makeAutomataRequest<TaskDetails>(`/task/${task_id}`);

            return {
                content: [{ type: "text", text: JSON.stringify(response) }]
            }
        }
    )

    server.registerTool(
        "get-task-status",
        {
            title: "Get Task Status",
            description: "Gets status of the specified task",
            inputSchema: {
                task_id: z.string()
            }
        },
        async ({ task_id }) => {
            const response = await makeAutomataRequest<TaskStatus>(`/task/${task_id}/status`);

            if (response) {
                return {
                    content: [{ type: "text", text: response.status }]
                }
            } else {
                return {
                    content: [{ type: "text", text: "Failed to get task status." }]
                }
            }
        }
    )

    server.registerTool(
        "get-task-screenshots",
        {
            title: "Get Task Screenshots",
            description: "Gets screenshots of the specified task",
            inputSchema: {
                task_id: z.string()
            }
        },
        async ({ task_id }) => {
            const response = await makeAutomataRequest<TaskScreenshots>(`/task/${task_id}/screenshots`);

            if (response) {
                return {
                    content: response.screenshots.map(screenshot => ({
                        type: "image",
                        data: screenshot,
                        mimeType: "image/png"
                    }))
                }
            } else {
                return {
                    content: [{ type: "text", text: "Failed to get task screenshots." }]
                }
            }
        }
    )

    server.registerTool(
        "get-task-gif",
        {
            title: "Get Task GIF",
            description: "Gets GIF of the specified task",
            inputSchema: {
                task_id: z.string()
            }
        },
        async ({ task_id }) => {
            const response = await makeAutomataRequest<TaskGif>(`/task/${task_id}/screenshots`);

            if (response) {
                return {
                    content: [{
                        type: "image",
                        data: response.gif,
                        mimeType: "image/gif"
                    }]
                }
            } else {
                return {
                    content: [{ type: "text", text: "Failed to get task gif." }]
                }
            }
        }
    )

    return { server };
}