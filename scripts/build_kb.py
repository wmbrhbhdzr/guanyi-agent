# -*- coding: utf-8 -*-
"""知识库准备脚本（实验5 §2.3）：抓取《杀戮尖塔 2》公开数据，生成 knowledge/*.md。

数据来源
--------
`https://spire-codex.com/api/*?lang=zhs`（社区接口，60 请求/分钟，免费使用）
    /api/characters  角色（含起始卡组与起始遗物）
    /api/cards       卡牌（含已解析数值：damage / block / hit_count / keywords 等）
    /api/keywords    技能关键词
    /api/powers      增益与减益
    /api/monsters    怪物（含 moves 与意图）
    /api/relics      遗物

说明：卡牌与文本的版权归 Mega Crit Games，spire-codex 以社区接口形式提供；
本项目只取**铁甲战士**这一小部分、按原义转写为中文条目并标注来源，用于课程演示。
原始 JSON 落在 `data/knowledge_raw/`（已被 .gitignore 忽略），仓库只保留整理后的条目。

覆盖范围（按“够写报告即可”收敛）：铁甲战士起始卡组 + 常见牌 ≈22 张、关键词与机制 ≈12 条、
第一章常见敌人 4 个、遗物 4 件。

用法：
    .venv\\Scripts\\python.exe scripts\\build_kb.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://spire-codex.com/api"
LANG = "zhs"
UA = {"User-Agent": "GuanYi-coursework/0.1 (educational project; contact: repository owner)",
      "Accept": "application/json"}

RAW_DIR = os.path.join(ROOT, "data", "knowledge_raw")
KB_DIR = os.path.join(ROOT, "knowledge")

#: 覆盖范围：铁甲战士的**基础牌 + 全部普通牌**（日常最常遇到，最适合解释“为什么这样打”），
#: 再补 3 张有代表性的高级牌。合计约 26 张，符合“条目不用很多”。
EXTRA_CARDS = ["UPPERCUT", "IMPERVIOUS", "DEMON_FORM"]
#: 需要一并收录的关键词（技能关键词，见 /api/keywords）；None = 全部收录
KEYWORDS_KEEP = None
#: 需要收录的增益与减益（解释“为什么这样打更好”的核心概念，id 已按 STS2 实际数据核对）
POWERS_KEEP = ["VULNERABLE", "WEAK", "STRENGTH", "DEXTERITY", "FRAIL", "THORNS",
               "DEMON_FORM", "JUGGERNAUT", "REGEN", "BLOCK_NEXT_TURN", "FLAME_BARRIER"]
#: 敌人：自动从“第一章遭遇”里挑（普通 2 + 精英 1 + Boss 1），见 pick_monsters()
ACT1_PREFIX = "Act 1"
MONSTER_LIMIT = 6
#: 需要收录的遗物：起始遗物 + 与“伤害/格挡/易伤”判断直接相关的 4 件（铁甲战士池 + 通用池）
RELICS_KEEP = ["BURNING_BLOOD", "RED_SKULL", "PAPER_PHROG", "SELF_FORMING_CLAY", "BAG_OF_MARBLES"]


def clean_text(text):
    """清理接口文本里的富文本标记与占位符（讲义 2.3 要求“清理乱码与无关内容”）。

    `[gold]格挡[/gold]` → `格挡`；`[energy:2]` → `2 点能量`；`[blue][Amount][/blue]` → `若干`。
    """
    t = str(text or "")
    t = re.sub(r"\[energy:(\d+)\]", r"\1 点能量", t)
    t = re.sub(r"\[(?:Amount|Repeat|Damage|Block|Heal|Cards)\]", "若干", t)
    t = re.sub(r"\[/?[a-zA-Z]+\]", "", t)
    t = re.sub(r"\n+", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def norm_id(value):
    """统一 id 写法：忽略大小写与下划线（起始卡组写 `StrikeIronclad`，卡牌 id 写 `STRIKE_IRONCLAD`）。"""
    return str(value or "").upper().replace("_", "").replace(" ", "")


def fetch(path):
    """调用一次接口并返回 JSON；同时把原始响应存到 data/knowledge_raw/。"""
    url = "%s%s" % (API, path)
    req = urllib.request.Request(url, headers=UA)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    data = json.loads(body.decode("utf-8"))
    os.makedirs(RAW_DIR, exist_ok=True)
    name = path.split("?")[0].strip("/").replace("/", "_")
    with open(os.path.join(RAW_DIR, name + ".json"), "wb") as fp:
        fp.write(body)
    print("  取到 %-26s %5d 条  %6.1f KB  %.1fs" % (path, len(data), len(body) / 1024, time.time() - t0))
    return data


def by_id(items):
    return {norm_id(it.get("id", "")): it for it in items}


def pick_monsters(monsters, limit=MONSTER_LIMIT, act_prefix=ACT1_PREFIX):
    """挑出第一章会遇到的敌人：普通 → 精英 → Boss，各取若干。"""
    def in_act1(m):
        return any(str(e.get("act") or "").startswith(act_prefix) for e in (m.get("encounters") or []))

    pool = [m for m in monsters if in_act1(m)]
    order = {"Normal": 0, "Elite": 1, "Boss": 2}
    pool.sort(key=lambda m: (order.get(str(m.get("type")), 3), str(m.get("id"))))
    picked, seen_type = [], {}
    for m in pool:                     # 先保证三类各有一到两个
        t = str(m.get("type"))
        if seen_type.get(t, 0) < (2 if t == "Normal" else 1):
            picked.append(m)
            seen_type[t] = seen_type.get(t, 0) + 1
        if len(picked) >= limit:
            break
    return picked


def first_line(text):
    return (text or "").replace("\r", "").strip()


def card_block(card):
    """把一张卡渲染成一个 Markdown 片段（标题即片段边界，供切分器使用）。

    字段尽量完整：费用/类型/稀有度/目标、效果、数值、施加的状态、关键词、**升级后效果**。
    """
    target_cn = {"AnyEnemy": "单体敌人", "AllEnemies": "所有敌人", "Self": "自己",
                 "Ally": "队友", "None": "—", "RandomEnemy": "随机敌人"}
    lines = []
    lines.append("## 【%s】%s" % (card.get("name", "?"), card.get("id", "")))
    lines.append("")
    cost = card.get("cost")
    if card.get("is_x_cost"):
        cost = "X"
    tags = [
        "费用 %s" % (cost if cost is not None else "—"),
        "类型 %s" % (card.get("type") or "—"),
        "稀有度 %s" % (card.get("rarity") or "—"),
        "目标 %s" % target_cn.get(str(card.get("target")), card.get("target") or "—"),
    ]
    lines.append("- 基本：%s" % "　".join(tags))
    lines.append("- 效果：%s" % clean_text(card.get("description")))
    nums = []
    for key, label in (("damage", "伤害"), ("block", "格挡"), ("hit_count", "段数"),
                       ("cards_draw", "抽牌"), ("energy_gain", "获得能量"), ("hp_loss", "失去生命"),
                       ("star_cost", "星费")):
        if card.get(key):
            nums.append("%s %s" % (label, card[key]))
    if nums:
        lines.append("- 数值：%s" % "，".join(nums))
    if card.get("powers_applied"):
        lines.append("- 施加：%s" % "、".join(
            "%s %s 层" % (p.get("power"), p.get("amount")) for p in card["powers_applied"]))
    if card.get("keywords"):
        lines.append("- 关键词：%s" % "、".join(card["keywords"]))
    if card.get("upgrade_description"):
        lines.append("- 升级后：%s" % clean_text(card["upgrade_description"]))
    elif card.get("upgrade"):
        lines.append("- 升级：%s" % json.dumps(card["upgrade"], ensure_ascii=False))
    lines.append("- 来源：spire-codex `/api/cards?lang=%s`（id=%s，" % (LANG, card.get("id")) +
                 "版权 Mega Crit Games）")
    lines.append("")
    return "\n".join(lines)


def power_block(power):
    return "\n".join([
        "## 【%s】%s" % (power.get("name", "?"), power.get("id", "")),
        "",
        "- 效果：%s" % clean_text(power.get("description")),
        "- 来源：spire-codex `/api/powers?lang=%s`（id=%s）" % (LANG, power.get("id")),
        "",
    ])


def keyword_block(kw):
    return "\n".join([
        "## 【%s】%s" % (kw.get("name", "?"), kw.get("id", "")),
        "",
        "- 说明：%s" % clean_text(kw.get("description")),
        "- 来源：spire-codex `/api/keywords?lang=%s`（id=%s）" % (LANG, kw.get("id")),
        "",
    ])


def monster_block(mon):
    """把一只怪渲染成一个片段：血量 + 行动（意图），供解释“该防还是该打”。"""
    intent_cn = {"Attack": "攻击", "Defend": "防御", "Attack + Defend": "攻击+防御",
                 "Buff": "强化", "Debuff": "减益", "Attack Debuff": "攻击+减益",
                 "Attack Buff": "攻击+强化", "Attack + Buff": "攻击+强化",
                 "Stun": "眩晕", "Unknown": "未知", "Escape": "逃跑", "Sleep": "睡眠"}
    type_cn = {"Normal": "普通", "Elite": "精英", "Boss": "首领"}
    moves = []
    for mv in (mon.get("moves") or [])[:6]:
        if not isinstance(mv, dict):
            continue
        name = str(mv.get("name") or mv.get("id") or "?")
        dmg = mv.get("damage_values") or mv.get("damage")
        amount = ""
        if isinstance(dmg, dict):
            amount = dmg.get("normal") or ""
            if dmg.get("ascension"):
                amount = "%s（进阶 %s）" % (amount, dmg["ascension"])
        elif isinstance(dmg, (int, str)):
            amount = dmg
        intent = intent_cn.get(str(mv.get("intent") or ""), str(mv.get("intent") or ""))
        piece = name
        if amount:
            piece += " %s 点" % amount
        if intent:
            piece += "［%s］" % intent
        moves.append(piece)
    hp_span = "%s" % mon.get("min_hp")
    if mon.get("max_hp") and mon.get("max_hp") != mon.get("min_hp"):
        hp_span = "%s–%s" % (mon.get("min_hp"), mon.get("max_hp"))
    asc_span = "%s" % mon.get("min_hp_ascension")
    if mon.get("max_hp_ascension") and mon.get("max_hp_ascension") != mon.get("min_hp_ascension"):
        asc_span = "%s–%s" % (mon.get("min_hp_ascension"), mon.get("max_hp_ascension"))
    return "\n".join([
        "## 【%s】%s" % (mon.get("name", "?"), mon.get("id", "")),
        "",
        "- 血量：%s（进阶 %s）" % (hp_span, asc_span),
        "- 类型：%s" % type_cn.get(str(mon.get("type")), mon.get("type") or "—"),
        "- 行动（意图）：%s" % ("；".join(moves) if moves else "—"),
        "- 来源：spire-codex `/api/monsters?lang=%s`（id=%s）" % (LANG, mon.get("id")),
        "",
    ])


def relic_block(relic):
    return "\n".join([
        "## 【%s】%s" % (relic.get("name", "?"), relic.get("id", "")),
        "",
        "- 稀有度：%s" % (relic.get("rarity") or "—"),
        "- 效果：%s" % clean_text(relic.get("description")),
        "- 来源：spire-codex `/api/relics?lang=%s`（id=%s）" % (LANG, relic.get("id")),
        "",
    ])


def main():
    print("抓取 spire-codex（《杀戮尖塔 2》社区数据接口）")
    characters = fetch("/characters?lang=%s" % LANG)
    cards = fetch("/cards?lang=%s" % LANG)
    keywords = fetch("/keywords?lang=%s" % LANG)
    powers = fetch("/powers?lang=%s" % LANG)
    monsters = fetch("/monsters?lang=%s" % LANG)
    relics = fetch("/relics?lang=%s" % LANG)

    ironclad = None
    for ch in characters:
        if str(ch.get("id", "")).lower() in ("ironclad", "the_ironclad"):
            ironclad = ch
            break
    if ironclad is None:
        print("[错误] 没找到铁甲战士角色数据")
        return 2

    cbi, pbi, mbi, rbi = by_id(cards), by_id(powers), by_id(monsters), by_id(relics)
    starting = [norm_id(x) for x in (ironclad.get("starting_deck") or [])]

    # 覆盖范围：起始卡组 + 全部普通牌 + 3 张示例高级牌
    ironclad_cards = [c for c in cards if str(c.get("color", "")).lower() == "ironclad"]
    auto_ids = [c["id"] for c in ironclad_cards if c.get("rarity_key") == "Common"]
    picked_ids, seen = [], set()
    for cid in list(dict.fromkeys(starting + [norm_id(x) for x in auto_ids + EXTRA_CARDS])):
        if cid in cbi and cid not in seen:
            seen.add(cid)
            picked_ids.append(cid)
    picked_cards = [cbi[c] for c in picked_ids]

    os.makedirs(KB_DIR, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    header = ("<!-- 由 scripts/build_kb.py 生成，抓取时间 %s -->\n"
              "<!-- 数据来源：https://spire-codex.com/api/*?lang=%s（社区接口，数据版权归 Mega Crit Games）-->\n\n"
              % (stamp, LANG))

    with open(os.path.join(KB_DIR, "铁甲战士-卡牌.md"), "w", encoding="utf-8") as fp:
        fp.write(header + "# 铁甲战士 · 卡牌\n\n"
                 "> 覆盖范围：起始卡组 + 常见牌，共 %d 张。每张牌一个片段。\n\n" % len(picked_cards))
        fp.write("\n".join(card_block(c) for c in picked_cards))

    kw_sel = keywords if KEYWORDS_KEEP is None else [
        k for k in keywords if norm_id(k.get("id")) in {norm_id(x) for x in KEYWORDS_KEEP}]
    pw_sel = [pbi[norm_id(k)] for k in POWERS_KEEP if norm_id(k) in pbi]
    with open(os.path.join(KB_DIR, "机制-关键词与状态.md"), "w", encoding="utf-8") as fp:
        fp.write(header + "# 机制 · 关键词与状态\n\n"
                 "> 技能关键词 %d 条 + 增益/减益 %d 条。解释“为什么这样打更好”时引用这里。\n\n"
                 % (len(kw_sel), len(pw_sel)))
        fp.write("\n".join(keyword_block(k) for k in kw_sel))
        fp.write("\n".join(power_block(p) for p in pw_sel))

    mon_sel = pick_monsters(monsters)
    with open(os.path.join(KB_DIR, "第一章-敌人.md"), "w", encoding="utf-8") as fp:
        fp.write(header + "# 第一章 · 常见敌人\n\n> 收录 %d 个（普通/精英/Boss），含血量与行动（意图）。\n\n" % len(mon_sel))
        fp.write("\n".join(monster_block(m) for m in mon_sel))

    rel_sel = [rbi[norm_id(k)] for k in RELICS_KEEP if norm_id(k) in rbi]
    with open(os.path.join(KB_DIR, "遗物.md"), "w", encoding="utf-8") as fp:
        fp.write(header + "# 遗物\n\n> 收录 %d 件（含起始遗物）。\n\n" % len(rel_sel))
        fp.write("\n".join(relic_block(r) for r in rel_sel))

    total = len(picked_cards) + len(kw_sel) + len(pw_sel) + len(mon_sel) + len(rel_sel)
    with open(os.path.join(KB_DIR, "SOURCES.md"), "w", encoding="utf-8") as fp:
        fp.write(
            "# 知识库来源与使用权限\n\n"
            "- 抓取时间：%s（脚本 `scripts/build_kb.py`，可重跑更新）\n"
            "- 数据来源：`https://spire-codex.com/api/*?lang=%s`（社区维护的《杀戮尖塔 2》数据接口）\n"
            "- 使用条款：该站点 `API_TERMS.md` 声明 `/api/*` **对社区免费使用**，限速 60 请求/分钟；"
            "建议在使用处回链 `https://spire-codex.com`\n"
            "- 版权归属：卡牌、遗物、怪物等游戏数据版权归 **Mega Crit Games**，本知识库仅取铁甲战士相关的一小部分，"
            "用于课程作业的检索演示，不重新分发完整原始数据\n"
            "- 隐私处理：知识库只含**通用游戏知识**，不含任何真实对局记录、截图或个人信息；"
            "调用模型时只发送“用户问题 + 检索到的知识片段”\n"
            "- 更新方法：重跑 `scripts/build_kb.py`（原始 JSON 落在 `data/knowledge_raw/`，该目录不入库）\n"
            "- 本次条目数：卡牌 %d、关键词 %d、状态 %d、敌人 %d、遗物 %d，合计 **%d**\n"
            % (stamp, LANG, len(picked_cards), len(kw_sel), len(pw_sel), len(mon_sel), len(rel_sel), total))
    print("\n生成完毕：卡牌 %d、关键词 %d、状态 %d、敌人 %d、遗物 %d，合计 %d 条"
          % (len(picked_cards), len(kw_sel), len(pw_sel), len(mon_sel), len(rel_sel), total))
    print("输出目录：knowledge/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
