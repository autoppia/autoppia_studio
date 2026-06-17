const path = require("path");

const appDir = __dirname;
const backendDir = path.join(appDir, "backend");
const frontendDir = path.join(appDir, "frontend");
const mcpDir = path.join(appDir, "mcp");
const logsDir = path.join(appDir, "logs");

module.exports = {
  apps: [
    {
      name: "automata-cloud-backend",
      script: "/bin/bash",
      args: [
        "-lc",
        [
          "set -a",
          "source .env",
          "set +a",
          "exec .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080 --proxy-headers",
        ].join(" && "),
      ],
      cwd: backendDir,
      instances: 1,
      autorestart: true,
      watch: false,
      error_file: path.join(logsDir, "local-backend.err.log"),
      out_file: path.join(logsDir, "local-backend.out.log"),
      log_file: path.join(logsDir, "local-backend.combined.log"),
      time: true,
    },
    {
      name: "automata-cloud-worker",
      script: "/bin/bash",
      args: [
        "-lc",
        [
          "set -a",
          "source .env",
          "set +a",
          "exec .venv/bin/python -m app.worker",
        ].join(" && "),
      ],
      cwd: backendDir,
      instances: 1,
      autorestart: true,
      watch: false,
      error_file: path.join(logsDir, "local-worker.err.log"),
      out_file: path.join(logsDir, "local-worker.out.log"),
      log_file: path.join(logsDir, "local-worker.combined.log"),
      time: true,
    },
    {
      name: "automata-cloud-frontend",
      script: "/bin/bash",
      args: "-lc 'PORT=3000 exec node server.js'",
      cwd: frontendDir,
      instances: 1,
      autorestart: true,
      watch: false,
      error_file: path.join(logsDir, "local-frontend.err.log"),
      out_file: path.join(logsDir, "local-frontend.out.log"),
      log_file: path.join(logsDir, "local-frontend.combined.log"),
      time: true,
    },
    {
      name: "automata-cloud-mcp",
      script: "/bin/bash",
      args: "-lc 'PORT=5000 exec npm start'",
      cwd: mcpDir,
      instances: 1,
      autorestart: true,
      watch: false,
      error_file: path.join(logsDir, "local-mcp.err.log"),
      out_file: path.join(logsDir, "local-mcp.out.log"),
      log_file: path.join(logsDir, "local-mcp.combined.log"),
      time: true,
    },
  ],
};
