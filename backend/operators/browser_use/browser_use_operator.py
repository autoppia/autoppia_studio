import base64
import logging
from typing import Tuple
from dotenv import load_dotenv
from pathlib import Path

from browser_use import Agent
from browser_use.llm import ChatOpenAI
from browser_use.agent.views import AgentState
from browser_use.agent.gif import create_history_gif
from browser_use.browser import BrowserProfile, BrowserSession

from operators.shared import BaseOperator

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BrowserUseOperator(BaseOperator):
    def __init__(self):
        self.browser_profile = None
        self.browser_session = None
        self.agent_state = None
        self.agent = None

    async def initialize(
        self,
        task: str, 
        initial_url: str = None, 
        storage_state_path: Path = None
    ) -> None:
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path

        self.browser_profile = BrowserProfile(
            disable_security=True,
            headless=False,
            chromium_sandbox=False,
            highlight_elements=False,
            window_size={"width": 1024, "height": 768},
            user_data_dir=None,
            locale="en-US",
            storage_state=self.storage_state_path
        )
        self.browser_session = BrowserSession(
            browser_profile=self.browser_profile
        )
        await self.browser_session.start()        

        if self.initial_url:
            task = F"Go to {self.initial_url}, {self.task}"
        else:
            task = self.task

        self.agent_state = AgentState()
        self.agent = Agent(
            task=task,
            llm=ChatOpenAI(model='gpt-4.1'),
            temperature=0.0,
            browser_session=self.browser_session,
            injected_agent_state=self.agent_state,
            max_actions_per_step=1
        )

    async def take_step(self) -> Tuple[bool, bool]:
        if self.agent is None:
            await self.init_agent()

        return await self.agent.take_step()
    
    async def take_screenshot(self) -> str:
        # if self.browser_session:
        #     return await self.browser_session.take_screenshot()
        # else:
        #     return None
        screenshots = self.agent_state.history.screenshots()
        if len(screenshots) > 1:
            return screenshots[-1]
        else:
            return None
        
    async def close(self) -> None:
        await self.agent.close()
        await self.browser_session.stop()
        
    def add_new_task(self, new_task: str) -> None:
        self.task = new_task
        if self.agent is not None:
            self.agent.add_new_task(new_task)

    def get_model_thought(self) -> dict:
        model_thoughts = self.agent_state.history.model_thoughts()
        if not model_thoughts:
            return None

        next_goal = model_thoughts[-1].next_goal
        evaluation_previous_goal = model_thoughts[-1].evaluation_previous_goal
        previous_success = False if 'Failed' in evaluation_previous_goal else True
        return {
            'next_goal': next_goal,
            'evaluation_previous_goal': evaluation_previous_goal,
            'previous_success': previous_success
        }
    
    def get_result(self) -> dict:
        final_result = self.agent_state.history.final_result()
        is_successful = self.agent_state.history.is_successful()
        return {
            'content': final_result,
            'success': is_successful
        }
    
    def generate_gif(self, output_path: Path) -> str:
        try:
            create_history_gif(
                task=self.task,
                history=self.agent_state.history,
                output_path=str(output_path),
            )

            with open(output_path, 'rb') as f:
                base64_string = base64.b64encode(f.read()).decode('utf-8')
                return base64_string
        except Exception as e:
            logger.error(f'Error generating GIF: {e}')
            return ""