# -*- coding: utf-8 -*-
"""实验6 测试用例：单 Agent 与运行时 Harness 的五类场景（全部不联网）。

用脚本化的假模型（按预设返回 tool_calls / 最终回答）覆盖：

1. 正常完成（工具调用 → 结论 → 程序校验通过）
2. 参数错误（错误参数被程序拦下，错误回传给模型，模型修正后完成）
3. 工具异常（工具内部抛错 → 转成结构化错误回传）
4. 达到步数上限 / 总时限（停止控制由程序执行）
5. 人工确认（同意 → 执行；拒绝 → 不执行；等待超时 → 不执行）

另外覆盖：白名单（未知工具）、路径穿越、连续错误上限、成功校验（数字对不上 → 不放行）、
运行记录（JSONL 事件齐全、密钥遮挡）。

运行：
    .venv\\Scripts\\python.exe -m unittest tests.test_agent -v
"""

import io
import json
import shutil
import sys
import time
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guanyi.agent.confirm import AutoApprove, AutoReject, ConfirmBase          # noqa: E402
from guanyi.agent.harness import AgentConfig, AgentHarness, SYSTEM_PROMPT      # noqa: E402
from guanyi.agent.protocol import ParamSpec, ToolError, ToolRegistry, ToolSpec  # noqa: E402
from guanyi.agent.tools import build_registry                                  # noqa: E402
from guanyi.agent.trace import Trace                                           # noqa: E402
from guanyi.ai.llm_client import LlmResult                                     # noqa: E402
from guanyi.app.service import SessionService                                  # noqa: E402
from guanyi.data.sample import seed_sample_run                                 # noqa: E402
from guanyi.data.store import JsonlStore                                       # noqa: E402

TEST_ROOT = Path("data") / "_agent_test"


def call(name, args=None, call_id=None, delay=0.0):
    """构造一条工具调用（OpenAI tools 格式）。"""
    return {
        "id": call_id or "call_%s" % name,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)},
        "_delay": delay,
    }


def final(text):
    return {"text": text}


class ScriptedClient:
    """按脚本返回结果的假模型（确定性，不联网）。"""

    def __init__(self, script):
        self.script = list(script)
        self.messages_seen = []

    def chat(self, messages, **kwargs):
        self.messages_seen.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        step = self.script.pop(0) if self.script else final("（脚本已结束）")
        if "tool_calls" in step:
            calls = []
            for item in step["tool_calls"]:
                if item.pop("_delay", 0):
                    time.sleep(item["_delay"] if "_delay" in item else 0.2)
                calls.append(item)
            return LlmResult(ok=True, text=step.get("text", ""), tool_calls=calls,
                             usage={"prompt_tokens": 100, "completion_tokens": 20},
                             cost={"cost_total_yuan": 0.0001}, latency_ms=5.0, model="fake")
        return LlmResult(ok=True, text=step.get("text", ""),
                         usage={"prompt_tokens": 100, "completion_tokens": 20},
                         cost={"cost_total_yuan": 0.0001}, latency_ms=5.0, model="fake")


class TimeoutConfirm(ConfirmBase):
    """模拟“等待确认超时”。"""

    def confirm(self, request):
        return {"approved": False, "reason": "等待确认超时（30 秒）", "how": "timeout"}


