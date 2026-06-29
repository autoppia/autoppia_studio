# Backend Company Harvester Architecture

## Goal

Autoppia Studio backend should center the normal user flow on company intake and
company harvesting:

```text
Company intake -> Company harvester -> Tasks/benchmarks -> Task harvester
-> Trajectories -> Judges -> Skills -> AgentConfigs -> AgentRuntimes
```

The normal user should not need to understand tools, trajectories, skills,
benchmarks, or runtime traces. Those remain real backend concepts and become
developer-mode evidence.

## Canonical Terms

- `Tool`: a typed callable operation.
- `ToolCall`: one concrete invocation of a tool. Runtime executions persist
  these as `tool.call` records in `tool_runs`, including calls blocked before
  execution by human approval.
- `Task`: one evaluable business objective.
- `Benchmark`: a group of tasks.
- `Trajectory`: one concrete attempt or solution trace for a task.
- `Skill`: a reusable approved workflow, usually promoted from a trajectory.
- `Capability`: an aggregate/read model for tools, trajectories, skills,
  policy, lineage, and evidence. It does not replace the concrete terms.
- `AgentConfig`: declarative configuration.
- `AgentRuntime`: executable runtime.
- `CompanyHarvester`: full company onboarding/discovery pipeline.
- `TaskHarvester`: solves one task and emits trajectory/evidence.

## Runtime Families

Every agent should use one common runtime contract while supporting three
runtime families:

- `codex`: Codex-backed agent runtime.
- `claude_code`: Claude Code-backed agent runtime.
- `model_agent`: system prompt plus tools/skills/knowledge using a configurable
  model provider such as OpenAI or Anthropic.

Tools, skills, trajectories, knowledge, connectors, and tasks must remain
runtime-agnostic. Runtime adapters translate the shared `AgentStepRequest` and
context into the specific execution surface.

The backend owns a runtime registry under `backend/app/runtimes/`:

- `registry.py`: source of truth for valid runtime kinds, default profiles, and
  catalog metadata.
- `model_agent.py`: normal model-agent adapter contract.
- `codex.py`: Codex adapter contract.
- `claude_code.py`: Claude Code adapter contract.

`AgentConfig.runtimeKind` chooses the runtime family. `runtimeProfile` carries
the concrete provider/model/system prompt. `runtimeDescriptor` is read-only
catalog metadata returned in agent payloads and runtime contracts so the rest of
the backend can reason about runtime support without hard-coded strings.

## Company Harvester Pipeline

The backend pipeline states are:

```text
draft
intaking
indexing_knowledge
discovering_systems
discovering_connectors
discovering_tools
discovering_entities
discovering_tasks
building_benchmarks
solving_tasks
judging_trajectories
promoting_skills
building_agents
needs_user_input
ready
failed
```

The harvester should produce typed artifacts:

```text
knowledge_document
connector_candidate
tool_candidate
entity_candidate
task_candidate
benchmark
trajectory
skill
agent_config
question_for_user
```

Questions are modeled separately from tasks:

```text
CompanyHarvestQuestion
  questionId
  code
  prompt
  reason
  severity: info | warning | blocking
  expectedAnswerType: text | url | credentials | file | choice | task_list
  materialRef
```

A question is not a task and should not create a trajectory. Blocking questions
move the run to `needs_user_input` and appear in normal mode as simple setup
questions. Dev mode keeps the full question payload and related
`question_for_user` artifacts.

Answers update the underlying `CompanyIntake` as new material, auth notes, URLs,
or task examples. They do not mutate benchmark tasks or trajectories directly.
Once blocking questions are resolved, the run returns to `indexing_knowledge`
and can continue through the normal company harvest job.
Auth answers attach credential references to matching web/API connector
candidates and mark auth as configured without storing secrets in the run.

## Normal Mode vs Dev Mode

Normal mode exposes:

- progress status
- simple next action
- systems found
- knowledge sources found
- task candidates found
- agents ready
- delivery summary for chat, API, and widget usage
- blockers requiring user input
- simple setup questions

Dev mode exposes:

