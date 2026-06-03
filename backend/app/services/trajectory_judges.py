from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class TrajectoryJudge(Protocol):
    name: str

    async def judge(self, context: "TrajectoryJudgeContext") -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class JudgeTaskSpec:
    task_id: str
    task_name: str
    prompt: str
    success_criteria: str
    url: str
    web_project_id: str = ""
    use_case: str = ""
    is_web_real: bool = False
    tests: list[Any] = field(default_factory=list)
    specifications: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgeEvaluatorSpec:
    evaluator: str = ""
    web_agent_id: str = ""
    validator_id: str = ""
    headless: bool = True
    action_timeout_s: float = 20.0
    reset_timeout_s: float = 45.0
    step_timeout_s: float = 45.0
    page_default_timeout_ms: int = 15_000


@dataclass(frozen=True)
class TrajectoryJudgeContext:
    trajectory: dict[str, Any]
    agent_config: dict[str, Any]
    task: JudgeTaskSpec
    tool_calls: list[dict[str, Any]]
    harvester: dict[str, Any]
    metadata: dict[str, Any]
    artifacts: dict[str, Any] = field(default_factory=dict)
    evaluator: JudgeEvaluatorSpec = field(default_factory=JudgeEvaluatorSpec)

    def compact(self, *, max_actions: int = 50) -> dict[str, Any]:
        return {
            "agent": {
                "agentId": self.agent_config.get("agentId", ""),
                "name": self.agent_config.get("name", ""),
                "companyId": self.agent_config.get("companyId", ""),
                "runtimeType": self.agent_config.get("runtimeType", ""),
                "runtimeCapabilities": self.agent_config.get("runtimeCapabilities", {}),
            },
            "task": {
                "taskId": self.task.task_id,
                "taskName": self.task.task_name,
                "prompt": self.task.prompt,
                "successCriteria": self.task.success_criteria,
                "url": self.task.url,
                "webProjectId": self.task.web_project_id,
                "useCase": self.task.use_case,
                "isWebReal": self.task.is_web_real,
                "tests": self.task.tests,
                "specifications": self.task.specifications,
            },
            "trajectory": self.tool_calls[:max_actions],
            "harvester": self.harvester,
            "metadata": self.metadata,
            "artifacts": self.artifacts,
            "evaluator": {
                "evaluator": self.evaluator.evaluator,
                "webAgentId": self.evaluator.web_agent_id,
                "validatorId": self.evaluator.validator_id,
                "headless": self.evaluator.headless,
                "actionTimeoutS": self.evaluator.action_timeout_s,
                "resetTimeoutS": self.evaluator.reset_timeout_s,
                "stepTimeoutS": self.evaluator.step_timeout_s,
                "pageDefaultTimeoutMs": self.evaluator.page_default_timeout_ms,
            },
        }


