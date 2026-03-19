import asyncio
from datetime import date

from app.agents.poi_agent import SightseeingAgent
from app.agents.route_agent import RoutePlanningAgent
from app.schemas.planning import (
    InitialPlanDay,
    InitialPlanDraft,
    POIRecommendation,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
)


def _request(days: int = 1) -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=days,
        transport_preferences=["步行"],
    )


def test_poi_agent_fetches_restaurants_with_attraction_anchors() -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.received_anchors: list[POIRecommendation] | None = None

        async def fetch_attractions(self, request: TripPlanningRequest, trace: list[ToolCallRecord]):
            _ = (request, trace)
            return [
                POIRecommendation(name="外滩", district="黄浦区"),
                POIRecommendation(name="豫园", district="黄浦区"),
            ]

        async def fetch_restaurants(
            self,
            request: TripPlanningRequest,
            trace: list[ToolCallRecord],
            anchor_pois: list[POIRecommendation] | None = None,
        ):
            _ = (request, trace)
            self.received_anchors = anchor_pois
            return [POIRecommendation(name="本帮菜馆")]

    adapter = FakeAdapter()
    agent = SightseeingAgent(adapter)  # type: ignore[arg-type]

    attractions, restaurants = asyncio.run(agent.gather(_request(), []))

    assert [item.name for item in attractions] == ["外滩", "豫园"]
    assert [item.name for item in restaurants] == ["本帮菜馆"]
    assert adapter.received_anchors is not None
    assert [item.name for item in adapter.received_anchors] == ["外滩", "豫园"]


def test_route_agent_keeps_segment_order_when_planning_in_parallel() -> None:
    class FakeAdapter:
        async def plan_route(
            self,
            day_number: int,
            origin: POIRecommendation,
            destination: POIRecommendation,
            waypoints: list[POIRecommendation],
            mode: str,
            trace: list[ToolCallRecord],
        ) -> RouteSummary:
            _ = waypoints
            if destination.name.endswith("2"):
                await asyncio.sleep(0.08)
            elif destination.name.endswith("3"):
                await asyncio.sleep(0.02)
            else:
                await asyncio.sleep(0.05)
            trace.append(
                ToolCallRecord(
                    tool_name="maps_direction_walking_by_coordinates",
                    arguments={"origin": origin.name, "destination": destination.name},
                    success=True,
                    summary="ok",
                )
            )
            return RouteSummary(
                day_number=day_number,
                title="route",
                from_name=origin.name,
                to_name=destination.name,
                mode=mode,
            )

    agent = RoutePlanningAgent(FakeAdapter())  # type: ignore[arg-type]
    request = _request(days=1)
    initial_plan = InitialPlanDraft(
        summary="seed",
        days=[
            InitialPlanDay(
                day_number=1,
                date="2026-03-20",
                theme="D1",
                focus="focus",
                must_visit=[],
            )
        ],
    )
    attractions = [
        POIRecommendation(name="景点1", longitude=121.47, latitude=31.23),
        POIRecommendation(name="景点2", longitude=121.48, latitude=31.24),
    ]
    hotels = [POIRecommendation(name="酒店", longitude=121.46, latitude=31.22)]
    day_restaurants = {
        1: [
            POIRecommendation(name="餐厅3", longitude=121.49, latitude=31.25),
            POIRecommendation(name="餐厅4", longitude=121.50, latitude=31.26),
        ]
    }
    trace: list[ToolCallRecord] = []

    routes, execution = asyncio.run(
        agent.gather(
            request=request,
            initial_plan=initial_plan,
            attractions=attractions,
            hotels=hotels,
            day_restaurants=day_restaurants,
            trace=trace,
        )
    )

    assert [route.title for route in routes] == [
        "第 1 天路线 1",
        "第 1 天路线 2",
        "第 1 天路线 3",
        "第 1 天路线 4",
    ]
    assert execution.success is True
    assert len(routes) == 4