- connectors
- tools
- task contracts
- benchmarks
- trajectories
- judge results
- skill packages
- runtime contracts
- approvals
- artifacts
- usage and event traces

Backend payloads use `visibility: normal | dev | internal` so the same pipeline
can power both surfaces without muddying concepts.

## Initial Backend Entry Points

- `POST /company-intakes`
- `POST /company-intakes/{intake_id}/harvest-runs`
- `POST /company-harvest-runs/{run_id}/answers`
- `GET /company-harvest-runs/{run_id}/status?mode=normal|dev`

Automata can also invoke the same backend flow through assistant tools:

- `studio_start_company_harvest`
- `studio_answer_company_harvest`
- `studio_get_company_harvest_status`

Those tools are the normal-user conversational surface over the same
CompanyHarvester state machine. They create the intake, queue the
`company_harvest` job, answer blocking setup questions, and return normal/dev
status payloads.

## Current Backend Milestone

The initial backend implementation now does the following:

- stores company intakes
- starts company harvest runs
- queues `company_harvest` jobs
- exposes CompanyHarvester to Automata assistant tool-calling so onboarding can
  start from chat with docs, web/API URLs, auth notes, knowledge, and task lists
- persists connector candidates for company knowledge, web apps, and custom API
  docs/OpenAPI material
- persists custom connector candidates from structured onboarding hints in
  material metadata (`connector`, `connectors`, `system`, or `systems`), including
  connector specs, runtime requirements, auth state, and optional tool contracts
- extracts task/workflow candidates from those custom connector specs when they
  declare `tasks`, `taskCandidates`, or `workflows`, preserving expected tools
  and connector ids on the resulting benchmark tasks
- blocks onboarding with normal-mode credential questions when a custom connector
  spec is marked `authRequired` and no owner auth material has been provided
- applies owner auth answers to matching connector candidates through
  `credentialRefs`
- registers company knowledge materials as governed `knowledge_documents`
  resources in `pending_indexing` state with resource contracts
- enqueues `knowledge_index` jobs for registered knowledge documents during
  `company_harvest` and records queued indexing evidence back onto the run
- persists governed `tool_candidate` records for discovered connectors:
  knowledge search, API operation discovery, web workflow exploration, or
  explicit tools supplied in intake material or custom connector metadata
- creates benchmark validation tasks for custom connector tools so missing
  connector implementation work is modeled as task/trajectory/skill work instead
  of being hidden inside agent creation
- reports custom connector implementation gaps in normal/dev harvest summaries
  when connector tools exist but no runtime executor has been attached
- stores an `executorBlueprint` on custom connector tools with the suggested
  executor name, schemas, auth requirements and registration status. This is an
  implementation contract for the tool, not a trajectory or skill.
- aggregates custom connector executor blueprints into normal/dev
  CompanyHarvester status so missing executor work is visible as a setup/factory
  action instead of being buried in raw tool records
- sets the normal-mode next action to `implement_connectors` when custom
  connector executor blueprints are still missing, with a follow-up action to
  run TaskHarvester after those executors are registered
- prevents automatic TaskHarvester execution from the worker while the current
  company harvest next action is `implement_connectors`, so auto-solve cannot
  skip required connector implementation work
- synthesizes concrete API tool candidates and benchmark validation tasks from
  OpenAPI specs supplied in intake metadata/content, preferring API tools over
  browser fallback when structured API operations are available
- persists inferred `entity_candidate` records in `entities_collection` from
  tool IO contracts, explicit intake metadata, and company API/web/knowledge
  materials so runtime/tool binding has concrete business objects
- refreshes each discovered connector with `capabilityDiscovery`, linking its
  synthesized tools, inferred entities, candidate benchmark tasks, ingestion
  pipeline state, and factory readiness signals
- creates a company harvest benchmark
- creates `benchmark_tasks` from user-provided tasks, task-list material,
  explicit connector tools, and simple material-derived task candidates
- exposes normal/dev status views
- accepts conversational setup answers through
  `POST /company-harvest-runs/{run_id}/answers`
- queues and runs explicit `task_harvest` jobs against `benchmark_tasks`
- exposes `POST /task-harvest-runs` for manual or inline TaskHarvester execution
- optionally judges harvested trajectories and promotes passing trajectories to
  skills through `promoteSkills=true`
