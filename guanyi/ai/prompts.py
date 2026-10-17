# -*- coding: utf-8 -*-
"""Prompt 模板（实验5 §2.2）。

三套模板，用于讲义要求的“可重复使用的模板 + 至少一次修改 + 两组对照”：

- `DIRECT`  直接模型组：不给资料，只回答（对照组）
- `RAG_V1`  RAG 组第一版：给资料，要求“依据资料回答”
- `RAG_V2`  RAG 组第二版：**在 V1 的测试结果上修改**——强制「只依据资料」、
            统一 `[来源N]` 引用格式、资料不足时明确说“资料不足”、限制篇幅

任务与用户问题分开：任务要求写在 system 消息里，用户问题与检索资料放在 user 消息里，
便于复用与替换（讲义 2.2 明确要求区分）。
"""

SYSTEM_DIRECT = (
    "你是《杀戮尖塔 2》的游戏助手。请用简体中文回答玩家的问题，"
    "回答口语化、直接给结论，不超过 150 字。"
)

SYSTEM_RAG_V1 = (
    "你是《杀戮尖塔 2》的游戏助手。请用简体中文回答玩家的问题，"
    "可以结合下面的参考资料，回答不超过 200 字。"
)

SYSTEM_RAG_V2 = (
    "你是《杀戮尖塔 2》的游戏助手，只回答与《杀戮尖塔 2》游戏机制、卡牌、敌人、策略有关的问题。\n"
    "规则：\n"
    "1. 只能依据【参考资料】回答，不要使用资料之外的知识，也不要凭印象编造数值；\n"
    "2. 引用了哪条资料，就在那句话末尾标注编号，例如「造成 8 点伤害[来源1]」；\n"
    "3. 如果资料不足以回答，直接说「资料不足」，并说明还缺什么信息，不要猜；\n"
    "4. 如果问题与游戏无关，回答「这个问题超出我能回答的范围」；\n"
    "5. 用简体中文，先给结论再给一句依据，不超过 200 字。"
)

RAG_USER_TEMPLATE = (
    "【参考资料】\n{context}\n\n"
    "【玩家问题】{question}"
)


def build_context(hits):
    """把检索片段拼成带编号的参考资料。"""
    if not hits:
        return "（没有检索到相关资料）"
    blocks = []
    for rank, hit in enumerate(hits, start=1):
        blocks.append("[来源%d] %s（%s）\n%s" % (
            rank, hit["title"], hit.get("section", ""), hit["text"].strip()))
    return "\n\n".join(blocks)


def build_messages(question, hits=None, version="v2", history=None):
    """组装一次调用的完整 messages。

    version: `direct`（不给资料）/ `v1` / `v2`（RAG 两版）
    history: 多轮对话历史（[{"role": "user"/"assistant", "content": ...}]），按需加入。
    """
    version = (version or "v2").lower()
    if version == "direct":
        system = SYSTEM_DIRECT
        user = question
    else:
        system = SYSTEM_RAG_V1 if version == "v1" else SYSTEM_RAG_V2
        user = RAG_USER_TEMPLATE.format(context=build_context(hits), question=question)
    messages = [{"role": "system", "content": system}]
    for turn in (history or []):
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user})
    return messages


def template_text(version="v2"):
    """返回模板正文（供报告展示“实际发送的完整输入”）。"""
    version = (version or "v2").lower()
    if version == "direct":
        return SYSTEM_DIRECT
    return SYSTEM_RAG_V1 if version == "v1" else SYSTEM_RAG_V2
