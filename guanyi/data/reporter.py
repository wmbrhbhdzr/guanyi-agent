# -*- coding: utf-8 -*-
"""复盘报告生成（对应功能需求 FR-05 与实验3 图 12 的界面原型）。

输入的是一局的全部决策点，输出 Markdown 文本：
    ① 结果摘要（胜负、决策点数、建议与操作一致率、被护栏标记数）
    ② 逐回合表（回合｜局面摘要｜建议｜你的操作｜是否一致｜结果）
    ③ 关键决策点（建议与操作不一致的回合）

修订版新增：没有任何决策点时也要能出报告（写明“没有决策点记录”），而不是空白或报错。
"""

from datetime import datetime
from typing import List

from ..core.models import DecisionPoint, Run


def _action_text(action) -> str:
    if not action:
        return "—"
    kind = action.get("action_type", "")
    card = action.get("card_name", "")
    if kind == "end_turn":
        return "结束回合"
    return "%s【%s】" % (kind, card) if card else str(kind)


def _result_text(result) -> str:
    if not result:
        return "—"
    parts = []
    for key, label in (("hp_delta", "血量"), ("enemy_hp_delta", "敌方血量"), ("note", "备注")):
        if key in result:
            parts.append("%s %s" % (label, result[key]))
    return "；".join(parts) if parts else "—"


def build_report(run: Run, points: List[DecisionPoint]) -> str:
    """生成一局的逐回合复盘报告。"""
    lines = []
    lines.append("# 观弈复盘报告 · %s" % run.run_id)
    lines.append("")
    lines.append("- 生成时间：%s" % datetime.now().astimezone().isoformat(timespec="seconds"))
    lines.append("- 对局：%s（种子 %s）" % (run.game_title, run.seed or "未记录"))
    lines.append("- 结果：%s" % (run.outcome or "进行中"))
    lines.append("- 提示强度档位：%s" % run.config_snapshot.get("tier", "仅复盘"))
    lines.append("")

    total = len(points)
    consistent = sum(1 for p in points if p.is_consistent)
    flagged = sum(1 for p in points if p.is_flagged())
    rate = ("%.1f%%" % (consistent * 100.0 / total)) if total else "—"

    lines.append("## 结果摘要")
    lines.append("")
    if not points:
        lines.append("本局**没有决策点记录**（可能是刚开局、或该局记录被清理）。")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("> 说明：本报告由观弈在“仅复盘”档生成，只记录与统计，不介入游玩；"
                     "决策建议来自规则基线（实验4 为非 AI 版本），最终判断权在玩家。")
        return "\n".join(lines)
    lines.append("| 决策点数 | 建议与操作一致 | 一致率 | 被护栏标记 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| %d | %d | %s | %d |" % (total, consistent, rate, flagged))
    lines.append("")

    lines.append("## 逐回合表")
    lines.append("")
    lines.append("| 回合 | 局面摘要 | 建议 | 你的操作 | 是否一致 | 结果 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for p in points:
        lines.append("| %d | %s | %s | %s | %s | %s |" % (
            p.turn,
            p.state_summary or "—",
            _action_text(p.suggestion_action),
            _action_text(p.player_action),
            "✓" if p.is_consistent else "✗",
            _result_text(p.result),
        ))
    lines.append("")

    lines.append("## 关键决策点")
    lines.append("")
    key_points = [p for p in points if not p.is_consistent]
    if not key_points:
        lines.append("本局建议与操作完全一致，没有需要特别复盘的回合。")
    else:
        for p in key_points:
            lines.append("### 第 %d 回合（%s）" % (p.turn, p.dp_id))
            lines.append("")
            lines.append("- 局面：%s" % (p.state_summary or "—"))
            lines.append("- 系统建议：%s" % _action_text(p.suggestion_action))
            lines.append("- 建议依据：%s" % (p.suggestion_reason or "—"))
            lines.append("- 你的操作：%s" % _action_text(p.player_action))
            lines.append("- 本回合结果：%s" % _result_text(p.result))
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> 说明：本报告由观弈在“仅复盘”档生成，只记录与统计，不介入游玩；"
                 "决策建议来自规则基线（实验4 为非 AI 版本），最终判断权在玩家。")
    return "\n".join(lines)
