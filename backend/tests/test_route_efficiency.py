import asyncio
from datetime import date

from app.agents.route_agent import RoutePlanningAgent
from app.config import Settings
from app.schemas.planning import (
    AgentExecution,
    InitialPlanDay,
    InitialPlanDraft,
    POIRecommendation,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter, MCPProtocolError


def test_plan_route_prefers_mcp_tool_before_webservice() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_env={"AMAP_MAPS_API_KEY": "test-key"},
    )
    adapter = AmapMCPAdapter(settings)
    adapter.client = object()
    adapter._tool_catalog = [
        {"name": "maps_direction_driving_by_coordinates"},
        {"name": "maps_direction_driving_by_address"},
    ]

    call_order: list[str] = []

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        call_order.append("tool")
        return {
            "route": {
                "paths": [
                    {
                        "distance": "1200",
                        "duration": "600",
                        "steps": [],
                    }
                ]
            }
        }

    async def fake_plan_webservice(
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ):
        _ = (mode, origin, destination, waypoints, trace)
        call_order.append("web")
        raise AssertionError("webservice should not be called when MCP route tool succeeds")

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    adapter._plan_route_via_web_service = fake_plan_webservice  # type: ignore[method-assign]

    origin = POIRecommendation(name="Hotel", longitude=121.47, latitude=31.23)
    destination = POIRecommendation(name="Attraction", longitude=121.49, latitude=31.24)
    trace: list[ToolCallRecord] = []

    result = asyncio.run(
        adapter.plan_route(
            day_number=1,
            origin=origin,
            destination=destination,
            waypoints=[],
            mode="driving",
            trace=trace,
        )
    )

    assert result.mode == "driving"
    assert call_order == ["tool"]


def test_resolve_route_location_uses_cache(monkeypatch) -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_env={"AMAP_MAPS_API_KEY": "test-key"},
    )
    adapter = AmapMCPAdapter(settings)

    requested_addresses: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {"status": "1", "geocodes": [{"location": "121.4737,31.2304"}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = (args, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            _ = (exc_type, exc, tb)
            return False

        async def get(self, url: str, params: dict):
            _ = url
            requested_addresses.append(str(params.get("address", "")))
            return FakeResponse()

    monkeypatch.setattr("app.services.amap_mcp_adapter.httpx.AsyncClient", FakeAsyncClient)

    poi = POIRecommendation(
        name="Attraction",
        address="No.1 Test Road",
        district="Shanghai",
    )
    first = asyncio.run(adapter._resolve_route_location(poi))
    second = asyncio.run(adapter._resolve_route_location(poi))

    assert first == "121.4737,31.2304"
    assert second == first
    assert len(requested_addresses) == 1


def test_build_route_tool_attempts_prefers_coordinate_only_when_available() -> None:
    settings = Settings(amap_mcp_command="uvx")
    adapter = AmapMCPAdapter(settings)
    adapter._tool_catalog = [
        {"name": "maps_direction_driving_by_coordinates"},
        {"name": "maps_direction_driving_by_address"},
    ]

    origin = POIRecommendation(name="O", longitude=121.1, latitude=31.1)
    destination = POIRecommendation(name="D", longitude=121.2, latitude=31.2)
    attempts = adapter._build_route_tool_attempts("driving", origin, destination)

    assert len(attempts) == 1
    assert attempts[0][0] == "maps_direction_driving_by_coordinates"


def test_route_mode_candidates_driving_only() -> None:
    settings = Settings(amap_mcp_command="uvx")
    adapter = AmapMCPAdapter(settings)
    assert adapter._route_mode_candidates("driving") == ["driving"]


def test_call_route_tool_with_retry_on_rate_limit() -> None:
    settings = Settings(amap_mcp_command="uvx")
    adapter = AmapMCPAdapter(settings)
    attempts = {"count": 0}

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise MCPProtocolError("Direction failed: CUQPS_HAS_EXCEEDED_THE_LIMIT")
        return {"route": {"paths": [{"distance": "800", "duration": "480", "steps": []}]}}

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    result = asyncio.run(
        adapter._call_route_tool_with_retry(
            tool_name="maps_direction_driving_by_coordinates",
            arguments={"origin": "121.1,31.1", "destination": "121.2,31.2"},
            trace=[],
        )
    )

    assert attempts["count"] == 2
    assert isinstance(result, dict)


def test_route_agent_filters_out_points_without_coordinates() -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def plan_route(
            self,
            day_number: int,
            origin: POIRecommendation,
            destination: POIRecommendation,
            waypoints: list[POIRecommendation],
            mode: str,
            trace: list[ToolCallRecord],
        ) -> RouteSummary:
            _ = (waypoints, mode, trace)
            self.calls.append((origin.name, destination.name))
            return RouteSummary(
                day_number=day_number,
                title="route",
                from_name=origin.name,
                to_name=destination.name,
                mode="driving",
            )

    agent = RoutePlanningAgent(FakeAdapter())  # type: ignore[arg-type]
    request = TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=1,
        transport_preferences=["自驾"],
    )
    draft = InitialPlanDraft(
        summary="seed",
        days=[
            InitialPlanDay(
                day_number=1,
                date="2026-03-20",
                theme="d1",
                focus="citywalk",
                must_visit=[],
            )
        ],
    )
    attractions = [
        POIRecommendation(name="A-coord", longitude=121.47, latitude=31.23),
        POIRecommendation(name="A-no-coord"),
    ]
    hotels = [POIRecommendation(name="Hotel", longitude=121.46, latitude=31.22)]
    day_restaurants = {
        1: [
            POIRecommendation(name="R-no-coord"),
            POIRecommendation(name="R2-no-coord"),
        ]
    }

    routes, trace = asyncio.run(
        agent.gather(
            request=request,
            initial_plan=draft,
            attractions=attractions,
            hotels=hotels,
            day_restaurants=day_restaurants,
            trace=[],
        )
    )

    assert len(routes) == 1
    assert routes[0].from_name == "Hotel"
    assert routes[0].to_name == "A-coord"
    assert isinstance(trace, AgentExecution)


def test_route_agent_falls_back_to_global_attractions_for_coordinates() -> None:
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
            _ = (waypoints, mode, trace)
            return RouteSummary(
                day_number=day_number,
                title="route",
                from_name=origin.name,
                to_name=destination.name,
                mode="driving",
            )

    agent = RoutePlanningAgent(FakeAdapter())  # type: ignore[arg-type]
    request = TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=1,
        transport_preferences=["自驾"],
    )
    draft = InitialPlanDraft(
        summary="seed",
        days=[
            InitialPlanDay(
                day_number=1,
                date="2026-03-20",
                theme="d1",
                focus="citywalk",
                must_visit=[],
            )
        ],
    )
    attractions = [
        POIRecommendation(name="A-no-1"),
        POIRecommendation(name="A-no-2"),
        POIRecommendation(name="A-coord", longitude=121.47, latitude=31.23),
    ]
    hotels = [POIRecommendation(name="Hotel", longitude=121.46, latitude=31.22)]
    day_restaurants = {1: [POIRecommendation(name="R-no")]}

    routes, _ = asyncio.run(
        agent.gather(
            request=request,
            initial_plan=draft,
            attractions=attractions,
            hotels=hotels,
            day_restaurants=day_restaurants,
            trace=[],
        )
    )

    assert len(routes) == 1
    assert routes[0].to_name == "A-coord"