def build_trajectory_judge_context(*, trajectory: dict[str, Any], agent_config: dict[str, Any] | None = None) -> TrajectoryJudgeContext:
    agent = agent_config or {}
    metadata = trajectory.get("metadata") if isinstance(trajectory.get("metadata"), dict) else {}
    harvester = trajectory.get("harvester") if isinstance(trajectory.get("harvester"), dict) else {}
    canonical = trajectory.get("trajectory") if isinstance(trajectory.get("trajectory"), list) else []
    legacy_actions = trajectory.get("actions") if isinstance(trajectory.get("actions"), list) else []
    if canonical:
        tool_calls = canonical
    else:
        from app.services.iwa_modeling import canonical_tool_trajectory

        tool_calls = canonical_tool_trajectory(legacy_actions)
    artifacts = {
        "finalUrl": trajectory.get("finalUrl") or metadata.get("finalUrl") or "",
        "finalHtml": trajectory.get("finalHtml") or metadata.get("finalHtml") or "",
        "snapshotHtml": trajectory.get("snapshotHtml") or metadata.get("snapshotHtml") or "",
        "screenshots": trajectory.get("screenshots") if isinstance(trajectory.get("screenshots"), list) else [],
        "backendEvents": trajectory.get("backendEvents") if isinstance(trajectory.get("backendEvents"), list) else [],
        "browserSnapshots": trajectory.get("browserSnapshots") if isinstance(trajectory.get("browserSnapshots"), list) else [],
        "extractedData": trajectory.get("extractedData") or metadata.get("extractedData"),
        "htmlChecks": metadata.get("htmlChecks") if isinstance(metadata.get("htmlChecks"), list) else [],
    }
    return TrajectoryJudgeContext(
        trajectory=trajectory,
        agent_config=agent,
        task=JudgeTaskSpec(
            task_id=str(trajectory.get("trajectoryId") or trajectory.get("taskId") or ""),
            task_name=str(trajectory.get("taskName") or trajectory.get("name") or ""),
            prompt=str(trajectory.get("prompt") or ""),
            success_criteria=str(trajectory.get("successCriteria") or ""),
            url=str(metadata.get("iwaStartUrl") or metadata.get("startUrl") or trajectory.get("url") or agent.get("websiteUrl") or ""),
            web_project_id=str(metadata.get("iwaProjectId") or metadata.get("webProjectId") or trajectory.get("webProjectId") or ""),
            use_case=str(metadata.get("iwaUseCase") or metadata.get("useCase") or trajectory.get("useCase") or ""),
            is_web_real=bool(metadata.get("isWebReal") or trajectory.get("isWebReal") or False),
            tests=metadata.get("tests") if isinstance(metadata.get("tests"), list) else [],
            specifications=metadata.get("specifications") if isinstance(metadata.get("specifications"), dict) else {},
        ),
        tool_calls=tool_calls,
        harvester=harvester,
        metadata=metadata,
        artifacts=artifacts,
        evaluator=JudgeEvaluatorSpec(
            evaluator=str(metadata.get("evaluator") or ("iwa_stateful" if metadata.get("iwaProjectId") else "")),
            web_agent_id=str(metadata.get("webAgentId") or f"iwa_judge_{uuid.uuid4().hex[:12]}"),
            validator_id=str(metadata.get("validatorId") or os.getenv("VALIDATOR_ID", "1")),
            headless=(os.getenv("AUTOMATA_IWA_JUDGE_HEADLESS", "true").lower() not in {"0", "false", "no"}),
            action_timeout_s=float(os.getenv("AUTOMATA_IWA_JUDGE_ACTION_TIMEOUT_SECONDS", "20")),
            reset_timeout_s=float(os.getenv("AUTOMATA_IWA_JUDGE_RESET_TIMEOUT_SECONDS", "45")),
            step_timeout_s=float(os.getenv("AUTOMATA_IWA_JUDGE_STEP_TIMEOUT_SECONDS", "45")),
            page_default_timeout_ms=int(os.getenv("AUTOMATA_IWA_JUDGE_PAGE_TIMEOUT_MS", "15000")),
        ),
    )


def _confidence_from_harvester(context: TrajectoryJudgeContext) -> float:
    harvester = context.harvester
    return max(0.0, min(1.0, float(harvester.get("confidence") or 0)))


@dataclass(frozen=True)
class RulesJudge:
    name: str = "rules"

    async def judge(self, context: TrajectoryJudgeContext) -> dict[str, Any]:
        if not context.tool_calls:
            return {"label": "fail", "confidence": 1.0, "needsHumanReview": True, "reasoning": "Trajectory has no executable actions.", "judge": self.name}
        confidence = _confidence_from_harvester(context)
        return {
            "label": "pass" if confidence >= 0.85 else "pending",
            "confidence": confidence,
            "needsHumanReview": confidence < 0.85,
            "reasoning": "Rules judge used harvester confidence and executable-action presence.",
            "judge": self.name,
        }


