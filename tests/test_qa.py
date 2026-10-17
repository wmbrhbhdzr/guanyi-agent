# -*- coding: utf-8 -*-
"""实验5 测试用例（标准库 unittest，全部不联网）。

覆盖：知识库切分、检索与同义词、资料不足判定、Prompt 组装、
RAG 链路（假客户端）、以及模型调用失败（缺密钥 / 超时重试 / 费用折算）。

运行：
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guanyi.ai import prompts                                        # noqa: E402
from guanyi.ai.llm_client import LlmClient, LlmResult, compute_cost  # noqa: E402
from guanyi.app.qa_service import QaService                          # noqa: E402
from guanyi.knowledge import Retriever, load_chunks, stats          # noqa: E402

KB = Path("knowledge")


class FakeClient:
    """假客户端：记录收到的 messages 并返回固定回答，用于不联网测试。"""

    def __init__(self, text="痛击升级后造成 10 点伤害[来源1]"):
        self.text = text
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return LlmResult(ok=True, text=self.text,
                         usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                         cost={"cost_total_yuan": 0.0001}, latency_ms=10.0, model="fake")


class TestSplitter(unittest.TestCase):
    def test_01_chunks_loaded_with_metadata(self):
        """片段都带元数据：chunk_id / 来源文件 / 标题 / 来源行。"""
        chunks = load_chunks(KB)
        self.assertGreater(len(chunks), 30, "知识库应有多于 30 个片段")
        for chunk in chunks[:5]:
            self.assertTrue(chunk.chunk_id)
            self.assertTrue(chunk.title)
            self.assertTrue(chunk.text)
            self.assertTrue(chunk.source, "片段应带来源说明")

    def test_02_stats_no_overlap(self):
        """切分不重叠，片段规模有上下界。"""
        info = stats(load_chunks(KB))
        self.assertFalse(info["overlap"])
        self.assertGreater(info["max_chars"], info["min_chars"])
        self.assertEqual(info["count"], sum(info["by_section"].values()))


class TestRetriever(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = Retriever(kb_dir=str(KB))

    def test_03_expected_chunk_ranks_first(self):
        """问升级效果时，痛击条目应排第一。"""
        result = self.retriever.search("痛击升级之后有什么变化", top_k=3)
        self.assertTrue(result["ok"])
        self.assertIn("BASH", result["hits"][0]["title"])
        self.assertIn("score", result["hits"][0], "应给出排序依据")

    def test_04_synonym_alias_works(self):
        """口语“护盾”应能命中资料里的“格挡”。"""
        result = self.retriever.search("护盾怎么算", top_k=3)
        self.assertTrue(result["ok"])
        joined = " ".join(h["text"] for h in result["hits"])
        self.assertIn("格挡", joined)

    def test_05_insufficient_when_unrelated(self):
        """无关问题时返回资料不足，而不是硬凑片段。"""
        result = self.retriever.search("这游戏怎么联机", top_k=3)
        self.assertFalse(result["ok"])
        self.assertIn("资料不足", result["reason"])


class TestPrompts(unittest.TestCase):
    def test_06_rag_v2_rules_and_citations(self):
        """RAG v2 模板：只依据资料 + [来源N] 引用 + 资料不足要说。"""
        hits = [{"title": "【痛击】BASH", "section": "铁甲战士 · 卡牌", "text": "升级后造成10点伤害"}]
        messages = prompts.build_messages("痛击升级后呢？", hits, version="v2")
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("只能依据", messages[0]["content"])
        self.assertIn("[来源1]", messages[1]["content"])
        self.assertIn("痛击升级后呢？", messages[1]["content"])

    def test_07_direct_has_no_context(self):
        """直接模型组不提供检索资料。"""
        messages = prompts.build_messages("痛击升级后呢？", version="direct")
        self.assertEqual(len(messages), 2)
        self.assertNotIn("参考资料", messages[1]["content"])


class TestQaService(unittest.TestCase):
    def test_08_rag_flow(self):
        """RAG 链路：检索片段进上下文、调用一次、返回回答与出处。"""
        fake = FakeClient()
        qa = QaService(kb_dir=str(KB), client=fake)
        result = qa.ask("痛击升级之后有什么变化", save=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["answer"], fake.text)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("[来源1]", fake.calls[0][1]["content"])
        self.assertTrue(result["hits"])

    def test_09_insufficient_makes_no_call(self):
        """资料不足时不调用模型、不产生费用。"""
        fake = FakeClient()
        qa = QaService(kb_dir=str(KB), client=fake)
        result = qa.ask("这游戏怎么联机", save=False)
        self.assertFalse(result["ok"])
        self.assertTrue(result["insufficient"])
        self.assertEqual(len(fake.calls), 0)

    def test_10_direct_flow(self):
        """直接模型组：不检索、不注入资料。"""
        fake = FakeClient()
        qa = QaService(kb_dir=str(KB), client=fake)
        result = qa.ask("痛击要几费", use_rag=False, save=False)
        self.assertTrue(result["ok"])
        self.assertNotIn("参考资料", fake.calls[0][1]["content"])


class TestLlmFailures(unittest.TestCase):
    def test_11_missing_api_key(self):
        """缺密钥：直接返回错误码，不发请求。"""
        client = LlmClient(api_key="your_api_key_here")
        result = client.chat([{"role": "user", "content": "hi"}])
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "missing_api_key")

    def test_12_timeout_is_retried(self):
        """超时：按 retries 重试，仍失败则返回 timeout。"""
        class TimeoutClient(LlmClient):
            def __init__(self):
                super().__init__(api_key="sk-test", retries=1, timeout=0.01)
                self.posts = 0

            def _post(self, url, payload, timeout):
                self.posts += 1
                raise TimeoutError()

        client = TimeoutClient()
        result = client.chat([{"role": "user", "content": "hi"}])
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "timeout")
        self.assertEqual(result.attempts, 2, "retries=1 时应尝试 2 次")

    def test_13_cost_peak_vs_offpeak(self):
        """费用折算：高峰价是空闲价的 2 倍。"""
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        offpeak = compute_cost(usage, offpeak=True)
        peak = compute_cost(usage, offpeak=False)
        self.assertGreater(offpeak["cost_total_yuan"], 0)
        self.assertAlmostEqual(peak["cost_total_yuan"], offpeak["cost_total_yuan"] * 2, places=8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
