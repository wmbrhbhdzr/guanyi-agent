# -*- coding: utf-8 -*-
"""实验4 测试用例（标准库 unittest，不需要额外依赖）。

覆盖讲义 2.5 要求的四类异常，以及本项目的核心闭环：

    1  数据不存在      2  格式错误（损坏行）    3  数据冲突（重复录入）
    4  无效输入（越界） 5  无效输入（非法枚举）  6  空数据
    7  核心闭环（规则基线 → 护栏 → 落盘 → 报告）
    8  护栏拦截（以规则为准）
    9  报告内容（逐回合表、关键决策点、一致率）

运行：

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guanyi.app.logging_setup import reset_loggers          # noqa: E402
from guanyi.app.service import SessionService               # noqa: E402
from guanyi.core.errors import (                            # noqa: E402
    DuplicateError,
    NotFoundError,
    StorageError,
    ValidationError,
)
from guanyi.data.sample import seed_empty_run, seed_sample_run  # noqa: E402
from guanyi.data.store import JsonlStore                    # noqa: E402

TEST_ROOT = Path("data") / "_test"


class GuanyiBase(unittest.TestCase):
    """每个用例使用独立的临时数据目录，互不干扰。"""

    def setUp(self):
        reset_loggers()
        self.root = TEST_ROOT / self._testMethodName
        shutil.rmtree(self.root, ignore_errors=True)
        self.store = JsonlStore(self.root / "runs")
        self.service = SessionService(self.store)   # 日志目录默认跟随数据目录

    def tearDown(self):
        reset_loggers()
        shutil.rmtree(self.root, ignore_errors=True)


class TestExceptions(GuanyiBase):
    """四类异常：数据不存在、格式错误、数据冲突、无效输入。"""

    def test_01_missing_run_reports_not_found(self):
        """用例1 数据不存在：查不存在的对局应抛 NotFoundError，而不是裸 FileNotFoundError。"""
        with self.assertRaises(NotFoundError) as ctx:
            self.service.get_run("run-9999")
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertIn("run-9999", ctx.exception.message)

    def test_02_corrupted_line_reported_not_crash(self):
        """用例2 格式错误：损坏行跳过并报告行号，其余记录照常可用。"""
        seed_sample_run(self.store, "run-0001")
        with self.store.decisions_file("run-0001").open("a", encoding="utf-8") as fp:
            fp.write("{坏数据\n")

        points, problems = self.service.scan_decisions("run-0001")
        self.assertEqual(len(points), 3, "损坏行不应影响其它记录")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["line"], 4, "问题里应给出行号")

        with self.assertRaises(StorageError):
            self.store.load_decisions("run-0001", strict=True)

    def test_03_duplicate_turn_is_rejected(self):
        """用例3 数据冲突：同一 (run_id, turn) 重复录入被拒绝，记录数不变。"""
        seed_sample_run(self.store, "run-0001")
        with self.assertRaises(DuplicateError) as ctx:
            self.service.record_decision(
                run_id="run-0001", turn=3, state_summary="重复录入",
                suggestion_action={"action_type": "end_turn"},
                player_action={"action_type": "end_turn"})
        self.assertEqual(ctx.exception.code, "duplicate_record")
        self.assertEqual(len(self.store.load_decisions("run-0001")), 3)

    def test_04_confidence_out_of_range(self):
        """用例4 无效输入：置信度必须在 0–1 之间。"""
        seed_sample_run(self.store, "run-0001")
        with self.assertRaises(ValidationError) as ctx:
            self.service.record_decision(
                run_id="run-0001", turn=5, state_summary="置信度越界",
                suggestion_action={"action_type": "end_turn"},
                player_action={"action_type": "end_turn"}, confidence=5)
        self.assertEqual(ctx.exception.code, "invalid_input")
        self.assertEqual(len(self.store.load_decisions("run-0001")), 3)

    def test_05_invalid_action_type(self):
        """用例5 无效输入：动作类型只允许 play_card／end_turn／use_potion。"""
        seed_sample_run(self.store, "run-0001")
        with self.assertRaises(ValidationError) as ctx:
            self.service.record_decision(
                run_id="run-0001", turn=6, state_summary="非法动作",
                suggestion_action={"action_type": "fly", "card_name": "翅膀"},
                player_action={"action_type": "fly", "card_name": "翅膀"})
        self.assertEqual(ctx.exception.code, "invalid_input")
        self.assertIn("play_card", ctx.exception.message)


class TestCoreLoop(GuanyiBase):
    """空数据与核心闭环。"""

    def test_06_empty_run_report(self):
        """用例6 空数据：没有任何决策点也能生成报告，摘要写明“没有决策点记录”。"""
        seed_empty_run(self.store, "run-empty")
        result = self.service.build_report("run-empty")
        self.assertEqual(result["summary"]["decision_count"], 0)
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("没有决策点记录", text)

    def test_07_full_loop_rule_baseline_to_report(self):
        """用例7 核心闭环：规则基线决策 → 护栏放行 → 落盘 → 报告。"""
        self.service.start_run(run_id="run-loop", seed="TEST-1")
        point = self.service.record_decision(
            run_id="run-loop", turn=1,
            state_summary="HP 42/80，敌人 HP 23 意图攻击 11",
            player_action={"action_type": "play_card", "card_name": "打击"},
            state={"hp": 42, "max_hp": 80, "energy": 3, "enemy_hp": 23, "enemy_intent": 11,
                   "hand": ["防御", "打击"]},
            legal_actions=["play_card:防御", "play_card:打击", "end_turn"],
            result={"hp_delta": -11},
        )
        self.assertEqual(point.model_meta["source"], "rule_baseline", "应走规则基线决策")
        # 意图 11 < 血量 42 的三分之一（14），按规则应先压血而不是保血
        self.assertEqual(point.suggestion_action["card_name"], "打击")
        self.assertEqual(point.guardrail["verdict"], "allow")
        self.assertTrue(point.is_consistent, "建议与实际操作都是【打击】→ 应判定为一致")
        self.service.finish_run("run-loop", "胜")
        result = self.service.build_report("run-loop")
        self.assertEqual(result["summary"]["decision_count"], 1)
        self.assertTrue(Path(result["path"]).exists(), "报告文件应已落盘")

    def test_07b_rule_baseline_blocks_when_hp_is_low(self):
        """用例7b 规则基线的保血分支：意图 ≥ 血量三分之一时先出防御。"""
        suggestion = self.service.suggest(
            {"hp": 20, "max_hp": 80, "energy": 3, "enemy_hp": 30, "enemy_intent": 11,
             "hand": ["防御", "打击"]},
            ["play_card:防御", "play_card:打击", "end_turn"])
        self.assertEqual(suggestion["action"]["card_name"], "防御")
        self.assertIn("三分之一", suggestion["reason"])

    def test_08_guardrail_denies_illegal_action(self):
        """用例8 护栏：建议不在合法动作集内 → deny，且以规则为准留痕。"""
        seed_sample_run(self.store, "run-0001")
        point = self.service.record_decision(
            run_id="run-0001", turn=7, state_summary="护栏拦截测试",
            suggestion_action={"action_type": "play_card", "card_name": "打击"},
            player_action={"action_type": "play_card", "card_name": "打击"},
            legal_actions=["end_turn"])
        self.assertEqual(point.guardrail["verdict"], "deny")
        self.assertEqual(point.guardrail["code"], "guardrail_trigger")
        self.assertTrue(point.is_flagged(), "被护栏标记的决策点应能被报告识别")

    def test_09_report_contains_rounds_and_key_points(self):
        """用例9 报告内容：逐回合表、关键决策点、一致率都要出现。"""
        seed_sample_run(self.store, "run-0001")
        result = self.service.build_report("run-0001")
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertEqual(result["summary"]["decision_count"], 3)
        self.assertEqual(result["summary"]["consistent"], 2)
        self.assertIn("## 逐回合表", text)
        self.assertIn("## 关键决策点", text)
        self.assertIn("第 3 回合", text, "第 3 回合建议与实际不一致，应出现在关键决策点里")

    def test_10_log_file_records_events(self):
        """用例10 日志：录入与护栏结论都写入 app.log，便于定位问题。"""
        seed_sample_run(self.store, "run-0001")
        self.service.record_decision(
            run_id="run-0001", turn=7, state_summary="日志测试",
            suggestion_action={"action_type": "play_card", "card_name": "打击"},
            player_action={"action_type": "play_card", "card_name": "打击"},
            legal_actions=["end_turn"])
        log_text = self.store.log_file("run-0001").read_text(encoding="utf-8")
        self.assertIn("录入决策点", log_text)
        self.assertIn("护栏拦截", log_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
