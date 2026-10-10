# -*- coding: utf-8 -*-
"""样例数据维护脚本（讲义 2.2：样例数据要能初始化、清空、恢复）。

用法：

    python scripts/demo_data.py seed                     # 写入样例对局 run-0001
    python scripts/demo_data.py seed --run-id run-0002 --outcome 负
    python scripts/demo_data.py clear                    # 清空 runs/
    python scripts/demo_data.py restore                  # 清空后重新写入样例数据
    python scripts/demo_data.py report --run-id run-0001 # 顺手生成复盘报告
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guanyi.app.service import SessionService  # noqa: E402
from guanyi.data.sample import reset, seed_sample_run  # noqa: E402
from guanyi.data.store import JsonlStore  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="样例数据维护")
    parser.add_argument("--root", default="data/runs")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("seed")
    p.add_argument("--run-id", default="run-0001")
    p.add_argument("--outcome", default="胜")

    sub.add_parser("clear")
    sub.add_parser("restore")

    p = sub.add_parser("report")
    p.add_argument("--run-id", default="run-0001")

    args = parser.parse_args()
    store = JsonlStore(args.root)
    service = SessionService(store)

    if args.action == "seed":
        run = seed_sample_run(store, run_id=args.run_id, outcome=args.outcome)
        print("已写入样例对局：%s（%d 个决策点）" % (run.run_id, len(service.get_decisions(run.run_id))))
    elif args.action == "clear":
        print("已清空 %d 局运行记录" % reset(store))
    elif args.action == "restore":
        removed = reset(store)
        run = seed_sample_run(store, run_id="run-0001")
        print("已恢复：清空 %d 局 → 重新写入 %s" % (removed, run.run_id))
    elif args.action == "report":
        print("报告已生成：%s" % service.build_report(args.run_id))


if __name__ == "__main__":
    main()
