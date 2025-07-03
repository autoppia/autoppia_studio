import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Tuple

from openai import AsyncOpenAI
from playwright.async_api import Browser

from operators.shared import BaseOperator, BrowserExecutor

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class OpenAIOperator(BaseOperator):
    def __init__(self):
        self.client = AsyncOpenAI()
        self.model = "computer-use-preview"
        self.tools = [{
            "type": "computer_use_preview",
            "display_width": 1024,
            "display_height": 768,
            "environment": "browser"
        }],   

        self.response = None
        self.model_thoughts = []
        self.screenshots = []
        self.result = None

    async def initialize(
        self,
        browser: Browser,
        task: str,
        initial_url: str = None,
        storage_state_path: Path = None
    ) -> None:
        self.browser = browser
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path    

        self.browser_executor = BrowserExecutor()
        await self.browser_executor.initialize(self.browser)

    async def take_step(self) -> Tuple[bool, bool]:
        if self.response is None:
            await self._take_initial_step()
            return False, False

        computer_calls = [item for item in self.response.output if item.type == "computer_call"]
        if not computer_calls:
            print("No computer call found. Output from model:")
            for item in self.response.output:
                print(item)
            return True, True
        
        computer_call = computer_calls[0]
        last_call_id = computer_call.call_id
        action = computer_call.action
        pending_safety_checks = computer_call.get("pending_safety_checks", [])
        
        await self._handle_action(action)
        await asyncio.sleep(1)  

        screenshot_base64 = self.browser_executor.screenshot()
        self.screenshots.append(screenshot_base64)

        current_url = self.browser_executor.get_current_url()

        self.response = self.client.responses.create(
            model=self.model,
            previous_response_id=self.response.id,
            tools=self.tools,
            input=[
                {
                    "type": "computer_call_output",
                    "call_id": last_call_id,
                    "acknowledged_safety_checks": pending_safety_checks,
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot_base64}",
                        "current_url": current_url
                    }
                }
            ],
            truncation="auto"
        )
        return False, False

    async def take_screenshot(self) -> str:
        if len(self.screenshots) > 1:
            return self.screenshots[-1]
        else:
            return None
        
    async def close(self):
        await self.page.close()
        await self.context.close()

    def add_new_task(self, new_task: str) -> None:
        return  

    def get_model_thought(self) -> dict:
        return {}

    def get_result(self) -> dict:
        return {}

    def generate_gif(self, output_path: Path) -> str:
        return "GIF"

    async def _take_initial_step(self):
        self.response = await self.client.responses.create(
            model=self.model,
            tools=self.tools,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": F"Go to {self.initial_url}, {self.task}"
                        }
                    ]
                }
            ],
            reasoning={
                "summary": "concise",
            },
            truncation="auto"
        )

    async def _handle_action(self, action: dict):
        action_type = action["type"]
        action_args = {k: v for k, v in action.items() if k != "type"}

        method = getattr(self.browser_executor, action_type, None)
        if method:
            await method(**action_args)

