from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "trip-planning-agent"
    app_env: str = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""
    openai_backup_api_key: str = ""
    openai_backup_base_url: str = ""
    openai_backup_model: str = ""
    openai_timeout_seconds: int = 60
    openai_max_retries: int = 1
    openai_trust_env: bool = False
    openai_fast_mode: bool = False
    openai_diagnose_cache_seconds: float = 15
    openai_adaptive_retry_enabled: bool = True
    openai_adaptive_retry_window: int = 10
    openai_adaptive_retry_min_samples: int = 4
    openai_adaptive_retry_low_success_rate: float = 0.4

    amap_api_key: str = ""
    amap_security_js_code: str = ""
    amap_mcp_command: str = ""
    amap_mcp_args: list[str] = Field(default_factory=list)
    amap_mcp_env: dict[str, str] = Field(default_factory=dict)
    amap_mcp_inherit_proxy_env: bool = False
    amap_mcp_tool_poi_search: str = "maps_text_search"
    amap_mcp_tool_route_plan: str = "maps_direction_driving_by_address"
    amap_mcp_tool_weather: str = "maps_weather"
    amap_mcp_timeout_seconds: int = 20
    amap_mcp_tool_catalog_cache_seconds: float = 60
    amap_mcp_diagnose_cache_seconds: float = 15
    amap_mcp_circuit_enabled: bool = True
    amap_mcp_circuit_failure_threshold: int = 3
    amap_mcp_circuit_open_seconds: float = 10
    amap_mcp_circuit_slow_call_seconds: float = 8
    amap_mcp_circuit_slow_call_threshold: int = 3
    amap_mcp_adaptive_retry_enabled: bool = True
    amap_mcp_adaptive_retry_window: int = 20
    amap_mcp_adaptive_retry_min_samples: int = 6
    amap_mcp_adaptive_retry_low_success_rate: float = 0.35
    planner_hotel_binding_timeout_seconds: float = 45
    planner_meal_binding_timeout_seconds: float = 45
    planner_route_generation_timeout_seconds: float = 45
    planner_truth_binding_timeout_seconds: float = 45
    planner_route_segment_concurrency: int = 2
    planner_route_day_concurrency: int = 2
    planner_truth_binding_day_concurrency: int = 2
    planner_route_activity_resolve_concurrency: int = 3
    planner_generate_cache_enabled: bool = True
    planner_generate_cache_ttl_seconds: float = 20
    planner_generate_cache_max_entries: int = 64
    planner_trip_store_driver: str = "auto"
    planner_trip_store_path: str = "data/trips.db"
    planner_job_store_driver: str = "auto"
    planner_job_store_path: str = "data/planning_jobs.db"
    planner_stage_stats_enabled: bool = True
    planner_stage_stats_window: int = 50
    planner_stage_stats_series_points: int = 20
    planner_stage_slow_threshold_ms_per_stage: int = 8000
    planner_stage_slow_threshold_ms_total: int = 30000
    enable_mock_mcp: bool = True

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)

    @property
    def has_backup_openai(self) -> bool:
        return bool(self.openai_backup_api_key and self.openai_backup_model)

    @property
    def has_any_openai(self) -> bool:
        return self.has_openai or self.has_backup_openai

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

