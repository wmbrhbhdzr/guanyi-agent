# -*- coding: utf-8 -*-
"""RAG 问答服务（实验5 §2.4）：问题输入 → 检索 → 上下文组织 → 模型调用 → 带出处回答。

一次问答的完整记录（检索片段、**实际发送给模型的上下文**、回答、耗时、用量、费用）
会落盘到 `data/qa/qa_<时间戳>.json`，既便于报告取证，也便于重复实验时对照。

资料不足时**不调用模型**，直接返回提示 —— 讲义 2.4 明确要求“无结果或资料不相关时返回资料不足提示，
不编造答案或引用”。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..ai import prompts
from ..ai.llm_client import LlmClient
from ..knowledge import Retriever


class QaService:
    """知识问答用例编排（界面与命令行共用）。"""

    def __init__(self, kb_dir="knowledge", out_dir="data/qa", client=None, retriever=None):
        self.kb_dir = Path(kb_dir)
        self.out_dir = Path(out_dir)
        self.retriever = retriever if retriever is not None else Retriever(kb_dir=str(self.kb_dir))
        self.client = client if client is not None else LlmClient()

    # ---------- 主流程 ----------
    def ask(self, question: str, use_rag: bool = True, top_k: int = 3,
            prompt_version: Optional[str] = None, history: Optional[List[Dict]] = None,
            save: bool = True) -> Dict:
        """回答一个问题。`use_rag=False` 时走“直接模型组”（不给资料）。"""
        question = (question or "").strip()
        if not question:
            return {"ok": False, "answer": "请先输入问题", "error": {"code": "empty_question"}}

        version = (prompt_version or ("v2" if use_rag else "direct")).lower()
        hits: List[Dict] = []
        retrieval = None
        if use_rag:
            retrieval = self.retriever.search(question, top_k=top_k)
            if not retrieval.get("ok"):
                record = self._record(question, version, hits, None, None, retrieval,
                                      {"ok": False, "answer": "资料不足：" + retrieval.get("reason", "")})
                path = self._save(record) if save else None
                return {"ok": False, "insufficient": True, "answer": record["answer"],
                        "reason": retrieval.get("reason"), "hits": [], "prompt_version": version,
                        "saved_path": str(path) if path else None}
            hits = retrieval["hits"]

        messages = prompts.build_messages(question, hits, version=version, history=history)
        llm = self.client.chat(messages)

        record = self._record(question, version, hits, messages, llm.to_dict(), retrieval, None)
        path = self._save(record) if save else None
        return {
            "ok": llm.ok,
            "answer": llm.text,
            "error": llm.error,
            "insufficient": False,
            "hits": [{"rank": h["rank"], "title": h["title"], "chunk_id": h["chunk_id"],
                      "score": h["score"], "bm25": h["bm25"], "cosine": h["cosine"],
                      "matched_terms": h["matched_terms"], "source": h["source"]} for h in hits],
            "messages": messages,
            "usage": llm.usage,
            "cost": llm.cost,
            "latency_ms": llm.latency_ms,
            "model": llm.model,
            "finish_reason": llm.finish_reason,
            "attempts": llm.attempts,
            "prompt_version": version,
            "saved_path": str(path) if path else None,
        }

    # ---------- 记录 ----------
    def _record(self, question, version, hits, messages, llm_dict, retrieval, override) -> Dict:
        context = prompts.build_context(hits) if hits else ""
        record = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "question": question,
            "prompt_version": version,
            "use_rag": bool(hits),
            "context": context,
            "messages": messages or [],
            "hits": [{k: v for k, v in h.items() if k != "text"} for h in hits],
            "hit_texts": [h["text"] for h in hits],
            "retrieval": {"ok": retrieval.get("ok"), "reason": retrieval.get("reason"),
                          "query_terms": retrieval.get("query_terms")} if retrieval else None,
            "llm": llm_dict,
            "answer": (override or {}).get("answer") or (llm_dict or {}).get("text", ""),
        }
        return record

    def _save(self, record: Dict) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.out_dir / ("qa_%s_%s.json" % (stamp, record["prompt_version"]))
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ---------- 便捷方法 ----------
    def kb_stats(self) -> Dict:
        from ..knowledge import stats
        return stats(self.retriever.chunks)
