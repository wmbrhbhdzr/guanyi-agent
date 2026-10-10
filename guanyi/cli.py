# -*- coding: utf-8 -*-
"""命令行入口（实验3 设计的“自动化接口”在实验4 中的最小形态）。

界面层与命令行**调用同一套应用层服务**，所以“正常 / 空数据 / 错误输入”
三种情况都可以在这里用 JSON 观察，便于留证据。

用法示例：

    python -m guanyi.cli seed                         # 写入样例对局
    python -m guanyi.cli list                         # 列出所有对局
    python -m guanyi.cli show --run run-0001          # 查看一局的决策点
    python -m guanyi.cli record --run run-0001 --turn 4 \
        --state "HP 31/80，能量 3/3，敌人 HP 15" \
        --suggest "play_card:打击" --play "play_card:打击" \
        --result "enemy_hp_delta=-15"
    python -m guanyi.cli finish --run run-0001 --outcome 胜
    python -m guanyi.cli report --run run-0001        # 生成并打印报告路径
    python -m guanyi.cli clear                        # 清空全部运行记录
"""

import argparse
import json
import sys

from .app.service import SessionService
from .data.sample import reset, seed_sample_run
from .data.store import JsonlStore


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def parse_action(text):
    """把 `play_card:防御` 这样的文本解析成动作 dict；`end_turn` 表示结束回合。"""
    if not text:
        return None
    if ":" in text:
        kind, card = text.split(":", 1)
        return {"action_type": kind.strip(), "card_name": card.strip()}
    return {"action_type": text.strip()}


def parse_pairs(items):
    """把 `key=value` 列表解析成 dict，用于 --result。"""
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
        out[key.strip()] = value
    return out


# ---------------- 子命令 ----------------
def cmd_seed(args, service):
    run = seed_sample_run(service.store, run_id=args.run_id, outcome=args.outcome)
    _print({"ok": True, "run": run.to_dict(), "decisions": len(service.get_decisions(run.run_id))})


def cmd_clear(args, service):
    _print({"ok": True, "removed_runs": reset(service.store)})


def cmd_list(args, service):
    runs = service.list_runs()
    _print({"count": len(runs), "runs": runs})


def cmd_show(args, service):
    run = service.get_run(args.run)
    points = service.get_decisions(args.run)
    _print({"run": run.to_dict(), "decision_count": len(points),
            "decisions": [p.to_dict() for p in points]})


def cmd_record(args, service):
    point = service.record_decision(
        run_id=args.run,
        turn=args.turn,
        state_summary=args.state,
        suggestion_action=parse_action(args.suggest),
        player_action=parse_action(args.play),
        result=parse_pairs(args.result),
        suggestion_reason=args.reason or "",
        confidence=args.confidence,
        legal_actions=args.legal or [],
    )
    _print({"ok": True, "decision": point.to_dict(), "is_consistent": point.is_consistent})


def cmd_finish(args, service):
    run = service.finish_run(args.run, args.outcome)
    _print({"ok": True, "run": run.to_dict()})


def cmd_report(args, service):
    path = service.build_report(args.run)
    _print({"ok": True, "run_id": args.run, "report_path": path})


def build_parser():
    parser = argparse.ArgumentParser(prog="guanyi", description="观弈：离散决策游戏复盘助手（实验4 非AI 闭环）")
    parser.add_argument("--root", default="data/runs", help="运行记录目录（默认 data/runs/）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed", help="写入一局样例数据")
    p.add_argument("--run-id", default="run-0001")
    p.add_argument("--outcome", default="胜")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("clear", help="清空全部运行记录")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("list", help="列出所有对局")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="查看一局的决策点")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("record", help="录入一个决策点")
    p.add_argument("--run", required=True)
    p.add_argument("--turn", type=int, required=True)
    p.add_argument("--state", required=True, help="局面摘要")
    p.add_argument("--suggest", required=True, help="建议动作，如 play_card:防御")
    p.add_argument("--play", required=True, help="玩家实际操作，如 play_card:打击")
    p.add_argument("--result", action="append", help="结果，如 hp_delta=-11，可重复")
    p.add_argument("--reason", default="", help="建议依据")
    p.add_argument("--confidence", type=float, default=0.0)
    p.add_argument("--legal", action="append", help="合法动作集，可重复")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("finish", help="结束一局并记录胜负")
    p.add_argument("--run", required=True)
    p.add_argument("--outcome", required=True, choices=["胜", "负", "中止"])
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("report", help="生成逐回合复盘报告")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    service = SessionService(JsonlStore(args.root))
    args.func(args, service)
    return 0


if __name__ == "__main__":
    sys.exit(main())
