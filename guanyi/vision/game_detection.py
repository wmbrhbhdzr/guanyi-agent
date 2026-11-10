"""Detect only supported visible game titles; do not infer a game from filenames."""

import json
import re
from . import config


def detect_game(client, frame, deadline, wait_call):
    messages = [{"role": "system", "content": (
        '只检查图像中可见的游戏窗口标题或游戏自身标题文字。返回JSON {"game":"sts2或generic","title":"抄写可见标题或空字符串"}。'
        '仅标题明确是Slay the Spire 2或杀戮尖塔2（允许空格）才选sts2；不能仅凭画面像卡牌游戏判断。其他或看不清选generic。')},
        {"role": "user", "content": [{"type": "text", "text": "检查本张图片的可见标题："},
            {"type": "image_url", "image_url": {"url": frame.data_uri}}]}]
    import time
    response = wait_call(lambda: client.chat(messages, thinking=config.THINKING,
        temperature=config.TEMPERATURE, max_tokens=config.TITLE_MAX_TOKENS, timeout=max(0, deadline - time.monotonic()), deadline=deadline),
        deadline - time.monotonic())
    if not response.ok:
        return "generic", {"reason": "标题识别未成功，未启用专用规则", "error_code": (response.error or {}).get("code")}, response
    try:
        value = json.loads(response.text)
        title = value.get("title", "")
        if not isinstance(title, str) or len(title) > 200:
            raise ValueError("invalid title")
        supported = bool(re.search(r"slay\s+the\s+spire\s*2|杀戮尖塔\s*2", title, re.I))
        game = "sts2" if value.get("game") == "sts2" and supported else "generic"
        return game, {"visible_title": title, "reason": "按可见窗口标题选择适配" if game == "sts2" else "标题未确认，使用通用模式"}, response
    except (ValueError, AttributeError):
        return "generic", {"reason": "标题输出格式不正确，使用通用模式"}, response