@dataclass(frozen=True)
class LLMJudge:
    name: str = "llm"

    async def judge(self, context: TrajectoryJudgeContext) -> dict[str, Any]:
        if not context.tool_calls:
            return {"label": "fail", "confidence": 1.0, "needsHumanReview": True, "reasoning": "Trajectory has no executable actions.", "judge": self.name}

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            fallback = await RulesJudge().judge(context)
            return {**fallback, "judge": "rules:no_openai_api_key"}

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        model = os.getenv("AUTOMATA_EVAL_JUDGE_MODEL", "gpt-5-mini")
        payload = context.compact(max_actions=50)
        prompt = (
            "You are Automata LLMJudge. Decide whether this harvested trajectory is safe and useful enough "
            "to become an executable skill. Writes/sends are acceptable only if represented behind human approval, "
            "unless the connector/task metadata explicitly says the environment is a sandbox/demo web. "
            "You receive the same judge context shape as deterministic judges: task spec, actions, harvester result, "
            "metadata, available replay artifacts, backend events, screenshots/snapshots when present, and evaluator config. "
            "Return strict JSON with label pass|fail|pending, confidence 0-1, needsHumanReview boolean, reasoning string.\n\n"
            f"Judge context:\n{json.dumps(payload, ensure_ascii=False)[:18000]}"
        )
        try:
            response = await client.responses.create(
                model=model,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
        except Exception as exc:
            return {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": f"LLMJudge failed: {exc}", "judge": model}
        try:
            data = json.loads(response.output_text)
        except Exception:
            data = {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": response.output_text[:1000]}
        label = str(data.get("label") or "pending").lower()
        if label not in {"pass", "fail", "pending"}:
            label = "pending"
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
        return {
            "label": label,
            "confidence": confidence,
            "needsHumanReview": bool(data.get("needsHumanReview", confidence < 0.75 or label == "pending")),
            "reasoning": str(data.get("reasoning") or ""),
            "judge": model,
        }


@dataclass(frozen=True)
class HardcodedHtmlJudge:
    name: str = "hardcoded_html"

    async def judge(self, context: TrajectoryJudgeContext) -> dict[str, Any]:
        html = str(context.artifacts.get("finalHtml") or context.artifacts.get("snapshotHtml") or "")
        checks = context.artifacts.get("htmlChecks") if isinstance(context.artifacts.get("htmlChecks"), list) else []
        if not checks:
            return {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": "No htmlChecks metadata was provided.", "judge": self.name}
        missing = [str(item) for item in checks if str(item) not in html]
        return {
            "label": "fail" if missing else "pass",
            "confidence": 1.0,
            "needsHumanReview": bool(missing),
            "reasoning": f"Missing HTML strings: {missing}" if missing else "All configured HTML lookup strings were found.",
            "judge": self.name,
        }


@dataclass(frozen=True)
class RealWebJudge:
    name: str = "real_web"

    async def judge(self, context: TrajectoryJudgeContext) -> dict[str, Any]:
        if not context.tool_calls:
            return {"label": "fail", "confidence": 1.0, "needsHumanReview": True, "reasoning": "Trajectory has no executable tools.", "judge": self.name}
        tests = context.task.tests or context.metadata.get("tests")
        if not isinstance(tests, list) or not tests:
            return {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": "Real-web task has no tests.", "judge": self.name}

        from app.services.real_web_tests import RealWebTestRunner, build_execution_history

        parameters = context.metadata.get("parameters") if isinstance(context.metadata.get("parameters"), dict) else {}
        execution_history = build_execution_history(tool_calls=context.tool_calls, metadata=context.metadata, artifacts=context.artifacts)
        run = RealWebTestRunner(tests, parameters=parameters).run(tool_calls=context.tool_calls, execution_history=execution_history)
        label = "pass" if run.success else "fail"
        return {
            "label": label,
            "confidence": 1.0 if run.success else max(0.0, min(0.99, run.raw_score)),
            "needsHumanReview": not run.success,
            "reasoning": f"RealWeb tests scored {run.tests_passed}/{run.total_tests} raw={run.raw_score:.3f}.",
            "judge": self.name,
            "evidence": run.as_evidence(),
        }


@dataclass(frozen=True)
class IwaJudge:
    name: str = "iwa"

    async def judge(self, context: TrajectoryJudgeContext) -> dict[str, Any]:
        project_id = context.task.web_project_id
        use_case = context.task.use_case
        if not project_id or not use_case:
            return {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": "Trajectory has no IWA project/use-case metadata.", "judge": self.name}
        if not context.tool_calls:
            return {"label": "fail", "confidence": 1.0, "needsHumanReview": True, "reasoning": "Trajectory has no executable actions.", "judge": self.name}
        try:
            return await self._judge_with_stateful_evaluator(context=context, project_id=project_id, use_case=use_case)
        except Exception as exc:
            return {"label": "pending", "confidence": 0.0, "needsHumanReview": True, "reasoning": f"IWA judge failed: {exc}", "judge": self.name}

    async def _judge_with_stateful_evaluator(self, *, context: TrajectoryJudgeContext, project_id: str, use_case: str) -> dict[str, Any]:
        from autoppia_iwa.src.data_generation.tasks.classes import BrowserSpecification, Task
        from autoppia_iwa.src.data_generation.tests.classes import BaseTaskTest
        from autoppia_iwa.src.demo_webs.trajectory_registry import get_trajectory_map
        from autoppia_iwa.src.evaluation.stateful_evaluator import AsyncStatefulEvaluator, TaskExecutionSessionConfig
        from autoppia_iwa.src.execution.actions.actions import NavigateAction
        from autoppia_iwa.src.execution.actions.base import BaseAction
        from autoppia_iwa.src.web_agents.apified_iterative_agent import ApifiedWebAgent

        golden = get_trajectory_map(project_id) or {}
        expected = golden.get(use_case)
        if expected is None:
            return {
                "label": "pending",
                "confidence": 0.2,
                "needsHumanReview": True,
                "reasoning": f"IWA project {project_id!r} has no golden trajectory for use case {use_case!r}.",
                "judge": self.name,
            }
        tests = [BaseTaskTest.deserialize(json.loads(json.dumps(test.model_dump()))) for test in (expected.tests or [])]
        if not tests:
            return {
                "label": "pending",
                "confidence": 0.0,
                "needsHumanReview": True,
                "reasoning": f"IWA use case {project_id}/{use_case} has no tests.",
                "judge": self.name,
            }

        task_url = context.task.url or self._task_url(context.trajectory, expected)
        web_agent_id = context.evaluator.web_agent_id or f"iwa_judge_{uuid.uuid4().hex[:12]}"
        task = Task(
            id=context.task.task_id or str(uuid.uuid4()),
            url=task_url,
            prompt=context.task.prompt or str(expected.prompt or ""),
            web_project_id=project_id,
            is_web_real=context.task.is_web_real,
            specifications=BrowserSpecification(),
            tests=self._replace_web_agent_placeholders(tests, web_agent_id),
        )

        parsed_actions = self._build_iwa_actions(
            raw_actions=context.tool_calls,
            task_url=task_url,
            parser=ApifiedWebAgent(base_url="http://127.0.0.1:9999"),
            navigate_cls=NavigateAction,
            base_action_cls=BaseAction,
        )
        if not parsed_actions:
            return {"label": "fail", "confidence": 1.0, "needsHumanReview": True, "reasoning": "IWA evaluator could not parse any executable browser actions.", "judge": self.name}

        evaluator = AsyncStatefulEvaluator(
            task=task,
            web_agent_id=web_agent_id,
            should_record_gif=False,
            capture_screenshot=False,
            config=TaskExecutionSessionConfig(
                action_timeout_s=context.evaluator.action_timeout_s,
                page_default_timeout_ms=context.evaluator.page_default_timeout_ms,
            ),
            headless=context.evaluator.headless,
        )
        action_errors: list[str] = []
        final_url = ""
        try:
            await asyncio.wait_for(evaluator.reset(), context.evaluator.reset_timeout_s)
            for index, action in enumerate(parsed_actions, start=1):
                step = await asyncio.wait_for(evaluator.step(action), context.evaluator.step_timeout_s)
                final_url = step.snapshot.url
                result = step.action_result
                if result is not None and not getattr(result, "successfully_executed", False):
                    action_errors.append(f"{index}:{type(action).__name__}:{getattr(result, 'error', '')}")
                    break
                if getattr(step.score, "success", False):
                    break
            details = await evaluator.get_score_details()
        finally:
            await evaluator.close()

        passed = int(getattr(details, "tests_passed", 0) or 0)
        total = int(getattr(details, "total_tests", 0) or 0)
        raw_score = float(getattr(details, "raw_score", 0.0) or 0.0)
        success = bool(getattr(details, "success", False))
        label = "pass" if success else "fail"
        confidence = 1.0 if success else max(0.0, min(0.99, raw_score))
        return {
            "label": label,
            "confidence": confidence,
            "needsHumanReview": not success,
            "reasoning": (
                f"IWA StatefulEvaluator replayed {len(parsed_actions)} actions for {project_id}/{use_case}. "
                f"Score {passed}/{total} raw={raw_score:.3f}."
                + (f" Action errors: {action_errors}" if action_errors else "")
            ),
            "judge": "iwa_stateful",
            "evidence": {
                "projectId": project_id,
                "useCase": use_case,
                "testsPassed": passed,
                "totalTests": total,
                "rawScore": raw_score,
                "success": success,
                "finalUrl": final_url,
                "actionErrors": action_errors,
            },
        }

    @staticmethod
    def _task_url(trajectory: dict[str, Any], expected: Any) -> str:
        metadata = trajectory.get("metadata") if isinstance(trajectory.get("metadata"), dict) else {}
        start_url = str(metadata.get("iwaStartUrl") or "").strip()
        if start_url:
            return start_url
        for raw in (trajectory.get("trajectory") or trajectory.get("actions") or []):
            action = raw if isinstance(raw, dict) else {}
            name = str(action.get("action") or action.get("name") or "")
            args = action.get("args") if isinstance(action.get("args"), dict) else action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            if name in {"browser.navigate", "navigate"} and isinstance(args.get("url"), str):
                return args["url"]
        return str(getattr(expected, "to_step_tool_calls_trajectory", lambda: {})().get("url") or "")

    @staticmethod
    def _replace_web_agent_placeholders(tests: list[Any], web_agent_id: str) -> list[Any]:
        from autoppia_iwa.src.data_generation.tests.classes import BaseTaskTest

        replaced = []
        for test in tests:
            payload = json.loads(json.dumps(test.model_dump()))
            raw = json.dumps(payload)
            raw = raw.replace("<web_agent_id>", web_agent_id).replace("user<web_agent_id>", f"user{web_agent_id}")
            replaced.append(BaseTaskTest.deserialize(json.loads(raw)))
        return replaced

    @classmethod
    def _build_iwa_actions(cls, *, raw_actions: list[Any], task_url: str, parser: Any, navigate_cls: Any, base_action_cls: Any) -> list[Any]:
        built = []
        for raw in raw_actions:
            canonical = cls._canonical_tool_call(raw, task_url)
            if canonical is None:
                continue
            try:
                response = parser._parse_canonical_response({"tool_calls": [canonical], "done": False})
                if response is None or not response.tool_calls:
                    continue
                payload = parser._tool_call_to_action_payload(response.tool_calls[0])
                action = base_action_cls.create_action(payload)
                if action is None:
                    continue
                if isinstance(action, navigate_cls):
                    action.url = canonical["arguments"]["url"]
                built.append(action)
            except Exception:
                continue
        return built

    @classmethod
    def _canonical_tool_call(cls, raw: Any, task_url: str) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        name = str(raw.get("name") or raw.get("action") or "").strip()
        if not name:
            return None
        if name == "browser.done" or name.endswith(".done") or name == "api.human_approval":
            return None
        if name.startswith("api."):
            return None
        if not name.startswith("browser.") and name != "user.request_input":
            name = f"browser.{name}"
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else raw.get("args") if isinstance(raw.get("args"), dict) else {}
        args = json.loads(json.dumps(args))
        args.pop("attributes", None)
        selector = args.get("selector")
        if isinstance(selector, dict):
            selector.pop("attributes", None)
            normalized_selector = cls._normalize_selector(selector)
            if normalized_selector is None:
                return None
            args["selector"] = normalized_selector
        if name == "browser.navigate" and isinstance(args.get("url"), str):
            args["url"] = cls._normalize_navigation_url(args["url"], task_url)
        return {"name": name, "arguments": args}

    @staticmethod
    def _normalize_selector(selector: dict[str, Any]) -> dict[str, Any] | None:
        selector_type = str(selector.get("type") or "").strip()
        value = str(selector.get("value") or "").strip()
        if selector_type in {"attributeValueSelector", "tagContainsSelector", "xpathSelector"}:
            return selector
        if selector_type == "cssSelector":
            if value.startswith("#") and len(value) > 1 and not any(ch in value[1:] for ch in " .>#:["):
                return {"type": "attributeValueSelector", "attribute": "id", "value": value[1:], "case_sensitive": False}
            if value.startswith("[") and value.endswith("]") and "=" in value:
                key, raw = value[1:-1].split("=", 1)
                return {"type": "attributeValueSelector", "attribute": key.strip(), "value": raw.strip().strip("\"'"), "case_sensitive": False}
            escaped = value.replace("'", "\\'")
            return {"type": "xpathSelector", "value": f"//*[contains(concat(' ', normalize-space(@class), ' '), ' {escaped.lstrip('.')} ')]"} if value.startswith(".") else None
        if selector_type == "role":
            role = value or str(selector.get("role") or "*").strip() or "*"
            name = str(selector.get("name") or selector.get("label") or "").strip()
            if not name:
                return None
            tag = role if role in {"button", "a", "input", "textarea", "select"} else "*"
            escaped_name = name.replace('"', '\\"')
            return {
                "type": "xpathSelector",
                "value": (
                    f"//{tag}[normalize-space(.)=\"{escaped_name}\" "
                    f"or @aria-label=\"{escaped_name}\" "
                    f"or @title=\"{escaped_name}\" "
                    f"or @name=\"{escaped_name}\" "
                    f"or @value=\"{escaped_name}\"]"
                ),
            }
        return None

    @staticmethod
    def _normalize_navigation_url(action_url: str, task_url: str) -> str:
        task_parts = urlsplit(task_url)
        action_parts = urlsplit(action_url)
        if not task_parts.scheme or not task_parts.netloc:
            return action_url
        filtered_query = [(key, value) for key, value in parse_qsl(action_parts.query, keep_blank_values=True) if key not in {"X-WebAgent-Id", "web_agent_id", "X-Validator-Id", "validator_id"}]
        path = action_parts.path or task_parts.path or "/"
        query = urlencode(filtered_query, doseq=True)
        if "seed=" in task_parts.query and "seed=" not in query:
            query = task_parts.query
        return urlunsplit((task_parts.scheme, task_parts.netloc, path, query, ""))


JUDGES: dict[str, TrajectoryJudge] = {
    "rules": RulesJudge(),
    "llm": LLMJudge(),
    "hardcoded_html": HardcodedHtmlJudge(),
    "real_web": RealWebJudge(),
    "iwa": IwaJudge(),
}


def default_judge_name() -> str:
    return (os.getenv("AUTOMATA_TRAJECTORY_JUDGE") or "llm").strip() or "llm"


def get_trajectory_judge(name: str | None = None) -> TrajectoryJudge:
    key = (name or default_judge_name()).strip()
    return JUDGES.get(key) or JUDGES["llm"]


def list_trajectory_judges() -> list[dict[str, str]]:
    return [{"name": key, "status": "available"} for key in sorted(JUDGES)]
