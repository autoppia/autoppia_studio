# CompanyHarvester Contract

This is the benchmark-facing contract for ICA. A miner submits a
CompanyHarvester implementation. The harvester receives company material and
returns the package needed to build agents that can solve company tasks.

## Interface

```python
class ICompanyHarvester(Protocol):
    id: str
    name: str

    async def harvest_company(
        self,
        request: CompanyHarvesterInput,
    ) -> CompanyHarvesterOutput:
        ...
```

Existing Studio harvesters can be wrapped with `CompanyHarvesterAdapter` when
they expose `harvest(request)`.

## Input

`CompanyHarvesterInput` contains:

- `companyId`, `companyName`, `description`
- `materials`: web, OpenAPI/API docs, documents, auth notes, task lists, code
  repositories, or code files
- `discoveryMode`: source combination hint such as `ui_only`, `ui_api`,
  `code_only`, or `full_company`
- `userTasks`: optional user-supplied tasks; most ICA discovery modes pass no
  ground-truth tasks
- `availableInventory`: allowed connectors, tools, and runtime kinds
- `runtimeKinds`: valid agent providers: `model_agent`, `codex`, `claude_code`

The harvester should prefer existing allowed inventory. If no suitable connector
or tool exists, it may propose custom connector/tool code, but that proposal must
include evidence and executable implementation details.

## Output

`CompanyHarvesterOutput` must include:

- `proposedTasks`: tasks inferred from company material
- `taskSolutions`: one solution package per task when possible
- `agentConfigs`: optional built agent configs
- `questions`: user questions when material is insufficient
- `confidence` and metadata/evidence

Each `CompanyTaskSolution` should include:

- `connectors`
- `tools`
- `trajectories`
- `skills`
- `agentProvider`

## Origins

Connector/tool origins must be meaningful:

- `existing`: already available connector
- `existing_connector_tool`: already available tool
- `derived_from_openapi`: generated from API/OpenAPI evidence
- `derived_from_code`: inferred from source code
- `proposed_custom`: custom implementation required
- `unknown`: discouraged; usually fails solution discovery

For `derived_*` origins, include evidence. For `proposed_custom`, include
custom connector/tool code details.

## Evaluation Phases

ICA evaluates three phases:

- Task Discovery: inferred tasks vs expected demo company tasks.
- Solution Discovery: connectors/tools/trajectories/skills/agent provider,
  origin validity, hallucinated tools/connectors, and completeness.
- Agent Execution: build a task agent from the solution package and run
  deterministic demo company tests when available.

The final benchmark score weights task discovery, solution discovery, inventory,
and agent execution. If no execution tests exist for a legacy demo company, ICA
marks agent execution as skipped rather than failed.

