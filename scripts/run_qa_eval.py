# -*- coding: utf-8 -*-
"""实验5 §2.5：固定问题集的两组对照实验（直接模型组 vs RAG 组）。

每组使用**相同的问题、模型、主要参数与基本输出格式**，各次测试使用独立上下文；
RAG 组额外提供检索资料与“依据资料回答、标注来源”的要求。

产出：
    docs/实验5-对比测试.md     统一表格（问题 / 组别 / 回答 / 引用 / 耗时 / 用量 / 费用 / 自动检查）
    data/qa/eval_<时间戳>.json 原始记录（每次调用一行，便于复核）

用法：
    .venv\\Scripts\\python.exe scripts\\run_qa_eval.py            # 跑全部 7 个问题 × 2 组
    .venv\\Scripts\\python.exe scripts\\run_qa_eval.py --only Q1 Q5  # 只跑指定问题
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guanyi.app.qa_service import QaService          # noqa: E402

#: 固定问题集：覆盖单片段 / 多片段综合 / 资料无答案 / 缺信息 / 超出范围五类
QUESTIONS = [
    {"id": "Q1", "type": "单片段", "q": "痛击升级之后有什么变化？",
     "expect": ["10", "3", "2"], "note": "知识库【痛击】BASH 一段即可回答（伤害 8→10、易伤 2→3、费用 2）"},
    {"id": "Q2", "type": "单片段", "q": "防御这张牌能获得多少格挡？",
     "expect": ["5", "8"], "note": "知识库【防御】DEFEND_IRONCLAD（基础 5、升级 8）"},
    {"id": "Q3", "type": "多片段综合", "q": "易伤和虚弱有什么区别？",
     "expect": ["易伤", "50", "虚弱", "25"], "note": "需要【易伤】+【虚弱】两段综合"},
    {"id": "Q4", "type": "多片段综合", "q": "打劫掠者刺客的时候，先防御还是先打输出？",
     "expect": ["意图", "10"], "note": "需要【劫掠者刺客】意图 + 防御/伤害类知识"},
    {"id": "Q5", "type": "资料无答案", "q": "第三章的 Boss 应该怎么打？",
     "expect": [], "note": "知识库只收第一章，正确行为是提示资料不足、不编造"},
    {"id": "Q6", "type": "缺信息", "q": "我该升级哪张牌？",
     "expect": [], "note": "缺少角色/卡组信息，应追问补充或说明资料不足"},
    {"id": "Q7", "type": "超出范围", "q": "这游戏怎么联机和好友一起玩？",
     "expect": [], "note": "与游戏机制无关，应提示无法处理"},
]

#: 是否把回答判定为“明确拒答/资料不足”的关键词
REFUSE_MARKERS = ["资料不足", "无法回答", "超出", "没有相关", "无法处理", "不知道", "缺乏"]
#: 引用编号正则
CITE_RE = re.compile(r"\[来源(\d+)\]")


def auto_check(answer: str, expect, hits) -> dict:
    """自动检查：关键事实是否出现、是否明确拒答、引用编号是否有效、引用是否可对应。"""
    text = answer or ""
    missing = [word for word in expect if word.replace(" ", "") not in text.replace(" ", "")]
    cited = [int(n) for n in CITE_RE.findall(text)]
    cited_valid = all(1 <= n <= max(1, len(hits)) for n in cited) if cited else False
    cited_titles = []
    for n in sorted(set(cited)):
        if 1 <= n <= len(hits):
            cited_titles.append(hits[n - 1]["title"])
    return {
        "missing_facts": missing,
        "facts_ok": (not missing) if expect else None,
        "refused": any(m in text for m in REFUSE_MARKERS),
        "citations": cited,
        "citations_valid": cited_valid,
        "cited_titles": cited_titles,
    }


def judge(row) -> str:
    """按“能否用知识库核对”给出初判（最终结论由人工复核）。"""
    check = row["check"]
    if not row["expect"]:
        return "✅ 正确拒答" if check["refused"] else "⚠ 未拒答（可能编造）"
    if check["facts_ok"]:
        if row["group"] == "RAG" and not check["citations_valid"]:
            return "⚠ 要点齐全但引用无效"
        return "✅ 正确"
    if check["refused"]:
        return "⚠ 要点缺失且拒答"
    return "❌ 要点缺失/答错"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="只跑指定问题 id，如 Q1 Q5")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--out", default="data/qa/实验5-对比测试.md",
                        help="Markdown 输出路径（默认写到 data/qa/；要用 docs/ 请自行指定）")
    args = parser.parse_args()

    questions = [q for q in QUESTIONS if not args.only or q["id"] in args.only]
    qa = QaService(kb_dir="knowledge", out_dir="data/qa")
    rows, t0 = [], datetime.now()

    for item in questions:
        for group in ("RAG", "直接"):
            use_rag = group == "RAG"
            result = qa.ask(item["q"], use_rag=use_rag, top_k=args.top_k,
                            prompt_version="v2" if use_rag else "direct")
            hits = result.get("hits", [])
            row = {
                "id": item["id"], "type": item["type"], "question": item["q"], "group": group,
                "prompt_version": result.get("prompt_version"),
                "answer": result.get("answer", ""),
                "error": result.get("error") or None,
                "expect": item["expect"], "note": item["note"],
                "hits": [{"rank": h["rank"], "title": h["title"], "score": h["score"]} for h in hits],
                "latency_ms": result.get("latency_ms"),
                "usage": result.get("usage"), "cost": result.get("cost"),
                "insufficient": result.get("insufficient", False),
            }
            row["check"] = auto_check(row["answer"], item["expect"], hits)
            row["judgement"] = judge(row)
            rows.append(row)
            print("%-3s %-4s %-6s %5sms %s" % (item["id"], group, row["judgement"],
                                               int(row["latency_ms"] or 0),
                                               (row["answer"] or row["error"] or "")[:60].replace("\n", " ")))

    # ---------- 汇总 ----------
    def total(field):
        return sum((r["cost"] or {}).get(field, 0) or 0 for r in rows)

    summary = {
        "timestamp": t0.astimezone().isoformat(timespec="seconds"),
        "questions": len(questions), "calls": len(rows),
        "cost_total_yuan": round(total("cost_total_yuan"), 6),
        "latency_avg_ms": round(sum(r["latency_ms"] or 0 for r in rows) / max(1, len(rows)), 1),
        "rag_correct": sum(1 for r in rows if r["group"] == "RAG" and r["judgement"].startswith("✅")),
        "direct_correct": sum(1 for r in rows if r["group"] == "直接" and r["judgement"].startswith("✅")),
        "rag": sum(1 for r in rows if r["group"] == "RAG"),
        "direct": sum(1 for r in rows if r["group"] == "直接"),
    }

    os.makedirs("data/qa", exist_ok=True)
    raw_path = os.path.join("data/qa", "eval_%s.json" % t0.strftime("%Y%m%d_%H%M%S"))
    with open(raw_path, "w", encoding="utf-8") as fp:
        json.dump({"summary": summary, "rows": rows}, fp, ensure_ascii=False, indent=2)

    # ---------- 写 Markdown ----------
    lines = ["# 实验5 对比测试记录（自动生成）", "",
             "- 生成时间：%s" % summary["timestamp"],
             "- 问题数 %d，调用 %d 次（每组独立上下文），总费用约 %.4f 元，平均耗时 %.0f ms"
             % (summary["questions"], summary["calls"], summary["cost_total_yuan"], summary["latency_avg_ms"]),
             "- 两组使用相同问题、模型（deepseek-flash）、temperature 0.3、max_tokens 800；"
             "RAG 组额外给检索资料并要求标注 `[来源N]`（Prompt v2），直接模型组不给资料", "",
             "## 一、汇总", "",
             "| # | 类型 | 问题 | 组别 | 判定 | 耗时 ms | 输入/输出 tokens | 费用（元） | 引用 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        usage = r["usage"] or {}
        cost = (r["cost"] or {}).get("cost_total_yuan", 0)
        cites = "、".join("[来源%d]" % n for n in r["check"]["citations"]) or "—"
        lines.append("| %s | %s | %s | %s | %s | %s | %s/%s | %.6f | %s |" % (
            r["id"], r["type"], r["question"], r["group"], r["judgement"],
            int(r["latency_ms"] or 0), usage.get("prompt_tokens", "—"), usage.get("completion_tokens", "—"),
            cost, cites))
    lines += ["", "## 二、逐题回答", ""]
    for item in questions:
        lines += ["### %s（%s）%s" % (item["id"], item["type"], item["q"]), "",
                  "- 判断规则：%s　期望要点：%s" % (item["note"], "、".join(item["expect"]) or "应拒答/追问")]
        for r in [x for x in rows if x["id"] == item["id"]]:
            lines.append("- **%s 组**：%s" % (r["group"], (r["answer"] or "（失败：%s）" % r["error"]).replace("\n", " ")))
            if r["group"] == "RAG":
                lines.append("  - 检索 Top-k：%s" % "；".join(
                    "[%d] %s（%.2f）" % (h["rank"], h["title"], h["score"]) for h in r["hits"]))
                lines.append("  - 自动检查：要点缺失 %s；引用 %s；引用片段 %s" % (
                    r["check"]["missing_facts"] or "无", r["check"]["citations"] or "无",
                    "、".join(r["check"]["cited_titles"]) or "—"))
        lines.append("")
    lines += ["## 三、结论（人工复核）", "",
              "- 自动抽取的正确/错误判定已列入上表；人工复核要点：**正确性、要点遗漏、无依据内容、引用可靠性**。",
              "- 判断依据：知识库中的卡牌/敌人/状态条目（数值可逐条核对）。",
              "- 说明：自动判定只做主检查（关键数字是否出现、引用编号是否有效），最终结论由人工填写。"]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")

    print("\n汇总：RAG 组正确 %d/%d，直接组正确 %d/%d，总费用 %.4f 元"
          % (summary["rag_correct"], summary["rag"], summary["direct_correct"],
             summary["direct"], summary["cost_total_yuan"]))
    print("已写入：%s\n原始记录：%s" % (args.out, raw_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
