# -*- coding: utf-8 -*-
"""复盘分析 Agent 的工具集（实验6 §2.2）。

5 个工具，4 个只读、1 个写（写复盘报告，执行前需人工确认）：

| 工具 | 只读 | 改动数据 | 重复调用 |
| --- | --- | --- | --- |
| `list_runs` | 是 | 否 | 结果相同 |
| `get_decisions` | 是 | 否 | 结果相同 |
| `compute_stats` | 是 | 否 | 结果相同 |
| `query_knowledge` | 是 | 否 | 结果相同（只读检索） |
| `write_report` | 否 | **覆盖写 report.md** | 覆盖式写入，结果相同（幂等） |

对局工具访问 `data/runs`，知识检索只读 `knowledge`；`run_id` 先过正则再由存储层拼路径。
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional

from ..app.service import SessionService
from ..core.actions import action_key
from ..core.errors import GuanyiError
from ..knowledge import Retriever
from .protocol import ParamSpec, ToolError, ToolRegistry, ToolSpec, RUN_ID_PATTERN


def _to_tool_error(exc: Exception) -> ToolError:
    """把领域异常转成工具层错误码，方便模型读懂并决定下一步。"""
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, GuanyiError):
        mapping = {"not_found": "not_found", "storage_error": "storage_error",
                   "invalid_input": "invalid_argument", "duplicate_record": "conflict"}
        return ToolError(mapping.get(exc.code, exc.code or "error"), exc.message)
    return ToolError("tool_failed", "%s: %s" % (type(exc).__name__, exc))


def build_registry(service: Optional[SessionService] = None,
                   retriever: Optional[Retriever] = None) -> ToolRegistry:
    """构造工具注册表（白名单）。"""
    service = service or SessionService()
    retriever = retriever or Retriever(kb_dir="knowledge")
    registry = ToolRegistry(write_scope=str(service.store.root.resolve()))

    # ---------- 1. list_runs ----------
    def list_runs() -> Dict:
        runs = service.list_runs()
        items = []
        for run in runs:
            try:
                count = len(service.scan_decisions(run["run_id"])[0])
            except Exception:                     # noqa: BLE001
                count = None
            items.append({
                "run_id": run.get("run_id"), "seed": run.get("seed"),
                "status": run.get("status"), "outcome": run.get("outcome"),
                "decision_count": count,
            })
        return {"ok": True, "count": len(items), "runs": items}

    registry.register(ToolSpec(
        name="list_runs",
        description="列出所有对局（run_id、种子、状态、胜负、决策点数量）。用于确认要分析哪一局。",
        params=[],
        read_only=True,
        repeated_call="只读，重复调用结果相同",
    ), list_runs)

    # ---------- 2. get_decisions ----------
    def get_decisions(run_id: str) -> Dict:
        try:
            run = service.get_run(run_id)
            points, problems = service.scan_decisions(run_id)
        except Exception as exc:                  # noqa: BLE001
            raise _to_tool_error(exc)
        decisions = []
        for p in points:
            decisions.append({
                "turn": p.turn,
                "state_summary": p.state_summary,
                "suggestion": action_key(p.suggestion_action),
                "player_action": action_key(p.player_action),
                "is_consistent": p.is_consistent,
                "guardrail": p.guardrail.get("verdict"),
                "result": p.result,
            })
        return {"ok": True, "run_id": run_id, "outcome": run.outcome,
                "decision_count": len(decisions), "decisions": decisions,
                "problems": problems}

    registry.register(ToolSpec(
        name="get_decisions",
        description="读取一局的逐回合决策点（局面摘要、建议动作、玩家实际操作、是否一致、护栏结论、结果）。",
        params=[ParamSpec("run_id", "string", "对局编号，形如 run-0001",
                          required=True, pattern=RUN_ID_PATTERN)],
        read_only=True,
        repeated_call="只读，重复调用结果相同",
    ), get_decisions)

    # ---------- 3. compute_stats ----------
    def compute_stats(run_id: str) -> Dict:
        try:
            points, problems = service.scan_decisions(run_id)
        except Exception as exc:                  # noqa: BLE001
            raise _to_tool_error(exc)
        total = len(points)
        consistent = sum(1 for p in points if p.is_consistent)
        flagged = sum(1 for p in points if p.is_flagged())
        inconsistent_turns = [p.turn for p in points if not p.is_consistent]
        hp_lost = 0
        for p in points:
            value = (p.result or {}).get("hp_delta")
            if isinstance(value, (int, float)) and value < 0:
                hp_lost += int(value)
        return {
            "ok": True, "run_id": run_id,
            "decision_count": total,
            "consistent": consistent,
            "consistent_rate": round(consistent * 100.0 / total, 1) if total else 0.0,
            "flagged": flagged,
            "inconsistent_turns": inconsistent_turns,
            "hp_lost_total": hp_lost,
            "problems": problems,
        }

    registry.register(ToolSpec(
        name="compute_stats",
        description="计算一局的复盘统计：决策点数、建议与实际一致数、一致率(%)、被护栏标记数、"
                    "不一致的回合列表、累计掉血。",
        params=[ParamSpec("run_id", "string", "对局编号，形如 run-0001",
                          required=True, pattern=RUN_ID_PATTERN)],
        read_only=True,
        repeated_call="纯计算，重复调用结果相同",
    ), compute_stats)

    # ---------- 4. query_knowledge ----------
    def query_knowledge(question: str, top_k: int = 3) -> Dict:
        result = retriever.search(question, top_k=int(top_k))
        if not result.get("ok"):
            # 资料不足是“有效结果”而不是工具错误：ok=True + insufficient=True，
            # 这样不会被计入“连续工具错误”，模型可以自行决定换个问法或跳过。
            return {"ok": True, "insufficient": True,
                    "reason": result.get("reason", "资料不足"),
                    "hint": "知识库里没有对应片段，可换个问法，或不再依赖知识库解释。"}
        hits = []
        for hit in result["hits"]:
            hits.append({
                "rank": hit["rank"], "title": hit["title"], "score": hit["score"],
                "source": hit.get("source", ""),
                "text": hit["text"][:400],
            })
        return {"ok": True, "question": question, "hits": hits}

    registry.register(ToolSpec(
        name="query_knowledge",
        description="查询《杀戮尖塔 2》的游戏知识（卡牌数值、状态机制、敌人行动、遗物效果），"
                    "用于解释“为什么这样打更好”。只返回知识库里的片段，不含对局数据。",
        params=[ParamSpec("question", "string", "要查的问题，例如“易伤有什么效果”", required=True),
                ParamSpec("top_k", "integer", "返回片段数（1–5）", minimum=1, maximum=5, default=3)],
        read_only=True,
        repeated_call="只读检索，重复调用结果相同",
    ), query_knowledge)

    # ---------- 5. write_report（写操作，需人工确认）----------
    def write_report(run_id: str) -> Dict:
        try:
            before = service.store.report_file(run_id)
            existed = before.exists()
            result = service.build_report(run_id)
        except Exception as exc:                  # noqa: BLE001
            raise _to_tool_error(exc)
        return {
            "ok": True, "run_id": run_id, "path": result["path"],
            "sha256": hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest(),
            "decision_count": result["summary"]["decision_count"],
            "consistent_rate": result["summary"]["consistent_rate"],
            "overwritten": existed,
        }

    registry.register(ToolSpec(
        name="write_report",
        description="把一局的复盘报告写入 data/runs/<run_id>/report.md（含结果摘要、逐回合表、关键决策点）。"
                    "这是唯一的写操作，执行前需要用户确认。",
        params=[ParamSpec("run_id", "string", "对局编号，形如 run-0001",
                          required=True, pattern=RUN_ID_PATTERN)],
        read_only=False,
        requires_confirm=True,
        timeout_s=30.0,
        side_effects="覆盖写 data/runs/<run_id>/report.md；不删除数据、不改动决策记录",
        repeated_call="覆盖写同一文件，不新增对局或决策记录；报告生成时间可能更新",
    ), write_report)

    return registry


def describe_tools(registry: ToolRegistry) -> Dict:
    """把工具说明整理成可直接写进报告/界面的结构。"""
    return {"count": len(registry.names()), "tools": registry.describe()}
