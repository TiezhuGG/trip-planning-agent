from app.schemas.planning import POIRecommendation, TripPlanningRequest
from app.services.amap_mcp_adapter import AmapMCPAdapter


class HotelRecommendationAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter

    async def gather(
        self,
        request: TripPlanningRequest,
        attractions: list[POIRecommendation],
        trace: list,
    ) -> list[POIRecommendation]:
        return await self.adapter.fetch_hotels(request, trace, anchor_pois=attractions)
