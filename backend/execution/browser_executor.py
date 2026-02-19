import base64
import logging
from pathlib import Path

from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BrowserExecutor:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def initialize(self, initial_url: str = None, storage_state_path: Path = None):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-extensions",
                "--disable-file-system",
            ]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1024, "height": 768},
            storage_state=str(storage_state_path) if storage_state_path else None
        )
        self.context.on("page", self._handle_new_page)

        self.page = await self.context.new_page()
        self.page.on("close", self._handle_page_close)

        if not initial_url:
            initial_url = "https://duckduckgo.com"
        await self.page.goto(initial_url)

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

    def get_current_url(self) -> str:
        return self.page.url
    
    async def get_snapshot_html(self) -> str:
        return await self.page.content()

    async def screenshot(self) -> str:
        """Capture only the viewport (not fullpage)."""
        png_bytes = await self.page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("utf-8")
    

