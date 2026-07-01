# Autoppia Studio Structure

This repo currently has five product areas plus local/runtime support folders.

## Core Apps

- `backend/`: FastAPI backend for Studio. It owns API routes, persistence,
  agent config services, Studio harvesters, judges, integration wrappers, and
  backend tests.
- `frontend/`: main Autoppia Studio web app. This is the product UI for configuring
  agents, connectors, skills, benchmarks, runs, sessions, and workspace views.
- `ica/`: local Infinite Company Arena benchmark package. This is the SDK-like
  benchmark layer for CompanyHarvesters, demo company materialization, discovery
  scoring, solution scoring, agent execution checks, and ICA core tests.
- `ica_ui/`: standalone Infinite Company Arena cockpit. This is intentionally
  separate from `frontend/` so we can iterate on harvester/miner benchmark UX
  without making Studio more complex.
- `demo_companies/`: benchmark fixture companies. These are not just demo webs:
  each project can include web UI, API/OpenAPI, docs, code, auth notes, tasks,
  and execution test definitions. Benchmark test code itself lives in `ica/tests`.
  The `demo_companies/only_web/` category contains web-only ICA wrappers for the
  legacy IWA demo webs.

## Support Services

- `mcp/`: local MCP sidecar/service used by Studio integrations.
- `scripts/`: local benchmark, seed, smoke-test, and maintenance commands.
- `docs/`: architecture notes, runbooks, and benchmark/runtime documentation.
- `backend/data/`: local backend seed/demo data used by Studio examples.

## Generated Local State

These should be treated as local outputs, not product structure:

- `backend/.venv/`
- `frontend/node_modules/`
- `mcp/node_modules/`
- `frontend/build/`
- `.screenshots/`
- `logs/`
- Python/JS caches such as `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`

## Current ICA Flow

The CompanyHarvester benchmark flow is:

```text
demo_companies manifest
-> ICA source combinations
-> CompanyHarvester task discovery
-> solution discovery
-> agent execution tests when available
-> run report in ica_ui
```

`ica_ui` reads/writes ICA runs through the backend API. Local run snapshots may
exist under `logs/`, but they are generated state and should not be committed.
