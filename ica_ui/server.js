const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.ICA_UI_PORT || process.env.PORT || 3100);
const ROOT = __dirname;

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webp": "image/webp",
};

function safePath(urlPath) {
  const clean = decodeURIComponent(urlPath.split("?")[0]).replace(/^\/+/, "");
  const target = path.resolve(ROOT, clean || "index.html");
  if (!target.startsWith(ROOT)) return path.join(ROOT, "index.html");
  if (fs.existsSync(target) && fs.statSync(target).isFile()) return target;
  return path.join(ROOT, "index.html");
}

const server = http.createServer((req, res) => {
  const filePath = safePath(req.url || "/");
  const ext = path.extname(filePath);
  res.setHeader("Cache-Control", ext === ".html" ? "no-store" : "public, max-age=3600");
  res.setHeader("Content-Type", TYPES[ext] || "application/octet-stream");
  fs.createReadStream(filePath)
    .on("error", () => {
      res.statusCode = 500;
      res.end("Failed to read ICA UI asset");
    })
    .pipe(res);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`ICA UI running at http://127.0.0.1:${PORT}`);
});
