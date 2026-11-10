"""Validate observations without filling unreadable values with game defaults."""

import json
import re


OBSERVATION_EXAMPLE = {
    "scene": "combat",
    "turn": None,
    "player": {"hp": None, "max_hp": None, "energy": None, "max_energy": None, "block": None,
               "statuses": [{"name": None, "amount": None}]},
    "hand": [{"name": None, "cost": None, "upgraded": None}],
    "enemies": [{"name": None, "hp": None, "max_hp": None, "block": None,
                 "intent": None, "intent_damage": None, "intent_hits": None,
                 "statuses": [{"name": None, "amount": None}]}],
    "uncertainties": [],
    "tooltips": [],
}
SCENES = {"combat", "map", "reward", "menu", "unknown"}


class ObservationError(ValueError):
    pass


def _object(value, keys, where, optional=()):
    if not isinstance(value, dict) or not (set(keys) - set(optional) <= set(value) <= set(keys)):
        raise ObservationError("%s字段缺失或含未声明字段" % where)


def _number(value, where, minimum=0):
    if value is not None and (type(value) is not int or not minimum <= value <= 1_000_000):
        raise ObservationError("%s应为合理范围内的整数或null" % where)


def _text(value, where, limit=300):
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > limit):
        raise ObservationError("%s应为非空短文本或null" % where)


def _health(value, where):
    for key in ("hp", "max_hp", "block"):
        _number(value[key], where + "." + key, 1 if key == "max_hp" else 0)
    if value["hp"] is not None and value["max_hp"] is not None and value["hp"] > value["max_hp"]:
        raise ObservationError("%s当前血量大于最大血量，请核对截图" % where)


def _statuses(value):
    if value is None:
        return
    if not isinstance(value, list) or len(value) > 40:
        raise ObservationError("状态应为最多40项的数组或null")
    for status in value:
        _object(status, ("name", "amount", "source", "description"), "增减益", optional=("source", "description"))
        _text(status["name"], "状态名称", 120)
        if "source" in status and status["source"] not in ("tooltip", "icon", "both", None):
            raise ObservationError("状态来源应为tooltip/icon/both或null")
        _text(status.get("description"), "状态说明", 1000)
        amount = status["amount"]
        if amount is not None and (type(amount) is not int or not -1_000_000 <= amount <= 1_000_000):
            raise ObservationError("状态数值应为整数或null")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError("JSON包含重复字段：%s" % key)
        result[key] = value
    return result


def parse_observation(text):
    """Accept plain JSON or one fenced JSON block; refuse prose and invalid types."""
    text = (text or "").strip()
    if len(text) > 100_000:
        raise ObservationError("识别结果过长，本次未采用")
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    try:
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=lambda token: (_ for _ in ()).throw(ObservationError("非法数值：" + token)))
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ObservationError("识别结果不是完整JSON，请重新识别或换用更清晰的截图") from exc
    _object(value, OBSERVATION_EXAMPLE, "局面", optional=("tooltips",))
    if not isinstance(value["scene"], str) or value["scene"] not in SCENES:
        raise ObservationError("scene不是支持的画面类型")
    _number(value["turn"], "turn", 1)
    _object(value["player"], OBSERVATION_EXAMPLE["player"], "player", optional=("statuses",))
    _statuses(value["player"].get("statuses"))
    _health(value["player"], "player")
    for key in ("energy", "max_energy"):
        _number(value["player"][key], "player." + key)
    hand = value["hand"]
    if hand is not None:
        if not isinstance(hand, list) or len(hand) > 30:
            raise ObservationError("hand应为最多30张手牌的数组或null")
        for card in hand:
            _object(card, OBSERVATION_EXAMPLE["hand"][0], "手牌")
            _text(card["name"], "手牌名称", 120)
            if card["cost"] != "X":
                _number(card["cost"], "手牌费用")
            if card["upgraded"] is not None and type(card["upgraded"]) is not bool:
                raise ObservationError("upgraded应为布尔值或null")
    enemies = value["enemies"]
    if enemies is not None:
        if not isinstance(enemies, list) or len(enemies) > 20:
            raise ObservationError("enemies应为最多20个敌人的数组或null")
        for enemy in enemies:
            _object(enemy, OBSERVATION_EXAMPLE["enemies"][0], "敌人", optional=("statuses",))
            _statuses(enemy.get("statuses"))
            _health(enemy, "敌人")
            _text(enemy["name"], "敌人名称", 120)
            _text(enemy["intent"], "敌人意图")
            _number(enemy["intent_damage"], "敌人意图单次伤害")
            _number(enemy["intent_hits"], "敌人攻击次数", 1)
    notes = value["uncertainties"]
    if not isinstance(notes, list) or len(notes) > 20:
        raise ObservationError("uncertainties应为短文本数组")
    for note in notes:
        _text(note, "未确认内容", 500)
        if note is None:
            raise ObservationError("未确认内容不能为null")
    tooltips = value.get("tooltips", [])
    if not isinstance(tooltips, list) or len(tooltips) > 20:
        raise ObservationError("tooltips应为最多20项的数组")
    for tip in tooltips:
        _object(tip, ("owner", "owner_index", "title", "text"), "悬停详情")
        if tip["owner"] not in ("enemy", "player", "unknown"):
            raise ObservationError("悬停所属对象不正确")
        index = tip["owner_index"]
        if index is not None and (type(index) is not int or index < 0 or
                tip["owner"] != "enemy" or index >= len(enemies or [])):
            raise ObservationError("悬停窗口的敌人序号越界")
        _text(tip["title"], "悬停标题", 120)
        _text(tip["text"], "悬停说明", 1500)
    return value


