# AutoClaims

AutoClaims is a small full-company demo project for ICA.

It includes:

- `backend/main.py`: FastAPI app with Swagger/OpenAPI.
- `frontend/index.html`: simple web UI for claims operations.
- `docs/`: company policy and operating knowledge.
- `project.json`: ICA manifest consumed by Studio benchmark tooling.

Run locally:

```bash
cd demo_projects/autoclaims
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8123 --reload
```

Then open:

- Web UI: `http://127.0.0.1:8123/`
- Swagger docs: `http://127.0.0.1:8123/docs`
- OpenAPI JSON: `http://127.0.0.1:8123/openapi.json`

