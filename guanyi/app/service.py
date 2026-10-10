# -*- coding: utf-8 -*-
"""应用层服务：实验4 的核心业务闭环编排。

闭环（对应实验3 图 6 的顺序图，去掉 AI 与游戏真值部分）：

    开始对局 → 录入决策点（局面／建议／玩家实际操作／结果）
             → 规则护栏校验 → 落盘（JSONL）→ 结束对局
             → 生成逐回合复盘报告 → 读回报告展示

界面层与命令行入口都只调用本服务，不直接碰文件；异常统一为 `GuanyiError` 子类。
"""

from typing import Dict, List, Optional

from ..core import guardrail, rule_baseline
from ..core.actions import action_key
from ..core.errors import DuplicateError
from ..core.models import DecisionPoint, Run, new_id, now_iso
from ..data.reporter import build_report
from ..data.store import JsonlStore
from .logging_setup import get_logger


class SessionService:
    """一局对局的用例编排。"""

    def __init__(self, store: Optional[JsonlStore] = None, log_root: Optional[str] = None):
        self.store = store or JsonlStore()
        self.log_root = log_root or str(self.store.root)

    # ---------- 日志 ----------
    def logger(self, run_id: Optional[str] = None):
        return get_logger(run_id, root=self.log_root)

    # ---------- 对局 ----------
    def start_run(self, run_id: Optional[str] = None, seed: str = "", tier: str = "仅复盘") -> Run:
        """新建一局（此时还没有任何决策点，用于空数据场景）。"""
        run = Run(run_id=run_id or new_id("run"), seed=seed, status="running",
                  config_snapshot={"tier": tier})
        self.store.save_run(run)
        self.logger(run.run_id).info("开始对局 run_id=%s 档位=%s 种子=%s",
                                     run.run_id, tier, seed or "未记录")
        return run

    def finish_run(self, run_id: str, outcome: str) -> Run:
        run = self.store.load_run(run_id)
        run.status = "finished"
        run.outcome = outcome
        run.ended_at = now_iso()
        self.store.save_run(run)
        self.logger(run_id).info("结束对局 run_id=%s 结果=%s", run_id, outcome)
        return run

    # ---------- 决策 ----------
    def suggest(self, state: Dict, legal_actions: List[str]) -> Dict:
        """规则基线决策（非 AI）：给定局面与合法动作集，返回 {action, reason, confidence}。"""
        return rule_baseline.decide(state, legal_actions)

    def record_decision(
        self,
        run_id: str,
        turn: int,
        state_summary: str,
        suggestion_action: Optional[Dict] = None,
        player_action: Optional[Dict] = None,
        state: Optional[Dict] = None,
        result: Optional[Dict] = None,
        suggestion_reason: str = "",
        confidence: Optional[float] = None,
        legal_actions: Optional[List[str]] = None,
    ) -> DecisionPoint:
        """录入一个决策点：先过护栏，再落盘。

        - `suggestion_action` 省略且给了 `state` 时，用规则基线产出建议；
        - 护栏结论（allow/deny）随记录一起保存，冲突时以规则为准并留痕；
        - 同一 `(run_id, turn)` 重复录入会被拒绝。
        """
        run = self.store.load_run(run_id)                     # 不存在 → NotFoundError
        points = self.store.load_decisions(run_id)            # 容错读，损坏行不影响录入
        if any(int(p.turn) == int(turn) for p in points):
            raise DuplicateError("第 %s 回合已经录入过决策点" % turn, run_id=run_id, turn=turn)

        legal = list(legal_actions or [])
        source = "manual"
        if suggestion_action is None:
            baseline = self.suggest(state or {}, legal)
            suggestion_action = baseline["action"]
            suggestion_reason = suggestion_reason or baseline["reason"]
            if confidence is None:
                confidence = baseline["confidence"]
            source = "rule_baseline"

        verdict = guardrail.check_action(suggestion_action, legal,
                                         energy_left=(state or {}).get("energy"))

        point = DecisionPoint(
            dp_id="dp-%s-%02d" % (run.run_id, len(points) + 1),
            run_id=run.run_id,
            turn=turn,
            seq=len(points) + 1,
            state_summary=state_summary,
            legal_actions=legal,
            suggestion_action=suggestion_action,
            suggestion_reason=suggestion_reason,
            confidence=float(confidence if confidence is not None else 0.0),
            player_action=player_action,
            guardrail=verdict,
            model_meta={"source": source, "latency_ms": 0, "cost": 0.0},
            result=result or {},
        )
        point.is_consistent = point.check_consistency()
        point.validate()
        self.store.append_decision(point)

        log = self.logger(run_id)
        log.info("录入决策点 dp_id=%s 回合=%s 建议=%s 玩家=%s 一致=%s 护栏=%s",
                 point.dp_id, point.turn, action_key(point.suggestion_action),
                 action_key(point.player_action), point.is_consistent, verdict["verdict"])
        if verdict["verdict"] == "deny":
            log.warning("护栏拦截 dp_id=%s code=%s reason=%s",
                        point.dp_id, verdict["code"], verdict["reason"])
        return point

    # ---------- 查询与报告 ----------
    def list_runs(self) -> List[Dict]:
        return self.store.list_runs()

    def get_run(self, run_id: str) -> Run:
        return self.store.load_run(run_id)

    def get_decisions(self, run_id: str) -> List[DecisionPoint]:
        return self.store.load_decisions(run_id)

    def scan_decisions(self, run_id: str):
        """返回 (可用记录, 损坏行问题列表)，供界面把问题提示出来。"""
        return self.store.scan_decisions(run_id)

    def build_report(self, run_id: str) -> Dict:
        """生成复盘报告，返回路径、统计摘要与读取时发现的问题。"""
        run = self.store.load_run(run_id)
        points, problems = self.store.scan_decisions(run_id)
        text = build_report(run, points)
        path = self.store.save_report(run_id, text)
        total = len(points)
        consistent = sum(1 for p in points if p.is_consistent)
        summary = {
            "run_id": run_id,
            "decision_count": total,
            "consistent": consistent,
            "consistent_rate": round(consistent * 100.0 / total, 1) if total else 0.0,
            "flagged": sum(1 for p in points if p.is_flagged()),
        }
        self.logger(run_id).info("生成复盘报告 path=%s 决策点=%d 一致=%d 损坏行=%d",
                                 path, total, consistent, len(problems))
        return {"path": str(path), "problems": problems, "summary": summary}
