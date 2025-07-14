import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Tuple

from operators.shared import BaseOperator, BrowserExecutor
from cua.openai import OpenAICUA

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class OpenAIOperator(BaseOperator):
    def __init__(self):
        self.cua_output = None
        self.model_thoughts = []
        self.screenshots = []
        self.result = {}

    async def initialize(
        self,
        task: str,
        initial_url: str = None,
        storage_state_path: Path = None
    ) -> None:
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path

        self.cua = OpenAICUA()
        self.browser_executor = BrowserExecutor()
        await self.browser_executor.initialize(initial_url)

    async def take_step(self) -> Tuple[bool, bool]:
        if not self.cua_output:
            self.cua_output = await self.cua.call(user_input=self.task)
            return False, False

        computer_calls = [item for item in self.cua_output if item.type == "computer_call"]
        if not computer_calls:
            messages = [item for item in self.cua_output if item.type == "message"]
            self.result = {
                "content": messages[0].content[0].text,
                "success": True
            }
            return True, True
        
        action = computer_calls[0].action        
        await self._handle_action(action)
        await asyncio.sleep(1)  

        screenshot_base64 = await self.browser_executor.screenshot()
        self.screenshots.append(screenshot_base64)

        current_url = self.browser_executor.get_current_url()
        self.cua_output = await self.cua.call(screenshot=screenshot_base64, current_url=current_url)

        model_thoughts = [item for item in self.cua_output if item.type == "reasoning"]
        if model_thoughts:
            self.model_thoughts.append({
                "next_goal": model_thoughts[0].summary[0].text,
                "evaluation_previous_goal": "Not supported with OpenAI",
                "previous_success": True
            })

        return False, False

    async def take_screenshot(self) -> str:
        if len(self.screenshots) > 1:
            return self.screenshots[-1]
        else:
            return None
        
    async def close(self):
        await self.browser_executor.close()

    async def add_new_task(self, new_task: str) -> None:
        self.cua_output = await self.cua.call(user_input=self.task)

    def get_model_thought(self) -> dict:
        if self.model_thoughts:
            return self.model_thoughts[-1]
        else:
            return None

    def get_result(self) -> dict:
        return self.result

    def generate_gif(self, output_path: Path) -> str:
        return "GIF"        

    async def _handle_action(self, action: dict):
        action_type = action.type
        action_args = action.model_dump(exclude={"type"})

        method = getattr(self.browser_executor, action_type, None)
        if method:
            await method(**action_args)

