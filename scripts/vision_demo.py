"""Generate a known synthetic game frame; --online explicitly exercises vision."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont

from guanyi.app.vision_service import VisionService


def make_frame(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 760), "#192330")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/consola.ttf")
    font = ImageFont.truetype(str(font_path), 26) if font_path.exists() else ImageFont.load_default(size=26)
    small = ImageFont.truetype(str(font_path), 20) if font_path.exists() else ImageFont.load_default(size=20)
    draw.text((30, 20), "SYNTHETIC COMBAT FRAME - NOT A REAL GAME SCREENSHOT", font=small, fill="#9eb9cc")
    draw.rounded_rectangle((24, 65, 1176, 145), radius=12, fill="#263b4a", outline="#648b99", width=2)
    draw.text((42, 88), "PLAYER  HP 68 / 80    ENERGY 3 / 3    BLOCK 5    TURN 2", font=font, fill="white")
    draw.rounded_rectangle((760, 185, 1150, 400), radius=12, fill="#56363d", outline="#d29083", width=2)
    for i, text in enumerate(("ENEMY: TEST SLIME", "HP 23 / 30", "BLOCK 0", "INTENT: ATTACK 10 x 1")):
        draw.text((780, 200 + i * 43), text, font=font if i < 3 else small, fill="white")
    for i, (name, cost) in enumerate((("STRIKE", 1), ("DEFEND", 1), ("BASH", 2))):
        left = 36 + i * 385
        draw.rounded_rectangle((left, 450, left + 355, 695), radius=12, fill="#3b4856", outline="#d5bd7a", width=3)
        draw.text((left + 20, 475), name, font=font, fill="#f9e1a8")
        draw.text((left + 20, 535), "COST %d" % cost, font=font, fill="white")
        draw.text((left + 20, 595), "UPGRADED: NO", font=small, fill="white")
    draw.text((30, 722), "Test values are visible pixels. Expected values stay outside the model context.", font=small, fill="#9eb9cc")
    image.save(path)
    return path


def main():
    parser = argparse.ArgumentParser(description="视觉识别合成画面验证；默认只生成图片，不调用模型")
    parser.add_argument("--online", action="store_true", help="实际调用模型识别合成图片")
    parser.add_argument("--out-dir", default="runs/vision_demo")
    args = parser.parse_args()
    frame = make_frame(Path(args.out_dir) / "frame.png")
    print("已生成合成测试图：%s" % frame)
    if not args.online:
        print("未请求模型；添加 --online 可验证真实视觉接口。")
        return 0
    result = VisionService().recognize(frame)
    print(result.get("summary") or (result.get("error") or {}).get("message"))
    print("状态：%s；耗时：%.1f ms；估算费用：%s 元" % (
        result["status"], result["elapsed_ms"], (result.get("cost") or {}).get("cost_total_yuan", "未知")))
    print("运行记录：%s" % result.get("saved_path"))
    if not result["ok"]:
        return 2
    observation = result["observation"]
    player, enemies, cards = observation["player"], observation["enemies"], observation["hand"]
    checks = {"scene": observation["scene"] == "combat", "hp": player["hp"] == 68,
              "max_hp": player["max_hp"] == 80, "energy": player["energy"] == 3,
              "max_energy": player["max_energy"] == 3, "block": player["block"] == 5,
              "turn": observation["turn"] == 2,
              "enemy_hp": bool(enemies and len(enemies) == 1 and enemies[0]["hp"] == 23),
              "enemy_intent": bool(enemies and enemies[0]["intent_damage"] == 10 and enemies[0]["intent_hits"] == 1),
              "cards": bool(cards and [c["name"] for c in cards] == ["STRIKE", "DEFEND", "BASH"]),
              "costs": bool(cards and [c["cost"] for c in cards] == [1, 1, 2])}
    evidence = {"synthetic": True, "checks": checks, "passed": sum(checks.values()),
                "total": len(checks), "record_path": result.get("saved_path")}
    (Path(args.out_dir) / "check.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("合成画面核对：%d/%d；这不是实际游戏截图的准确率评测。" % (evidence["passed"], evidence["total"]))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
