"""Screenshot -> multimodal model -> validated observation -> local evidence."""

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..agent.runtime import wait_call
from ..ai.llm_client import LlmClient
from ..vision.images import ImageInputError, prepare_image
from ..vision.prompts import PROMPT_VERSION, build_messages
from ..vision.schema import ObservationError, observation_warnings, parse_observation, summarize_observation, annotate_tooltip_sources
from ..vision.profiles import apply_rules, load_references
from ..vision.diagnostics import model_error
from ..vision.game_detection import detect_game
from ..vision import config


class VisionService:
    """Independent of session storage/RAG; input is a user-selected image only."""

    def __init__(self, client=None, out_dir="data/vision"):
        self.client = client if client is not None else LlmClient(model=config.MODEL, max_tokens=config.MAX_TOKENS, retries=config.RETRIES)
        self.out_dir = Path(out_dir)

    prepare_image = staticmethod(prepare_image)

    def recognize(self, image_path, timeout_s=config.TIMEOUT_S, save=True, game="generic"):
        started = time.monotonic()
        record = {"ok": False, "status": "failed", "observation": None, "summary": "",
                  "warnings": [], "error": None, "prompt_version": PROMPT_VERSION,
                  "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                  "request_id": "vision-" + uuid.uuid4().hex,
                  "usage": {}, "cost": {}, "model": "", "saved_path": None,
                  "image_path": None, "elapsed_ms": 0.0}
        record["game_profile"] = game
        record["requested_profile"] = game
        record["request_settings"] = {"model": config.MODEL, "max_tokens": config.MAX_TOKENS,
                                      "temperature": config.TEMPERATURE, "thinking": config.THINKING["type"]}
        folder = None

        def finish():
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
            if folder is not None:
                target = folder / "result.json"
                record["saved_path"] = str(target)
                try:
                    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                except OSError:
                    record["saved_path"] = None
                    record["warnings"].append("结果未能保存，请检查目录写入权限；识别结果仍可在界面查看")
            return record

        try:
            if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= 300:
                raise ImageInputError("等待时间应在0到300秒之间")
            frame = prepare_image(image_path)
            record["image"] = frame.metadata()
            if game not in ("auto", "generic", "sts2"):
                raise ImageInputError("请选择通用识别或杀戮尖塔2适配")
        except ImageInputError as exc:
            record["error"] = {"code": "invalid_image", "message": str(exc)}
            return finish()

        if save:
            try:
                folder = self.out_dir / record["request_id"]
                folder.mkdir(parents=True, exist_ok=False)
                target = folder / "input.png"
                target.write_bytes(frame.png)
                record["image_path"] = str(target)
            except OSError:
                folder = None
                record["error"] = {"code": "storage_error", "message": "无法保存输入截图，尚未请求模型，请检查保存目录权限"}
                return finish()

        # One deadline covers network retries. Timed-out background requests cannot alter UI/storage.
        deadline = started + timeout_s
        detection = None
        if game == "auto":
            try:
                game, evidence, detection = detect_game(self.client, frame, deadline, wait_call)
                record["game_profile"] = game
                record["profile_detection"] = {**evidence, "usage": detection.usage, "cost": detection.cost}
                if not detection.ok:
                    record["error"] = model_error(detection, config.TITLE_MAX_TOKENS)
                    record["status"] = "timeout" if record["error"]["code"] == "timeout" else "failed"
                    return finish()
            except TimeoutError:
                record["status"] = "timeout"
                record["error"] = {"code": "timeout", "message": "识别游戏标题时等待超时，尚未进行局面提取。",
                                   "action": "可以手动选择游戏模式后重试，跳过自动标题检查。"}
                return finish()
            except Exception:
                game = "generic"
                record["game_profile"] = game
                record["profile_detection"] = {"reason": "标题检查未完成，使用通用模式；可手动指定游戏"}
        try:
            references = load_references(game)
        except (OSError, ValueError, ImageInputError) as exc:
            record["error"] = {"code": "reference_error", "message": "本地敌人参考图无法读取，尚未请求模型。",
                               "action": "检查knowledge/visual/sts2中的图片与清单，或切换通用识别。"}
            return finish()
        try:
            record["references"] = [{k: v for k, v in entry.items() if k != "frame"} for entry in references]
            messages = build_messages(frame, game=game, references=references)
            llm = wait_call(lambda: self.client.chat(messages, temperature=config.TEMPERATURE,
                            thinking=config.THINKING, max_tokens=config.MAX_TOKENS, timeout=timeout_s, deadline=deadline),
                            deadline - time.monotonic())
        except TimeoutError:
            record["status"] = "timeout"
            record["error"] = {"code": "timeout", "message": "识别等待超过%.0f秒；远端请求可能仍在处理，本次不自动重发" % timeout_s,
                               "action": "检查网络或稍后重试；不要连续发起多次识别。"}
            return finish()
        except Exception:
            record["error"] = {"code": "model_error", "message": "模型请求未完成，请检查服务配置或稍后重试"}
            return finish()

        record.update(model=llm.model, usage=llm.usage, cost=llm.cost,
                      latency_ms=llm.latency_ms, attempts=llm.attempts, finish_reason=llm.finish_reason)
        if detection is not None:
            record["recognition_cost"] = dict(llm.cost)
            record["cost"] = {**llm.cost, "cost_total_yuan": round(
                (llm.cost.get("cost_total_yuan", 0) or 0) +
                (detection.cost.get("cost_total_yuan", 0) or 0), 8)}
        if not llm.ok:
            record["error"] = model_error(llm, config.MAX_TOKENS)
            record["status"] = "timeout" if record["error"]["code"] == "timeout" else "failed"
            return finish()
        record["raw_response"] = re.sub(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{6,}", "sk-***", llm.text)
        try:
            if llm.finish_reason == "length":
                raise ObservationError("模型输出达到长度上限，本次结果未采用")
            observation = parse_observation(llm.text)
        except ObservationError as exc:
            record["error"] = (model_error(llm, config.MAX_TOKENS) if llm.finish_reason == "length" else
                               {"code": "invalid_observation", "message": str(exc),
                                "action": "完整结果页可查看原始回答与错误；不必因格式错误反复检查网络。"})
            return finish()
        try:
            annotate_tooltip_sources(observation)
            record["normalizations"] = apply_rules(observation, game)
        except (OSError, ValueError, KeyError):
            record["error"] = {"code": "reference_error", "message": "本地卡牌规则资料无法读取，本次未采用识别结果。",
                               "action": "检查knowledge/visual/sts2/card_rules.json，或切换通用识别。"}
            return finish()
        record.update(ok=True, observation=observation, summary=summarize_observation(observation),
                      warnings=observation_warnings(observation))
        if references:
            record["summary"] += "\n\n已提供%d张敌人/增减益参考图：名称可按外形比对，并非都在画面上直接显示；当前数值仍取自当前截图。" % len(references)
            record["identity_evidence"] = "visual_reference_candidates_not_verified"
        record["status"] = ("unrecognized" if observation["scene"] == "unknown"
                            else "partial" if record["warnings"] else "recognized")
        return finish()
