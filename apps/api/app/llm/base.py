from abc import ABC, abstractmethod


class LLMClient(ABC):
    """LLM 抽象接口"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...
