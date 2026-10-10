# -*- coding: utf-8 -*-
"""JSONL 数据访问实现（实验3 设计里的 `StoragePort`）。

目录结构（与实验3 报告 3.4.1 一致，物理位置为 data/runs，避开实验1 遗留的探针目录）：

    data/runs/index.json                 运行索引（列表页使用）
    data/runs/<run_id>/run.json          一局元信息
    data/runs/<run_id>/decisions.jsonl   逐决策点记录，每行一条
    data/runs/<run_id>/report.md         复盘报告
    data/runs/<run_id>/app.log           运行日志
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List

from ..core.models import DecisionPoint, Run


class JsonlStore:
    """基于“一局一目录 + JSONL”的存储实现。"""

    def __init__(self, root="data/runs"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- 路径 ----------
    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def run_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def decisions_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "decisions.jsonl"

    def report_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "report.md"

    def log_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "app.log"

    def index_file(self) -> Path:
        return self.root / "index.json"

    # ---------- Run ----------
    def save_run(self, run: Run) -> Path:
        self.run_dir(run.run_id).mkdir(parents=True, exist_ok=True)
        path = self.run_file(run.run_id)
        path.write_text(json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_index(run)
        return path

    def load_run(self, run_id: str) -> Run:
        path = self.run_file(run_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Run.from_dict(data)

    def list_runs(self) -> List[Dict]:
        path = self.index_file()
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _update_index(self, run: Run) -> None:
        runs = [r for r in self.list_runs() if r.get("run_id") != run.run_id]
        runs.append(run.to_dict())
        runs.sort(key=lambda r: r.get("started_at", ""))
        self.index_file().write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- DecisionPoint ----------
    def append_decision(self, point: DecisionPoint) -> Path:
        path = self.decisions_file(point.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(point.to_dict(), ensure_ascii=False) + "\n")
        return path

    def load_decisions(self, run_id: str) -> List[DecisionPoint]:
        path = self.decisions_file(run_id)
        if not path.exists():
            return []
        points = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                points.append(DecisionPoint.from_dict(json.loads(line)))
        return points

    # ---------- 报告 ----------
    def save_report(self, run_id: str, text: str) -> Path:
        path = self.report_file(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    # ---------- 维护 ----------
    def clear(self) -> int:
        """清空所有运行记录，返回删除的对局数。"""
        count = 0
        for child in sorted(self.root.glob("*/")):
            if child.is_dir():
                shutil.rmtree(child)
                count += 1
        index = self.index_file()
        if index.exists():
            index.unlink()
        return count