class AgentBase(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        self.store = JsonlStore(TEST_ROOT / "runs")
        self.service = SessionService(self.store)
        seed_sample_run(self.store, "run-0001")
        self.registry = build_registry(service=self.service)
        self.trace_dir = TEST_ROOT / "agent"

    def tearDown(self):
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def harness(self, script, confirm=None, config=None):
        client = ScriptedClient(script)
        tracer = Trace(task_id="test", out_dir=str(self.trace_dir))
        agent = AgentHarness(client=client, registry=self.registry,
                             confirm=confirm or AutoApprove(), config=config, trace=tracer)
        return agent, client


class TestAgentLoop(AgentBase):
    def test_01_normal_completion(self):
        """正常完成：工具调用 → 结论 → 程序校验通过；写操作经确认后执行。"""
        agent, client = self.harness([
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            {"tool_calls": [call("write_report", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合是 3，建议第 3 回合先防御。"),
        ])
        result = agent.run("分析 run-0001 并写报告")
        self.assertTrue(result.ok, result.status)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual([c["tool"] for c in result.tool_calls], ["compute_stats", "write_report"])
        self.assertTrue(result.validation["ok"], result.validation)
        self.assertTrue((TEST_ROOT / "runs" / "run-0001" / "report.md").exists())
        # 工具结果必须以 role=tool 回传给模型（不是只打印）
        roles = [m["role"] for m in client.messages_seen[-1]]
        self.assertIn("tool", roles)

    def test_02_argument_error_fed_back_then_fixed(self):
        """参数错误：程序拦下并回传错误，模型修正后完成。"""
        agent, client = self.harness([
            {"tool_calls": [call("get_decisions", {"run_id": "not-a-run-id"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("分析 run-0001")
        self.assertTrue(result.ok, result.status)
        self.assertFalse(result.tool_calls[0]["ok"])
        self.assertEqual(result.tool_calls[0]["error"], "invalid_argument")
        tool_messages = [m for m in client.messages_seen[-1] if m["role"] == "tool"]
        self.assertTrue(any("invalid_argument" in str(m.get("content")) for m in tool_messages))

    def test_03_tool_exception_is_caught(self):
        """工具异常：工具内部抛出异常 → 转成 tool_failed 结构化错误回传，Agent 不崩。"""
        registry = ToolRegistry()
        registry.register(ToolSpec(name="boom", description="故意失败的工具",
                                   params=[ParamSpec("x", "string", "参数", required=True)],
                                   read_only=True),
                          lambda x: (_ for _ in ()).throw(RuntimeError("磁盘炸了")))
        registry.register(ToolSpec(name="compute_stats", description="统计",
                                   params=[ParamSpec("run_id", "string", "对局", required=True,
                                                     pattern=r"^run-[A-Za-z0-9_\-]{1,30}$")],
                                   read_only=True),
                          lambda run_id: self.registry.call("compute_stats", {"run_id": run_id}))
        client = ScriptedClient([
            {"tool_calls": [call("boom", {"x": "1"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        agent = AgentHarness(client=client, registry=registry, confirm=AutoApprove(),
                             config=AgentConfig(),
                             trace=Trace(task_id="test-boom", out_dir=str(self.trace_dir)))
        result = agent.run("分析 run-0001")
        self.assertTrue(result.ok, result.status)
        self.assertEqual(result.tool_calls[0]["error"], "tool_failed")

    def test_04_max_steps(self):
        """达到步数上限：程序在第 N 步停止，状态明确。"""
        script = [{"tool_calls": [call("list_runs")]} for _ in range(5)]
        agent, _ = self.harness(script, config=AgentConfig(max_steps=2))
        result = agent.run("无休止地调用工具")
        self.assertEqual(result.status, "max_steps")
        self.assertEqual(result.steps, 2)
        self.assertFalse(result.ok)

    def test_05_total_timeout(self):
        """总时限：超过总运行时限后停止，状态为 timeout。"""
        slow = {"tool_calls": [call("list_runs")]}
        agent, _ = self.harness([slow, slow, slow], config=AgentConfig(total_timeout_s=0.05))
        # 让第一次模型调用变慢，从而在下一次循环检查时超时
        agent.client = ScriptedClient([slow])

        def slow_chat(messages, **kwargs):
            time.sleep(0.2)
            return LlmResult(ok=True, text="", tool_calls=[call("list_runs")], latency_ms=200.0)
        agent.client.chat = slow_chat
        result = agent.run("超时测试")
        self.assertEqual(result.status, "timeout")
        self.assertFalse(result.ok)

    def test_06_consecutive_tool_errors_stop(self):
        """连续工具错误上限：连续 2 次参数错误后停止并给出原因。"""
        bad = {"tool_calls": [call("get_decisions", {"run_id": "bad id!"})]}
        agent, _ = self.harness([bad, bad, bad],
                                config=AgentConfig(max_consecutive_tool_errors=2))
        result = agent.run("连续错误测试")
        self.assertEqual(result.status, "tool_errors")
        self.assertEqual(result.error["code"], "too_many_tool_errors")


class TestWhitelistAndValidation(AgentBase):
    def test_07_unknown_tool_rejected(self):
        """白名单：模型要求调用未注册工具 → 被拒绝，不执行。"""
        agent, client = self.harness([
            {"tool_calls": [call("rm_rf", {})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("越权测试")
        self.assertTrue(result.ok, result.status)
        self.assertEqual(result.tool_calls[0]["error"], "unknown_tool")

    def test_08_path_traversal_rejected(self):
        """路径锚定：run_id 带路径分隔符 → 参数校验拒绝。"""
        agent, _ = self.harness([
            {"tool_calls": [call("get_decisions", {"run_id": "../../etc/passwd"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("路径穿越测试")
        self.assertEqual(result.tool_calls[0]["error"], "invalid_argument")

    def test_09_validation_rejects_wrong_numbers(self):
        """成功校验：结论里的数字与工具结果不一致时，不放行（不能只凭模型说完成）。"""
        agent, _ = self.harness([
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("这局打得很好，全部一致，没有需要复盘的地方。"),     # 数字缺失 + 说法错误
        ])
        result = agent.run("分析 run-0001")
        self.assertEqual(result.status, "validation_failed")
        self.assertFalse(result.validation["ok"])
        self.assertIn("consistent_rate_mentioned", result.validation["failed"])


class TestHumanConfirm(AgentBase):
    def test_10_confirm_approved_executes(self):
        """人工确认-同意：写操作执行，报告文件生成。"""
        agent, _ = self.harness([
            {"tool_calls": [call("write_report", {"run_id": "run-0001"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ], confirm=AutoApprove())
        agent.run("写报告")
        self.assertTrue((TEST_ROOT / "runs" / "run-0001" / "report.md").exists())

    def test_11_confirm_rejected_does_not_execute(self):
        """人工确认-拒绝：写操作不执行，模型被告知“用户未确认”。"""
        target = TEST_ROOT / "runs" / "run-0001" / "report.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("原始内容", encoding="utf-8")
        agent, client = self.harness([
            {"tool_calls": [call("write_report", {"run_id": "run-0001"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3；报告未写入。"),
        ], confirm=AutoReject())
        result = agent.run("写报告（用户会拒绝）")
        self.assertEqual(result.tool_calls[0]["error"], "not_confirmed")
        self.assertEqual(target.read_text(encoding="utf-8"), "原始内容", "拒绝后不得修改文件")
        self.assertIn("not_confirmed",
                      json.dumps(client.messages_seen[-1], ensure_ascii=False))

    def test_12_confirm_timeout_does_not_execute(self):
        """人工确认-等待超时：视为拒绝，不执行。"""
        target = TEST_ROOT / "runs" / "run-0001" / "report.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("原始内容", encoding="utf-8")
        agent, _ = self.harness([
            {"tool_calls": [call("write_report", {"run_id": "run-0001"})]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ], confirm=TimeoutConfirm())
        result = agent.run("写报告（等待确认超时）")
        self.assertEqual(result.tool_calls[0]["error"], "not_confirmed")
        self.assertEqual(target.read_text(encoding="utf-8"), "原始内容")


class TestTrace(AgentBase):
    def test_13_trace_events_and_masking(self):
        """运行记录：关键事件齐全，密钥被遮挡。"""
        agent, _ = self.harness([
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        tracer = Trace(task_id="test-trace", out_dir=str(self.trace_dir))
        agent.trace = tracer
        result = agent.run("记录测试 sk-abcdef123456 这个密钥不应出现在日志里")
        self.assertTrue(result.ok, result.status)
        events = [json.loads(line) for line in tracer.jsonl_path.read_text(encoding="utf-8").splitlines()]
        kinds = {event["event"] for event in events}
        for required in ("run_start", "model_request", "model_response", "tool_call",
                         "tool_result", "validation", "run_end"):
            self.assertIn(required, kinds)
        log_text = tracer.log_path.read_text(encoding="utf-8")
        self.assertNotIn("sk-abcdef123456", log_text)
        self.assertIn("sk-***", log_text)


class TestRuntimeRegression(AgentBase):
    """补充复核：旧截图保留，新增边界由可复现的自动化测试记录。"""

    def test_14_tool_timeout_is_enforced_and_fed_back(self):
        release = threading.Event()
        done = threading.Event()

        def slow():
            release.wait(2)
            done.set()
            return {"ok": True}

        self.registry.register(ToolSpec(name="slow", description="慢工具", timeout_s=.03), slow)
        agent, client = self.harness([
            {"tool_calls": [call("slow")]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        try:
            result = agent.run("工具超时后修正")
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.tool_calls[0]["error"], "timeout")
            outputs = [json.loads(m["content"]) for m in client.messages_seen[-1] if m["role"] == "tool"]
            self.assertEqual(outputs[0]["error"]["code"], "timeout")
        finally:
            release.set()
            self.assertTrue(done.wait(2))

    def test_15_late_final_answer_cannot_succeed(self):
        agent, _ = self.harness([], config=AgentConfig(total_timeout_s=.06))
        def late(*args, **kwargs):
            time.sleep(.2)
            return LlmResult(ok=True, text="决策点数 3，一致率 66.7%，不一致回合 3。")
        agent.client.chat = late
        result = agent.run("不能接受晚到的最终回答")
        self.assertEqual(result.status, "timeout")
        self.assertFalse(result.ok)

    def test_16_late_model_cannot_start_write(self):
        agent, _ = self.harness([], config=AgentConfig(total_timeout_s=.04))
        target = self.store.report_file("run-0001")
        def late(*args, **kwargs):
            time.sleep(.12)
            return LlmResult(ok=True, tool_calls=[call("write_report", {"run_id": "run-0001"})])
        agent.client.chat = late
        result = agent.run("到期后禁止开始写入")
        time.sleep(.15)  # 即使后台模型后来返回，也不能再分发工具。
        self.assertEqual(result.status, "timeout")
        self.assertFalse(target.exists())
        self.assertEqual(result.tool_calls, [])

    def test_17_confirmation_consumes_total_budget(self):
        class SlowConfirm(ConfirmBase):
            def confirm(self, request):
                time.sleep(.12)
                return {"approved": True}
        agent, _ = self.harness([
            {"tool_calls": [call("write_report", {"run_id": "run-0001"})]},
        ], confirm=SlowConfirm(), config=AgentConfig(total_timeout_s=.04))
        result = agent.run("晚到的同意不能触发写入")
        time.sleep(.15)
        self.assertEqual(result.status, "timeout")
        self.assertFalse(self.store.report_file("run-0001").exists())

    def test_18_write_timeout_stops_and_blocks_retry(self):
        scope = object()
        self.registry = ToolRegistry(write_scope=scope)
        release, done = threading.Event(), threading.Event()
        target = self.store.report_file("run-0001")
        executed = []
        def slow_write():
            executed.append(1)
            release.wait(2)
            target.write_text("后台写入结果", encoding="utf-8")
            done.set()
            return {"ok": True}
        self.registry.register(ToolSpec(name="slow_write", description="慢写入", read_only=False,
                                       requires_confirm=True, timeout_s=.03), slow_write)
        agent, client = self.harness([
            {"tool_calls": [call("slow_write")]},
            {"tool_calls": [call("slow_write")]},
        ])
        try:
            result = agent.run("写入超时必须核对")
            self.assertEqual(result.status, "write_state_unknown")
            self.assertEqual(len(client.messages_seen), 1)
            with self.assertRaises(ToolError) as caught:
                self.registry.call("slow_write", {})
            self.assertEqual(caught.exception.code, "write_state_unknown")
            another_registry = ToolRegistry(write_scope=scope)
            another_registry.register(ToolSpec(name="slow_write", description="同目录重新建表", read_only=False), slow_write)
            with self.assertRaises(ToolError) as caught:
                another_registry.call("slow_write", {})
            self.assertEqual(caught.exception.code, "write_state_unknown")
        finally:
            release.set()
            self.assertTrue(done.wait(2))
        self.assertEqual(target.read_text(encoding="utf-8"), "后台写入结果")
        self.assertEqual(len(executed), 1)

    def test_19_numeric_substrings_and_swapped_fields_rejected(self):
        agent, _ = self.harness([])
        stats = self.registry.call("compute_stats", {"run_id": "run-0001"})
        for text in ["决策点数 30，一致率 66.7%，不一致回合 13。",
                     "决策点数 66，一致率 3%，不一致回合 3。",
                     "决策点数 3，一致率 66.7%，不一致回合 3、13。",
                     "决策点数 3，一致率 66.7%，不一致回合 3。决策点数 30。"]:
            with self.subTest(text=text):
                self.assertFalse(agent.validate_success(text, {"compute_stats": stats})["ok"])

    def test_20_report_missing_or_changed_rejected(self):
        agent, _ = self.harness([])
        stats = self.registry.call("compute_stats", {"run_id": "run-0001"})
        with self.assertRaises(ToolError) as caught:
            self.registry.call("write_report", {"run_id": "run-9999"})
        self.assertEqual(caught.exception.code, "not_found")
        report = self.registry.call("write_report", {"run_id": "run-0001"})
        answer = "决策点数 3，一致率 66.7%，不一致回合 3。"
        results = {"compute_stats": stats, "write_report": report}
        self.assertTrue(agent.validate_success(answer, results, report)["ok"])
        path = Path(report["path"])
        path.write_text("已被替换", encoding="utf-8")
        self.assertFalse(agent.validate_success(answer, results, report)["ok"])
        path.unlink()
        self.assertFalse(agent.validate_success(answer, results, report)["ok"])

    def test_21_empty_turn_list_must_be_explicit(self):
        agent, _ = self.harness([])
        stats = {"ok": True, "decision_count": 3, "consistent_rate": 100.0, "inconsistent_turns": []}
        self.assertTrue(agent.validate_success("决策点数：3；一致率：100%；不一致回合：无。", {"compute_stats": stats})["ok"])
        self.assertFalse(agent.validate_success("决策点数：3；一致率：100%。", {"compute_stats": stats})["ok"])

    def test_22_extra_tool_calls_have_matching_results(self):
        calls = [call("list_runs", call_id="c%d" % n) for n in range(4)]
        agent, client = self.harness([
            {"tool_calls": calls},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("超出本步上限的调用也应回传拒绝原因")
        self.assertTrue(result.ok, result.error)
        tool_messages = [m for m in client.messages_seen[1] if m["role"] == "tool"]
        self.assertEqual({m["tool_call_id"] for m in tool_messages}, {"c0", "c1", "c2", "c3"})
        self.assertIn("tool_call_limit", tool_messages[-1]["content"])

    def test_23_model_retries_respect_deadline(self):
        from guanyi.ai.llm_client import LlmClient
        client = LlmClient(api_key="test", retries=2)
        attempts = []
        def failing(url, payload, timeout):
            attempts.append(timeout)
            raise TimeoutError("模拟超时")
        client._post = failing
        result = client.chat([], deadline=time.monotonic() + .1)
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "timeout")
        self.assertEqual(len(attempts), 1)
        self.assertLessEqual(attempts[0], .1)

    def test_24_json_nonobject_is_feedback_not_crash(self):
        malformed = call("list_runs")
        malformed["function"]["arguments"] = "[]"
        agent, _ = self.harness([
            {"tool_calls": [malformed]},
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("JSON 类型错误")
        self.assertTrue(result.ok)
        self.assertEqual(result.tool_calls[0]["error"], "invalid_arguments")

    def test_25_model_timeout_without_total_expiry(self):
        agent, _ = self.harness([], config=AgentConfig(model_timeout_s=.03, total_timeout_s=2))
        def late(*args, **kwargs):
            time.sleep(.12)
            return LlmResult(ok=True, text="晚到的回答")
        agent.client.chat = late
        result = agent.run("独立模型超时")
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.steps, 1)

    def test_26_total_budget_stops_remaining_tools(self):
        release, done = threading.Event(), threading.Event()
        def slow():
            release.wait(2)
            done.set()
            return {"ok": True}
        self.registry.register(ToolSpec(name="slow", description="慢读", timeout_s=2), slow)
        agent, _ = self.harness([
            {"tool_calls": [call("slow"), call("write_report", {"run_id": "run-0001"})]},
        ], config=AgentConfig(total_timeout_s=.04))
        try:
            result = agent.run("预算不足不能继续写入")
            self.assertEqual(result.status, "timeout")
            self.assertFalse(self.store.report_file("run-0001").exists())
            self.assertEqual(len(result.tool_calls), 1)
        finally:
            release.set()
            self.assertTrue(done.wait(2))

    def test_27_wrong_run_cannot_succeed(self):
        agent, _ = self.harness([
            {"tool_calls": [call("compute_stats", {"run_id": "run-0001"})]},
            final("决策点数 3，一致率 66.7%，不一致回合 3。"),
        ])
        result = agent.run("分析 run-0002")
        self.assertEqual(result.status, "validation_failed")
        self.assertIn("target_run_matches", result.validation["failed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
