#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视觉 API 最小调用冒烟测试（实验1 §2.5）

功能：
  1. 从 .env 读取密钥（不会打印密钥）
  2. 载入一张图片（命令行指定；未指定时自动截屏，截屏不可用则生成一张可核验的测试图）
  3. 调用具备视觉能力的模型，要求其描述图片内容
  4. 打印：模型名 / 请求类型 / 返回摘要 / 时延 / token 用量 / 按单价折算的费用
  5. 将本次调用记录为 JSON，存到 runs/ 目录（该目录已被 .gitignore 忽略）

用法：
  python scripts/api_smoke_test.py                  # 自动准备图片
  python scripts/api_smoke_test.py shot.png         # 使用指定图片
  python scripts/api_smoke_test.py shot.png "描述这张图"

只依赖 Python 标准库，无需安装任何第三方包。
"""

import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# ----------------------------------------------------------------------
# 计费单价（元 / 百万 token）。来源：官方公告，如价格调整请同步修改。
# ----------------------------------------------------------------------
PRICE = {
    "input_cached": {"offpeak": 0.02, "peak": 0.04},
    "input_miss":   {"offpeak": 1.0,  "peak": 2.0},
    "output":       {"offpeak": 4.0,  "peak": 8.0},
}

# 空闲时段定义（北京时间）。DeepSeek 的优惠时段为 00:30–08:30，请以官方最新公告为准。
OFFPEAK_START = (0, 30)
OFFPEAK_END = (8, 30)

MODEL = os.environ.get("MODEL_NAME", "deepseek-flash")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PROMPT = (
    "请描述这张图片的内容。如果你能看到文字或数字，请把文字和数字原样读出来。"
    "只描述你确实看到的内容，看不清的部分请明确说明看不清，不要猜测。"
)


def load_dotenv(path):
    """极简 .env 解析器（不依赖 python-dotenv）。"""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def is_offpeak(now=None):
    now = now or datetime.now()
    cur = (now.hour, now.minute)
    return OFFPEAK_START <= cur < OFFPEAK_END


def make_test_image(path):
    """生成一张内容已知的测试图，便于人工核验模型读数是否正确。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    W, H = 640, 360
    img = Image.new("RGB", (W, H), (24, 26, 32))
    d = ImageDraw.Draw(img)
    # 模拟一个简化的卡牌战斗界面，便于核验读数能力
    d.rectangle([16, 16, W - 16, 60], outline=(120, 130, 160), width=2)
    d.text((28, 30), "HP 68 / 80      ENERGY 3 / 3      FLOOR 7", fill=(230, 235, 245))
    labels = [("STRIKE", "6"), ("DEFEND", "5"), ("BASH", "8")]
    for i, (name, val) in enumerate(labels):
        x0 = 30 + i * 196
        d.rectangle([x0, 120, x0 + 170, 300], outline=(200, 170, 90), width=2)
        d.text((x0 + 14, 140), name, fill=(240, 220, 160))
        d.text((x0 + 14, 200), "dmg " + val, fill=(220, 225, 235))
    d.text((28, 318), "SYNTHETIC TEST FRAME - ground truth known", fill=(120, 200, 140))
    img.save(path, "PNG")
    return path


def capture_screen(path):
    """尝试截屏；不可用时返回 None。"""
    try:
        import mss
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            from PIL import Image
            Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(path, "PNG")
        return path
    except Exception:
        pass
    try:
        import pyautogui
        pyautogui.screenshot(path)
        return path
    except Exception:
        return None


def to_data_uri(path, max_width=1280):
    """读取图片并转为 data URI；过大时按宽度缩放以控制 token 消耗。"""
    from PIL import Image
    img = Image.open(path).convert("RGB")
    if img.width > max_width:
        h = int(img.height * max_width / img.width)
        img = img.resize((max_width, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    raw = buf.getvalue()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii"), img.size, len(raw)


def call_api(base_url, api_key, model, prompt, data_uri, timeout=120):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }],
        "max_tokens": 400,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    return body, (time.perf_counter() - t0) * 1000.0


def compute_cost(usage, offpeak):
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


