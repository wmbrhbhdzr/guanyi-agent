"""Game-specific visual conventions and public identity reference images."""

import json
from pathlib import Path

from .images import prepare_image

ROOT = Path(__file__).resolve().parents[2]
PROFILE_RULES = """当前由用户选择《杀戮尖塔2》适配。以下为该游戏显示约定，不是对局真值：
战斗中攻击意图的数字若完整可见，只有伤害D、没有×N，表示单次攻击，intent_hits=1；D×N则分别填D和N。
玩家或敌人的血条周围区域完整可见且没有格挡盾牌/数值时，block=0；被遮挡、裁掉或图标不清才填null。
没有攻击意图（如增益图标）时intent_damage和intent_hits为null，表示不适用，不列为不确定。
敌人名称往往仅悬停显示。可用附带的公开参考图按外形比对名称；匹配不明确仍填null，不按血量或意图反推身份。
参考图只有外形和身份标签，不提供当前状态。当前血量、格挡、意图仍必须从本次截图读取。
卡牌左上角没有费用标记时不要抄相邻卡牌费用；不可打出的诅咒牌没有普通能量费用，应填null。
笨拙是诅咒牌，不能被打出，具有虚无；不可把它记成费用1。其卡牌规则来源会由程序单独标注。
上述由显示约定可以确定的0、单次攻击1，以及不可打出牌没有费用，均不是“不确定”；
只有真实被遮挡、模糊或效果未展示时才列入uncertainties。参考图匹配名称可注明“外形匹配，待核对”。
状态证据包括血条下方图标和悬停详情窗口；必须优先读取悬停窗口的标题、说明与其中数值。
例如详情说明“受到的所有伤害和生命减少效果不会超过N点”，该状态amount=N；不是把N称作层数。
根据窗口位置、指向、鼠标和对应血条确定详情所属敌人；同名敌人不一定有相同状态，不能只因同名而复制详情到所有敌人。
其他敌人必须分别查看血条下的图标及数字；若图标与悬停标题旁图标一致，可用本张图的配对关系认出其名称。
敌人头顶红色剑是攻击意图，不是力量增益。详情窗挡住某些画面时，只把被挡住的字段保留未知。
图标外形对照：难以杀灭是红褐色分节甲壳/虫壳；力量是红色剑。不要把甲壳图标匹配为力量。
若意图图标可见但效果未知，intent仍写可见图标简述（如“蓝色向上箭头，增益”），不要仅因效果未知把intent填null。
"""


def load_references(game):
    if game != "sts2":
        return []
    manifest = ROOT / "knowledge/visual/sts2/references.json"
    if not manifest.is_file():
        return []
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    return [{**entry, "frame": prepare_image(manifest.parent / entry["file"], max_edge=320)}
            for entry in entries]


def apply_rules(value, game):
    """Keep normalization traceable; never overwrite historical raw responses."""
    changes = []
    if game == "sts2":
        references = json.loads((ROOT / "knowledge/visual/sts2/references.json").read_text(encoding="utf-8"))
        powers = {r["name"]: r for r in references if r.get("kind") == "power"}
        for owner in [value["player"]] + (value["enemies"] or []):
            for status in owner.get("statuses") or []:
                rule = powers.get(status["name"])
                if rule:
                    status.update(rule_id=rule["id"], effect_type=rule["effect_type"],
                                  stack_type=rule["stack_type"], rules_source=rule["source"])
        rules = json.loads((ROOT / "knowledge/visual/sts2/card_rules.json").read_text(encoding="utf-8"))
        by_name = {rule["name"]: rule for rule in rules}
        for index, card in enumerate(value["hand"] or []):
            if card["name"] in by_name:
                rule = by_name[card["name"]]
                before = card["cost"]
                card.update({key: rule[key] for key in ("cost", "card_type", "playable", "keywords")})
                card["rules_source"] = rule["source"] + "#" + rule["id"]
                changes.append({"field": "hand[%d]" % index, "previous_cost": before,
                                "reason": "CLUMSY规则：不可打出且无普通能量费用；这是规则资料，不是OCR数值"})
    return changes
