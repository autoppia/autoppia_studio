Automata Cloud Backend
======================

FastAPI + Socket.IO backend for Automata Cloud.

Run locally:

```bash
uvicorn main:app --host 127.0.0.1 --port 8080
```

Run tests:

```bash
pytest -q
```

Main modules:

- `app/routes/onboarding.py`: chat onboarding flow that creates companies, connectors, benchmark tasks, agents and draft trajectories.
- `app/routes/connectors.py`: company connectors and generated toolkits. Official connectors are marked `provider=official`; ad hoc API connectors are marked `provider=custom`.
- `app/routes/knowledge.py`: uploaded company documents and the Knowledge connector backing store.
- `app/routes/agent_configs.py`: AgentConfig CRUD and bundled Autocinema bootstrap.
- `app/routes/agent_assets.py`: webs, trajectories and skills/capabilities for an agent.
- `app/routes/agent_creation.py`: agent creation pipeline state machine: connector validation, harvesting, review, skill conversion and benchmark readiness.
- `app/models/agent_config.py`: versioned `AgentConfig` and `/step` request/response contracts.
- `app/services/agent_runtime.py`: injects `AgentConfig` into `/step`, exposes skills as callable tools, executes connector tools, and records runtime events.
- `app/services/agent_harvesters.py`: pluggable agent harvester registry; use `AUTOMATA_AGENT_HARVESTER` to switch implementation.
- `scripts/run_harvester_worker.py`: durable worker loop for queued agent harvester runs when `AUTOMATA_HARVESTER_INLINE=false`.
- `app/harvester/claude_cli.py`: Claude Code based Automata Harvester adapter. It runs in an isolated workspace, asks Claude to discover replayable trajectories, parses structured JSON, redacts secrets, and stores candidates for human review.
- `app/routes/evals.py`: benchmark tasks and benchmark/eval runs.
- `app/routes/api/agents.py`: API-key protected agent runtime proxy.
- `app/sio_app.py`: interactive browser/session Socket.IO runtime.

Public API:

All `/api/v1/*` routes require `x-api-key: <key>`. API keys are scoped to the email that created them.

- `GET /api/v1/agents`: list agents owned by the API key email. Optional `companyId` filters the list.
- `GET /api/v1/agents/{agent_id}`: fetch one owned AgentConfig summary, including `tasks`, `runtimeCapabilities`, `status`, and `trainingStatus`.
- `GET /api/v1/agents/{agent_id}/skills`: list owned agent skills in normalized API form. Approved skills have `status=approved` and `runtime=trajectory_replay_with_recovery`.
- `GET /api/v1/agents/{agent_id}/runtime-contract`: machine-readable `/step` request/response contract and supported tool calls.
- `POST /api/v1/agents/{agent_id}/step`: execute one runtime step. Send either `prompt` or `task`, plus the current `url`, optional `snapshot_html`, `history`, and previous `state_out` as `state_in`.

API key management routes (`/api-keys`) are intended for the Studio frontend. In production (`AUTOMATA_ENV=production`, `ENVIRONMENT=production`, or `APP_ENV=production`) they are disabled unless `AUTOMATA_API_KEY_ADMIN_TOKEN` is configured; when configured, all list/create/rename/delete API-key calls require `x-admin-key`.

Use `/openapi-public.json` for integrator docs. In production, internal OpenAPI/docs are hidden automatically. You can also hide them locally with `AUTOMATA_HIDE_INTERNAL_OPENAPI=true`.

Errors from `/api/v1/*` use:

```json
{"error": {"code": "agent_not_found", "message": "Agent not found", "details": {}}}
```

`POST /api/v1/agents/{agent_id}/step` is rate limited per API key with `AUTOMATA_API_STEP_RATE_LIMIT_PER_MINUTE` (default `120`, set `0` to disable locally). API calls are audited as runtime events with API key id/prefix, email, agent id, and step index.

Minimal `/step` loop:

```python
import requests

base = "http://127.0.0.1:8080"
agent_id = "..."
headers = {"x-api-key": "..."}
prompt = "Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente."
state = {}
url = "about:blank"

for step_index in range(25):
    response = requests.post(
        f"{base}/api/v1/agents/{agent_id}/step",
        headers=headers,
        json={"prompt": prompt, "url": url, "step_index": step_index, "state_in": state},
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    for call in data.get("tool_calls", []):
        # Execute browser.* or connector tool calls in your runtime.
        if call["name"] == "browser.navigate":
            url = call.get("arguments", {}).get("url", url)
    state = data.get("state_out") or state
    if data.get("done"):
        print(data.get("content", ""))
        break
```

`POST /step` returns the runtime contract directly: `tool_calls`, `reasoning`, `done`, `state_out`, `executionMode`, and optional `capability_match` when an approved skill is being replayed.

Run the API smoke test:

```bash
python scripts/smoke_api.py --agent-id <agent_id>
```

Use `AUTOMATA_API_KEY=<existing key>` to test with an existing key, or allow the script to create and delete a temporary key. If `AUTOMATA_API_KEY_ADMIN_TOKEN` is set, the script sends it as `x-admin-key`.

Current intentional placeholders:

- Credit analytics are not wired to billing telemetry yet; `/analytics` returns credit availability as false.
- Custom API connectors validate docs/auth shape and expose generated-toolkit metadata, but do not yet fetch public docs or synthesize typed tools automatically.
- Knowledge uploads are stored and attached to the company Knowledge connector, but vector indexing/search is not wired yet.
- Newly onboarded agents are created with `runtimeType=pending` until a runtime is deployed or attached.
- Harvester execution currently runs as an in-process background task for local/dev. Production should move this to a durable worker queue before multi-user use.
- `/api/v1/run-task` is a legacy in-memory task runner. Prefer `/api/v1/agents/{agent_id}/step` for deployed agents.
