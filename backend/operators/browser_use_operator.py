import os
import base64
import logging
from typing import Tuple
from dotenv import load_dotenv
from pathlib import Path

from browserbase import Browserbase
from browser_use import Agent, ChatOpenAI
from browser_use.agent.gif import create_history_gif
from browser_use.browser import BrowserProfile, BrowserSession

from operators.base_operator import BaseOperator

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BrowserUseOperator(BaseOperator):
    def __init__(self):
        self.browser_profile = None
        self.browser_session = None
        self.agent_state = None
        self.agent = None
        self._bb_client = None
        self._bb_session_id = None
        self.live_url = None

    async def initialize(
        self,
        task: str,
        initial_url: str = None,
        storage_state_path: Path = None
    ) -> None:
        self.task = task
        self.initial_url = initial_url
        self.storage_state_path = storage_state_path

        bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")

        cdp_url = None
        if bb_api_key and bb_project_id:
            self._bb_client = Browserbase(api_key=bb_api_key)
            session = self._bb_client.sessions.create(project_id=bb_project_id, keep_alive=True)
            self._bb_session_id = session.id
            cdp_url = session.connect_url

            debug_urls = self._bb_client.sessions.debug(session.id)
            self.live_url = debug_urls.debugger_fullscreen_url
            logger.info(f"Browserbase session created: {session.id}")
            logger.info(f"Live URL: {self.live_url}")

        if cdp_url:
            # Remote Browserbase session: only pass CDP URL and minimal options.
            # Local-only options (storage_state, stealth, headless, disable_security)
            # conflict with the already-running remote browser.
            self.browser_profile = BrowserProfile(
                cdp_url=cdp_url,
                highlight_elements=False,
            )
        else:
            self.browser_profile = BrowserProfile(
                disable_security=True,
                headless=True,
                stealth=True,
                chromium_sandbox=False,
                highlight_elements=False,
                window_size={"width": 1024, "height": 768},
                user_data_dir=None,
                locale="en-US",
                storage_state=self.storage_state_path,
            )
        self.browser_session = BrowserSession(
            browser_profile=self.browser_profile
        )
        await self.browser_session.start()

        if self.initial_url:
            task = F"Go to {self.initial_url}, {self.task}"
        else:
            task = self.task

        self.agent = Agent(
            task=task,
            llm=ChatOpenAI(model='gpt-4.1'),
            temperature=0.0,
            browser_session=self.browser_session,
            max_actions_per_step=1
        )

    async def take_step(self) -> Tuple[bool, bool]:
        if self.agent is None:
            await self.init_agent()

        return await self.agent.take_step()

    async def take_screenshot(self) -> str:
        screenshots = self.agent.history.screenshots()
        if len(screenshots) > 1:
            return screenshots[-1]
        else:
            return None

    def get_live_url(self) -> str | None:
        return self.live_url

    async def close(self) -> None:
        await self.agent.close()
        await self.browser_session.stop()

        # keep_alive=True keeps the browser alive after Playwright disconnects.
        # Call release_session() separately when the user leaves.

    async def release_session(self) -> None:
        """Release the Browserbase session to free credits."""
        if self._bb_client and self._bb_session_id:
            try:
                project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")
                self._bb_client.sessions.update(
                    self._bb_session_id,
                    project_id=project_id,
                    status="REQUEST_RELEASE",
                )
                logger.info(f"Browserbase session released: {self._bb_session_id}")
            except Exception as e:
                logger.warning(f"Failed to release Browserbase session: {e}")

    async def add_new_task(self, new_task: str) -> None:
        self.task = new_task
        if self.agent is not None:
            self.agent.add_new_task(new_task)

    def get_model_thought(self) -> dict:
        model_thoughts = self.agent.history.model_thoughts()
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
        final_result = self.agent.history.final_result()
        is_successful = self.agent.history.is_successful()
        return {
            'content': final_result,
            'success': is_successful
        }

    def generate_gif(self, output_path: Path) -> str:
        try:
            create_history_gif(
                task=self.task,
                history=self.agent.history,
                output_path=str(output_path),
            )

            with open(output_path, 'rb') as f:
                base64_string = base64.b64encode(f.read()).decode('utf-8')
                return base64_string
        except Exception as e:
            logger.error(f'Error generating GIF: {e}')
            return "GIF"
