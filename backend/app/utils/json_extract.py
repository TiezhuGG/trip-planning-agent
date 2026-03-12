import json
from typing import Any


def extract_json_payload(text: str) -> Any | None:
    text = text.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for opening, closing in (("{", "}"), ("[", "]")):
        start = text.find(opening)
        if start == -1:
            continue

        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    return None
