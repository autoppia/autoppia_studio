import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class OpenAICUA:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.model = "computer-use-preview"
        self.tools = [{
            "type": "computer_use_preview",
            "display_width": 1024,
            "display_height": 768,
            "environment": "browser"
        }]
        self.items = []

    def set_dimension(self, width: int, height: int):
        self.tools[0]["display_width"] = width
        self.tools[0]["display_height"] = height

    async def call(
        self, 
        user_input: str = None,
        screenshot: str = None,
        current_url: str = None,
    ) -> dict:
        if user_input is not None:
            self.items.append({
                "role": "user",
                "content": user_input
            })

        elif screenshot is not None:
            last_item = self.items[-1]
            pending_safety_checks = last_item.pending_safety_checks
            self.items.append({
                "type": "computer_call_output",
                "call_id": last_item.call_id,
                "acknowledged_safety_checks": pending_safety_checks,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot}",
                    "current_url": current_url
                }
            })

        response = await self.client.responses.create(
            model=self.model,
            tools=self.tools,
            input=self.items,
            reasoning={
                "summary": "concise"
            },
            truncation="auto"
        )

        logger.info(f"Model output: {response.output}")

        if not response.output:
            logger.error("No output found in the response.")
            return {}

        self.items += response.output
        return response.output

    def process_input(self, user_input: str) -> str:
        if len(self.items) == 0:
            return (
                "Do the following task without human in the loop.\n"
                "Never ask to me and try to solve everything by yourself including captcha.\n"
                f"Task: {user_input}"
            )
        else:
            return (
                "Do the following task without human in the loop.\n"
                "Never ask to me and try to solve everything by yourself including captcha.\n"
                f"Task: {user_input}"
            )
            

        