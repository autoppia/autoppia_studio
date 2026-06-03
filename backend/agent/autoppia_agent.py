import os
import io
import uuid
import asyncio
import base64
import logging
import json
from pathlib import Path
from dotenv import load_dotenv

from agent.apified_cua import ApifiedCUA
from agent.browser_executor import BrowserExecutor

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _build_selector(sel) -> str:
    """Convert the agent's selector dict into a Playwright selector string."""
    if isinstance(sel, str):
        return sel
    if not isinstance(sel, dict):
        return ""
    sel_type = sel.get("type", "")
    attr = sel.get("attribute", "")
    value = sel.get("value", "")
    if sel_type == "attributeValueSelector" and attr and value:
        if attr == "custom":
            return value
        return f'[{attr}="{value}"]'
    if sel_type == "cssSelector" and value:
        return value
    if sel_type == "xpathSelector" and value:
        return f"xpath={value}"
    if sel_type == "testIdSelector" and value:
        return f'[data-testid="{value}"]'
    if value:
        if attr and attr != "custom":
            return f'[{attr}="{value}"]'
        return value
    return ""


def _resolve_selector(args: dict) -> str:
    """Resolve a selector from tool_call arguments.

    Supports: selector dict (legacy), element_id, css_selector, xpath.
    """
    if "selector" in args:
        return _build_selector(args["selector"])
    if "element_id" in args:
        return f'[data-element-id="{args["element_id"]}"]'
    if "css_selector" in args:
        return args["css_selector"]
    if "xpath" in args:
        return f"xpath={args['xpath']}"
    return ""


def _normalize_tool_call(tool_call: dict) -> dict:
    if not isinstance(tool_call, dict):
        return {"name": "unknown", "arguments": {}}
    fn = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else None
    if fn is None:
        return {
            "name": str(tool_call.get("name") or ""),
            "arguments": tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {},
        }

    raw_args = fn.get("arguments")
    if isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            args = parsed if isinstance(parsed, dict) else {}
        except Exception:
            args = {}
    else:
        args = {}
    return {"name": str(fn.get("name") or ""), "arguments": args}


def _action_from_tool_call(tool_call: dict) -> dict:
    args = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
    return args if isinstance(args, dict) else {}


async def _execute_tool_call(page, tool_call: dict) -> None:
    """Execute a tool_call dict (browser.* format) on a Playwright page."""
    name = tool_call.get("name", "")
    args = tool_call.get("arguments", {})

    if name == "browser.click":
        selector = _resolve_selector(args)
        if selector:
            await page.click(selector, timeout=5000)

    elif name == "browser.dblclick":
        selector = _resolve_selector(args)
        if selector:
            await page.dblclick(selector, timeout=5000)

    elif name == "browser.rightclick":
        selector = _resolve_selector(args)
        if selector:
            await page.click(selector, button="right", timeout=5000)

    elif name == "browser.hover":
        selector = _resolve_selector(args)
        if selector:
            await page.hover(selector, timeout=5000)

    elif name in ("browser.input", "browser.type"):
        selector = _resolve_selector(args)
        text = args.get("text", "")
        if selector and text:
            try:
                await page.fill(selector, text, timeout=5000)
            except Exception:
                await page.click(selector, timeout=5000)
                await page.keyboard.type(text, delay=50)

    elif name == "browser.navigate":
        url = args.get("url", "")
        if url:
            await page.goto(url, timeout=15000)

    elif name == "browser.go_back":
        await page.go_back()

    elif name == "browser.scroll":
        direction = args.get("direction", "down")
        amount = int(args.get("amount", 500))
        delta = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {delta})")

    elif name == "browser.search":
        query = args.get("query", "")
        if query:
            await page.goto(f"https://www.google.com/search?q={query}", timeout=15000)

    elif name == "browser.wait":
        wait_time = float(args.get("seconds", args.get("time_seconds", 1.0)))
        await asyncio.sleep(wait_time)

    elif name in ("browser.select_dropdown", "browser.select_option"):
        text = args.get("text", args.get("value", ""))
        selector_arg = args.get("selector") if isinstance(args.get("selector"), dict) else {}
        if selector_arg.get("type") == "role" and selector_arg.get("value") and text:
            await page.get_by_role(selector_arg["value"]).select_option(label=text, timeout=5000)
        else:
            selector = _resolve_selector(args)
            if selector and text:
                await page.select_option(selector, label=text, timeout=5000)

    elif name == "browser.send_keys":
        keys = args.get("keys", "")
        if keys:
            await page.keyboard.press(keys)

    elif name == "browser.hold_key":
        key = args.get("key", "")
        if key:
            await page.keyboard.down(key)
            await asyncio.sleep(0.1)
            await page.keyboard.up(key)

    elif name == "browser.evaluate":
        script = args.get("script", args.get("expression", ""))
        if script:
            await page.evaluate(script)

    elif name in ("browser.screenshot", "browser.snapshot", "browser.done", "browser.finish", "browser.extract", "browser.dropdown_options"):
        pass  # handled at the step level or no-op

    else:
        logger.warning(f"Unknown tool_call name: {name}")


