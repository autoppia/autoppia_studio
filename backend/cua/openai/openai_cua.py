from openai import AsyncOpenAI

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

        self.response = None
        self.pending_safety_checks = []

    def set_dimension(self, width: int, height: int):
        self.tools[0]["display_width"] = width
        self.tools[0]["display_height"] = height

    async def start(
        self, 
        task: str = None,
    ) -> dict:
        self.response = await self.client.responses.create(
            model=self.model,
            tools=self.tools,
            input=[
                {
                    "role": "user",
                    "content": task
                }
            ],
            reasoning={
                "summary": "concise",
            },
            truncation="auto"
        )

        return self.response.output
    
    async def forward(
        self,
        user_message: str = None,
        screenshot: str = None,
        current_url: str = None
    ) -> dict:
        pass

    def process_response(self) -> dict:
        pass