def main():
    env = load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    api_key = os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY", "")
    base_url = (os.environ.get("DEEPSEEK_BASE_URL")
                or env.get("DEEPSEEK_BASE_URL")
                or "https://api.deepseek.com")

    if not api_key or api_key.startswith("your_"):
        print("[错误] 未找到有效的 DEEPSEEK_API_KEY。")
        print("       请在项目根目录的 .env 中填写，例如：")
        print("       DEEPSEEK_API_KEY=sk-xxxxxxxx")
        return 2

    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    prompt = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROMPT

    if img_path is None:
        img_path = os.path.join(PROJECT_ROOT, "runs", "smoke_input.png")
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        img_path = capture_screen(img_path) or make_test_image(img_path)
        if img_path is None:
            print("[错误] 无法截屏，也未能生成测试图片（缺少 Pillow）。")
            return 2
        print(f"[信息] 自动准备图片：{img_path}")

    if not os.path.exists(img_path):
        print(f"[错误] 图片不存在：{img_path}")
        return 2

    data_uri, size, raw_bytes = to_data_uri(img_path)
    offpeak = is_offpeak()

    print("=" * 68)
    print("视觉 API 冒烟测试")
    print("=" * 68)
    print(f"  请求时间      : {datetime.now():%Y-%m-%d %H:%M:%S}  ({'空闲时段' if offpeak else '高峰时段'})")
    print(f"  模型调用名    : {MODEL}")
    print(f"  接口地址      : {base_url}/chat/completions")
    print(f"  请求类型      : 多模态 chat completion（文本 + 图片）")
    print(f"  输入图片      : {os.path.basename(img_path)}  {size[0]}x{size[1]}  {raw_bytes/1024:.1f} KB")
    print(f"  密钥来源      : .env / 环境变量（长度 {len(api_key)}，不显示内容）")
    print("-" * 68)

    try:
        body, elapsed_ms = call_api(base_url, api_key, MODEL, prompt, data_uri)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        print(f"[失败] HTTP {e.code}: {e.reason}")
        print(detail)
        return 1
    except Exception as e:
        print(f"[失败] {type(e).__name__}: {e}")
        return 1

    try:
        text = body["choices"][0]["message"]["content"]
    except Exception:
        text = json.dumps(body, ensure_ascii=False)[:800]

    usage = body.get("usage") or {}
    cost = compute_cost(usage, offpeak)

    print("【模型返回】")
    print(text.strip())
    print("-" * 68)
    print("【耗时与用量】")
    print(f"  端到端时延    : {elapsed_ms:.0f} ms")
    print(f"  返回模型      : {body.get('model', '(未提供)')}")
    print(f"  输入 token    : {usage.get('prompt_tokens', '(未提供)')}"
          f"   其中缓存命中 {cost['input_cached_tokens']} / 未命中 {cost['input_miss_tokens']}")
    print(f"  输出 token    : {cost['output_tokens']}")
    print(f"  总 token      : {usage.get('total_tokens', '(未提供)')}")
    print("-" * 68)
    print("【费用折算】（单价：元/百万 token）")
    print(f"  输入（缓存命中）: {cost['input_cached_tokens']:>7} × {PRICE['input_cached'][cost['tier']]:>5} = {cost['cost_input_cached_yuan']:.8f} 元")
    print(f"  输入（未命中）  : {cost['input_miss_tokens']:>7} × {PRICE['input_miss'][cost['tier']]:>5} = {cost['cost_input_miss_yuan']:.8f} 元")
    print(f"  输出            : {cost['output_tokens']:>7} × {PRICE['output'][cost['tier']]:>5} = {cost['cost_output_yuan']:.8f} 元")
    print(f"  本次合计        : {cost['cost_total_yuan']:.6f} 元")
    print("=" * 68)

    runs_dir = os.path.join(PROJECT_ROOT, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_requested": MODEL,
        "model_returned": body.get("model"),
        "endpoint": base_url + "/chat/completions",
        "request_type": "multimodal chat completion (text + image)",
        "image": {"file": os.path.basename(img_path), "width": size[0], "height": size[1], "bytes": raw_bytes},
        "prompt": prompt,
        "response_text": text,
        "latency_ms": round(elapsed_ms, 1),
        "usage": usage,
        "cost": cost,
    }
    out = os.path.join(runs_dir, f"smoke_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"记录已保存：{out}")
    print("（runs/ 已被 .gitignore 忽略，不会进入版本库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
