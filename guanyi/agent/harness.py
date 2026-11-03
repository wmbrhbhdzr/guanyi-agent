# -*- coding: utf-8 -*-
"""运行时 Harness（实验6 §2.3–2.4）：单 Agent 的循环、上下文、限制与结果校验。

一次运行的控制流：

    接收目标 → [模型调用（带 tools schema）]
        ├─ 模型返回 tool_calls → 白名单/参数校验 →（写操作→人工确认）→ 执行工具
        │                        → 以 `role=tool` 把结果写回上下文 → 回到模型调用
        └─ 模型返回最终回答 → **程序校验成功标准** → 结束

由程序（而不是提示词）执行的关键限制：
    · 工具白名单与参数 Schema 校验（protocol.py）
    · 最大步数、总时限、单次模型超时、单步工具调用数、连续工具错误上限
    · 写操作必须先经人工确认（confirm.py）
    · 结束时按成功标准校验结果（不能只凭模型声称完成）
"""

import json
import hashlib
import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..ai.llm_client import LlmClient
from .confirm import AutoReject, ConfirmBase
from .protocol import ToolError, ToolRegistry
from .trace import Trace, summarize
from .runtime import wait_call

#: Agent 的系统提示词（只描述“怎么合作”，真正的限制在程序里）
SYSTEM_PROMPT = """你是观弈（GuanYi）的复盘分析助手，负责分析《杀戮尖塔 2》的对局记录并给出可核对结论。

工作方式：
1. 需要数据时必须调用工具获取，不要凭印象编造任何数字；
2. 工具名与参数必须严格符合提供的 schema；参数错误会返回 {"ok": false, "error": ...}，请据此修正；
3. 写操作（write_report）执行前会请求用户确认；若未确认，如实说明“用户未确认，未写入”；
4. 目标完成后直接输出最终结论，不要再调用工具。

最终结论必须包含：决策点数、建议与实际一致率、不一致的回合号，以及一条改进建议。
结论中请单独写明「决策点数：N；一致率：R%；不一致回合：T」。多个回合用顿号分隔；没有则写「无」。
"""


@dataclass
class AgentConfig:
    """运行限制（全部由程序执行）。"""

    max_steps: int = 8
    total_timeout_s: float = 120.0
    model_timeout_s: float = 60.0
    max_tool_calls_per_step: int = 3
    max_consecutive_tool_errors: int = 2


@dataclass
class AgentResult:
    ok: bool
    status: str
    final_answer: str = ""
    steps: int = 0
    tool_calls: List[Dict] = field(default_factory=list)
    elapsed_ms: float = 0.0
    trace_path: str = ""
    task_id: str = ""
    validation: Dict = field(default_factory=dict)
    error: Dict = field(default_factory=dict)
    report_written: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok, "status": self.status, "final_answer": self.final_answer,
            "steps": self.steps, "tool_calls": self.tool_calls, "elapsed_ms": self.elapsed_ms,
            "trace_path": self.trace_path, "task_id": self.task_id,
            "validation": self.validation, "error": self.error,
            "report_written": self.report_written,
        }


