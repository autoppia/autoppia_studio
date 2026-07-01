# Demo Companies

`demo_companies` contains full company simulation projects for ICA benchmarks.
Unlike the older IWA demo webs, a demo company can expose multiple company
surfaces:

- web UI
- API with OpenAPI/Swagger docs
- company knowledge documents
- source code
- auth notes and fixtures
- benchmark tasks with expected surfaces

These projects are inputs for ICA, the Infinite Company Arena. ICA benchmark
scripts convert project manifests into CompanyHarvester intake material and then
evaluate whether Studio discovers connectors, tools, tasks, skills, and agents
from the same material a non-technical company owner would provide.

This directory should contain only demo company projects and their own source
files. Benchmark schemas, evaluators, harnesses, and tests live in `../ica`.

## Included Companies

- `only_web/`: ICA wrappers for all legacy `autoppia_webs_demo` projects. These
  are web-only demo companies that point to the existing deployed demo-web
  surfaces and expose a `web_only` benchmark mode.
- `autoclaims/`: full company example with web, API, docs, benchmark tasks, and
  execution checks for claim workflows.
- `autocommerce/`: commerce/fulfillment company with web, API docs, documents,
  tasks, and execution checks.
- `autopricing/`: code-heavy pricing company used to test the `code` source
  surface and whether harvesters can infer tasks from implementation logic.

## Benchmark Expectations

Each complete project should model two phases:

- Task discovery: can the harvester infer the expected company tasks from the
  provided sources?
- Solution discovery and execution: can it propose connectors, tools,
  trajectories, skills, and an agent provider that actually solve the task
  against project tests?

When possible, include source-combination coverage in `project.json`, for
example web-only, API-only, code-only, web+API, web+code, and all sources.

The `only_web` category intentionally contains manifests and small README files
only. The runnable web app source remains in the legacy demo-web corpus until a
specific web is promoted into a full demo company with API/docs/code/tests.
