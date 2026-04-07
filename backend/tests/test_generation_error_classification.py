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


def test_classify_generation_error_marks_mcp_startup_failure_as_503() -> None:
    code, _, status = _classify_generation_error(
        RuntimeError(
            "MCPProtocolError: MCP SDK 调用失败: FileNotFoundError: [WinError 2] 系统找不到指定的文件。"
        )
    )

    assert code == "MCP_STARTUP_ERROR"
    assert status == 503


def test_classify_generation_error_marks_mcp_tool_mapping_failure_as_503() -> None:
    code, _, status = _classify_generation_error(
        RuntimeError("RuntimeError: MCP 工具映射不完整: poi_search, weather")
    )

    assert code == "MCP_TOOL_MAPPING_ERROR"
    assert status == 503


def test_classify_generation_error_marks_amap_key_missing_as_503() -> None:
    code, _, status = _classify_generation_error(
        RuntimeError("MCPProtocolError: 未配置高德 Web Service Key，无法走路线直连兜底。")
    )

    assert code == "AMAP_KEY_MISSING"
    assert status == 503
