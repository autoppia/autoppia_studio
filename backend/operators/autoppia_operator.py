import os
import io
import uuid
import asyncio
import base64
import logging
from pathlib import Path
from dotenv import load_dotenv

from cua.apified_cua import ApifiedCUA
from operators.base_operator import BaseOperator
from execution.browser_executor import BrowserExecutor

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
        # "custom" attribute means value is already a Playwright selector
        if attr == "custom":
            return value
        return f'[{attr}="{value}"]'
    if sel_type == "cssSelector" and value:
        return value
    if sel_type == "xpathSelector" and value:
        return f"xpath={value}"
    if sel_type == "testIdSelector" and value:
        return f'[data-testid="{value}"]'
    # Fallback
    if value:
        if attr and attr != "custom":
            return f'[{attr}="{value}"]'
        return value
    return ""


async def _execute_action(page, action: dict) -> None:
    """Execute a raw action dict on a Playwright page."""
    action_type = action.get("type", "")

    if action_type == "ClickAction":
        selector = _build_selector(action.get("selector"))
        if selector:
            await page.click(selector, timeout=5000)
        else:
            logger.warning(f"ClickAction missing selector: {action}")

    elif action_type == "TypeAction":
        selector = _build_selector(action.get("selector"))
        text = action.get("text", "")
        if selector and text:
            try:
                await page.fill(selector, text, timeout=5000)
            except Exception:
                # Fallback: click the element then type via keyboard
                await page.click(selector, timeout=5000)
                await page.keyboard.type(text, delay=50)
        else:
            logger.warning(f"TypeAction missing selector or text: {action}")

    elif action_type == "NavigateAction":
        url = action.get("url", "")
        go_back = action.get("go_back", False)
        go_forward = action.get("go_forward", False)
        if go_back:
            await page.go_back()
        elif go_forward:
            await page.go_forward()
        elif url:
            await page.goto(url, timeout=15000)
        else:
            logger.warning(f"NavigateAction missing url: {action}")

    elif action_type == "ScrollAction":
        down = action.get("down", True)
        pixels = 500
        if down:
            await page.evaluate(f"window.scrollBy(0, {pixels})")
        else:
            await page.evaluate(f"window.scrollBy(0, -{pixels})")

    elif action_type == "WaitAction":
        wait_time = float(action.get("time_seconds", 1.0))
        logger.info(f"Waiting {wait_time}s")
        await asyncio.sleep(wait_time)

    elif action_type == "SelectDropDownOptionAction":
        selector = _build_selector(action.get("selector"))
        text = action.get("text", "")
        if selector and text:
            await page.select_option(selector, label=text, timeout=5000)
        else:
            logger.warning(f"SelectDropDownOptionAction missing selector or text: {action}")

    else:
        logger.warning(f"Unknown action type: {action_type}")


class AutoppiaOperator(BaseOperator):
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

    def set_on_action(self, callback):
        """Set an async callback called after each individual action executes.
        Signature: async callback(action_type: str, screenshot: str | None, success: bool)
        """
        self._on_action = callback

    async def initialize(
        self,
        task: str,
        initial_url: str = None,
        storage_state_path: Path = None
    ) -> None:
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path

        base_url = os.getenv("AUTOPPIA_AGENT_BASE_URL", "")
        if not base_url:
            raise ValueError("AUTOPPIA_AGENT_BASE_URL environment variable is not set.")

        self.cua = ApifiedCUA(base_url=base_url)
        self.browser_executor = BrowserExecutor()
        await self.browser_executor.initialize(
            initial_url=initial_url,
            storage_state_path=storage_state_path
        )

    async def take_step(self) -> tuple[bool, bool]:
        try:
            url = self.browser_executor.get_current_url()
            snapshot_html = await self.browser_executor.get_snapshot_html()

            actions = await self.cua.act(
                task_id=self.task_id,
                prompt=self.task,
                snapshot_html=snapshot_html,
                url=url,
                step_index=self.step_index,
                history=self.history
            )

            # None = CUA signalled task is done
            if actions is None:
                logger.info("Task done — CUA returned no actions")
                self.result = {
                    "content": "Task completed",
                    "success": True
                }
                self.step_index += 1
                return True, True

            # Store thought
            action_descriptions = [a.get("type", "unknown") for a in actions]
            self._last_thought = {
                "next_goal": ", ".join(action_descriptions),
                "evaluation_previous_goal": "Starting" if self.step_index == 0 else "Success",
                "previous_success": True
            }
            self.model_thoughts.append(self._last_thought)

            # Execute actions one by one
            executed_any = False
            for action in actions:
                action_type = action.get("type", "unknown")
                success = False
                try:
                    await _execute_action(self.browser_executor.page, action)
                    executed_any = True
                    success = True
                    self.history.append({
                        "step_index": self.step_index,
                        "action": action,
                    })
                except Exception as e:
                    logger.error(f"Error executing action {action_type}: {e}")
                    self._last_thought["previous_success"] = False
                    self._last_thought["evaluation_previous_goal"] = f"Failed: {str(e)}"
                    self.history.append({
                        "step_index": self.step_index,
                        "action": action,
                        "error": str(e),
                    })

                # Screenshot after each action (skip for WaitAction)
                screenshot = None
                if action_type != "WaitAction":
                    try:
                        screenshot = await self.browser_executor.screenshot()
                        if screenshot:
                            self.screenshots.append(screenshot)
                    except Exception as e:
                        logger.error(f"Error taking screenshot: {e}")

                # Notify per-action callback
                if self._on_action:
                    try:
                        await self._on_action(action_type, screenshot, success)
                    except Exception as e:
                        logger.error(f"Error in on_action callback: {e}")

            self.step_index += 1
            return False, executed_any

        except Exception as e:
            logger.error(f"Error in take_step: {e}")
            self.step_index += 1
            return False, False

    async def take_screenshot(self) -> str:
        if self.screenshots:
            return self.screenshots[-1]
        try:
            return await self.browser_executor.screenshot()
        except Exception:
            return None

    async def close(self) -> None:
        if self.browser_executor:
            await self.browser_executor.close()

    async def add_new_task(self, new_task: str) -> None:
        self.task = new_task
        self.task_id = str(uuid.uuid4())
        self.step_index = 0
        self.history = []
        self.model_thoughts = []
        self.result = {}

    def get_model_thought(self) -> dict:
        return self._last_thought

    def get_result(self) -> dict:
        if self.result:
            return self.result
        return {
            "content": None,
            "success": False
        }

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

            frames[0].save(
                str(output_path),
                save_all=True,
                append_images=frames[1:],
                duration=1000,
                loop=0
            )

            with open(output_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')

        except Exception as e:
            logger.error(f"Error generating GIF: {e}")
            return "GIF"
