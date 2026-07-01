# Infinite Company Arena

`ica` is the local benchmark package for CompanyHarvester evaluation.

It should stay independent from Studio product concerns. Studio may call ICA,
persist ICA runs, and render ICA reports, but the benchmark contracts and
evaluation logic belong here.

## Responsibilities

- Define demo company benchmark schemas.
- Define CompanyHarvester input/output contracts used by miners.
- Materialize company sources into harvester input.
- Evaluate task discovery.
- Evaluate solution discovery.
- Build and execute benchmark agents against demo company tests.

## Current Layout

- `schemas.py`: ICA demo company and evaluation result schemas.
- `company_harvesters/interfaces.py`: public CompanyHarvester protocol.
- `company_harvesters/schemas.py`: CompanyHarvester request/result contracts.
- `company_harvesters/runners.py`: Studio-backed runner adapters.
- `demo_companies/loader.py`: manifest loading and demo company path helpers.
- `demo_companies/materializer.py`: source-combination materialization.
- `evaluation/task_discovery.py`: task discovery scoring.
- `evaluation/solution_discovery.py`: solution package scoring.
- `evaluation/agent_execution.py`: build/run agent execution checks.
- `evaluation/benchmark.py`: full benchmark orchestration.
- `benchmark.py`: compatibility facade that reexports the public API.
- `execution/demo_company_executors.py`: deterministic execution harnesses for
  demo company tests.
- `tests/`: ICA benchmark and demo-company corpus tests. Backend route tests
  stay under `backend/tests`; `demo_companies` should not contain benchmark test
  code.
- `docs/harvester_contract.md`: miner-facing CompanyHarvester contract.

## CLI

```bash
python -m ica.cli.run --company autocommerce --mode all_sources --harvester agentic
python -m ica.cli.run --company autocommerce --mode all_sources --inventory-only
```

## Direction

Do not add new benchmark logic under `backend/app/services/infinite_company_arena.py`.
That file is only a compatibility wrapper.
