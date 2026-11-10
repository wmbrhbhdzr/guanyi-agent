"""Visual recognition tests use synthetic pixels and fake clients, never network."""

import base64
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from guanyi.ai.llm_client import LlmResult
from guanyi.app.vision_service import VisionService
from guanyi.vision.images import ImageInputError, prepare_image
from guanyi.vision.prompts import build_messages
from guanyi.vision.schema import OBSERVATION_EXAMPLE, ObservationError, parse_observation


def valid_observation():
    value = copy.deepcopy(OBSERVATION_EXAMPLE)
    value.update(turn=2, hand=[{"name": "打击", "cost": 1, "upgraded": False}],
                 enemies=[{"name": "敌人", "hp": 23, "max_hp": 30, "block": 0,
                           "intent": "攻击10×1", "intent_damage": 10, "intent_hits": 1}])
    value["player"].update(hp=68, max_hp=80, energy=3, max_energy=3, block=5)
    value["player"]["statuses"] = []
    return value


class FakeClient:
    def __init__(self, result=None):
        self.result = result or LlmResult(ok=True, text=json.dumps(valid_observation(), ensure_ascii=False),
                                          model="fake", finish_reason="stop")
        self.messages = []
        self.options = []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        self.options.append(kwargs)
        return self.result


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guanyi-vision-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "private-run-9999.png"
        Image.new("RGB", (400, 240), "#456789").save(self.image)
        self.client = FakeClient()
        self.service = VisionService(client=self.client, out_dir=self.root / "records")

    def test_01_image_pixels_and_metadata(self):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("secret", "this must not enter model input")
        Image.new("RGB", (3200, 1600), "red").save(self.image, pnginfo=metadata)
        frame = prepare_image(self.image)
        self.assertEqual(frame.size, (1920, 960))
        decoded = base64.b64decode(frame.data_uri.split(",", 1)[1])
        self.assertEqual(decoded, frame.png)
        with Image.open(io.BytesIO(decoded)) as normalized:
            self.assertEqual(normalized.info, {})

    def test_02_portrait_resize_and_exif(self):
        image = Image.new("RGB", (128, 256), "blue")
        exif = image.getexif()
        exif[274] = 6
        image.save(self.image.with_suffix(".jpg"), exif=exif)
        self.assertEqual(prepare_image(self.image.with_suffix(".jpg")).size, (256, 128))
        portrait = self.root / "portrait.png"
        Image.new("RGB", (100, 4000), "blue").save(portrait)
        self.assertEqual(prepare_image(portrait).size, (48, 1920))

    def test_03_invalid_input_does_not_call_model(self):
        self.image.write_text("not an image", encoding="utf-8")
        result = self.service.recognize(self.image)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_image")
        self.assertEqual(self.client.messages, [])
        self.assertFalse((self.root / "records").exists())

    def test_04_missing_tiny_and_oversized_images(self):
        with self.assertRaises(ImageInputError):
            prepare_image(self.root / "missing.png")
        Image.new("RGB", (32, 32), "black").save(self.image)
        with self.assertRaises(ImageInputError):
            prepare_image(self.image)
        with self.image.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
        with self.assertRaises(ImageInputError):
            prepare_image(self.image)

    def test_05_unknown_values_remain_null(self):
        value = valid_observation()
        value["player"]["hp"] = None
        value["hand"] = None
        self.client.result.text = json.dumps(value)
        result = self.service.recognize(self.image, save=False)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["observation"]["player"]["hp"])
        self.assertIsNone(result["observation"]["hand"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("未识别", result["summary"])

    def test_06_type_range_and_health_checks(self):
        cases = [("player", "hp", True), ("player", "hp", -1), ("player", "hp", 90),
                 ("player", "energy", "3"), ("player", "max_hp", 0)]
        for key, field, item in cases:
            value = valid_observation()
            value[key][field] = item
            with self.subTest(field=field, item=item), self.assertRaises(ObservationError):
                parse_observation(json.dumps(value))

    def test_07_card_cost_and_upgraded(self):
        value = valid_observation()
        value["hand"][0]["cost"] = "X"
        self.assertEqual(parse_observation(json.dumps(value))["hand"][0]["cost"], "X")
        value["hand"][0]["upgraded"] = "true"
        with self.assertRaises(ObservationError):
            parse_observation(json.dumps(value))

    def test_08_fenced_json_supported_and_prose_rejected(self):
        text = json.dumps(valid_observation())
        self.assertEqual(parse_observation("```json\n" + text + "\n```"), valid_observation())
        for invalid in ("Here is the result: " + text, "[]", '{"scene":"combat","scene":"map"}', text[:-2]):
            with self.subTest(invalid=invalid[:30]), self.assertRaises(ObservationError):
                parse_observation(invalid)

    def test_09_pixel_only_context(self):
        result = self.service.recognize(self.image, save=False)
        self.assertTrue(result["ok"])
        messages = self.client.messages[0]
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(len(messages[1]["content"]), 2)
        self.assertTrue(messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        context = json.dumps(messages)
        for token in (str(self.image), self.image.name, "run-9999", "decisions.jsonl"):
            self.assertNotIn(token, context)
        self.assertIn("deadline", self.client.options[0])

    def test_10_evidence_saved_without_payload_or_secrets(self):
        result = self.service.recognize(self.image)
        path = Path(result["saved_path"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(Path(saved["image_path"]).exists())
        self.assertEqual(saved["image"]["submitted_sha256"], prepare_image(saved["image_path"]).sha256)
        self.assertEqual(saved["observation"], valid_observation())
        self.assertNotIn("base64", path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", saved)
        self.assertNotIn("messages", saved)

    def test_11_no_save_has_no_files(self):
        self.assertTrue(self.service.recognize(self.image, save=False)["ok"])
        self.assertFalse((self.root / "records").exists())

    def test_12_invalid_response_not_adopted(self):
        self.client.result.text = '{"hp":80}'
        result = self.service.recognize(self.image)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["observation"])
        self.assertEqual(result["error"]["code"], "invalid_observation")
        self.assertTrue(Path(result["saved_path"]).is_file())

    def test_13_truncated_response_rejected_even_if_parseable(self):
        self.client.result.finish_reason = "length"
        result = self.service.recognize(self.image, save=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "output_limit")

    def test_14_model_failure_does_not_log_response_body(self):
        self.client.result = LlmResult(ok=False, error={"code": "http_401", "detail": "sk-secret123456"})
        result = self.service.recognize(self.image)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "http_401")
        self.assertNotIn("secret123456", Path(result["saved_path"]).read_text(encoding="utf-8"))

    def test_15_timeout_returns_and_late_result_not_saved(self):
        def slow(*args, **kwargs):
            time.sleep(.12)
            return LlmResult(ok=True, text=json.dumps(valid_observation()))
        self.client.chat = slow
        result = self.service.recognize(self.image, timeout_s=.03)
        self.assertEqual(result["status"], "timeout")
        time.sleep(.15)
        saved = json.loads(Path(result["saved_path"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "timeout")
        self.assertIsNone(saved["observation"])

    def test_16_unknown_scene_is_not_successful_combat(self):
        value = copy.deepcopy(OBSERVATION_EXAMPLE)
        value.update(scene="unknown", hand=None, enemies=None)
        self.client.result.text = json.dumps(value)
        result = self.service.recognize(self.image, save=False)
        self.assertEqual(result["status"], "unrecognized")
        self.assertIsNone(result["observation"]["player"]["hp"])

    def test_17_missing_extra_and_nonfinite_fields_rejected(self):
        for kind in ("missing", "extra", "nan"):
            value = valid_observation()
            if kind == "missing":
                del value["hand"]
            elif kind == "extra":
                value["execute"] = "click"
            else:
                value["player"]["hp"] = float("nan")
            with self.subTest(kind=kind), self.assertRaises(ObservationError):
                parse_observation(json.dumps(value))

    def test_18_empty_vs_unknown_regions(self):
        value = valid_observation()
        value.update(hand=[], enemies=[])
        parsed = parse_observation(json.dumps(value))
        self.assertEqual(parsed["hand"], [])
        self.assertEqual(parsed["enemies"], [])

    def test_19_storage_failure_prevents_request(self):
        blocking = self.root / "file"
        blocking.write_text("blocked", encoding="utf-8")
        service = VisionService(client=self.client, out_dir=blocking / "out")
        result = service.recognize(self.image)
        self.assertEqual(result["error"]["code"], "storage_error")
        self.assertEqual(self.client.messages, [])

    def test_20_same_image_gets_distinct_record_ids(self):
        one = self.service.recognize(self.image)
        two = self.service.recognize(self.image)
        self.assertNotEqual(one["saved_path"], two["saved_path"])
        self.assertEqual(one["image"]["submitted_sha256"], two["image"]["submitted_sha256"])

    def test_21_vision_cli_never_initializes_run_storage(self):
        from guanyi.cli import main
        with patch("guanyi.cli.SessionService") as storage, patch("sys.stdout", new=io.StringIO()):
            code = main(["vision", "--image", str(self.root / "missing.png"), "--no-save"])
        self.assertEqual(code, 2)
        storage.assert_not_called()

    def test_22_invalid_timeout_does_not_call_model(self):
        for timeout in (0, -1, 301, True, float("nan")):
            with self.subTest(timeout=timeout):
                result = self.service.recognize(self.image, timeout_s=timeout, save=False)
                self.assertFalse(result["ok"])
        self.assertEqual(self.client.messages, [])

    def test_23_blank_frames_rejected_without_model_call(self):
        for color in ("black", "white"):
            Image.new("RGB", (800, 500), color).save(self.image)
            result = self.service.recognize(self.image, save=False)
            self.assertEqual(result["error"]["code"], "invalid_image")
        self.assertEqual(self.client.messages, [])

    def test_24_missing_card_and_enemy_details_are_partial(self):
        value = valid_observation()
        value["hand"][0]["name"] = None
        value["enemies"][0]["intent"] = None
        self.client.result.text = json.dumps(value)
        result = self.service.recognize(self.image, save=False)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("手牌" in item for item in result["warnings"]))
        self.assertTrue(any("敌人" in item for item in result["warnings"]))

    def test_25_empty_reasoning_only_response_explained(self):
        self.client.result = LlmResult(ok=False, finish_reason="length", error={"code": "empty_response"},
            attempts=1, usage={"completion_tokens": 2500, "completion_tokens_details": {"reasoning_tokens": 2500}})
        result = self.service.recognize(self.image, save=False)
        self.assertEqual(result["error"]["code"], "output_limit")
        self.assertEqual(result["error"]["details"]["reasoning_tokens"], 2500)
        self.assertIn("推理2500", result["error"]["message"])
        self.assertNotIn("密钥", result["error"]["message"])

    def test_26_sts2_references_are_images_without_state(self):
        result = self.service.recognize(self.image, game="sts2", save=False)
        self.assertTrue(result["ok"])
        content = self.client.messages[0][1]["content"]
        self.assertEqual(sum(c["type"] == "image_url" for c in content), 13)
        text = " ".join(c.get("text", "") for c in content)
        self.assertIn("外骨骼虫", text)
        self.assertNotIn("min_hp", text)
        self.assertEqual(len(result["references"]), 12)
        self.assertEqual(result["identity_evidence"], "visual_reference_candidates_not_verified")
        self.assertIn("外形比对", result["summary"])

    def test_27_clumsy_rules_do_not_leak_to_generic(self):
        value = valid_observation()
        value["hand"] = [{"name": "笨拙", "cost": 1, "upgraded": None}]
        self.client.result.text = json.dumps(value)
        generic = self.service.recognize(self.image, save=False)
        adapted = self.service.recognize(self.image, game="sts2", save=False)
        self.assertEqual(generic["observation"]["hand"][0]["cost"], 1)
        card = adapted["observation"]["hand"][0]
        self.assertIsNone(card["cost"])
        self.assertFalse(card["playable"])
        self.assertEqual(card["keywords"], ["不能被打出", "虚无"])
        self.assertTrue(card["rules_source"].endswith("#CLUMSY"))
        self.assertIn("笨拙（诅咒", adapted["summary"])
        self.assertNotIn("费用1", adapted["summary"])
        self.assertEqual(adapted["normalizations"][0]["previous_cost"], 1)

    def test_28_profile_conventions_and_null_for_obscured_fields(self):
        from guanyi.vision.prompts import build_messages
        from guanyi.vision.profiles import apply_rules
        generic = build_messages(prepare_image(self.image))[0]["content"]
        sts2 = build_messages(prepare_image(self.image), game="sts2")[0]["content"]
        self.assertNotIn("intent_hits=1", generic)
        self.assertIn("intent_hits=1", sts2)
        self.assertIn("block=0", sts2)
        self.assertIn("被遮挡", sts2)
        value = valid_observation()
        value["player"]["block"] = None
        apply_rules(value, "sts2")
        self.assertIsNone(value["player"]["block"], "不能在缺少可见性证据时全局把null改0")

    def test_29_thinking_disabled_is_forwarded_to_http_payload(self):
        from guanyi.ai.llm_client import LlmClient
        client = LlmClient(api_key="test")
        payloads = []
        def post(url, payload, timeout):
            payloads.append(payload)
            return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}, 1
        client._post = post
        client.chat([], thinking={"type": "disabled"})
        client.chat([])
        self.assertEqual(payloads[0]["thinking"], {"type": "disabled"})
        self.assertNotIn("thinking", payloads[1], "旧问答/Agent调用设置不改变")
        self.service.recognize(self.image, save=False)
        self.assertEqual(self.client.options[0]["thinking"], {"type": "disabled"})
        self.assertEqual(self.client.options[0]["max_tokens"], 4096)

    def test_30_specific_failures_have_distinct_recovery(self):
        for code in ("missing_api_key", "http_401", "http_402", "http_429", "network_error", "http_400", "timeout"):
            self.client.result = LlmResult(ok=False, error={"code": code, "detail": "sk-private-secret"})
            result = self.service.recognize(self.image, save=False)
            self.assertEqual(result["error"]["code"], code)
            self.assertTrue(result["error"]["action"])
            self.assertNotIn("sk-private", json.dumps(result))

    def test_31_missing_reference_diagnosed_before_model_call(self):
        with patch("guanyi.app.vision_service.load_references", side_effect=OSError("missing")):
            result = self.service.recognize(self.image, game="sts2", save=False)
        self.assertEqual(result["error"]["code"], "reference_error")
        self.assertEqual(self.client.messages, [])

    def test_32_nonattack_intent_has_no_unknown_hit_summary(self):
        from guanyi.vision.schema import summarize_observation
        value = valid_observation()
        value["enemies"][0].update(intent="增益", intent_damage=None, intent_hits=None)
        text = summarize_observation(value)
        self.assertIn("意图：增益", text)
        self.assertNotIn("次数未识别", text)

    def test_33_statuses_allow_visible_counters_and_unknown_names(self):
        value = valid_observation()
        value["player"]["statuses"] = [{"name": "力量", "amount": -2}]
        value["enemies"][0]["statuses"] = [{"name": None, "amount": 9}]
        parsed = parse_observation(json.dumps(value))
        self.assertEqual(parsed["player"]["statuses"][0]["amount"], -2)
        self.assertIsNone(parsed["enemies"][0]["statuses"][0]["name"])
        for amount in (True, "9", 1.5):
            value["enemies"][0]["statuses"][0]["amount"] = amount
            with self.assertRaises(ObservationError):
                parse_observation(json.dumps(value))

    def test_34_status_rules_do_not_invent_counters(self):
        from guanyi.vision.profiles import apply_rules
        from guanyi.vision.schema import summarize_observation
        value = valid_observation()
        value["player"]["statuses"] = []
        value["enemies"][0]["statuses"] = [{"name": "难以杀灭", "amount": 9}, {"name": "虚弱", "amount": None}]
        apply_rules(value, "sts2")
        status = value["enemies"][0]["statuses"][0]
        self.assertEqual(status["amount"], 9)
        self.assertEqual(status["rule_id"], "HARD_TO_KILL")
        self.assertIsNone(value["enemies"][0]["statuses"][1]["amount"])
        self.assertIn("数值9，伤害上限", summarize_observation(value))

    def test_35_optional_statuses_remain_backward_compatible(self):
        value = valid_observation()
        value["player"].pop("statuses", None)
        self.assertEqual(parse_observation(json.dumps(value)), value)

    def test_36_auto_title_enables_adapter_and_tracks_cost(self):
        detection = LlmResult(ok=True, text='{"game":"sts2","title":"Slay the Spire 2"}',
                              cost={"cost_total_yuan": .001})
        observation = valid_observation()
        observation["hand"] = [{"name": "笨拙", "cost": 1, "upgraded": None}]
        client = FakeClient()
        replies = [detection, LlmResult(ok=True, text=json.dumps(observation), cost={"cost_total_yuan": .002})]
        def chat(messages, **kwargs):
            client.messages.append(messages)
            return replies.pop(0)
        client.chat = chat
        result = VisionService(client=client).recognize(self.image, game="auto", save=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["game_profile"], "sts2")
        self.assertEqual(result["cost"]["cost_total_yuan"], .003)
        self.assertFalse(result["observation"]["hand"][0]["playable"])
        self.assertNotIn(self.image.name, json.dumps(client.messages[0]))

    def test_37_unconfirmed_title_does_not_enable_sts2(self):
        from guanyi.vision.game_detection import detect_game
        from guanyi.agent.runtime import wait_call
        for title in ("", "Slay the Spire", "Plants vs. Zombies", "card game"):
            self.client.result = LlmResult(ok=True, text=json.dumps({"game": "sts2", "title": title}))
            game, _, _ = detect_game(self.client, prepare_image(self.image), time.monotonic()+2, wait_call)
            self.assertEqual(game, "generic")

    def test_38_hover_text_belongs_only_to_associated_enemy(self):
        from guanyi.vision.schema import annotate_tooltip_sources
        value = valid_observation()
        value["enemies"][0]["statuses"] = [{"name": "难以杀灭", "amount": 9}]
        value["enemies"].append(copy.deepcopy(value["enemies"][0]))
        value["enemies"][1]["statuses"][0]["amount"] = 7
        value["tooltips"] = [{"owner": "enemy", "owner_index": 0, "title": "难以杀灭", "text": "伤害不超过9点"}]
        parsed = parse_observation(json.dumps(value));annotate_tooltip_sources(parsed)
        one, two = parsed["enemies"]
        self.assertEqual(one["statuses"][0]["description"], "伤害不超过9点")
        self.assertEqual(one["statuses"][0]["source"], "tooltip")
        self.assertNotIn("description", two["statuses"][0])
        self.assertEqual(two["statuses"][0]["amount"], 7)

    def test_39_hover_window_owner_validation_and_unknown_owner(self):
        value = valid_observation()
        value["tooltips"] = [{"owner": "enemy", "owner_index": 99, "title": "难以杀灭", "text": "9"}]
        with self.assertRaises(ObservationError):
            parse_observation(json.dumps(value))
        value["tooltips"][0].update(owner="unknown", owner_index=None)
        from guanyi.vision.schema import summarize_observation
        self.assertIn("所属对象未确认", summarize_observation(parse_observation(json.dumps(value))))

    def test_40_auto_auth_failure_stops_before_extraction(self):
        self.client.result = LlmResult(ok=False, error={"code": "http_401"})
        result = self.service.recognize(self.image, game="auto", save=False)
        self.assertFalse(result["ok"])
        self.assertEqual(len(self.client.messages), 1)
        self.assertEqual(result["error"]["code"], "http_401")


if __name__ == "__main__":
    unittest.main(verbosity=2)
