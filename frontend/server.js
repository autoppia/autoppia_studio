const express = require('express');
const history = require("connect-history-api-fallback");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(history());

// Serve the built SPA. CRA fingerprints hashed assets under /static, so those
// can be cached aggressively, but index.html must never be cached or a local
// redeploy keeps serving the old bundle (and stale UI) until a hard refresh.
app.use(
  "/",
  express.static("./build", {
    etag: true,
    lastModified: true,
    setHeaders: (res, filePath) => {
      if (/[\\/]static[\\/]/.test(filePath)) {
        res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
      } else if (filePath.endsWith("index.html")) {
        res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
      } else {
        res.setHeader("Cache-Control", "no-cache");
      }
    },
  })
);

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
