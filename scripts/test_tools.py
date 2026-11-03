# -*- coding: utf-8 -*-
"""实验6 §2.2：在接入 Agent 之前，直接测试工具的正确参数与错误参数。

    python scripts/test_tools.py

输出每个工具的调用结果摘要，用于报告取证（含错误码与提示）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                    # noqa: BLE001
    pass

from guanyi.agent.protocol import ToolError          # noqa: E402
from guanyi.agent.tools import build_registry        # noqa: E402


def show(title, fn):
    try:
        result = fn()
        flag = "OK  " if result.get("ok") else "FAIL"
        print("  %-42s %s  %s" % (title, flag, _summary(result)))
    except ToolError as exc:
        print("  %-42s 拒绝  [%s] %s" % (title, exc.code, exc.message))
    except Exception as exc:                          # noqa: BLE001
        print("  %-42s 异常  %s: %s" % (title, type(exc).__name__, exc))


def _summary(result):
    """把结果压成一行。"""
    if result.get("insufficient"):
        return "资料不足（有效结果）：%s" % result.get("reason")
    if not result.get("ok"):
        err = result.get("error") or {}
        return "[%s] %s" % (err.get("code"), err.get("message"))
    for key in ("count", "decision_count", "consistent_rate", "path"):
        if key in result:
            return "%s=%s" % (key, result[key])
    if result.get("hits"):
        return "hits=%d 首条=%s" % (len(result["hits"]), result["hits"][0]["title"])
    return "ok"


def main():
    registry = build_registry()
    print("工具白名单：%s\n" % "、".join(registry.names()))

    print("【正确参数】")
    show("list_runs()", lambda: registry.call("list_runs", {}))
    show("get_decisions(run-0001)", lambda: registry.call("get_decisions", {"run_id": "run-0001"}))
    show("compute_stats(run-0001)", lambda: registry.call("compute_stats", {"run_id": "run-0001"}))
    show("query_knowledge(易伤效果)", lambda: registry.call(
        "query_knowledge", {"question": "易伤有什么效果", "top_k": 2}))
    show("write_report(run-0001)", lambda: registry.call("write_report", {"run_id": "run-0001"}))

    print("\n【错误参数】")
    show("get_decisions(run-9999) 不存在", lambda: registry.call("get_decisions", {"run_id": "run-9999"}))
    show("get_decisions(../../etc) 路径穿越", lambda: registry.call(
        "get_decisions", {"run_id": "../../etc/passwd"}))
    show("compute_stats(缺少 run_id)", lambda: registry.call("compute_stats", {}))
    show("compute_stats(run_id=123) 类型错误", lambda: registry.call("compute_stats", {"run_id": 123}))
    show("query_knowledge(top_k=99) 越界", lambda: registry.call(
        "query_knowledge", {"question": "易伤", "top_k": 99}))
    show("query_knowledge(空问题)", lambda: registry.call("query_knowledge", {"question": "  "}))
    show("query_knowledge(无关问题→资料不足)", lambda: registry.call(
        "query_knowledge", {"question": "这游戏怎么联机"}))
    show("未知工具 rm_rf", lambda: registry.call("rm_rf", {}))
    show("多余参数 foo=1", lambda: registry.call("list_runs", {"foo": 1}))

    print("\n结论：白名单、参数类型/范围、路径锚定、资料不足与工具未知都由程序拦截并返回结构化错误。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
