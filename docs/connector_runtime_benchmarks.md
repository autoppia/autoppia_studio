# Connector Runtime Benchmarks

This runbook covers the connector runtime benchmark flow for Autoppia Studio:

```text
Connector -> toolkit tools -> benchmark tasks -> live AgentRuntime smoke
-> connector harvester -> approved skills -> AgentRuntime smoke with skill replay
```

Use it when changing connector tooling, AgentRuntime routing, skill replay,
browser handling, artifacts, approvals, or the `/evals` benchmark UI.

## What The Audit Proves

The connector audit matrix verifies each connector benchmark in two modes:

- `runtimeWithoutSkill`: skill routing is disabled. The agent must solve the
  task live with connector/browser tools.
- `runtimeWithSkill`: approved benchmark skills are available. Harvestable
  tasks must route through `router.matched_skill` and replay the approved
  trajectory.

The audit also separates unavailable connectors from runtime failures:

- `pass`: live runtime and approved skill replay both passed.
- `blocked_auth`: a compatible connector exists but is not authenticated.
- `blocked_connector`: a connector exists but is not in a runnable state.
- `missing_connector`: no compatible connector exists for that benchmark.
- `fail`: connector is runnable, but runtime, harvest, artifact, browser, or
  skill replay validation failed.

## Current Coverage

Connector benchmark definitions live in:

```text
backend/app/services/connector_benchmarks.py
```

The current benchmark catalog covers:

- `email`: IMAP search/read, SMTP draft, approval-gated send.
- `telegram`: chat metadata, approval-gated send.
- `holded`: invoices and clients.
- `bopa`: latest bulletin metadata and PDF artifact.
- `knowledge`: document search and document listing.
- `web`: HTTP text fetch, link extraction, browser navigation.

Tasks that require human approval, such as send actions, are intentionally not
auto-harvested into skills.

## Run The Matrix

CLI:

```bash
python scripts/connector_runtime_benchmark.py --audit-matrix
```

API:

```bash
curl -s http://localhost:8080/connector-benchmarks/audit-matrix \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "demo@autoppia.com",
    "companyId": "deae345c-8e98-42ec-a517-267b47f1488a",
    "publishTools": true
  }'
```

UI:

```text
/evals -> Connector runtime smoke -> Connector audit matrix -> Run matrix
```

## Expected Celeris State

For Celeris (`deae345c-8e98-42ec-a517-267b47f1488a`), the latest local audit
observed:

```text
email      pass          live 3/3   skill 3/3
bopa       pass          live 2/2   skill 2/2
knowledge  pass          live 2/2   skill 2/2
web        pass          live 3/3   skill 3/3
telegram   blocked_auth  needs_auth
holded     blocked_auth  needs_auth
```

When Telegram or Holded move from `needs_auth` to `connected`, rerun the matrix.
They should move from `blocked_auth` to either `pass` or a concrete `fail` with
task-level failures.

## Session-Level Smokes

Backend smoke results are not enough for UI changes. For runtime/session work,
also verify socket events used by the UI:

- `runtime.think`
- `router.no_match` for live runtime without skill.
- `router.matched_skill` for approved skill replay.
- connector tool action, such as `bopa.latest_bulletin_pdf`.
- browser action, such as `browser.navigate`, only when browser is required.
- artifacts in the final `result` payload when a connector returns a PDF/file
  URL.

Representative real socket checks previously passed:

```text
BOPA live:
runtime.think -> router.no_match -> bopa.latest_bulletin_pdf
result success true, artifacts 1

BOPA with skill:
runtime.think -> router.matched_skill -> bopa.latest_bulletin_pdf
result success true, artifacts 1

Web browser task:
runtime.think -> router.no_match/router.matched_skill -> browser.navigate
actionHistory contains browser.navigate URL and executed=false
```

## Important Invariants

- Do not use broad deterministic prompt routing. Skill replay is allowed only
  after the router matches a concrete source task strongly enough and the linked
  trajectory is approved and executable.
- Live runtime smoke must set `disableSkillRouting` so existing approved skills
  cannot mask live-tool regressions.
- Skill smoke must require `router.matched_skill` for approved harvestable
  tasks.
- Non-browser connector agents must not show an empty browser panel. Browser UI
  should appear only when there is browser content or a browser action.
- Connector outputs with `pdfUrl`, `fileUrl`, `downloadUrl`, or `url` should be
  promoted to session artifacts when appropriate.
- Write/send actions must go through human approval instead of executing
  silently.

## Useful Test Commands

Backend:

```bash
PYTHONPATH=backend pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm run build
npm test -- --watchAll=false agent-response.test.tsx
```

Local services:

```bash
pm2 status
pm2 restart automata-cloud-backend automata-cloud-frontend
```
