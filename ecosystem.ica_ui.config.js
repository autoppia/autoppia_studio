const path = require("path");

const appDir = __dirname;
const icaUiDir = path.join(appDir, "ica_ui");
const logsDir = path.join(appDir, "logs");

module.exports = {
  apps: [
    {
      name: "autoppia-ica-ui",
      script: "/bin/bash",
      args: "-lc 'ICA_UI_PORT=3101 exec npm start'",
      cwd: icaUiDir,
      instances: 1,
      autorestart: true,
      watch: false,
      error_file: path.join(logsDir, "ica-ui.err.log"),
      out_file: path.join(logsDir, "ica-ui.out.log"),
      log_file: path.join(logsDir, "ica-ui.combined.log"),
      time: true,
    },
  ],
};
