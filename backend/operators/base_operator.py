from abc import ABC, abstractmethod
from typing import Tuple
from pathlib import Path
from playwright.async_api import Browser


class BaseOperator(ABC):
    @abstractmethod
    async def initialize(
        self,
        task: str, 
        initial_url: str = None, 
        storage_state_path: Path = None
    ) -> None:
        pass
                        
    @abstractmethod
    async def take_step(self) -> Tuple[bool, bool]:
        pass
    
    @abstractmethod
    async def take_screenshot(self) -> str:
        pass
        
    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def add_new_task(self, new_task: str) -> None:
        pass

    @abstractmethod
    def get_model_thought(self) -> dict:
        pass
    
    @abstractmethod
    def get_result(self) -> dict:
        pass

    @abstractmethod
    def get_live_url(self) -> str | None:
        pass

    @abstractmethod
    def generate_gif(self, output_path: Path) -> str:
        pass

    async def release_session(self) -> None:
        """Release the cloud browser session (e.g. Browserbase).
        Called on Socket.IO disconnect to free credits."""
        pass
