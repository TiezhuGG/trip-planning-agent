from __future__ import annotations


_GENERIC_LOCAL_FOOD_KEYWORDS: tuple[str, ...] = (
    "老字号",
    "小吃",
    "地方菜",
    "风味",
    "海鲜",
    "私房",
    "土菜",
    "本地",
    "渔港",
    "大排档",
    "早餐",
)


_CITY_SIGNATURE_FOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "泉州": ("面线糊", "姜母鸭", "海蛎煎", "土笋冻", "牛肉羹", "四果汤", "闽南", "醋肉"),
    "厦门": ("沙茶面", "海蛎煎", "土笋冻", "花生汤", "姜母鸭", "闽南", "海鲜"),
    "北京": ("豆汁", "卤煮", "炸酱面", "烤鸭", "涮肉", "铜锅", "京味", "爆肚", "门钉肉饼"),
    "杭州": ("杭帮菜", "片儿川", "东坡肉", "龙井虾仁", "定胜糕", "酱鸭", "小笼"),
    "上海": ("本帮菜", "生煎", "小笼", "葱油拌面", "排骨年糕", "蟹粉", "沪上"),
    "广州": ("粤菜", "早茶", "茶楼", "烧腊", "肠粉", "云吞面", "艇仔粥", "老火汤"),
    "成都": ("川菜", "串串", "火锅", "冒菜", "兔头", "钵钵鸡", "担担面", "小酒馆"),
    "重庆": ("火锅", "江湖菜", "小面", "串串", "烤鱼", "抄手", "梯坎", "老灶"),
    "西安": ("泡馍", "肉夹馍", "凉皮", "biang", "葫芦头", "胡辣汤", "陕菜"),
}


def normalize_city_name(city: str) -> str:
    normalized = (city or "").strip()
    for suffix in ("市", "地区", "自治州", "特别行政区"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def get_generic_local_food_keywords() -> tuple[str, ...]:
    return _GENERIC_LOCAL_FOOD_KEYWORDS


def get_city_signature_keywords(city: str) -> tuple[str, ...]:
    normalized = normalize_city_name(city)
    return _CITY_SIGNATURE_FOOD_KEYWORDS.get(normalized, ())
