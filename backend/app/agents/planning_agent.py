from app.agents.hotel_agent import HotelRecommendationAgent
from app.agents.itinerary_composer_agent import ItineraryComposerAgent
from app.agents.meal_agent import MealRecommendationAgent
from app.agents.planner_seed_agent import PlannerSeedAgent
from app.agents.planning_agent_runtime import PlanningCoordinatorRuntimeMixin
from app.agents.poi_agent import SightseeingAgent
from app.agents.route_agent import RoutePlanningAgent
from app.agents.weather_agent import WeatherAgent
from app.config import Settings
from app.services.ai_client import TravelAIClient
from app.services.amap_mcp_adapter import AmapMCPAdapter


class PlanningCoordinatorAgent(PlanningCoordinatorRuntimeMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.adapter = AmapMCPAdapter(settings)
        self.ai_client = TravelAIClient(settings)
        self.seed_agent = PlannerSeedAgent(self.ai_client)
        self.sight_agent = SightseeingAgent(self.adapter)
        self.weather_agent = WeatherAgent(self.adapter)
        self.hotel_agent = HotelRecommendationAgent(self.adapter)
        self.meal_agent = MealRecommendationAgent(self.adapter)
        self.route_agent = RoutePlanningAgent(self.adapter, settings)
        self.composer_agent = ItineraryComposerAgent(self.ai_client)