- builds company agents from promoted skills through `POST /company-agent-builds`
  or `buildAgents=true`
- `buildAgents=true` can run after company discovery even without promoted
  skills, so users can receive agents backed by discovered tools, governed
  knowledge resources, and entity context while task solving/promotion continues
- accepts `runtimeProfiles` for generated agents so CompanyHarvester/Automata
  can configure the normal `model_agent` with provider, model, system prompt,
  endpoint, and metadata while keeping Codex and Claude Code on the same
  abstract AgentConfig contract
- records automatic task harvest, skill promotion, and agent build results back
  onto `CompanyHarvestRun` as typed artifacts and normal/dev status summaries
- exposes a normal-mode `delivery` summary with generated agents and their
  chat/API/widget surfaces
- exposes the three runtime families through a backend registry and includes
  runtime descriptors in `AgentConfig` payloads and runtime contracts
- dispatches the general external `/step` fallback through the selected runtime
  adapter based on `AgentConfig.runtimeKind`

This is deliberately still before final autonomous company completion. The
`TaskHarvester` boundary now consumes generated `benchmark_tasks` and delegates
to the existing harvester adapters to generate trajectories. Before delegation
it writes `harvesterStrategy` / `metadata.taskHarvesterStrategy` onto the task.
The strategy preference is:

```text
api_tool -> connector_tool -> knowledge -> browser -> model_agent
```

Task-specific evidence wins over generic connector availability. For example,
an expected tool with `executionType=browser_automation` plans as `browser` even
if the company also has a knowledge connector; an expected
`knowledge_search` tool plans as `knowledge`; API/OpenAPI material plans as
`api_tool`; custom connector tools or connector implementation gaps plan as
`connector_tool` so they stay distinct from direct API calls.

The persisted strategy also records execution readiness. Matched tools are
listed as tool evidence, and custom connector tools without an attached runtime
executor set `executionReadiness=implementation_required` with an
`implementationGaps` entry. This keeps missing connector implementation work
modeled as task planning evidence instead of pretending that a synthesized tool
is already an implemented skill or trajectory.
TaskHarvester does not call a harvester adapter or create a trajectory when
`canExecuteEndToEnd=false`; it marks the task result as
`implementation_required` and returns the connector gap as evidence. Batch
harvest summaries expose `implementationRequiredCount` separately from
`harvestedCount`.
`implementation_required` remains a retryable task state: once the missing
custom connector executor is registered, the same benchmark task is picked up by
TaskHarvester again and can produce a real trajectory.
When that retry becomes executable, TaskHarvester clears stale
`implementationGaps` and resets the pending `trajectoryId` before delegating to
the harvester adapter, so old connector gaps do not survive alongside the new
trajectory.
CompanyHarvester preserves that distinction in normal summaries:
`tasksSolved` only counts harvested/approved trajectories, while
`tasksImplementationRequired` counts tasks blocked by missing connector
executors.
The worker also preserves the boundary: if an automatic task harvest returns
implementation-required tasks, it does not auto-promote skills or build agents
in the same job. The run stays pointed at connector implementation before
judging, promotion, or delivery.
The standalone `task_harvest` worker path and inline `POST /task-harvest-runs`
path use the same gate, so manual/inline promotion cannot convert blocked work
into skills or agent delivery either.
CompanyHarvester aggregates those task-level gaps back into normal/dev run
status. If task solving finds missing connector executors and no later
promotion/agent-build step has resolved the flow, normal mode points the next
action at `implement_connectors` instead of moving straight to trajectory
judging.

