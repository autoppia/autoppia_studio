# Autoppia Studio Capability Factory Plan

## Purpose

This document turns the current Studio direction into an execution plan for
this repository. The target is not "an app to create agents", but a governed
enterprise AI layer factory built on top of existing systems.

Studio should evolve into three things at once:

- `control plane`: company setup, security, approvals, policies, runtime config
- `capability factory`: tasks, benchmarks, trajectories, skills, promotion
- `runtime lab`: sessions, trace, artifacts, approvals, replay, auditability

## Product Positioning

Recommended product framing:

- `Capability Factory for enterprise AI operations`
- `Build, validate and operate business capabilities on top of existing systems`

Avoid centering the product around "agent builder". Customers buy governed
business capabilities, not connectors or generic agents.

## Canonical Model

These terms should be treated as first-class across backend, frontend, and UI
copy.

- `Connector`: access to an external system
- `Resource`: readable, versioned context
- `Entity`: normalized business object
- `Tool`: typed atomic action
- `Task`: one evaluable business objective
- `Benchmark`: a set of tasks
- `Trajectory`: evidence of how a task was attempted/resolved
- `Skill`: hardened reusable workflow
- `AgentConfig`: definition/configuration
- `AgentRuntime`: executable runtime
- `Session`: durable execution instance
- `Artifact`: business output separate from the trace

## Current Repo Mapping

The current repo already has most surfaces needed for this model.

### Backend surfaces already present

- `backend/app/routes/agent_configs.py`
- `backend/app/routes/runtime.py`
- `backend/app/routes/session.py`
- `backend/app/routes/connectors.py`
- `backend/app/routes/credentials.py`
- `backend/app/routes/knowledge.py`
- `backend/app/routes/entities.py`
- `backend/app/routes/capabilities.py`
- `backend/app/routes/skills.py`
- `backend/app/routes/evals.py`
- `backend/app/routes/approvals.py`
- `backend/app/routes/artifacts.py`
- `backend/app/routes/work_items.py`
- `backend/app/routes/assistant.py`

### Frontend surfaces already present

- `/agents`
- `/connectors`
- `/knowledge`
- `/capabilities`
- `/entities`
- `/evals`
- `/eval-runs`
- `/approvals`
- `/work`
- `/session/:id`
- `/canvas`

### Existing strong direction

- Task -> Benchmark -> Trajectory -> Skill flow is already documented
- runtime approvals exist
- session artifacts exist
- connector benchmark work already exists
- agent config/runtime naming is already moving in the right direction

### Current gaps

- `Connector`, `Resource`, `Tool`, `Trajectory`, and `Skill` are still too
  close conceptually in product surfaces
- `Skill` is not yet hardened enough as a portable, versioned artifact
- `Session` is still partly presented like chat instead of operational runtime
- `Evals` is strong technically but not yet the center of the capability flow
- capability discovery, synthesis, and promotion are spread across sections

## Target Product Surfaces

Studio should be organized into five product areas.

### 1. Company Setup

Purpose: define the operating perimeter.

Should contain:

- companies
- environments
- secrets and credentials
- approval policies
- allowed domains
- compliance and risk policy
- system inventory

Current repo anchors:

- backend: `companies`, `credentials`, `connectors`, `profile`
- frontend: `connectors`, `credentials`, onboarding flows

### 2. Capability Factory

Purpose: turn system access into reusable business capabilities.

Should contain:

- connectors
- resources
- entities
- tools
- tasks
- benchmarks
- trajectories
- skills
- promotion pipeline

Current repo anchors:

- backend: `capabilities`, `skills`, `entities`, `evals`
- frontend: `/connectors`, `/knowledge`, `/entities`, `/capabilities`, `/evals`

### 3. Runtime Lab

Purpose: inspect and operate real executions.

Should contain:

- sessions
- selected runtime kind
- skill routing decisions
- tool calls
- browser actions
- artifacts
- approvals
- trace ids
- cost and latency

Current repo anchors:

- backend: `runtime`, `session`, `artifacts`, `approvals`
- frontend: `/session/:id`

