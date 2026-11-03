# -*- coding: utf-8 -*-
"""运行记录与可观测性（实验6 §2.5）。

每次运行生成一个任务编号，同时写两份记录：

- `data/agent/<任务号>.jsonl`：逐事件结构化记录（程序读取、复核用）
- `data/agent/<任务号>.log`：人类可读摘要（报告取证、界面展示用）

记录内容：时间、事件类型、工具名与参数摘要、工具结果摘要、错误类型、执行步数、耗时、最终状态。
**密钥与个人信息遮挡**：形如 `sk-...` 的串一律替换为 `sk-***`，长文本截断到 200 字符。
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

SECRET_PATTERN = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{6,}|Bearer\s+[A-Za-z0-9_\-\.]{8,}")


def _mask(value):
    """遮挡密钥类字符串；递归处理 dict/list。"""
    if isinstance(value, str):
        return SECRET_PATTERN.sub("sk-***", value)
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask(v) for v in value]
    return value


def summarize(value, limit: int = 200) -> str:
    """把任意结果压成一行摘要（用于日志）。"""
    if isinstance(value, (dict, list)):
        text = json.dumps(_mask(value), ensure_ascii=False)
    else:
        text = str(value)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


class Trace:
    """一次 Agent 运行的记录器。"""

    def __init__(self, task_id: Optional[str] = None, out_dir="data/agent", echo=None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_id = task_id or "task-%s" % stamp
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.out_dir / ("%s.jsonl" % self.task_id)
        self.log_path = self.out_dir / ("%s.log" % self.task_id)
        self.echo = echo                       # 可选回调：把日志实时推给界面
        self.events = []
        self.started = time.time()
        self._jsonl = self.jsonl_path.open("w", encoding="utf-8")
        self._log = self.log_path.open("w", encoding="utf-8")

    # ---------- 记录 ----------
    def event(self, kind: str, **data) -> Dict:
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "elapsed_ms": round((time.time() - self.started) * 1000, 1),
            "event": kind,
        }
        record.update(_mask(data))
        self.events.append(record)
        self._jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl.flush()

        text = self._render(record)
        if text:
            self._log.write(text + "\n")
            self._log.flush()
            if self.echo:
                try:
                    self.echo(text)
                except Exception:              # noqa: BLE001 —— 界面回调失败不影响运行
                    pass
        return record

    @staticmethod
    def _render(record: Dict) -> str:
        kind = record.get("event")
        t = record.get("ts", "")[11:23]
        if kind == "run_start":
            return "[%s] 开始任务 %s：%s" % (t, record.get("task_id"), record.get("goal"))
        if kind == "model_request":
            return "[%s] 第 %s 步：请求模型（上下文 %s 条消息）" % (
                t, record.get("step"), record.get("message_count"))
        if kind == "model_response":
            if record.get("tool_calls"):
                return "[%s] 第 %s 步：模型请求调用工具 %s" % (
                    t, record.get("step"), record.get("tool_calls"))
            return "[%s] 第 %s 步：模型给出最终回答（%s 字）" % (
                t, record.get("step"), record.get("chars"))
        if kind == "tool_call":
            return "[%s]   调用工具 %s 参数 %s" % (t, record.get("tool"), record.get("args"))
        if kind == "tool_result":
            return "[%s]   工具 %s 返回：%s" % (t, record.get("tool"), record.get("summary"))
        if kind == "tool_error":
            return "[%s]   工具 %s 出错：%s %s" % (
                t, record.get("tool"), record.get("code"), record.get("message"))
        if kind == "confirm":
            return "[%s]   需要确认：%s → %s" % (t, record.get("request"), record.get("decision"))
        if kind == "validation":
            return "[%s] 结果校验：%s（%s）" % (t, "通过" if record.get("ok") else "未通过",
                                           record.get("detail"))
        if kind == "limit":
            return "[%s] 触发限制：%s" % (t, record.get("reason"))
        if kind == "run_end":
            return "[%s] 结束任务 %s：状态=%s，步数=%s，耗时=%.0f ms" % (
                t, record.get("task_id"), record.get("status"), record.get("steps"),
                record.get("elapsed_ms") or 0)
        if kind == "error":
            return "[%s] 错误：%s %s" % (t, record.get("code"), record.get("message"))
        return "[%s] %s %s" % (t, kind, summarize({k: v for k, v in record.items()
                                                   if k not in ("ts", "elapsed_ms", "event")}))

    # ---------- 收尾 ----------
    def close(self, status: str, **extra) -> None:
        payload = {"status": status}
        payload.update(extra)
        self.event("run_end", task_id=self.task_id, **payload)
        try:
            self._jsonl.close()
            self._log.close()
        except Exception:                     # noqa: BLE001
            pass

    @property
    def path(self) -> str:
        return str(self.jsonl_path)