`agent_runtime.py` still owns policy orchestration before execution: skill
routing, local email/local connector paths, permission enforcement, connector
tool execution, telemetry, and usage metering. When no local path handles the
step, it dispatches the shared payload through the selected runtime adapter.
Custom connector tools generated during company harvesting are treated as real
tools, but if they do not yet have an executor attached the runtime returns an
`implementation_required` tool result with a `connector_gap_report` artifact
instead of hiding the gap as a generic connector failure.
Custom connector tools can attach an in-process runtime executor by declaring
`runtimeExecutor`/`executor` and registering a handler in
`custom_connector_executors`. Registered executors run as ToolCalls and return
normal tool results; unregistered executor names still surface as
`implementation_required`, including the expected executor name, so the gap is
actionable.
If no executor name is declared, CompanyHarvester still writes an
`executorBlueprint` with a deterministic suggested executor name so a later
connector factory can implement/register the missing handler without changing
the tool/task/trajectory model.
Blueprint summaries recompute `registrationStatus` from the live custom
executor registry, so a stored blueprint that was originally `missing` becomes
`registered` in status views once the executor is attached.
Connector ToolCalls that require human approval are also persisted with
`status=approval_required`, so the approval boundary is traceable even though
the tool was not executed. The `/step` response includes that blocked invocation
in `executed_tool_calls` with the same approval id/key.
The next backend step is to split more of those policy stages into smaller
runtime services without changing the concrete Task/Trajectory/Skill/Tool
boundaries.

The current post-harvest boundary is:

```text
benchmark_tasks -> TaskHarvester -> trajectories
trajectories(status=harvested) -> TrajectoryJudge -> SkillPromoter -> skills
skills + governed company tools -> AgentConfigBuilder
-> AgentConfigs(model_agent, codex, claude_code)
```

`harvested` means the trajectory exists and is ready for judging. After judging,
passing trajectories move to `approved` and can be promoted to skills; failing
or low-confidence trajectories move to `review_required` with
`needsHumanReview=true`. This prevents repeated promotion of the same harvested
trajectory and keeps trajectory state distinct from skill state.
The state transition to `approved` happens after `approve_trajectory_as_skill`
succeeds and records the `capabilityId`; if skill promotion fails, the trajectory
is not marked approved.

Backend smoke coverage now exercises this boundary end to end with in-memory
collections and fake harvester/judge adapters:

```text
CompanyIntake -> CompanyHarvester -> benchmark_tasks -> TaskHarvester
-> trajectories -> SkillPromoter -> AgentConfigBuilder -> delivery summary
```

That smoke proves the service contracts line up without requiring a browser,
Mongo, or external LLM. It does not replace live `/step` or connector executor
smokes, which are still required before calling a customer onboarding fully
production-ready.

`AgentConfigBuilder` is intentionally a builder, not a runtime. It emits
declarative AgentConfigs with `runtimeKind`, `runtimeProfile`, tool callables,
skill callables, governed knowledge resources, and the company entity graph.
Tools remain tools, skills remain skills, resources remain resources, and
entities remain business objects inside the config; the concrete AgentRuntime
adapter remains responsible for execution.

Custom connector tool blueprints remain visible in generated AgentConfigs, but
they do not make an agent `ready` until their executor is registered. The
builder records `runtimeReadiness.executableToolCount`,
`missingToolExecutorCount`, and `missingToolNames`; agents backed only by missing
custom executors stay in `draft` with
`trainingStatus=connector_implementation_required`.
CompanyHarvester delivery summaries use that readiness too: an agent build with
only draft agents leaves the run in `building_agents`, marks delivery as
`blocked`, and keeps the next normal action at `implement_connectors` instead of
returning `use_agents`.

Generated AgentConfigs also carry `deliverySurfaces` for chat, API and widget
usage. This makes the onboarding output directly deployable without mixing
delivery concerns into tools, skills, trajectories or resources.
Normal CompanyHarvester status exposes only a simplified delivery summary
(`agentId`, runtime kind, chat availability, API endpoint, and widget embed
script). Dev status keeps the raw `deliverySurfaces` payload for debugging and
integration work.

Runtime smoke coverage verifies that an AgentConfig produced by
`AgentConfigBuilder` can be loaded through `/runtime/agents/{agent_id}/step`,
serialized with its tools, skills, governed knowledge resources, entity graph,
runtime profile, runtime descriptor and delivery surfaces, then dispatched to
the selected runtime adapter. This proves the generated config is consumable by
the shared `/step` contract. It still does not prove external model quality,
browser replay quality, or concrete customer connector executor behavior.
