# -*- coding: utf-8 -*-
"""云端模型调用（实验5 §2.1）：文本 chat completion，只用标准库。

- 密钥与地址从项目根目录 `.env` 读取（`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`），**不打印密钥**；
- 参数：`model`、`temperature`、`max_tokens`、`timeout`、`retries`（网络类错误才重试，带退避）；
- 失败不抛异常，统一返回 `LlmResult(ok=False, error={code, message, ...})`，便于界面与命令行提示；
- 返回用量与按单价折算的费用（单价沿用实验1 的 `.env` 配置，便于跨实验对比）。

价格（元 / 百万 token，来自官方公告，如调整请同步 `.env`）：
    输入缓存命中 0.02–0.04、输入未命中 1–2、输出 4–8（空闲时段为高峰的一半）
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_MODEL = os.environ.get("MODEL_NAME", "deepseek-flash")
DEFAULT_BASE_URL = "https://api.deepseek.com"

PRICE = {
    "input_cached": {"offpeak": 0.02, "peak": 0.04},
    "input_miss": {"offpeak": 1.0, "peak": 2.0},
    "output": {"offpeak": 4.0, "peak": 8.0},
}
#: 高峰时段（北京时间，周一至周五 09:00–12:00、14:00–18:00）
PEAK_WINDOWS = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))


def load_dotenv(path: Optional[str] = None) -> Dict[str, str]:
    """极简 .env 解析器（不依赖 python-dotenv）。"""
    env: Dict[str, str] = {}
    path = path or os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def is_offpeak(now: Optional[datetime] = None) -> bool:
    """当前是否适用空闲价。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return True
    cur = now.hour * 60 + now.minute
    return not any(start <= cur < end for start, end in PEAK_WINDOWS)


def compute_cost(usage: Dict, offpeak: bool) -> Dict:
    """按单价折算费用（与实验1 的脚本同一套口径）。"""
    tier = "offpeak" if offpeak else "peak"
    hit = usage.get("prompt_cache_hit_tokens") or 0
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:
        miss = max((usage.get("prompt_tokens") or 0) - hit, 0)
    out = usage.get("completion_tokens") or 0
    c_hit = hit / 1e6 * PRICE["input_cached"][tier]
    c_miss = miss / 1e6 * PRICE["input_miss"][tier]
    c_out = out / 1e6 * PRICE["output"][tier]
    return {
        "tier": tier,
        "input_cached_tokens": hit,
        "input_miss_tokens": miss,
        "output_tokens": out,
        "cost_input_cached_yuan": round(c_hit, 8),
        "cost_input_miss_yuan": round(c_miss, 8),
        "cost_output_yuan": round(c_out, 8),
        "cost_total_yuan": round(c_hit + c_miss + c_out, 8),
    }


@dataclass
class LlmResult:
    """一次调用的结果（成功或失败都用同一个结构，便于记录与展示）。"""

    ok: bool
    text: str = ""
    error: Dict = field(default_factory=dict)
    usage: Dict = field(default_factory=dict)
    cost: Dict = field(default_factory=dict)
    latency_ms: float = 0.0
    model: str = ""
    finish_reason: str = ""
    attempts: int = 0

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok, "text": self.text, "error": self.error, "usage": self.usage,
            "cost": self.cost, "latency_ms": self.latency_ms, "model": self.model,
            "finish_reason": self.finish_reason, "attempts": self.attempts,
        }


class LlmClient:
    """文本模型客户端（OpenAI 兼容的 chat/completions）。"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, timeout: int = 60, retries: int = 2,
                 temperature: float = 0.3, max_tokens: int = 800):
        env = load_dotenv()
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL")
                         or env.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        self.retries = retries
        self.temperature = temperature
        self.max_tokens = max_tokens

    # ---------- 对外接口 ----------
    def chat(self, messages: List[Dict], **overrides) -> LlmResult:
        """发一次 chat 请求；网络类错误按 `retries` 次退避重试，其余错误直接返回。"""
        if not self.api_key or self.api_key.startswith("your_"):
            return LlmResult(ok=False, error={
                "code": "missing_api_key",
                "message": "未找到有效的 DEEPSEEK_API_KEY，请在项目根目录 .env 中填写"})

        payload = {
            "model": overrides.get("model", self.model),
            "messages": messages,
            "temperature": overrides.get("temperature", self.temperature),
            "max_tokens": overrides.get("max_tokens", self.max_tokens),
            "stream": False,
        }
        url = self.base_url + "/chat/completions"
        timeout = overrides.get("timeout", self.timeout)
        attempts = 0
        last_error: Dict = {}
        for attempt in range(self.retries + 1):
            attempts = attempt + 1
            try:
                body, elapsed_ms = self._post(url, payload, timeout)
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:300]
                except Exception:                       # noqa: BLE001
                    pass
                last_error = {"code": "http_%s" % exc.code,
                              "message": "接口返回 HTTP %s %s" % (exc.code, exc.reason),
                              "detail": detail}
                if exc.code in (400, 401, 402, 403, 404, 422):     # 参数/鉴权类错误，重试无意义
                    break
            except urllib.error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                    last_error = {"code": "timeout",
                                  "message": "调用超时（%.1f 秒）：%s" % (timeout, reason)}
                else:
                    last_error = {"code": "network_error", "message": "网络不可达：%s" % reason}
            except TimeoutError:
                last_error = {"code": "timeout", "message": "调用超时（%.0f 秒）" % timeout}
            except Exception as exc:                    # noqa: BLE001
                last_error = {"code": "unexpected", "message": "%s: %s" % (type(exc).__name__, exc)}
            else:
                return self._parse(body, elapsed_ms, attempts)
            if attempt < self.retries:
                time.sleep(1.5 * (attempt + 1))          # 退避后重试
        return LlmResult(ok=False, error=last_error, attempts=attempts,
                         model=payload["model"])

    # ---------- 内部 ----------
    def _post(self, url: str, payload: Dict, timeout: float):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key,
                     "Accept": "application/json"},
            method="POST")
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        return body, (time.perf_counter() - started) * 1000.0

    def _parse(self, body: Dict, elapsed_ms: float, attempts: int) -> LlmResult:
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except Exception:                               # noqa: BLE001
            text = ""
        finish = (body.get("choices") or [{}])[0].get("finish_reason") or ""
        usage = body.get("usage") or {}
        result = LlmResult(
            ok=True, text=text.strip(), usage=usage, cost=compute_cost(usage, is_offpeak()),
            latency_ms=round(elapsed_ms, 1), model=body.get("model", self.model),
            finish_reason=finish, attempts=attempts)
        if not result.text:
            result.ok = False
            result.error = {"code": "empty_response",
                            "message": "模型返回为空（可能是 max_tokens 被推理占满或被截断）"}
        return result