### 4. Work Orchestration

Purpose: schedule and govern recurring or queued work.

Should contain:

- work items
- queues
- retries
- schedules
- SLAs
- budgets
- approval checkpoints

Current repo anchors:

- backend: `work_items`
- frontend: `/work`

### 5. Automata

Purpose: internal copilot for Studio operators.

Should contain:

- next-best-step guidance
- benchmark gap suggestions
- risk warnings
- connector/tool/skill assistance
- explanation of runtime failures

Current repo anchors:

- backend: `assistant`
- frontend: in-product assistant surfaces

## Architecture Principles

### 1. Connector is access, capability is value

A customer does not buy "6 connected systems". A customer buys "12 governed
business capabilities with benchmarks, runtime policies, and audit trails".

### 2. Resource and tool must be distinct

- `Resource`: readable context such as schemas, docs, records, policies
- `Tool`: executable operation with input/output schema and side effects

This distinction should exist in both backend contracts and UI.

### 3. Trajectory is evidence, not the product

Trajectories prove how work was attempted. They support replay, judgment,
promotion, and debugging. They should not be treated as the customer-facing
capability itself.

### 4. Skill is a hardened artifact

Every promoted skill should expose at least:

- name
- description
- activation description
- inputs
- outputs
- allowed systems
- source trajectories
- risk class
- approval policy
- regression coverage
- version
- publication status

### 5. Browser runtime is exceptional

Default execution should prefer APIs and structured tools. Browser runtime
should be explicit, costly, allowlisted, and auditable.

## Implementation Phases

## Phase 1: Normalize the Core

Goal: make backend, frontend, and naming use one coherent model.

### Backend work

- consolidate canonical schemas for `Skill`, `Task`, `Trajectory`, `Artifact`,
  and `Session`
- add `skillVersion`, `promotionStatus`, and `sourceTrajectoryIds`
- add explicit `runtimeKind` to session/runtime metadata
- make approval state part of session state, not just event side effects
- add artifact metadata that cleanly separates `content`, `url`, `kind`,
  `sourceTool`, and `approvalRelation`

### Frontend work

- reflect `resource` vs `tool` in capability views
- distinguish `trajectory` and `skill` visually and semantically
- treat session as runtime execution, not just chat history
- show artifact outputs as a primary result surface

### Recommended first schema additions

- `skills.version`
- `skills.activationDescription`
- `skills.allowedSystems`
- `skills.requiredApprovals`
- `skills.regressionSuite`
- `sessions.runtimeKind`
- `sessions.selectedSkillId`
- `sessions.traceId`
- `sessions.approvalState`
- `sessions.metrics`

## Phase 2: Build the Real Capability Factory

Goal: move from "systems connected" to "capabilities produced".

### Pipeline stages

Each connector pipeline should produce:

1. auth state
2. discovered resources
3. discovered entities
4. synthesized tools
5. candidate tasks
6. benchmark runs
7. trajectories
8. promoted skills

### Backend work

- create a dedicated capability lifecycle service
- separate discovery/synthesis services from runtime execution services
- add richer tool synthesis metadata:
  - risk classification
  - permission scopes
  - side effects
  - input entity types
  - output entity types
- add entity relationship metadata and aliases

### Frontend work

- add a capability detail page or pane that shows:
  - entities
  - tools
  - benchmarks
  - trajectories
  - skills
- add a promotion flow:
  - task
  - benchmark run
  - judge result
  - trajectory review
  - skill hardening
  - publish

## Phase 3: Put Evals at the Center

Goal: no meaningful capability ships without benchmark coverage.

### Rules

- every skill must link to at least one benchmark task
- every task must define:
  - business intent
  - initial state
  - allowed systems
  - expected artifact
  - success criteria
  - risk class
- deterministic evaluators come first
- stateful evaluators are preferred when available
- LLM judges are supporting signals, not the only truth

### Backend work

- store explicit benchmark coverage per skill
- attach regression runs to skill versions
- surface evaluator type and coverage strength in APIs

### Frontend work

