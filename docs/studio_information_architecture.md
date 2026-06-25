# Autoppia Studio Information Architecture Proposal

## Goal

Reorganize Studio around the lifecycle of enterprise capabilities while
preserving the current repo's main surfaces and route structure.

This is an IA proposal, not a mandatory immediate route rewrite. The intent is
to make the current product legible as a `Capability Factory` and `Runtime Lab`.

## Current Navigation

Today the main navigation groups are:

- `Canvas`
- `Studio`
  - `Agents`
  - `Connectors`
  - `Knowledge`
  - `Capabilities`
  - `Entities`
- `Eval`
  - `Benchmarks`
  - `Runs`
- `Workspace`
  - `Work`
  - `Approvals`

This is already close to the target model, but two things are missing:

- the user journey is still section-first, not lifecycle-first
- runtime/session is powerful but not visible as a first-class top-level lab

## Proposed Top-Level IA

Recommended top-level groups:

- `Canvas`
- `Factory`
- `Runtime`
- `Operations`
- `Setup`

## Group Definitions

### Canvas

Purpose: visual overview and cross-cutting workspace.

Should contain:

- visual system map
- capability map
- recently active sessions
- blocked approvals
- benchmark health summary

Current route anchor:

- `/canvas`

### Factory

Purpose: design and validate capabilities.

Recommended subpages:

- `Agents`
- `Connectors`
- `Resources`
- `Entities`
- `Tools`
- `Capabilities`
- `Benchmarks`
- `Trajectories`
- `Skills`

Current route anchors:

- `/agents`
- `/connectors`
- `/knowledge` as interim `Resources`
- `/entities`
- `/capabilities`
- `/evals`

Missing or weak surfaces:

- first-class `Resources`
- first-class `Tools`
- first-class `Trajectories`
- capability lineage detail

### Runtime

Purpose: observe, debug, and govern live execution.

Recommended subpages:

- `Sessions`
- `Approvals`
- `Artifacts`
- `Replay`

Current route anchors:

- `/session/:id`
- `/approvals`
- `/artifacts` behavior currently embedded in session

Missing or weak surfaces:

- session index page
- explicit runtime taxonomy display
- replay-oriented views detached from chat framing

### Operations

Purpose: scheduled, queued, and SLA-bound work.

Recommended subpages:

- `Work`
- `Queues`
- `Schedules`
- `Budgets`

Current route anchors:

- `/work`

Missing or weak surfaces:

- queue visibility
- schedule/retry controls
- budget and SLA dashboards

### Setup

Purpose: company perimeter, environments, and governance.

Recommended subpages:

- `Companies`
- `Credentials`
- `Domains`
- `Policies`
- `Compliance`

Current route anchors:

- `/credentials`
- connector and onboarding setup flows

Missing or weak surfaces:

- policy console
- domain allowlists
- explicit compliance/governance pages

## Recommended Migration Strategy

Do not rename every route immediately. Start with relabeling and IA overlays
while preserving stable paths.

### Step 1: Relabel existing groups

Minimal near-term rename:

- `Studio` -> `Factory`
- `Eval` -> `Factory`
- `Workspace` -> `Operations`

Rationale:

- `Benchmarks` and `Runs` belong to capability production, not an isolated eval silo
- `Approvals` are runtime/operations concerns, not generic workspace clutter

### Step 2: Make Runtime visible

Add a top-level `Runtime` entry that lands on a session index or recent runs
view. Sessions are too important to remain reachable mostly through deep links.

### Step 3: Split resource/tool surfaces

Treat:

- `/knowledge` as the interim home for `Resources`
- `/capabilities` as the interim home for `Tools`, `Trajectories`, and `Skills`

Then split them into dedicated tabs or sections before creating more routes.

### Step 4: Add capability detail as the center of the Factory

The most important missing page is not another list. It is a detail page that
shows one capability end-to-end:

- business intent
- linked entities
- linked tools
- benchmark coverage
- source trajectories
- promoted skills
- runtime constraints
- approval policy

## Recommended Screens

### 1. Factory Home

Purpose: overview of capability production status.

Widgets:

- connectors connected vs blocked
- entities discovered
- tools synthesized
- benchmark coverage
- trajectories pending review
- skills ready to publish

### 2. Capability Detail

Purpose: central page for one business capability.

Sections:

- overview
- systems and entities
- tool graph
- benchmark coverage
- trajectories
- promoted skills
- runtime policy
- artifacts expected

### 3. Runtime Session View

Purpose: operational execution and debugging.

Sections:

- session summary
- runtime kind
- router decision
- approval strip
- timeline
- browser pane when needed
- artifact outputs
- trace and metrics

### 4. Promotion Review

Purpose: convert evidence into reusable workflow.

Sections:

- source task
- benchmark result
- trajectory replay
- parameter hardening
- activation description
- policy and approvals
- publish readiness

### 5. Coverage Dashboard

Purpose: make evals part of the factory.

Sections:

- by connector
- by entity
- by tool
- by skill
- recent regressions
- blocked promotions

## Navigation Mapping to Current Routes

Near-term recommended mapping without breaking route compatibility:

- `Canvas` -> `/canvas`
- `Factory / Agents` -> `/agents`
- `Factory / Connectors` -> `/connectors`
- `Factory / Resources` -> `/knowledge`
- `Factory / Entities` -> `/entities`
- `Factory / Capabilities` -> `/capabilities`
- `Factory / Benchmarks` -> `/evals`
- `Factory / Runs` -> `/eval-runs`
- `Runtime / Sessions` -> new session index, then `/session/:id`
- `Runtime / Approvals` -> `/approvals`
- `Operations / Work` -> `/work`
- `Setup / Credentials` -> `/credentials`

## UI Copy Recommendations

Prefer:

- `Capability`
- `Benchmark`
- `Trajectory`
- `Skill`
- `Runtime`
- `Artifact`

Avoid using:

- `tool` when you mean end-to-end capability
- `trajectory` when you mean reusable workflow
- `chat` when the screen is really a governed runtime session

## Immediate UI Changes Worth Doing First

These are the highest-signal IA changes with the lowest migration cost.

- rename the top nav group `Studio` to `Factory`
- move `Benchmarks` and `Runs` under the same conceptual factory grouping
- add a visible `Runtime` entry for sessions and approvals
- relabel `Knowledge` as `Resources` in UI copy while preserving the route
- add a capability detail entry point from `/capabilities` and `/evals`

## Definition of Success

The IA is working when a new user can answer these questions quickly:

- Which systems are connected?
- Which business entities are understood?
- Which actions are executable?
- Which tasks are benchmarked?
- Which trajectories are approved?
- Which skills are production-ready?
- Which runtime executed this session?
- Which artifacts were produced?
- Which approvals are still blocking execution?
