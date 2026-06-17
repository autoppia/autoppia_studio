const path = require("path");

const appDir = process.env.APP_DIR || __dirname;
const backendDir = path.join(appDir, "backend");
const logsDir = path.join(appDir, "logs");

module.exports = {
  apps: [
    {
      name: "autoppia-studio-backend",
      script: "/usr/bin/bash",
      args: [
        "-lc",
        [
          "set -a",
          "source .env",
          "set +a",
          "export AUTOMATA_ENV=production",
          "exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8100 --proxy-headers",
        ].join(" && "),
      ],
      cwd: backendDir,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "2G",
      error_file: path.join(logsDir, "backend.err.log"),
      out_file: path.join(logsDir, "backend.out.log"),
      log_file: path.join(logsDir, "backend.combined.log"),
      time: true,
    },
    {
      name: "autoppia-studio-worker",
      script: "/usr/bin/bash",
      args: [
        "-lc",
        [
          "set -a",
          "source .env",
          "set +a",
          "export AUTOMATA_ENV=production",
          "exec .venv/bin/python -m app.worker",
        ].join(" && "),
      ],
      cwd: backendDir,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "2G",
      error_file: path.join(logsDir, "worker.err.log"),
      out_file: path.join(logsDir, "worker.out.log"),
      log_file: path.join(logsDir, "worker.combined.log"),
      time: true,
    },
  ],
};