class AgentHarness:
    """单 Agent 运行时：负责循环、限制、确认、日志与结果校验。"""

    def __init__(self, client: Optional[LlmClient] = None, registry: Optional[ToolRegistry] = None,
                 confirm: Optional[ConfirmBase] = None, config: Optional[AgentConfig] = None,
                 trace: Optional[Trace] = None, logger=None):
        self.client = client or LlmClient()
        if registry is None:
            from .tools import build_registry
            registry = build_registry()
        self.registry = registry
        self.confirm = confirm or AutoReject()      # 默认拒绝：没人确认的写操作不执行
        self.config = config or AgentConfig()
        self.trace = trace
        self.logger = logger
        self.max_observed_steps = 0

    # ---------- 主循环 ----------
    def run(self, goal: str, task_id: Optional[str] = None) -> AgentResult:
        cfg = self.config
        tracer = self.trace or Trace(task_id=task_id)
        self.trace = tracer
        started = time.monotonic()
        deadline = started + cfg.total_timeout_s
        tracer.event("run_start", task_id=tracer.task_id, goal=goal,
                     tools=self.registry.names(), max_steps=cfg.max_steps,
                     total_timeout_s=cfg.total_timeout_s,
                     max_consecutive_tool_errors=cfg.max_consecutive_tool_errors)

        messages: List[Dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "任务目标：%s" % goal},
        ]
        calls: List[Dict] = []            # 每次工具调用的摘要（写进结果）
        results: Dict[str, Dict] = {}     # 最近一次成功的工具结果（用于成功校验）
        consecutive_errors = 0
        steps = 0
        report_written = None
        target_runs = set(re.findall(r"\brun-[A-Za-z0-9_-]+", goal))
        target_run = next(iter(target_runs)) if len(target_runs) == 1 else None

        def finish(status: str, **extra) -> AgentResult:
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            result = AgentResult(
                ok=(status == "succeeded"),
                status=status,
                final_answer=extra.get("final_answer", ""),
                steps=steps,
                tool_calls=calls,
                elapsed_ms=elapsed_ms,
                trace_path=tracer.path,
                task_id=tracer.task_id,
                validation=extra.get("validation", {}),
                error=extra.get("error", {}),
                report_written=report_written,
            )
            tracer.close(status, steps=steps, elapsed_ms=elapsed_ms,
                         tool_calls=[c["tool"] for c in calls],
                         ok=result.ok)
            if self.logger:
                self.logger.info("agent 任务结束 status=%s steps=%s elapsed=%.0fms task=%s",
                                 status, steps, elapsed_ms, tracer.task_id)
            return result

        while True:
            # ---- 停止检查（步数 / 总时限）----
            if steps >= cfg.max_steps:
                tracer.event("limit", reason="达到最大步数 %d" % cfg.max_steps)
                return finish("max_steps")
            if time.monotonic() >= deadline:
                tracer.event("limit", reason="超过总运行时限 %.0f 秒" % cfg.total_timeout_s)
                return finish("timeout")
            steps += 1

            # ---- 模型调用 ----
            tracer.event("model_request", step=steps, message_count=len(messages))
            model_deadline = min(deadline, time.monotonic() + cfg.model_timeout_s)
            try:
                response = wait_call(lambda: self.client.chat(
                    messages, tools=self.registry.schemas(), tool_choice="auto",
                    timeout=min(cfg.model_timeout_s, max(0, model_deadline - time.monotonic())),
                    deadline=model_deadline), model_deadline - time.monotonic())
            except TimeoutError:
                return finish("timeout", error={"code": "timeout", "message": "模型或总运行等待超时"})
            except Exception as exc:
                return finish("model_error", error={"code": "model_error", "message": str(exc)})
            if time.monotonic() >= deadline:
                return finish("timeout", error={"code": "timeout", "message": "总运行时限已到"})
            if not response.ok:
                error = response.error or {"code": "model_error", "message": "模型调用失败"}
                tracer.event("error", code=error.get("code"), message=error.get("message"))
                return finish("timeout" if error.get("code") == "timeout" else "model_error", error=error)

            names = [tc.get("function", {}).get("name", "?") for tc in response.tool_calls]
            tracer.event("model_response", step=steps, tool_calls=names,
                         chars=len(response.text or ""), finish_reason=response.finish_reason)

            # ---- 没有工具调用 → 最终回答 → 程序校验 ----
            if not response.tool_calls:
                try:
                    validation = wait_call(lambda: self.validate_success(
                        response.text, results, report_written, target_run), deadline - time.monotonic())
                except TimeoutError:
                    return finish("timeout", error={"code": "timeout", "message": "成功校验等待超时"})
                tracer.event("validation", ok=validation["ok"], detail=validation["detail"])
                return finish("succeeded" if validation["ok"] else "validation_failed",
                              final_answer=response.text, validation=validation)

            # ---- 把带 tool_calls 的 assistant 消息写回上下文（接口要求，不是只打印）----
            messages.append({
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": response.tool_calls,
            })

            for index, call in enumerate(response.tool_calls):
                name = call.get("function", {}).get("name", "")
                raw_args = call.get("function", {}).get("arguments") or "{}"
                call_id = call.get("id") or name
                if time.monotonic() >= deadline:
                    return finish("timeout", error={"code": "timeout", "message": "工具执行前总时限已到"})
                if index >= cfg.max_tool_calls_per_step:
                    error = {"code": "tool_call_limit", "message": "本步工具数超限，此调用未执行"}
                    tool_result = {"ok": False, "error": error}
                else:
                    tool_result, error = self._execute(name, raw_args, tracer, deadline)
                calls.append({"tool": name, "ok": error is None,
                              "args": summarize(raw_args, 120) if isinstance(raw_args, str) else "",
                              "error": (error or {}).get("code") if error else ""})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
                if error and error.get("detail", {}).get("state_unknown"):
                    tracer.event("reconciliation_required", tool=name,
                                 reason="写入结果不明；本任务停止，不自动重试。请等待后台结束并核对目标文件。")
                    return finish("write_state_unknown", error=error)
                if time.monotonic() >= deadline:
                    return finish("timeout", error={"code": "timeout", "message": "总运行时限已到"})
                if error:
                    consecutive_errors += 1
                    if consecutive_errors >= cfg.max_consecutive_tool_errors:
                        tracer.event("limit", reason="连续工具错误达到 %d 次"
                                     % cfg.max_consecutive_tool_errors)
                        return finish("tool_errors", error={
                            "code": "too_many_tool_errors",
                            "message": "连续 %d 次工具调用失败，已停止"
                                       % cfg.max_consecutive_tool_errors})
                else:
                    consecutive_errors = 0
                    results[name] = tool_result
                    if name == "write_report":
                        report_written = tool_result

    # ---------- 单次工具执行（含白名单、参数校验、人工确认）----------
    def _execute(self, name: str, raw_args, tracer: Trace, deadline=None):
        """返回 (给模型的 content dict, 错误 dict 或 None)。"""
        try:
            spec = self.registry.spec(name)                    # 白名单
            if isinstance(raw_args, str):
                args = json.loads(raw_args) if raw_args.strip() else {}
            else:
                args = raw_args
        except ToolError as exc:
            tracer.event("tool_error", tool=name, code=exc.code, message=exc.message)
            return exc.to_dict(), exc.to_dict()["error"]
        except json.JSONDecodeError as exc:
            error = {"code": "invalid_arguments", "message": "参数不是合法 JSON：%s" % exc}
            tracer.event("tool_error", tool=name, **error)
            return {"ok": False, "error": error}, error

        try:
            clean = spec.validate(args)                        # 参数约束
        except ToolError as exc:
            tracer.event("tool_error", tool=name, code=exc.code, message=exc.message,
                         args=summarize(args, 120))
            return exc.to_dict(), exc.to_dict()["error"]

        tracer.event("tool_call", tool=name, args=summarize(clean, 160),
                     read_only=spec.read_only)

        # ---- 写操作：先展示内容与影响，由用户明确同意；拒绝/超时 → 不执行 ----
        if spec.requires_confirm:
            request = {
                "title": "工具 %s 需要确认" % name,
                "lines": ["工具：%s（%s）" % (name, "只读" if spec.read_only else "写操作"),
                          "参数：%s" % summarize(clean, 120),
                          "目标路径：data/runs/%s/report.md"
                          % clean.get("run_id", "?") if name == "write_report" else ""],
                "impact": spec.side_effects or spec.repeated_call,
            }
            remaining = max(0, deadline - time.monotonic()) if deadline is not None else 30.0
            try:
                decision = self.confirm.confirm_with_timeout(request, remaining)
            except TimeoutError:
                decision = {"approved": False, "reason": "等待确认超时", "how": "timeout"}
            tracer.event("confirm", request="%s %s" % (name, summarize(clean, 80)),
                         decision=decision.get("reason"), how=decision.get("how"),
                         approved=bool(decision.get("approved")))
            if not decision.get("approved"):
                error = {"code": "not_confirmed",
                         "message": "用户未确认（%s），操作未执行" % decision.get("reason", "拒绝")}
                tracer.event("tool_error", tool=name, **error)
                return {"ok": False, "error": error}, error

        try:
            remaining = max(0, deadline - time.monotonic()) if deadline is not None else None
            result = self.registry.call(name, clean, timeout_s=remaining)
        except ToolError as exc:
            tracer.event("tool_error", tool=name, code=exc.code, message=exc.message)
            return exc.to_dict(), exc.to_dict()["error"]
        tracer.event("tool_result", tool=name, summary=summarize(result, 160))
        return result, None

    # ---------- 成功标准校验（§2.3 要求：不能只凭模型说完成）----------
    def validate_success(self, answer: str, results: Dict[str, Dict],
                         report_written: Optional[Dict] = None, target_run=None) -> Dict:
        answer = answer or ""
        checks: Dict[str, bool] = {}
        stats = results.get("compute_stats") or {}
        checks["compute_stats_called"] = bool(stats.get("ok"))
        if target_run:
            checks["target_run_matches"] = stats.get("run_id") == target_run
        if stats.get("ok"):
            text = answer.replace("*", "").replace("`", "")
            counts = re.findall(r"决策点(?:数|数量)\s*[:：|]?\s*(?:为|是|共)?\s*(\d+)(?![\d.])", text)
            rates = re.findall(r"(?<!不)一致率\s*[:：|]?\s*(?:为|是)?\s*(\d+(?:\.\d+)?)\s*[%％]", text)
            turn_fields = re.findall(
                r"不一致(?:的)?回合(?:号)?\s*[:：|]?\s*(?:为|是)?\s*"
                r"(无|没有|\[\s*\]|第?\s*\d+(?:\s*(?:回合)?\s*[、,，]\s*第?\s*\d+)*)", text)
            checks["decision_count_mentioned"] = bool(counts) and all(int(n) == stats.get("decision_count") for n in counts)
            checks["consistent_rate_mentioned"] = bool(rates) and all(float(n) == stats.get("consistent_rate") for n in rates)
            expected = set(stats.get("inconsistent_turns") or [])
            checks["inconsistent_turns_mentioned"] = bool(turn_fields) and all(
                set(map(int, re.findall(r"\d+", value))) == expected for value in turn_fields)
        if "write_report" in results:
            report = report_written or {}
            checks["report_run_matches"] = report.get("run_id") == stats.get("run_id")
            try:
                path = Path(report.get("path", ""))
                checks["report_written"] = bool(report.get("ok") and path.is_file()
                    and report.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest())
            except (OSError, ValueError, TypeError):
                checks["report_written"] = False
        failed = [name for name, passed in checks.items() if not passed]
        return {
            "ok": bool(checks) and not failed,
            "checks": checks,
            "failed": failed,
            "detail": ("全部通过" if not failed else "未通过：" + "、".join(failed)),
        }
