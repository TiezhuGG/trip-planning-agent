from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Smart Travel Planner"
    app_env: str = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""

    amap_api_key: str = ""
    amap_security_js_code: str = ""
    amap_mcp_command: str = ""
    amap_mcp_args: list[str] = Field(default_factory=list)
    amap_mcp_env: dict[str, str] = Field(default_factory=dict)
    amap_mcp_tool_poi_search: str = "maps_poi_search"
    amap_mcp_tool_route_plan: str = "maps_route_plan"
    amap_mcp_tool_weather: str = "maps_weather"
    amap_mcp_timeout_seconds: int = 20
    enable_mock_mcp: bool = True

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)

    @property
    def has_mcp(self) -> bool:
        return bool(self.amap_mcp_command)

    @property
    def has_map_rendering(self) -> bool:
        return bool(self.amap_api_key)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
