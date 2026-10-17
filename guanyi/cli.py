# -*- coding: utf-8 -*-
"""命令行入口（实验3 设计的“自动化接口”在实验4 中的形态）。

界面层与命令行**调用同一套应用层服务**，因此“正常 / 空数据 / 错误输入”三种情况
都可以在这里用 JSON 观察，也便于留证据。

退出码：`0` 成功；`2` 业务错误（`GuanyiError`，带中文提示）；`3` 程序内部错误。

用法示例：

    python -m guanyi.cli start --run-id run-0002            # 新建空对局（空数据场景）
    python -m guanyi.cli suggest --hand 防御,打击 --hp 42 \
        --enemy-hp 23 --enemy-intent 11                     # 只调规则基线（非 AI 决策）
    python -m guanyi.cli record --run run-0001 --turn 4 \
        --state "HP 31/80，敌人 HP 15" --hand 打击,打击 --hp 31 --enemy-hp 15 \
        --enemy-intent 8 --play "play_card:打击" --result enemy_hp_delta=-15
    python -m guanyi.cli report --run run-0001              # 生成复盘报告
"""

import argparse
import json
import sys

from .ai import prompts
from .app.service import SessionService
from .core.errors import GuanyiError, ValidationError, zh_message
from .data.sample import reset, seed_empty_run, seed_sample_run
from .data.store import JsonlStore