def observation_warnings(value):
    warnings = list(value["uncertainties"])
    if value["scene"] == "unknown":
        warnings.append("无法确认这是哪类游戏画面")
    if value["scene"] == "combat":
        for key, label in (("hp", "血量"), ("max_hp", "最大血量"), ("energy", "能量")):
            if value["player"][key] is None:
                warnings.append("玩家%s未识别" % label)
        for key, label in (("hand", "手牌"), ("enemies", "敌人")):
            if value[key] is None:
                warnings.append("%s区域未识别" % label)
        for i, card in enumerate(value["hand"] or [], 1):
            if card["name"] is None or (card["cost"] is None and card.get("playable") is not False):
                warnings.append("第%d张手牌的名称或费用未识别" % i)
        for i, enemy in enumerate(value["enemies"] or [], 1):
            if enemy["hp"] is None or enemy["intent"] is None:
                warnings.append("第%d个敌人的血量或意图未识别" % i)
        for label, owner in [("玩家", value["player"])] + [
                ("敌人%d" % i, enemy) for i, enemy in enumerate(value["enemies"] or [], 1)]:
            for status in owner.get("statuses") or []:
                if status["name"] is None:
                    warnings.append("%s有增减益图标尚未匹配名称；可见数值保留" % label)
    return list(dict.fromkeys(warnings))


def annotate_tooltip_sources(value):
    """Attach visible text only to matching statuses of the associated owner."""
    for tip in value.get("tooltips", []):
        if tip["owner"] == "player":
            owner = value["player"]
        elif tip["owner"] == "enemy" and tip["owner_index"] is not None:
            owner = value["enemies"][tip["owner_index"]]
        else:
            continue
        for status in owner.get("statuses") or []:
            if status["name"] and status["name"] == tip["title"]:
                status["source"] = "both" if status.get("source") in ("icon", "both") else "tooltip"
                status["description"] = tip["text"]


def summarize_observation(value):
    def show(item):
        return "未识别" if item is None else str(item)
    scenes = {"combat": "战斗", "map": "地图", "reward": "奖励", "menu": "菜单", "unknown": "未识别"}
    p = value["player"]
    def status_text(owner):
        statuses = owner.get("statuses")
        if statuses is None:
            return "增减益：区域未识别"
        if not statuses:
            return "增减益：无"
        return "增减益：" + "、".join("%s（%s%s）" % (
            show(s["name"]), "数值未识别或未显示" if s["amount"] is None else "数值%s" % s["amount"],
            "，伤害上限" if s.get("rule_id") == "HARD_TO_KILL" else "") for s in statuses)
    lines = ["画面：%s　回合：%s" % (scenes[value["scene"]], show(value["turn"])),
             "玩家血量：%s / %s　能量：%s / %s　格挡：%s" % tuple(
                 show(p[k]) for k in ("hp", "max_hp", "energy", "max_energy", "block"))]
    lines.append("玩家" + status_text(p))
    if value["hand"] is None:
        lines.append("手牌：区域未识别")
    else:
        cards = ["%s（%s%s）" % (show(c["name"]),
                 "诅咒，不能被打出，虚无；规则资料" if c.get("playable") is False
                 else "费用" + show(c["cost"]), "，已升级" if c["upgraded"] is True else "")
                 for c in value["hand"]]
        lines.append("手牌：" + ("、".join(cards) or "画面显示为空"))
    if value["enemies"] is None:
        lines.append("敌人：区域未识别")
    else:
        for i, enemy in enumerate(value["enemies"], 1):
            attack = ("；单次伤害%s，次数%s" % (show(enemy["intent_damage"]), show(enemy["intent_hits"]))) if enemy["intent_damage"] is not None else ""
            lines.append("敌人%d：%s　血量%s/%s　格挡%s\n    意图：%s%s" % (
                i, show(enemy["name"]), show(enemy["hp"]), show(enemy["max_hp"]), show(enemy["block"]),
                show(enemy["intent"]), attack))
            lines.append("    " + status_text(enemy))
    notes = observation_warnings(value)
    if value.get("tooltips"):
        lines.append("\n悬停详情（当前截图文字）：")
        for tip in value["tooltips"]:
            owner = ("敌人%d" % (tip["owner_index"] + 1) if tip["owner"] == "enemy" and tip["owner_index"] is not None
                     else "玩家" if tip["owner"] == "player" else "所属对象未确认")
            lines.append("· %s / %s：%s" % (owner, show(tip["title"]), show(tip["text"])))
    if notes:
        lines.append("\n待核对：\n" + "\n".join("· " + note for note in notes))
    return "\n".join(lines)
