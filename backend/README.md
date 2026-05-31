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
- `app/routes/operators.py`: agent CRUD and bundled Autocinema bootstrap.
- `app/routes/operator_assets.py`: webs, trajectories and skills/capabilities for an agent.
- `app/routes/evals.py`: benchmark tasks and benchmark/eval runs.
- `app/routes/api/agents.py`: API-key protected agent runtime proxy.
- `app/sio_app.py`: interactive browser/session Socket.IO runtime.

Current intentional placeholders:

- Credit analytics are not wired to billing telemetry yet; `/analytics` returns credit availability as false.
- Custom API connectors validate docs/auth shape and expose generated-toolkit metadata, but do not yet fetch public docs or synthesize typed tools automatically.
- Knowledge uploads are stored and attached to the company Knowledge connector, but vector indexing/search is not wired yet.
- Newly onboarded agents are created with `runtimeType=pending` until a runtime is deployed or attached.
- `/api/v1/run-task` is a legacy in-memory task runner. Prefer `/api/v1/agents/{operator_id}/act` for deployed agents.
