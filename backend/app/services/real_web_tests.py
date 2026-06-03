from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return html
    return " ".join(parser.parts)


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str).lower()
    except Exception:
        return str(value).lower()


def _tool_name(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    name = str(raw.get("name") or raw.get("action") or "").strip()
    if name.startswith("browser."):
        name = name.split(".", 1)[1]
    return name


def _arguments(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else raw.get("args")
    return args if isinstance(args, dict) else {}


def _template(value: Any, parameters: dict[str, Any]) -> str:
    text = str(value or "")
    for key, param_value in parameters.items():
        text = text.replace("{{" + str(key) + "}}", str(param_value))
    return text


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2]


@dataclass(frozen=True)
class StepTrace:
    """IWA-style per-step state exposed to tests as execution_history."""

    step_index: int
    tool_call: dict[str, Any] = field(default_factory=dict)
    url: str = ""
    html: str = ""
    text: str = ""
    screenshot: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def haystack(self) -> str:
        return " ".join([self.url, self.text, _html_to_text(self.html), _json_text(self.metadata)]).lower()


@dataclass(frozen=True)
class TaskTestResult:
    test_type: str
    success: bool
    reasoning: str
    step_index: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RealWebTestRun:
    success: bool
    raw_score: float
    tests_passed: int
    total_tests: int
    results: list[TaskTestResult]
    execution_history: list[StepTrace]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "rawScore": self.raw_score,
            "testsPassed": self.tests_passed,
            "totalTests": self.total_tests,
            "tests": [
                {
                    "type": result.test_type,
                    "success": result.success,
                    "reasoning": result.reasoning,
                    "stepIndex": result.step_index,
                    "evidence": result.evidence,
                }
                for result in self.results
            ],
            "executionHistory": [
                {
                    "stepIndex": step.step_index,
                    "toolCall": step.tool_call,
                    "url": step.url,
                    "text": step.text[:1000],
                    "screenshot": step.screenshot,
                    "metadata": step.metadata,
                }
                for step in self.execution_history
            ],
        }


def build_execution_history(*, tool_calls: list[dict[str, Any]], metadata: dict[str, Any], artifacts: dict[str, Any]) -> list[StepTrace]:
    raw_history = metadata.get("execution_history") or metadata.get("executionHistory") or artifacts.get("execution_history") or artifacts.get("executionHistory")
    history: list[StepTrace] = []
    if isinstance(raw_history, list):
        for index, raw_step in enumerate(raw_history):
            if not isinstance(raw_step, dict):
                continue
            html = str(raw_step.get("html") or raw_step.get("snapshotHtml") or "")
            text = str(raw_step.get("text") or raw_step.get("visibleText") or _html_to_text(html))
            history.append(
                StepTrace(
                    step_index=int(raw_step.get("step_index") or raw_step.get("stepIndex") or index),
                    tool_call=raw_step.get("tool_call") if isinstance(raw_step.get("tool_call"), dict) else raw_step.get("toolCall") if isinstance(raw_step.get("toolCall"), dict) else {},
                    url=str(raw_step.get("url") or raw_step.get("currentUrl") or raw_step.get("finalUrl") or ""),
                    html=html,
                    text=text,
                    screenshot=str(raw_step.get("screenshot") or ""),
                    metadata=raw_step.get("metadata") if isinstance(raw_step.get("metadata"), dict) else {},
                )
            )
    if not history:
        current_url = str(metadata.get("startUrl") or metadata.get("iwaStartUrl") or "")
        for index, tool_call in enumerate(tool_calls):
            args = _arguments(tool_call)
            if _tool_name(tool_call) == "navigate" and isinstance(args.get("url"), str):
                current_url = args["url"]
            history.append(StepTrace(step_index=index, tool_call=tool_call, url=current_url))

    final_html = str(artifacts.get("finalHtml") or artifacts.get("snapshotHtml") or "")
    final_text = str(artifacts.get("finalText") or _html_to_text(final_html))
    final_url = str(artifacts.get("finalUrl") or "")
    if final_url or final_html or final_text:
        if history:
            last = history[-1]
            history[-1] = StepTrace(
                step_index=last.step_index,
                tool_call=last.tool_call,
                url=final_url or last.url,
                html=final_html or last.html,
                text=final_text or last.text,
                screenshot=last.screenshot,
                metadata=last.metadata,
            )
        else:
            history.append(StepTrace(step_index=0, url=final_url, html=final_html, text=final_text))
    return history


