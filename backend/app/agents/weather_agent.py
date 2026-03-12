from app.schemas.planning import TripPlanningRequest, WeatherSummary
from app.services.amap_mcp_adapter import AmapMCPAdapter


class WeatherAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter

    async def gather(self, request: TripPlanningRequest, trace: list) -> WeatherSummary:
        return await self.adapter.fetch_weather(request, trace)
