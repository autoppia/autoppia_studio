import time
import base64
from typing import List, Dict
from playwright.async_api import  Browser

# Optional: key mapping if your model uses "CUA" style keys
CUA_KEY_TO_PLAYWRIGHT_KEY = {
    "/": "Divide",
    "\\": "Backslash",
    "alt": "Alt",
    "arrowdown": "ArrowDown",
    "arrowleft": "ArrowLeft",
    "arrowright": "ArrowRight",
    "arrowup": "ArrowUp",
    "backspace": "Backspace",
    "capslock": "CapsLock",
    "cmd": "Meta",
    "ctrl": "Control",
    "delete": "Delete",
    "end": "End",
    "enter": "Enter",
    "esc": "Escape",
    "home": "Home",
    "insert": "Insert",
    "option": "Alt",
    "pagedown": "PageDown",
    "pageup": "PageUp",
    "shift": "Shift",
    "space": " ",
    "super": "Meta",
    "tab": "Tab",
    "win": "Meta",
}


class BrowserExecutor:
    def __init__(self):
        return

    async def initialize(self, browser: Browser):
        self.browser = browser
        self.context = await self.browser.new_context()
        self.page = await self.context.newpage()

    def get_current_url(self) -> str:
        return self.page.url

    # --- Common "Computer" actions ---
    def screenshot(self) -> str:
        """Capture only the viewport (not fullpage)."""
        png_bytes = self.page.screenshot(fullpage=False)
        return base64.b64encode(png_bytes).decode("utf-8")

    def click(self, x: int, y: int, button: str = "left") -> None:
        match button:
            case "back":
                self.back()
            case "forward":
                self.forward()
            case "wheel":
                self.page.mouse.wheel(x, y)
            case _:
                button_mapping = {"left": "left", "right": "right"}
                button_type = button_mapping.get(button, "left")
                self.page.mouse.click(x, y, button=button_type)

    def double_click(self, x: int, y: int) -> None:
        self.page.mouse.dblclick(x, y)

    def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        self.page.mouse.move(x, y)
        self.page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")

    def type(self, text: str) -> None:
        self.page.keyboard.type(text)

    def wait(self, ms: int = 1000) -> None:
        time.sleep(ms / 1000)

    def move(self, x: int, y: int) -> None:
        self.page.mouse.move(x, y)

    def keypress(self, keys: List[str]) -> None:
        mapped_keys = [CUA_KEY_TO_PLAYWRIGHT_KEY.get(key.lower(), key) for key in keys]
        for key in mapped_keys:
            self.page.keyboard.down(key)
        for key in reversed(mapped_keys):
            self.page.keyboard.up(key)

    def drag(self, path: List[Dict[str, int]]) -> None:
        if not path:
            return
        self.page.mouse.move(path[0]["x"], path[0]["y"])
        self.page.mouse.down()
        for point in path[1:]:
            self.page.mouse.move(point["x"], point["y"])
        self.page.mouse.up()

    # --- Extra browser-oriented actions ---
    def goto(self, url: str) -> None:
        try:
            return self.page.goto(url)
        except Exception as e:
            print(f"Error navigating to {url}: {e}")

    def back(self) -> None:
        return self.page.go_back()

    def forward(self) -> None:
        return self.page.go_forward()