class AutoppiaAgent:
    def __init__(self):
        self.task_id = str(uuid.uuid4())
        self.step_index = 0
        self.history = []
        self.model_thoughts = []
        self.screenshots = []
        self.result = {}
        self.task = None
        self.initial_url = None
        self.storage_state_path = None
        self.cua = None
        self.browser_executor = None
        self._last_thought = None
        self._on_action = None
        self._on_screenshot = None
        self._state = {}  # state roundtrip for the external agent runtime
        self._active_skill_id = None

    def set_on_action(self, callback):
        """Called before each action is executed.
        Signature: async callback(reasoning: str | None, action: str, previous_success: bool, metadata: dict | None = None)
        """
        self._on_action = callback

    def set_on_screenshot(self, callback):
        """Called after a screenshot is captured.
        Signature: async callback(screenshot_base64: str)
        """
        self._on_screenshot = callback

    async def initialize(
        self,
        task: str,
        initial_url: str = None,
        storage_state_path: Path = None,
        context_id: str = "",
        agent_base_url: str = "",
        browser_mode: str = "",
    ) -> None:
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path

        base_url = agent_base_url or os.getenv("AUTOPPIA_AGENT_BASE_URL", "")
        if not base_url:
            raise ValueError("AUTOPPIA_AGENT_BASE_URL environment variable is not set.")

        if base_url.endswith("/step"):
            base_url = base_url[:-5]

        self.cua = ApifiedCUA(base_url=base_url)
        self.browser_executor = BrowserExecutor()
        await self.browser_executor.initialize(
            initial_url=initial_url,
            storage_state_path=storage_state_path,
            context_id=context_id,
            browser_mode=browser_mode,
        )

    async def take_step(self) -> tuple[bool, bool]:
        # Bail out immediately if the browser page is gone (unrecoverable)
        if not self.browser_executor or not self.browser_executor.page:
            logger.error("Browser page is None — cannot continue")
            self.result = {"content": "Browser session lost", "success": False}
            return True, False

        try:
            url = self.browser_executor.get_current_url()
            snapshot_html = ""
            for attempt in range(3):
                try:
                    snapshot_html = await self.browser_executor.get_snapshot_html()
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    logger.warning(f"Snapshot read failed while page was changing; retrying: {e}")
                    await asyncio.sleep(0.5)

            response = await self.cua.act(
                task_id=self.task_id,
                prompt=self.task,
                snapshot_html=snapshot_html,
                url=url,
                step_index=self.step_index,
                history=self.history,
                state_in=self._state,
            )

            # Log the full /step response for debugging
            log_resp = {k: v for k, v in response.items() if k not in ("state_out", "snapshot_html")}
            logger.info(f"/step response: {log_resp}")

            tool_calls = [_normalize_tool_call(tc) for tc in response.get("tool_calls", [])]
            reasoning = response.get("reasoning")
            content = response.get("content")
            done = response.get("done", False)
            state_out = response.get("state_out", {})
            capability_match = response.get("capability_match") if isinstance(response.get("capability_match"), dict) else None

            if capability_match and self._on_action:
                skill_id = str(capability_match.get("skillId") or "")
                if skill_id and skill_id != self._active_skill_id:
                    self._active_skill_id = skill_id
                    try:
                        await self._on_action(
                            f"Using approved skill: {capability_match.get('name') or skill_id}",
                            "skill.use",
                            True,
                            {"skill": capability_match},
                        )
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")

            # Update state for next roundtrip
            self._state = state_out

            # Extract action names for the step callback
            action_names = [tc.get("name", "unknown") for tc in tool_calls]

            # Task done with no actions to execute. If the runtime returns
            # done=true alongside tool calls, execute those calls first.
            if done and not tool_calls:
                logger.info("Task done — agent signalled completion")
                self.result = {
                    "content": content or "Task completed",
                    "success": True,
                }
                if self._on_action and reasoning:
                    try:
                        await self._on_action(reasoning, "browser.done", True)
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")
                self.step_index += 1
                return True, True

            if not tool_calls:
                logger.info("Task stopped — agent returned no tool calls")
                self.result = {
                    "content": content or "Task completed",
                    "success": bool(done),
                }
                if self._on_action and reasoning:
                    try:
                        await self._on_action(reasoning, "browser.done" if done else "browser.wait", True)
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")
                self.step_index += 1
                return True, bool(done)

            # Store thought
            self._last_thought = {
                "reasoning": reasoning,
                "action": ", ".join(action_names),
                "previous_success": True,
            }
            self.model_thoughts.append(self._last_thought)

            # Execute tool_calls one by one
            executed_any = False
            previous_success = True
            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call.get("name", "unknown")

                # Emit action BEFORE executing it
                if self._on_action:
                    try:
                        await self._on_action(reasoning, tool_name, previous_success)
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")

                success = False
                try:
                    await _execute_tool_call(self.browser_executor.page, tool_call)
                    executed_any = True
                    success = True
                    self.history.append(
                        {
                            "step_index": self.step_index,
                            "tool_call": tool_call,
                            "action": _action_from_tool_call(tool_call),
                            "success": True,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error executing {tool_name}: {e}")
                    self._last_thought["previous_success"] = False
                    self.history.append(
                        {
                            "step_index": self.step_index,
                            "tool_call": tool_call,
                            "action": _action_from_tool_call(tool_call),
                            "success": False,
                            "error": str(e),
                        }
                    )

                previous_success = success

                # Screenshot after each action (skip for wait)
                if tool_name != "browser.wait":
                    try:
                        screenshot = await self.browser_executor.screenshot()
                        if screenshot:
                            self.screenshots.append(screenshot)
                            if self._on_screenshot:
                                await self._on_screenshot(screenshot)
                    except Exception as e:
                        logger.error(f"Error taking screenshot: {e}")

            self.step_index += 1
            if done:
                self.result = {
                    "content": content or "Task completed",
                    "success": True,
                }
                if self._on_action and reasoning:
                    try:
                        await self._on_action(reasoning, "browser.done", previous_success)
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")
                return True, executed_any
            return False, executed_any

        except ConnectionError as e:
            logger.error(f"CUA connection failed: {e}")
            self.result = {"content": f"Agent error: {e}", "success": False}
            self.step_index += 1
            return True, False
        except Exception as e:
            logger.error(f"Error in take_step: {e}")
            self.step_index += 1
            # If the page is gone, stop immediately
            if not self.browser_executor.page:
                self.result = {"content": "Browser session lost", "success": False}
                return True, False
            return False, False

    async def take_screenshot(self) -> str:
        if self.screenshots:
            return self.screenshots[-1]
        try:
            return await self.browser_executor.screenshot()
        except Exception:
            return None

    def get_live_url(self) -> str | None:
        if self.browser_executor:
            return self.browser_executor.get_live_url()
        return None

    async def close(self) -> None:
        if self.browser_executor:
            await self.browser_executor.close()

    async def release_session(self) -> None:
        if self.browser_executor:
            await self.browser_executor.release_session()

    async def add_new_task(self, new_task: str, preserve_history: bool = False) -> None:
        self.task = new_task
        self.task_id = str(uuid.uuid4())
        if not preserve_history:
            self.step_index = 0
            self.history = []
            self.model_thoughts = []
            self._state = {}
        self.result = {}

    def get_model_thought(self) -> dict:
        return self._last_thought

    def get_result(self) -> dict:
        if self.result:
            return self.result
        return {"content": None, "success": False}

    def generate_gif(self, output_path: Path) -> str:
        try:
            from PIL import Image

            if not self.screenshots:
                return "GIF"

            frames = []
            for screenshot_b64 in self.screenshots:
                img_data = base64.b64decode(screenshot_b64)
                img = Image.open(io.BytesIO(img_data))
                frames.append(img.convert("RGBA"))

            if not frames:
                return "GIF"

            frames[0].save(str(output_path), save_all=True, append_images=frames[1:], duration=1000, loop=0)

            with open(output_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        except Exception as e:
            logger.error(f"Error generating GIF: {e}")
            return "GIF"
