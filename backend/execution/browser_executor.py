import os
import asyncio
import base64
import logging
from pathlib import Path

from browserbase import Browserbase
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BrowserExecutor:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._bb_client = None
        self._bb_session_id = None
        self.live_url = None

    async def initialize(self, initial_url: str = None, storage_state_path: Path = None, context_id: str = ""):
        bb_api_key = os.getenv("BROWSERBASE_API_KEY", "")
        bb_project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")

        self.playwright = await async_playwright().start()

        if bb_api_key and bb_project_id:
            self._bb_client = Browserbase(api_key=bb_api_key)

            session_kwargs = {
                "project_id": bb_project_id,
                "keep_alive": True,
                "api_timeout": 900,
                "browser_settings": {
                    "viewport": {"width": 1280, "height": 720},
                },
            }
            if context_id:
                session_kwargs["browser_settings"]["context"] = {"id": context_id, "persist": True}
                logger.info(f"Using BrowserBase context: {context_id}")

            logger.info(f"Creating BrowserBase session with kwargs: {session_kwargs}")
            session = self._bb_client.sessions.create(**session_kwargs)
            self._bb_session_id = session.id

            # Verify the session was created with the context
            session_info = self._bb_client.sessions.retrieve(session.id)
            logger.info(f"Browserbase session created: {session.id}, context_id on session: {session_info.context_id}, status: {session_info.status}")

            debug_urls = self._bb_client.sessions.debug(session.id)
            self.live_url = debug_urls.debugger_fullscreen_url
            logger.info(f"Live URL: {self.live_url}")

            self.browser = await self.playwright.chromium.connect_over_cdp(session.connect_url)
            logger.info(f"CDP connected. Browser contexts: {len(self.browser.contexts)}")
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

            # Log cookies to verify context loaded correctly
            cookies = await self.context.cookies()
            logger.info(f"Context has {len(cookies)} cookies after CDP connect")
            for c in cookies[:5]:
                logger.info(f"  Cookie: {c['name']} @ {c['domain']}")
        else:
            logger.warning("Browserbase credentials not set, falling back to local Chromium")
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-extensions",
                    "--disable-file-system",
                ]
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1440, "height": 900},
                storage_state=str(storage_state_path) if storage_state_path else None
            )
            self.page = await self.context.new_page()

        self.context.on("page", self._handle_new_page)
        self.page.on("close", self._handle_page_close)

        if not initial_url:
            initial_url = "https://duckduckgo.com"
        await self.page.goto(initial_url)

        if context_id:
            cookies_after = await self.context.cookies()
            logger.info(f"Context has {len(cookies_after)} cookies after navigating to {initial_url}")

    async def _handle_new_page(self, page: Page):
        logger.info("New page created")
        self.page = page
        page.on("close", self._handle_page_close)

    async def _handle_page_close(self, page: Page):
        logger.info("Page closed")
        if self.page == page:
            if self.browser.contexts[0].pages:
                self.page = self.browser.contexts[0].pages[-1]
            else:
                logger.warning("All pages have been closed.")
                self.page = None

    async def close(self):
        if self.page and not self.page.is_closed():
            await self.page.close()

        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        # keep_alive=True keeps the browser alive after Playwright disconnects.
        # Call release_session() separately when the user leaves.

    async def release_session(self):
        """Release the Browserbase session and wait for context to persist."""
        if self._bb_client and self._bb_session_id:
            try:
                project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")
                self._bb_client.sessions.update(
                    self._bb_session_id,
                    project_id=project_id,
                    status="REQUEST_RELEASE",
                )
                logger.info(f"Browserbase session release requested: {self._bb_session_id}")

                # Wait for session to complete so context is persisted
                for _ in range(15):
                    await asyncio.sleep(1)
                    try:
                        session_info = self._bb_client.sessions.retrieve(self._bb_session_id)
                        if session_info.status in ("COMPLETED", "ERROR", "TIMED_OUT"):
                            logger.info(f"Browserbase session {self._bb_session_id} status: {session_info.status}")
                            break
                    except Exception:
                        break
            except Exception as e:
                logger.warning(f"Failed to release Browserbase session: {e}")

    def get_current_url(self) -> str:
        return self.page.url

    def get_live_url(self) -> str | None:
        return self.live_url

    async def keep_alive_ping(self) -> bool:
        """Send a lightweight CDP command to keep the Browserbase session alive."""
        try:
            if self.page and not self.page.is_closed():
                await self.page.evaluate("1")
                return True
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        return False

    async def get_snapshot_html(self) -> str:
        return await self.page.content()

    async def screenshot(self) -> str:
        """Capture only the viewport (not fullpage)."""
        png_bytes = await self.page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("utf-8")
