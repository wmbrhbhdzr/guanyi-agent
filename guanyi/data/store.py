# -*- coding: utf-8 -*-
"""JSONL 数据访问实现（实验3 设计里的 `StoragePort`）。

目录结构（物理位置 data/runs，避开实验1 遗留的探针目录）：

    data/runs/index.json                 运行索引（列表页使用）
    data/runs/<run_id>/run.json          一局元信息
    data/runs/<run_id>/decisions.jsonl   逐决策点记录，每行一条
    data/runs/<run_id>/report.md         复盘报告
    data/runs/<run_id>/app.log           运行日志

修订版相对初版的变化：
    - 文件不存在 → NotFoundError（而不是裸 FileNotFoundError）；
    - run.json 解析失败 → StorageError；
    - decisions.jsonl 逐行容错：损坏行被跳过并报告行号，其余记录照常可用；
    - 落盘前统一走 `validate()`，脏数据进不来。
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from ..core.errors import NotFoundError, StorageError, ValidationError
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
        run.validate()
        self.run_dir(run.run_id).mkdir(parents=True, exist_ok=True)
        path = self.run_file(run.run_id)
        path.write_text(json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_index(run)
        return path

    def load_run(self, run_id: str) -> Run:
        path = self.run_file(run_id)
        if not path.exists():
            raise NotFoundError("找不到对局 %s 的记录文件" % run_id, run_id=run_id, path=str(path))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError("对局 %s 的 run.json 内容损坏，无法解析" % run_id,
                               run_id=run_id, path=str(path), error=str(exc))
        run = Run.from_dict(data)
        run.validate()
        return run

    def list_runs(self) -> List[Dict]:
        path = self.index_file()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError("index.json 内容损坏，无法解析", path=str(path), error=str(exc))

    def _update_index(self, run: Run) -> None:
        runs = [r for r in self.list_runs() if r.get("run_id") != run.run_id]
        runs.append(run.to_dict())
        runs.sort(key=lambda r: r.get("started_at", ""))
        self.index_file().write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- DecisionPoint ----------
    def append_decision(self, point: DecisionPoint) -> Path:
        point.validate()
        path = self.decisions_file(point.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(point.to_dict(), ensure_ascii=False) + "\n")
        return path

    def scan_decisions(self, run_id: str) -> Tuple[List[DecisionPoint], List[Dict]]:
        """读取决策点：返回 (可用记录, 问题列表)。损坏行被跳过并在问题里给出行号。"""
        if not self.run_dir(run_id).exists():
            raise NotFoundError("找不到对局 %s 的运行目录" % run_id,
                                run_id=run_id, path=str(self.run_dir(run_id)))
        path = self.decisions_file(run_id)
        if not path.exists():
            return [], []
        points, problems = [], []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                point = DecisionPoint.from_dict(json.loads(line))
                point.validate()
            except (json.JSONDecodeError, ValidationError) as exc:
                problems.append({
                    "line": lineno,
                    "error": type(exc).__name__,
                    "message": str(exc),
                })
                continue
            points.append(point)
        return points, problems

    def load_decisions(self, run_id: str, strict=False) -> List[DecisionPoint]:
        """读取决策点；strict=True 时只要有问题就抛 StorageError。"""
        points, problems = self.scan_decisions(run_id)
        if problems and strict:
            raise StorageError("decisions.jsonl 有 %d 行无法解析" % len(problems),
                               run_id=run_id, problems=problems)
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