class RealWebTestRunner:
    def __init__(self, tests: list[Any], *, parameters: dict[str, Any] | None = None) -> None:
        self.tests = [test for test in tests if isinstance(test, dict)]
        self.parameters = parameters or {}

    def run(self, *, tool_calls: list[dict[str, Any]], execution_history: list[StepTrace]) -> RealWebTestRun:
        results = [self._run_one(test, tool_calls=tool_calls, execution_history=execution_history) for test in self.tests]
        passed = sum(1 for result in results if result.success)
        total = len(results)
        return RealWebTestRun(
            success=total > 0 and passed == total,
            raw_score=(passed / total) if total else 0.0,
            tests_passed=passed,
            total_tests=total,
            results=results,
            execution_history=execution_history,
        )

    def _run_one(self, test: dict[str, Any], *, tool_calls: list[dict[str, Any]], execution_history: list[StepTrace]) -> TaskTestResult:
        test_type = str(test.get("type") or test.get("name") or "").strip()
        if test_type == "ToolSequenceTest":
            return self._tool_sequence_test(test, tool_calls)
        if test_type == "StepUrlTest":
            return self._step_url_test(test, execution_history)
        if test_type == "StepTextTest":
            return self._step_text_test(test, execution_history)
        if test_type == "SafetyPolicyTest":
            return self._safety_policy_test(test, tool_calls)
        return TaskTestResult(test_type or "UnknownTest", False, "Unsupported real-web test type.")

    def _tool_sequence_test(self, test: dict[str, Any], tool_calls: list[dict[str, Any]]) -> TaskTestResult:
        names = [_tool_name(call) for call in tool_calls]
        required = [str(item) for item in test.get("must_include", []) if str(item)]
        missing = [item for item in required if item not in names]
        any_of_groups = test.get("any_of") if isinstance(test.get("any_of"), list) else []
        missing_any = []
        for group in any_of_groups:
            options = [str(item) for item in group] if isinstance(group, list) else [str(group)]
            if not any(option in names for option in options):
                missing_any.append(options)
        success = not missing and not missing_any
        return TaskTestResult(
            "ToolSequenceTest",
            success,
            "Tool sequence matched." if success else f"Missing tools: {missing}; missing alternatives: {missing_any}.",
            evidence={"tools": names},
        )

    def _step_url_test(self, test: dict[str, Any], execution_history: list[StepTrace]) -> TaskTestResult:
        steps = self._select_steps(test, execution_history)
        contains = [_template(item, self.parameters).lower() for item in test.get("url_contains", []) if str(item)]
        contains_any = [_template(item, self.parameters).lower() for item in test.get("url_contains_any", []) if str(item)]
        regexes = [_template(item, self.parameters) for item in test.get("url_regex", []) if str(item)]
        host_contains = [_template(item, self.parameters).lower() for item in test.get("host_contains", []) if str(item)]
        for step in steps:
            url = step.url.lower()
            host = urlsplit(step.url).netloc.lower()
            checks = [
                all(item in url for item in contains) if contains else True,
                any(item in url for item in contains_any) if contains_any else True,
                any(re.search(pattern, step.url, re.IGNORECASE) for pattern in regexes) if regexes else True,
                all(item in host for item in host_contains) if host_contains else True,
            ]
            if all(checks):
                return TaskTestResult("StepUrlTest", True, "URL matched.", step.step_index, {"url": step.url})
        return TaskTestResult("StepUrlTest", False, "No selected step URL matched.", evidence={"checked": [step.url for step in steps]})

    def _step_text_test(self, test: dict[str, Any], execution_history: list[StepTrace]) -> TaskTestResult:
        steps = self._select_steps(test, execution_history)
        contains = [_template(item, self.parameters).lower() for item in test.get("contains", []) if str(item)]
        contains_any = [_template(item, self.parameters).lower() for item in test.get("contains_any", []) if str(item)]
        param_tokens_key = str(test.get("contains_param_tokens") or "")
        min_token_matches = int(test.get("min_token_matches") or 1)
        param_tokens = _tokens(str(self.parameters.get(param_tokens_key) or "")) if param_tokens_key else []
        for step in steps:
            haystack = step.haystack()
            token_matches = [token for token in param_tokens if token in haystack]
            checks = [
                all(item in haystack for item in contains) if contains else True,
                any(item in haystack for item in contains_any) if contains_any else True,
                len(token_matches) >= min_token_matches if param_tokens else True,
            ]
            if all(checks):
                return TaskTestResult("StepTextTest", True, "Step text matched.", step.step_index, {"tokenMatches": token_matches})
        return TaskTestResult("StepTextTest", False, "No selected step text matched.")

    def _safety_policy_test(self, test: dict[str, Any], tool_calls: list[dict[str, Any]]) -> TaskTestResult:
        forbidden_tools = {str(item) for item in test.get("forbidden_tool_names", []) if str(item)}
        forbidden_text = [str(item).lower() for item in test.get("forbidden_arguments_contains", []) if str(item)]
        violations: list[dict[str, Any]] = []
        for index, call in enumerate(tool_calls):
            name = _tool_name(call)
            body = _json_text(call)
            if name in forbidden_tools or any(item in body for item in forbidden_text):
                violations.append({"stepIndex": index, "tool": name, "toolCall": call})
        return TaskTestResult(
            "SafetyPolicyTest",
            not violations,
            "No forbidden tool calls found." if not violations else "Forbidden tool calls found.",
            evidence={"violations": violations},
        )

    @staticmethod
    def _select_steps(test: dict[str, Any], execution_history: list[StepTrace]) -> list[StepTrace]:
        selector = str(test.get("step") or "final")
        if not execution_history:
            return []
        if selector == "any":
            return execution_history
        if selector == "first":
            return [execution_history[0]]
        return [execution_history[-1]]
