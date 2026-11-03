# -*- coding: utf-8 -*-
"""实验6 §2.6 正常完成场景：真实模型 + 真实工具跑一次复盘分析 Agent。

    python scripts/run_agent_demo.py                # 自动同意写操作（演示用）
    python scripts/run_agent_demo.py --ask          # 写操作前在命令行请求确认
    python scripts/run_agent_demo.py --goal "分析 run-0001 并写报告" --max-steps 6

输出：最终状态、步数、耗时、工具调用序列、程序侧校验结果、最终回答、运行记录路径。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                    # noqa: BLE001
    pass

from guanyi.agent import (AgentConfig, AgentHarness, AutoApprove, CliConfirm,  # noqa: E402
                          build_registry)

DEFAULT_GOAL = ("分析 run-0001 这一局：先用工具查出这局的决策点数量、建议与实际操作的一致率、"
                "有哪些回合不一致，需要时查知识库解释原因，最后把复盘报告写出来并给出结论。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--ask", action="store_true", help="写操作前请求命令行确认")
    args = parser.parse_args()

    registry = build_registry()
    print("工具白名单：%s" % "、".join(registry.names()))
    confirm = CliConfirm(timeout_s=30) if args.ask else AutoApprove()
    harness = AgentHarness(registry=registry, confirm=confirm,
                           config=AgentConfig(max_steps=args.max_steps,
                                              total_timeout_s=args.timeout))
    print("任务：%s\n" % args.goal)
    print("-" * 72)
    result = harness.run(args.goal)
    print("-" * 72)
    print("\n【结果】")
    print("  状态      ：%s（ok=%s）" % (result.status, result.ok))
    print("  执行步数  ：%d" % result.steps)
    print("  耗时      ：%.1f ms" % result.elapsed_ms)
    print("  工具序列  ：%s" % " → ".join("%s(%s)" % (c["tool"], "ok" if c["ok"] else "err")
                                         for c in result.tool_calls))
    print("  程序校验  ：%s（%s）" % ("通过" if result.validation.get("ok") else "未通过",
                                   result.validation.get("detail")))
    print("  运行记录  ：%s" % result.trace_path)
    print("\n【最终回答】\n%s" % (result.final_answer or "（无）"))
    if result.report_written:
        print("\n【写报告】%s（决策点 %s 个）"
              % (result.report_written.get("path"), result.report_written.get("decision_count")))
    if result.error:
        print("\n【错误】%s" % json.dumps(result.error, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
