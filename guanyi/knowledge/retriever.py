# -*- coding: utf-8 -*-
"""混合检索：关键词（BM25 简化）+ 词频向量余弦（实验5 §2.4）。

为什么选这个组合
----------------
1. 本机不方便安装分词库（课程环境不引第三方依赖），因此用「同义词归一 + 中文 2-gram」做关键词匹配；
2. 单靠关键词，问法和资料用词不一致时会漏（例如用户说“护盾”，资料写“格挡”）→ 用同义词表补上；
3. 单靠词频向量，长片段会因为词多而虚高 → 用 BM25 的长度归一做主干，向量余弦做补充；
4. 两者都**可解释**：返回命中词、BM25 分、余弦分，便于复核排序依据（讲义要求说明排序依据）。

注意：这里的“向量”是**词频向量**（bag-of-words + 余弦），不是神经网络嵌入向量；
本课程环境没有嵌入接口（DeepSeek 只提供 chat 接口），所以如实标注，并在局限性里说明。
"""

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Tuple

from .splitter import Chunk, load_chunks

#: 同义词/口语 → 资料里的规范用词
ALIASES = {
    "护盾": "格挡", "护甲": "格挡", "护罩": "格挡", "盾": "格挡", "抵挡": "格挡",
    "受伤加成": "易伤", "增伤": "易伤", "增伤状态": "易伤",
    "攻击力": "力量", "灵巧": "敏捷", "摸牌": "抽牌", "抓牌": "抽牌",
    "费用": "能量", "费": "能量", "消失": "消耗", "血": "生命",
    "血量": "生命", "hp": "生命", "回血": "回复", "加血": "回复",
    "行动": "意图", "打法": "出牌", "打牌": "出牌",
}

#: 检索时忽略的高频虚词（避免“为什么/怎么”这类词把无关片段拉上来）
STOPWORDS = set("""
的 了 是 在 和 与 或 我 你 他 她 它 这 那 有 没 没有 不 也 就 都 而 及 等 被 把 给 对 为 从 到
吗 呢 吧 啊 呀 请问 一下 什么 怎么 怎样 如何 为何 为什么 应该 可以 需要 值得 该 会 能 要 好 更
一张 一个 这个 那个 时候 情况 问题 一下 现在 本回合 回合 时候
""".split())


def tokenize(text: str) -> List[str]:
    """把文本切成检索用的词：同义词归一词 + 中文 2-gram + 英文/数字词。"""
    text = str(text or "").lower()
    tokens: List[str] = []
    for word in re.findall(r"[a-z0-9_]+", text):                 # 英文与数字（如 vulnerable、6）
        if word not in STOPWORDS:
            tokens.append(word)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):            # 连续汉字
        if run in ALIASES:
            tokens.append(ALIASES[run])
        for size in (2, 3):                                      # 2-gram 与 3-gram
            for i in range(len(run) - size + 1):
                gram = run[i:i + size]
                if gram not in STOPWORDS:
                    tokens.append(gram)
    # 同义词补充：文本里出现“护盾”，额外计入“格挡”
    for key, canon in ALIASES.items():
        if key in text and canon not in tokens:
            tokens.append(canon)
    return tokens


class Retriever:
    """知识库检索器：BM25 + 词频向量余弦的混合排序。"""

    def __init__(self, chunks: List[Chunk] = None, kb_dir=None):
        self.chunks: List[Chunk] = chunks if chunks is not None else load_chunks(kb_dir or "knowledge")
        self.df: Counter = Counter()
        self.vecs: List[Counter] = []
        self.lengths: List[int] = []
        for chunk in self.chunks:
            tokens = tokenize(chunk.title + "\n" + chunk.text)
            vec = Counter(tokens)
            self.vecs.append(vec)
            self.lengths.append(max(1, sum(vec.values())))
            for term in vec:
                self.df[term] += 1
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0

    # ---------- 打分 ----------
    def _bm25(self, query_terms: Iterable[str], index: int, k1=1.5, b=0.75) -> Tuple[float, List[str]]:
        vec, length = self.vecs[index], self.lengths[index]
        n_docs = max(1, len(self.chunks))
        score, matched = 0.0, []
        for term in set(query_terms):
            tf = vec.get(term, 0)
            if not tf:
                continue
            matched.append(term)
            idf = math.log(1 + (n_docs - self.df[term] + 0.5) / (self.df[term] + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / self.avg_len))
        return score, matched

    @staticmethod
    def _cosine(query_vec: Counter, doc_vec: Counter) -> float:
        common = set(query_vec) & set(doc_vec)
        if not common:
            return 0.0
        num = sum(query_vec[t] * doc_vec[t] for t in common)
        den = math.sqrt(sum(v * v for v in query_vec.values())) * math.sqrt(sum(v * v for v in doc_vec.values()))
        return num / den if den else 0.0

    def search(self, query: str, top_k: int = 3, min_score: float = 0.08) -> Dict:
        """检索 Top-k。返回 {ok, hits, reason, query_terms}；无相关内容时 ok=False（资料不足）。"""
        query_terms = tokenize(query)
        if not query_terms or not self.chunks:
            return {"ok": False, "hits": [], "query_terms": query_terms,
                    "reason": "问题里没有可用于检索的关键词"}
        query_vec = Counter(query_terms)

        rows = []
        for index, chunk in enumerate(self.chunks):
            bm25, matched = self._bm25(query_terms, index)
            cos = self._cosine(query_vec, self.vecs[index])
            if not matched and cos == 0:
                continue
            title_boost = 0.15 if any(t in chunk.title.lower() for t in set(query_terms)) else 0.0
            rows.append({"index": index, "bm25": bm25, "cosine": cos,
                         "matched": sorted(matched, key=len, reverse=True)[:6],
                         "title_boost": title_boost, "raw": bm25 + cos})
        if not rows:
            return {"ok": False, "hits": [], "query_terms": query_terms,
                    "reason": "知识库里没有任何片段与问题匹配（资料不足）"}

        max_bm25 = max(r["bm25"] for r in rows) or 1.0
        max_cos = max(r["cosine"] for r in rows) or 1.0
        for r in rows:
            r["score"] = round(0.6 * (r["bm25"] / max_bm25) + 0.4 * (r["cosine"] / max_cos)
                               + r["title_boost"], 4)
        rows.sort(key=lambda r: r["score"], reverse=True)
        top = rows[:top_k]
        if top[0]["score"] < min_score:
            return {"ok": False, "hits": [], "query_terms": query_terms,
                    "reason": "最高相关度 %.3f 低于阈值 %.2f，按“资料不足”处理" % (top[0]["score"], min_score)}

        hits = []
        for rank, r in enumerate(top, start=1):
            chunk = self.chunks[r["index"]]
            hits.append({
                "rank": rank,
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "section": chunk.section,
                "source_file": chunk.source_file,
                "source": chunk.source,
                "score": r["score"],
                "bm25": round(r["bm25"], 3),
                "cosine": round(r["cosine"], 3),
                "matched_terms": r["matched"],
                "chars": chunk.chars,
                "text": chunk.text,
            })
        return {"ok": True, "hits": hits, "query_terms": query_terms[:20],
                "reason": "混合打分 = 0.6×BM25(归一) + 0.4×词频余弦 + 标题命中加权"}


def search(query: str, top_k: int = 3, kb_dir=None) -> Dict:
    """便捷函数：一次性检索（每次重建索引，片段只有 53 条，开销可忽略）。"""
    return Retriever(kb_dir=kb_dir or "knowledge").search(query, top_k=top_k)
