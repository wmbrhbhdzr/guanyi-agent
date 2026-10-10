# -*- coding: utf-8 -*-
"""应用层服务：实验4 的核心业务闭环编排。

闭环（对应实验3 图 6 的顺序图，去掉 AI 与真值部分）：

    开始对局 → 录入一个决策点（局面 / 建议 / 玩家实际操作 / 结果）
             → 落盘 -> 结束对局 -> 生成逐回合复盘报告 -> 读取报告展示

界面层与命令行入口都只调用本服务，不直接碰文件。
"""

from typing import Dict, List, Optional

from ..core.models import DecisionPoint, Run, new_id, now_iso
from ..data.reporter import build_report
from ..data.store import JsonlStore


class SessionService:
    """一局对局的用例编排。"""

    def __init__(self, store: Optional[JsonlStore] = None):
        self.store = store or JsonlStore()

    # ---------- 对局 ----------
    def start_run(self, run_id: Optional[str] = None, seed: str = "", tier: str = "仅复盘") -> Run:
        run = Run(
            run_id=run_id or new_id("run"),
            seed=seed,
            status="running",
            config_snapshot={"tier": tier},
        )
        self.store.save_run(run)
        return run

    def finish_run(self, run_id: str, outcome: str) -> Run:
        run = self.store.load_run(run_id)
        run.status = "finished"
        run.outcome = outcome
        run.ended_at = now_iso()
        self.store.save_run(run)
        return run

    # ---------- 决策点 ----------
    def record_decision(
        self,
        run_id: str,
        turn: int,
        state_summary: str,
        suggestion_action: Dict,
        player_action: Dict,
        result: Optional[Dict] = None,
        suggestion_reason: str = "",
        confidence: float = 0.0,
        legal_actions: Optional[List[str]] = None,
    ) -> DecisionPoint:
        """录入一个决策点并落盘。"""
        run = self.store.load_run(run_id)
        decisions = self.store.load_decisions(run_id)
        point = DecisionPoint(
            dp_id="dp-%s-%02d" % (run.run_id, len(decisions) + 1),
            run_id=run.run_id,
            turn=turn,
            seq=len(decisions) + 1,
            state_summary=state_summary,
            legal_actions=list(legal_actions or []),
            suggestion_action=suggestion_action,
            suggestion_reason=suggestion_reason,
            confidence=confidence,
            player_action=player_action,
            guardrail={"verdict": "allow", "reason": "未启用护栏", "code": "ok"},
            model_meta={"source": "manual", "latency_ms": 0, "cost": 0.0},
            result=result or {},
        )
        point.is_consistent = point.check_consistency()
        self.store.append_decision(point)
        return point

    # ---------- 查询与报告 ----------
    def list_runs(self) -> List[Dict]:
        return self.store.list_runs()

    def get_run(self, run_id: str) -> Run:
        return self.store.load_run(run_id)

    def get_decisions(self, run_id: str) -> List[DecisionPoint]:
        return self.store.load_decisions(run_id)

    def build_report(self, run_id: str) -> str:
        """生成复盘报告并返回报告文件路径。"""
        run = self.store.load_run(run_id)
        points = self.store.load_decisions(run_id)
        text = build_report(run, points)
        path = self.store.save_report(run_id, text)
        return str(path)