- elevate `/evals` from utility page to core factory surface
- add coverage views by:
  - connector
  - entity
  - tool
  - skill
- show recent regressions and blocked promotions

## Phase 4: Enterprise Runtime

Goal: make execution reliable, reviewable, and constrained.

### Runtime taxonomy

Support three explicit runtime kinds:

- `api_runtime`
- `browser_runtime`
- `hybrid_runtime`

### Policy taxonomy

Support at least:

- `read`
- `draft`
- `write`
- `send`

### Backend work

- persist runtime kind and policy envelope in session state
- require approval binding for write/send actions
- add allowlist-aware browser controls
- standardize audit trail records across runtime and approvals

### Frontend work

- show runtime kind clearly in the session header
- show policy mode and pending approvals in the timeline
- separate draft artifacts from executed write/send actions

## Backlog by Epic

## Epic A: Canonical Data Model

Definition of done:

- shared backend/frontend field names for core capability objects
- no ambiguous UI copy between trajectory and skill
- session metadata includes runtime, skill, approvals, artifacts, metrics

Tickets:

- define canonical API fields for `Skill`, `Trajectory`, `Artifact`, `Session`
- add migration-compatible response serialization
- update frontend types in `frontend/src/utils/types`
- audit copy for "agent", "capability", "trajectory", "skill"

## Epic B: Capability Registry

Definition of done:

- a capability can be inspected end-to-end from connector to promoted skill

Tickets:

- add capability lifecycle service
- add entity alias and relationship support
- add promotion status fields
- add a capability detail API
- add a capability detail page

## Epic C: Tool and Resource Separation

Definition of done:

- users can tell which objects are context and which are executable actions

Tickets:

- add resource registry model
- expose connector-discovered resources separately from tools
- add UI split between resources and tools
- enrich synthesized tools with side effects and scopes

## Epic D: Eval-Centered Promotion

Definition of done:

- every promoted skill shows benchmark lineage and regression status

Tickets:

- require source benchmark linkage for promotion
- attach regression suite metadata to skill versions
- add coverage dashboard to `/evals`
- add blocked-promotion reasons

## Epic E: Runtime Lab

Definition of done:

- sessions are inspectable as operational runs, not just conversations

Tickets:

- add runtime summary card
- add trace ids and metrics panel
- add policy and approval strip
- improve artifact-first result rendering
- show skill match and router decision prominently

## Epic F: Enterprise Governance

Definition of done:

- risky actions are policy-controlled and auditable

Tickets:

- add per-tool risk classification
- add per-skill approval policy
- add browser allowlist support
- standardize approval audit records

## 90-Day Roadmap

### Weeks 1-2

- freeze vocabulary and canonical contracts
- define final skill/session/artifact fields
- align frontend types with backend serializers

### Weeks 3-5

- implement capability registry and skill versioning
- add session metadata for runtime kind, approvals, and metrics
- redesign navigation around factory/lab model

### Weeks 6-8

- deepen tool synthesis and entity discovery
- add capability detail page
- add trajectory-to-skill hardening pipeline

### Weeks 9-10

- make benchmark and regression coverage a promotion gate
- surface connector benchmark matrix directly in Studio UI

### Weeks 11-12

- harden runtime policies
- constrain browser runtime
- run an end-to-end vertical smoke for a real business workflow

## Demo Vertical Recommendation

Use one strict end-to-end scenario to validate the architecture:

- `Respond to a customer about claim status without sending the final email`

It should cover:

- email read
- ERP lookup
- document retrieval
- draft artifact generation
- approval boundary
- benchmark
- trajectory
- skill promotion
- runtime replay

If this flow is reliable, the overall architecture is probably directionally
correct.

## Success Metrics

Studio is moving in the right direction when these statements become true:

- a connected system yields a typed tool catalog and a resource catalog
- a business task can be benchmarked before promotion
- a promoted skill shows version, lineage, coverage, and policy
- a session clearly exposes runtime kind, router decision, approvals, and artifacts
- browser steps are visible and exceptional, not default
- one business capability can be inspected end-to-end from system access to
  governed runtime execution
