from app.schemas.planning import POIRecommendation, ToolCallRecord, TripPlanningRequest
from app.services.amap_mcp_adapter import AmapMCPAdapter


class SightseeingAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter

    async def gather(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> tuple[list[POIRecommendation], list[POIRecommendation]]:
        attractions = await self.adapter.fetch_attractions(request, trace)
        restaurants = await self.adapter.fetch_restaurants(request, trace)
        return attractions, restaurants
