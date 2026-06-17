# Agent Harvesters

This folder documents the task-to-trajectory harvesters used by Automata Cloud.
The compatibility import path remains `app.services.agent_harvesters` for now.

Official internal names:

- `autoppia_harvester`: official HTTP adapter for the external
  `autoppia_harvester` service. The external service owns provider selection
  with `AUTOPPIA_HARVESTER_PROVIDER` (`claude_code` or `openai`).
- `claude_cli`: local experimental fallback that runs Claude CLI from this repo.
- `noop`: test/off switch.

Legacy aliases:

- `top_miner`: old name for the external Autoppia/IWA HTTP contract. Keep it for
  old runs and scripts, but do not expose it as a separate product option.

The Studio UI must not allow users to choose a harvester. Production onboarding
uses `AUTOMATA_AGENT_HARVESTER` from backend environment/config. Benchmark
scripts may still pass a harvester name explicitly for internal experiments.
