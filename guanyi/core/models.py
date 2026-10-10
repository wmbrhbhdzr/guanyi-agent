# -*- coding: utf-8 -*-
"""领域数据结构（对应实验3 图 5 的核心数据模型）。

实验4 只实现非AI 闭环需要的最小集：Run、DecisionPoint、Report。
`Action` 与 `GuardrailVerdict` 在这一版里用 dict 表示（值对象，内嵌于 DecisionPoint）。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


def now_iso() -> str:
    """本地时区的 ISO 时间串，便于人读与排序。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """生成短 ID，例如 run-3f9a2c1d、dp-3f9a2c1d-02。"""
    return "%s-%s" % (prefix, uuid.uuid4().hex[:8])


@dataclass
class Run:
    """一局运行。"""

    run_id: str
    game_title: str = "《杀戮尖塔》"
    seed: str = ""
    started_at: str = field(default_factory=now_iso)
    ended_at: Optional[str] = None
    status: str = "running"                # running / finished / aborted
    config_snapshot: Dict = field(default_factory=dict)
    outcome: Optional[str] = None          # 胜 / 负

    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "game_title": self.game_title,
            "seed": self.seed,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "config_snapshot": self.config_snapshot,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Run":
        return cls(
            run_id=data.get("run_id", ""),
            game_title=data.get("game_title", "《杀戮尖塔》"),
            seed=data.get("seed", ""),
            started_at=data.get("started_at", now_iso()),
            ended_at=data.get("ended_at"),
            status=data.get("status", "running"),
            config_snapshot=data.get("config_snapshot") or {},
            outcome=data.get("outcome"),
        )


@dataclass
class DecisionPoint:
    """决策点：核心实体，记录局面、建议、玩家实际操作与结果四项。"""

    dp_id: str
    run_id: str
    turn: int
    seq: int
    state_summary: str = ""
    legal_actions: List[str] = field(default_factory=list)
    suggestion_action: Optional[Dict] = None
    suggestion_reason: str = ""
    confidence: float = 0.0
    player_action: Optional[Dict] = None
    is_consistent: bool = False
    guardrail: Dict = field(default_factory=dict)
    model_meta: Dict = field(default_factory=dict)
    result: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict:
        return {
            "dp_id": self.dp_id,
            "run_id": self.run_id,
            "turn": self.turn,
            "seq": self.seq,
            "state_summary": self.state_summary,
            "legal_actions": list(self.legal_actions),
            "suggestion_action": self.suggestion_action,
            "suggestion_reason": self.suggestion_reason,
            "confidence": self.confidence,
            "player_action": self.player_action,
            "is_consistent": self.is_consistent,
            "guardrail": self.guardrail,
            "model_meta": self.model_meta,
            "result": self.result,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DecisionPoint":
        return cls(
            dp_id=data.get("dp_id", ""),
            run_id=data.get("run_id", ""),
            turn=int(data.get("turn", 0)),
            seq=int(data.get("seq", 0)),
            state_summary=data.get("state_summary", ""),
            legal_actions=list(data.get("legal_actions") or []),
            suggestion_action=data.get("suggestion_action"),
            suggestion_reason=data.get("suggestion_reason", ""),
            confidence=float(data.get("confidence", 0.0)),
            player_action=data.get("player_action"),
            is_consistent=bool(data.get("is_consistent", False)),
            guardrail=data.get("guardrail") or {},
            model_meta=data.get("model_meta") or {},
            result=data.get("result") or {},
            created_at=data.get("created_at", now_iso()),
        )

    # ---- 领域行为（纯逻辑，不碰 IO）----
    def check_consistency(self) -> bool:
        """建议动作与玩家实际操作是否一致（按 action_type + card_name 比较）。"""
        if not self.suggestion_action or not self.player_action:
            return False
        key = lambda a: (a.get("action_type"), a.get("card_name"))
        return key(self.suggestion_action) == key(self.player_action)

    def is_flagged(self) -> bool:
        """是否被护栏标记（冲突或低置信）。"""
        return bool(self.guardrail) and self.guardrail.get("verdict") == "deny"


@dataclass
class Report:
    """复盘报告。"""

    report_id: str
    run_id: str
    generated_at: str = field(default_factory=now_iso)
    path: str = ""
    key_points: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "path": self.path,
            "key_points": list(self.key_points),
            "summary": self.summary,
        }
