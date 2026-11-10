"""Check independent grading and frozen input identity for the report evaluation."""

import hashlib
import json
import unittest
from pathlib import Path

from scripts.run_exp7_eval import score


class EvaluationTests(unittest.TestCase):
    def test_missing_field_is_not_equal_to_expected_null(self):
        checks = score({"expected": {"player.hp": None}}, {"observation": {"player": {}}})
        self.assertFalse(checks[0]["passed"])
        self.assertTrue(score({"expected": {"player.hp": None}}, {"observation": {"player": {"hp": None}}})[0]["passed"])

    def test_invalid_input_is_expected_boundary_result(self):
        self.assertTrue(score({"expected_error": "invalid_image"}, {"error": {"code": "invalid_image"}})[0]["passed"])
        self.assertFalse(score({"expected_error": "invalid_image"}, {"ok": True})[0]["passed"])

    def test_hover_with_wrong_owner_fails(self):
        case = {"required_tooltip": "难以杀灭"}
        result = {"observation": {"tooltips": [{"title": "难以杀灭", "owner": "enemy", "owner_index": 1, "text": "伤害不超9点"}]}}
        self.assertFalse(score(case, result)[0]["passed"])
        result["observation"]["tooltips"][0]["owner_index"] = 0
        self.assertTrue(score(case, result)[0]["passed"])

    def test_fixed_ten_cases_have_intact_distinct_inputs(self):
        root = Path(__file__).resolve().parents[1] / "evaluation/exp7"
        manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["cases"]), 10)
        hashes = set()
        for filename in manifest["cases"]:
            case = json.loads((root/filename).read_text(encoding="utf-8"))
            digest = hashlib.sha256((root/case["image"]).read_bytes()).hexdigest()
            self.assertEqual(case["sha256"], digest)
            hashes.add(digest)
        self.assertEqual(len(hashes), 10)
