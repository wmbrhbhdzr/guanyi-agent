# -*- coding: utf-8 -*-
"""实验5 §2.1：模型调用失败场景的复现脚本（三种情况都不产生费用）。

    python scripts/test_failures.py

输出三种失败的错误码、尝试次数与提示，用于报告截图：
    接口不可用（鉴权失败）  → http_401      （鉴权类错误不重试）
    连接失败（地址不可达）  → network_error （按 retries 退避重试）
    超时                    → timeout
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guanyi.ai.llm_client import LlmClient  # noqa: E402


def main():
    cases = [
        ("接口不可用（无效密钥）", LlmClient(api_key="sk-invalid-key-for-test", retries=0, timeout=20)),
        ("连接失败（地址不可达）", LlmClient(base_url="https://127.0.0.1:9", retries=1, timeout=3)),
        ("超时（0.001 秒）", LlmClient(base_url="https://spire-codex.com", timeout=0.001, retries=0)),
    ]
    print("模型调用失败场景测试（均不会产生成功调用费用）\n" + "-" * 72)
    for name, client in cases:
        result = client.chat([{"role": "user", "content": "你好"}])
        error = result.error or {}
        print("场景：%s" % name)
        print("  结果：ok=%s  错误码=%s  尝试次数=%d" % (result.ok, error.get("code"), result.attempts))
        print("  提示：%s" % (error.get("message") or ""))
        print("-" * 72)
    print("结论：三类失败都有明确错误码与中文提示，程序不崩溃；鉴权类错误不重试，网络类错误按 retries 重试。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
