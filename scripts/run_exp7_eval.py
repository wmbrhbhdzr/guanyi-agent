"""Run reconstructed baseline and current prototype on identical fixed images."""

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guanyi.agent.runtime import wait_call
from guanyi.ai.llm_client import LlmClient
from guanyi.app.vision_service import VisionService
from guanyi.vision import config
from guanyi.vision.images import ImageInputError, prepare_image
from guanyi.vision.schema import parse_observation, ObservationError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/exp7/results"


def baseline(path):
    started = time.monotonic()
    result = {"ok": False, "status": "failed", "observation": None, "error": None, "usage": {}, "cost": {}, "attempts": 0}
    try:
        frame = prepare_image(path)
    except ImageInputError as exc:
        result.update(error={"code": "invalid_image", "message": str(exc)}, elapsed_ms=(time.monotonic()-started)*1000)
        return result
    messages = [{"role": "system", "content": config.BASELINE_PROMPT}, {"role": "user", "content": [
        {"type": "text", "text": "请识别这张游戏截图，仅按约定JSON结构输出可见局面。"},
        {"type": "image_url", "image_url": {"url": frame.data_uri}}]}]
    client = LlmClient(model=config.MODEL)
    deadline = started + config.TIMEOUT_S
    try:
        llm = wait_call(lambda: client.chat(messages, max_tokens=config.BASELINE["max_tokens"], temperature=0,
                        timeout=config.TIMEOUT_S, deadline=deadline), deadline-time.monotonic())
        result.update(usage=llm.usage, cost=llm.cost, attempts=llm.attempts, model=llm.model,
                      finish_reason=llm.finish_reason, raw_response=llm.text)
        if not llm.ok:
            result["error"] = llm.error
        elif llm.finish_reason == "length":
            result["error"] = {"code": "output_limit"}
        else:
            result.update(ok=True, status="parsed", observation=parse_observation(llm.text))
    except TimeoutError:
        result.update(status="timeout", error={"code": "timeout"})
    except ObservationError as exc:
        result["error"] = {"code": "invalid_observation", "message": str(exc)}
    result["elapsed_ms"] = round((time.monotonic()-started)*1000, 1)
    return result


def get_field(value, path):
    try:
        for key in path.split("."):
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value, True
    except (KeyError, IndexError, TypeError, ValueError):
        return None, False


def score(case, result):
    if case.get("expected_error"):
        actual = (result.get("error") or {}).get("code")
        return [{"field": "error.code", "expected": case["expected_error"], "actual": actual, "passed": actual == case["expected_error"]}]
    checks = []
    for field, expected in case.get("expected", {}).items():
        actual, exists = get_field(result.get("observation"), field)
        checks.append({"field": field, "expected": expected, "actual": actual, "present": exists,
                       "passed": exists and actual == expected})
    for field, allowed in case.get("allowed", {}).items():
        actual, exists = get_field(result.get("observation"), field)
        checks.append({"field": field, "allowed": allowed, "actual": actual, "passed": exists and actual in allowed})
    if case.get("required_tooltip"):
        tips = (result.get("observation") or {}).get("tooltips", [])
        passed = any(t["title"] == case["required_tooltip"] and t["owner"] == "enemy" and t["owner_index"] == 0
                     and "9" in (t["text"] or "") for t in tips)
        checks.append({"field": "tooltip_association", "expected": "enemy[0]难以杀灭9", "passed": passed})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true", help="实际调用收费模型；无此参数仅汇总已有结果")
    parser.add_argument("--version", choices=["baseline", "revised", "both"], default="both")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/"evaluation/exp7/manifest.json").read_text(encoding="utf-8"))
    cases = [json.loads((ROOT/"evaluation/exp7"/p).read_text(encoding="utf-8")) for p in manifest["cases"]]
    versions = ["baseline", "revised"] if args.version == "both" else [args.version]
    rows = []
    service = VisionService(out_dir=ROOT/"data/vision")
    for version in versions:
        for case in cases:
            target = OUT / (version + "-" + case["id"] + ".json")
            if args.online and not target.exists():
                image = ROOT/"evaluation/exp7"/case["image"]
                assert hashlib.sha256(image.read_bytes()).hexdigest() == case["sha256"]
                print("RUN", version, case["id"], flush=True)
                # Only image pixels reach the model; all labels stay on this side.
                result = baseline(image) if version == "baseline" else service.recognize(image, game="auto")
                checks = score(case, result)
                record = {"version": version, "case_id": case["id"], "kind": case["kind"],
                          "scenario": case["scenario"], "timestamp": datetime.now().astimezone().isoformat(),
                          "result": result, "checks": checks,
                          "review": {"basis": "固定标签规则评分；真实图标签AI辅助目视核对，待用户确认", "user_confirmed": False}}
                target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                print("DONE", version, case["id"], sum(c["passed"] for c in checks), "/", len(checks), result.get("elapsed_ms"), flush=True)
            if target.exists():
                rows.append(json.loads(target.read_text(encoding="utf-8")))
    summaries = {}
    for version in versions:
        group = [r for r in rows if r["version"] == version]
        if not group:
            continue
        checks = [c for r in group for c in r["checks"]]
        times = [r["result"]["elapsed_ms"] for r in group]
        summaries[version] = {"cases": len(group), "case_pass": sum(all(c["passed"] for c in r["checks"]) for r in group),
            "field_pass": sum(c["passed"] for c in checks), "fields": len(checks),
            "median_ms": statistics.median(times), "max_ms": max(times),
            "estimated_yuan": round(sum((r["result"].get("cost") or {}).get("cost_total_yuan", 0) for r in group), 8),
            "tokens": sum((r["result"].get("usage") or {}).get("total_tokens", 0) +
                ((r["result"].get("profile_detection") or {}).get("usage") or {}).get("total_tokens", 0) for r in group),
            "api_attempts": sum(r["result"].get("attempts", 0) + (1 if r["result"].get("profile_detection") else 0) for r in group)}
    (OUT/"summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
