from app.agents.base import BaseAgent


class RouterAgent(BaseAgent):
    """图3: Router模式 - 多类型任务意图分发"""

    def __init__(self, name: str = "router"):
        super().__init__(name)
        self.routes: dict[str, BaseAgent] = {}

    def register_route(self, intent: str, agent: BaseAgent) -> None:
        self.routes[intent] = agent

    async def classify(self, input_data: dict) -> str:
        return "default"

    async def run(self, input_data: dict) -> dict:
        intent = await self.classify(input_data)
        handler = self.routes.get(intent)
        if handler:
            return await handler.run(input_data)
        return {"agent": self.name, "status": "stub", "intent": intent}
