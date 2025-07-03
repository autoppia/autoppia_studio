from contextlib import asynccontextmanager

from fastapi import FastAPI
from playwright.async_api import async_playwright

from app.sockets.sio_app import socket_app
from app.routes.api import v1
from app.utils.browser_manager import set_browser

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        set_browser(browser)
        yield
        await browser.close()

app = FastAPI(
    title="Automata API",
    description="This is API for Automata Web Operator",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/", socket_app)

app.include_router(v1.router, prefix="/api/v1")
