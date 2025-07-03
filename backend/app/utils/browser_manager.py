from playwright.async_api import Browser

_browser: Browser | None = None

def set_browser(browser: Browser):
    global _browser
    _browser = browser

def get_browser() -> Browser:
    if _browser is None:
        raise RuntimeError("Browser not initialized")
    return _browser