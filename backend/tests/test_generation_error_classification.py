from app.api.routes.planning import _classify_generation_error


def test_classify_generation_error_keeps_internal_value_error_as_500() -> None:
    code, _, status = _classify_generation_error(ValueError("database write failed"))

    assert code == "INTERNAL_ERROR"
    assert status == 500


def test_classify_generation_error_marks_city_validation_as_422() -> None:
    code, _, status = _classify_generation_error(
        RuntimeError("目的地仅支持中文城市名（例如：上海、北京市）")
    )

    assert code == "VALIDATION_ERROR"
    assert status == 422


def test_classify_generation_error_marks_rate_limit_as_503() -> None:
    code, _, status = _classify_generation_error(
        RuntimeError("RateLimitError: Error code: 429 - SetLimitExceeded")
    )

    assert code == "LLM_RATE_LIMIT"
    assert status == 503
