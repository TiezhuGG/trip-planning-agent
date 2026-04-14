from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from app.schemas.planning import DailyForecast, TripPlanningRequest, WeatherSummary


IntParser = Callable[[Any], int | None]

_DEFAULT_OVERVIEW = "\u884c\u7a0b\u671f\u95f4\u5929\u6c14\u6574\u4f53\u9002\u5408\u51fa\u6e38\u3002"
_DEFAULT_SUGGESTIONS = [
    "\u5efa\u8bae\u51c6\u5907\u8f7b\u8584\u5916\u5957",
    "\u4e2d\u5348\u65f6\u6bb5\u6ce8\u610f\u9632\u6652",
]
_DEFAULT_TEMP_RANGE = "18-28\u00b0C"
_DEFAULT_DAY_WEATHER = "\u6674\u5230\u591a\u4e91"
_DEFAULT_NIGHT_WEATHER = "\u591a\u4e91"
_DEFAULT_ADVICE = (
    "\u767d\u5929\u6ce8\u610f\u9632\u6652\uff0c\u591c\u95f4\u53ef\u51c6\u5907\u4e00\u4ef6\u8f7b\u8584\u5916\u5957\u3002"
)


def normalize_weather(
    raw: Any,
    *,
    request: TripPlanningRequest,
    to_int: IntParser,
) -> WeatherSummary:
    forecasts: list[DailyForecast] = []
    overview = f"{request.destination}{_DEFAULT_OVERVIEW}"
    suggestions: list[str] = list(_DEFAULT_SUGGESTIONS)
    temp_range = _DEFAULT_TEMP_RANGE

    if isinstance(raw, dict):
        overview = str(raw.get("overview", raw.get("summary", overview)))
        suggestions_raw = raw.get("suggestions", raw.get("tips", suggestions))
        if isinstance(suggestions_raw, str):
            suggestions = [suggestions_raw]
        elif isinstance(suggestions_raw, list):
            suggestions = [str(item) for item in suggestions_raw][:4]

        temp_range = str(
            raw.get(
                "temperature_range",
                raw.get("temperature", raw.get("temp_range", temp_range)),
            )
        )

        forecast_items = None
        for key in ("daily_forecasts", "forecasts", "casts", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                forecast_items = value
                break
            if isinstance(value, dict):
                for nested_key in ("casts", "forecasts", "daily"):
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, list):
                        forecast_items = nested_value
                        break
            if forecast_items is not None:
                break

        if isinstance(forecast_items, list):
            for index, item in enumerate(forecast_items[: request.days]):
                if not isinstance(item, dict):
                    continue
                forecasts.append(
                    DailyForecast(
                        date=str(item.get("date", request.start_date + timedelta(days=index))),
                        day_weather=str(
                            item.get("day_weather", item.get("dayweather", item.get("weather", "")))
                        ),
                        night_weather=str(item.get("night_weather", item.get("nightweather", ""))),
                        high_temperature=str(
                            item.get("high_temperature", item.get("daytemp", item.get("high", "")))
                        ),
                        low_temperature=str(
                            item.get("low_temperature", item.get("nighttemp", item.get("low", "")))
                        ),
                        advice=str(item.get("advice", item.get("tip", ""))),
                    )
                )

    if not forecasts:
        for index in range(request.days):
            date = request.start_date + timedelta(days=index)
            forecasts.append(
                DailyForecast(
                    date=str(date),
                    day_weather=_DEFAULT_DAY_WEATHER,
                    night_weather=_DEFAULT_NIGHT_WEATHER,
                    high_temperature="28",
                    low_temperature="20",
                    advice=_DEFAULT_ADVICE,
                )
            )

    if forecasts:
        highs = [to_int(item.high_temperature) for item in forecasts if to_int(item.high_temperature) is not None]
        lows = [to_int(item.low_temperature) for item in forecasts if to_int(item.low_temperature) is not None]
        if highs and lows:
            temp_range = f"{min(lows)}-{max(highs)}\u00b0C"

    return WeatherSummary(
        overview=overview,
        temperature_range=temp_range,
        suggestions=suggestions,
        daily_forecasts=forecasts,
    )