def _print(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def parse_action(text):
    """把 `play_card:防御` 解析成动作 dict；`end_turn` 表示结束回合。"""
    if not text:
        return None
    if ":" in text:
        kind, card = text.split(":", 1)
        return {"action_type": kind.strip(), "card_name": card.strip()}
    return {"action_type": text.strip()}


def parse_pairs(items):
    """把 `key=value` 列表解析成 dict（值尽量转成数字）。"""
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        for cast in (int, float):
            try:
                value = cast(value)
                break
            except ValueError:
                continue
        out[key.strip()] = value
    return out


def parse_state(args):
    """从命令行参数拼出结构化局面；都没给时返回 None。"""
    if all(getattr(args, name, None) is None for name in ("hp", "max_hp", "energy", "enemy_hp",
                                                          "enemy_intent", "hand")):
        return None
    hand = [x.strip() for x in (args.hand or "").replace("，", ",").split(",") if x.strip()]
    return {
        "hp": args.hp or 0,
        "max_hp": args.max_hp or 80,
        "energy": args.energy if args.energy is not None else 3,
        "enemy_hp": args.enemy_hp or 0,
        "enemy_intent": args.enemy_intent or 0,
        "hand": hand,
    }


# ---------------- 子命令 ----------------
def cmd_seed(args, service):
    run = seed_sample_run(service.store, run_id=args.run_id, outcome=args.outcome)
    return _print({"ok": True, "run": run.to_dict(), "decisions": len(service.get_decisions(run.run_id))})


def cmd_start(args, service):
    run = service.start_run(run_id=args.run_id, seed=args.seed)
    return _print({"ok": True, "run": run.to_dict(), "decisions": 0,
                   "log_path": str(service.store.log_file(run.run_id))})


def cmd_clear(args, service):
    return _print({"ok": True, "removed_runs": reset(service.store)})


def cmd_list(args, service):
    runs = service.list_runs()
    return _print({"count": len(runs), "runs": runs})


def cmd_show(args, service):
    run = service.get_run(args.run)
    points, problems = service.scan_decisions(args.run)
    return _print({
        "ok": True,
        "run": run.to_dict(),
        "decision_count": len(points),
        "problems": problems,
        "decisions": [p.to_dict() for p in points],
    })


def cmd_suggest(args, service):
    state = parse_state(args)
    legal = args.legal or ["play_card:防御", "play_card:打击", "end_turn"]
    result = service.suggest(state or {}, legal)
    return _print({"ok": True, "source": "rule_baseline", "state": state,
                   "legal_actions": legal, "suggestion": result})


def cmd_record(args, service):
    if args.suggest is None and args.hand is None:
        raise ValidationError("省略 --suggest 时需要用 --hand 等参数给出局面，才能让规则基线决策",
                              field="suggest")
    point = service.record_decision(
        run_id=args.run,
        turn=args.turn,
        state_summary=args.state,
        suggestion_action=parse_action(args.suggest) if args.suggest else None,
        player_action=parse_action(args.play),
        state=parse_state(args),
        result=parse_pairs(args.result),
        suggestion_reason=args.reason or "",
        confidence=args.confidence,
        legal_actions=args.legal or [],
    )
    return _print({"ok": True, "decision": point.to_dict(),
                   "is_consistent": point.is_consistent,
                   "guardrail": point.guardrail})


def cmd_finish(args, service):
    run = service.finish_run(args.run, args.outcome)
    return _print({"ok": True, "run": run.to_dict()})


def cmd_report(args, service):
    result = service.build_report(args.run)
    return _print({"ok": True, **result})


# ---------------- 实验5：知识问答（RAG）----------------
def _qa_service(args):
    from .app.qa_service import QaService
    return QaService(kb_dir=args.kb, out_dir=args.qa_dir)


def cmd_kb(args, service):
    """只做检索预览（不调用模型），用于检查检索质量与排序依据。"""
    qa = _qa_service(args)
    stats = qa.kb_stats()
    if not args.q:
        return _print({"ok": True, "knowledge_base": stats})
    result = qa.retriever.search(args.q, top_k=args.top_k)
    hits = [{"rank": h["rank"], "title": h["title"], "chunk_id": h["chunk_id"],
             "score": h["score"], "bm25": h["bm25"], "cosine": h["cosine"],
             "matched_terms": h["matched_terms"], "chars": h["chars"], "source": h["source"],
             "text": h["text"] if args.show_text else h["text"][:120] + "…"} for h in result["hits"]]
    return _print({"ok": result["ok"], "query": args.q, "top_k": args.top_k,
                   "reason": result["reason"], "query_terms": result.get("query_terms"),
                   "hits": hits})


def cmd_ask(args, service):
    """问答入口：`--no-rag` 走直接模型组，默认走 RAG 组。"""
    qa = _qa_service(args)
    result = qa.ask(args.q, use_rag=not args.no_rag, top_k=args.top_k,
                    prompt_version=args.prompt_version)
    return _print({
        "ok": result["ok"],
        "question": args.q,
        "prompt_version": result.get("prompt_version"),
        "insufficient": result.get("insufficient", False),
        "answer": result.get("answer"),
        "sources": [{"source_id": "[来源%d]" % h["rank"], "title": h["title"],
                     "score": h["score"], "chunk_id": h["chunk_id"]} for h in result.get("hits", [])],
        "usage": result.get("usage"), "cost": result.get("cost"),
        "latency_ms": result.get("latency_ms"), "model": result.get("model"),
        "error": result.get("error") or None,
        "saved_path": result.get("saved_path"),
    })


def cmd_context(args, service):
    """展示“实际发送给模型的完整输入”（讲义 2.2 要求留证）。不调用模型，不产生费用。"""
    qa = _qa_service(args)
    hits, reason = [], "未使用检索（--no-rag）"
    if not args.no_rag:
        retrieval = qa.retriever.search(args.q, top_k=args.top_k)
        hits, reason = retrieval.get("hits", []), retrieval.get("reason", "")
    version = args.prompt_version or ("v2" if not args.no_rag else "direct")
    messages = prompts.build_messages(args.q, hits, version=version)
    return _print({"ok": True, "question": args.q, "prompt_version": version,
                   "retrieval": reason, "hit_count": len(hits),
                   "message_count": len(messages),
                   "total_chars": sum(len(m["content"]) for m in messages),
                   "messages": messages})


def _add_state_args(parser):
    parser.add_argument("--hp", type=int, help="玩家当前血量")
    parser.add_argument("--max-hp", type=int, help="玩家最大血量（默认 80）")
    parser.add_argument("--energy", type=int, help="本回合剩余能量（默认 3）")
    parser.add_argument("--enemy-hp", type=int, help="敌人剩余血量")
    parser.add_argument("--enemy-intent", type=int, help="敌人意图伤害")
    parser.add_argument("--hand", help="手牌，逗号分隔，如 防御,打击")


def build_parser():
    parser = argparse.ArgumentParser(prog="guanyi", description="观弈：离散决策游戏复盘助手（实验4 非AI 闭环）")
    parser.add_argument("--root", default="data/runs", help="运行记录目录（默认 data/runs/）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed", help="写入一局样例数据（3 个决策点）")
    p.add_argument("--run-id", default="run-0001")
    p.add_argument("--outcome", default="胜")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("start", help="新建一局空对局")
    p.add_argument("--run-id", default=None)
    p.add_argument("--seed", default="")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("clear", help="清空全部运行记录")
    p.set_defaults(func=cmd_clear)

    p = sub.add_parser("list", help="列出所有对局")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="查看一局的决策点")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("suggest", help="只调用规则基线（非 AI 决策）给出建议")
    _add_state_args(p)
    p.add_argument("--legal", action="append", help="合法动作集，可重复")
    p.set_defaults(func=cmd_suggest)

    p = sub.add_parser("record", help="录入一个决策点")
    p.add_argument("--run", required=True)
    p.add_argument("--turn", type=int, required=True)
    p.add_argument("--state", required=True, help="局面摘要（人类可读）")
    p.add_argument("--suggest", help="建议动作，如 play_card:防御；省略则用规则基线")
    p.add_argument("--play", required=True, help="玩家实际操作，如 play_card:打击")
    p.add_argument("--result", action="append", help="结果，如 hp_delta=-11，可重复")
    p.add_argument("--reason", default="", help="建议依据")
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--legal", action="append", help="合法动作集，可重复")
    _add_state_args(p)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("finish", help="结束一局并记录胜负")
    p.add_argument("--run", required=True)
    p.add_argument("--outcome", required=True, choices=["胜", "负", "中止"])
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("report", help="生成逐回合复盘报告")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_report)

    # ---- 实验5：知识问答（RAG）----
    for name, func, helptext in (("kb", cmd_kb, "检索预览：查看 Top-k 片段与排序依据"),
                                 ("ask", cmd_ask, "知识问答：默认用 RAG，--no-rag 为直接模型组"),
                                 ("context", cmd_context, "展示实际发送给模型的完整输入")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--q", default="", help="问题")
        p.add_argument("--top-k", type=int, default=3, help="检索片段数（默认 3）")
        p.add_argument("--prompt-version", default=None, choices=["v1", "v2", "direct"])
        p.add_argument("--no-rag", action="store_true", help="不给资料，直接问模型")
        p.add_argument("--kb", default="knowledge", help="知识库目录（默认 knowledge/）")
        p.add_argument("--qa-dir", default="data/qa", help="问答记录目录（默认 data/qa/）")
        p.add_argument("--show-text", action="store_true", help="（kb）输出完整片段正文")
        p.set_defaults(func=func)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    service = SessionService(JsonlStore(args.root))
    try:
        return args.func(args, service)
    except GuanyiError as exc:
        service.logger(getattr(args, "run", None)).warning(
            "命令失败 code=%s message=%s details=%s", exc.code, exc.message, exc.details)
        _print({"ok": False, "error": exc.to_dict(), "zh": zh_message(exc.code)})
        return 2
    except Exception as exc:  # 兜底：不把栈丢给用户，但完整写进日志
        service.logger(getattr(args, "run", None)).exception("未预期的异常：%s", exc)
        _print({"ok": False, "error": {"code": "internal_error", "message": "程序内部错误：%s" % exc}})
        return 3


if __name__ == "__main__":
    sys.exit(main())
