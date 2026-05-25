from app.agents.base import BaseAgent


class SingleAgent(BaseAgent):
    """图1: 单Agent模式 - 简单任务直接LLM调用"""

    def __init__(self, name: str = "single_agent"):
        super().__init__(name)

    async def run(self, input_data: dict) -> dict:
        return {"agent": self.name, "status": "stub", "result": "Single agent response"}
