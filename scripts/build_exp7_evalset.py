"""Prepare ten numbered, fixed samples and labels, separate from model input."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from scripts.vision_demo import make_frame

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/exp7"


def main():
    images = OUT / "inputs"
    cases = OUT / "cases"
    images.mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 26)
    small = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 20)
    samples = []
    checks = {"scene": "combat", "turn": 2, "player.hp": 68, "player.max_hp": 80,
              "player.energy": 3, "player.max_energy": 3, "player.block": 5,
              "enemies.0.hp": 23, "enemies.0.max_hp": 30, "enemies.0.intent_damage": 10,
              "enemies.0.intent_hits": 1, "hand.0.name": "STRIKE", "hand.0.cost": 1}
    for index, kind in enumerate(("clear", "zero_energy", "x_cost", "multi_hit", "hidden_hud", "hud_only"), 1):
        p = images / ("E%02d.png" % index)
        make_frame(p)
        im = Image.open(p).convert("RGB")
        draw = ImageDraw.Draw(im)
        expected = dict(checks)
        if kind == "zero_energy":
            draw.rectangle((35, 80, 1160, 135), fill="#263b4a")
            draw.text((42, 88), "PLAYER  HP 10 / 80    ENERGY 0 / 3    BLOCK 0    TURN 2", font=font, fill="white")
            expected.update({"player.hp": 10, "player.energy": 0, "player.block": 0})
        elif kind == "x_cost":
            draw.rectangle((50, 470, 370, 580), fill="#3b4856")
            draw.text((56, 475), "WHIRLWIND", font=font, fill="#f9e1a8")
            draw.text((56, 535), "COST X", font=font, fill="white")
            expected.update({"hand.0.name": "WHIRLWIND", "hand.0.cost": "X"})
        elif kind == "multi_hit":
            draw.rectangle((776, 325, 1140, 370), fill="#56363d")
            draw.text((780, 329), "INTENT: ATTACK 2 x 3", font=small, fill="white")
            expected.update({"enemies.0.intent_damage": 2, "enemies.0.intent_hits": 3})
        elif kind == "hidden_hud":
            draw.rectangle((24, 65, 1176, 145), fill="#263b4a")
            draw.text((42, 88), "HUD OBSCURED - VALUES NOT VISIBLE", font=font, fill="white")
            expected.update({"turn": None, "player.hp": None, "player.max_hp": None,
                             "player.energy": None, "player.max_energy": None, "player.block": None})
        elif kind == "hud_only":
            im = im.crop((24, 65, 1176, 145))
            expected = {k: v for k, v in checks.items() if k.startswith("player.") or k == "turn"}
            expected.update({"hand": None, "enemies": None})
        im.save(p)
        samples.append({"id": p.stem, "kind": "synthetic", "scenario": kind, "expected": expected})
    im = Image.new("RGB", (1000, 650), "#25364a")
    draw = ImageDraw.Draw(im)
    for i, text in enumerate(("APP SETTINGS", "AUDIO    50", "LANGUAGE    ENGLISH", "RETURN")):
        draw.text((80, 80 + i * 100), text, font=font, fill="white")
    im.save(images / "E07.png")
    samples.append({"id": "E07", "kind": "synthetic", "scenario": "non_combat_out_of_scope",
                    "expected": {"player.hp": None, "player.energy": None, "turn": None},
                    "allowed": {"scene": ["menu", "unknown"]}})
    Image.new("RGB", (1000, 650), "black").save(images / "E08.png")
    samples.append({"id": "E08", "kind": "synthetic", "scenario": "blank_invalid_input", "expected_error": "invalid_image"})
    sources = ["vision-e744a23b6d494abf9051b12b5f40af25", "vision-5ac3dee6ebcd4fa4b28e660381f52bb6"]
    for index, source in enumerate(sources, 9):
        p = images / ("E%02d.png" % index)
        shutil.copyfile(ROOT / "data/vision" / source / "input.png", p)
        expected = {"scene": "combat", "turn": 1, "player.hp": 107, "player.max_hp": 107,
                    "player.energy": 3 if index == 9 else 2, "player.max_energy": 3, "player.block": 0,
                    "hand.1.name": "笨拙", "hand.1.cost": None,
                    "enemies.0.hp": 24 if index == 9 else 18,
                    "enemies.1.hp": 26, "enemies.2.hp": 25,
                    "enemies.0.intent_damage": 1, "enemies.0.intent_hits": 3,
                    "enemies.1.intent_damage": 8, "enemies.1.intent_hits": 1}
        for i in range(3):
            expected.update({"enemies.%d.block" % i: 0,
                             "enemies.%d.statuses.0.name" % i: "难以杀灭",
                             "enemies.%d.statuses.0.amount" % i: 9})
        samples.append({"id": p.stem, "kind": "real", "scenario": "battle" if index == 9 else "hover_detail",
                        "expected": expected, "source_record": source,
                        "required_tooltip": "难以杀灭" if index == 10 else None})
    for sample in samples:
        sample.update(image="inputs/%s.png" % sample["id"],
                      sha256=hashlib.sha256((images/(sample["id"]+".png")).read_bytes()).hexdigest(),
                      label_source="合成图生成参数" if sample["kind"] == "synthetic" else "原图目视核对，AI辅助标注，待用户最终确认")
        (cases/(sample["id"]+".json")).write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({"version": "exp7-fixed-10-v1", "cases": ["cases/%s.json" % s["id"] for s in samples]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared", len(samples), "cases; labels never enter model messages")


if __name__ == "__main__":
    main()
