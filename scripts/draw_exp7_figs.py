"""Create report figures from actual fixed inputs/results; no fabricated UI."""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "image/实验7-软件核心AI能力原型设计与开发"
EVAL = ROOT / "evaluation/exp7"


def font(size=24, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/msyh%s.ttc" % ("bd" if bold else ""), size)


def text(draw, xy, content, size=24, fill="#26344b", bold=False):
    draw.text(xy, content, font=font(size, bold), fill=fill, spacing=10)


def canvas(title, height):
    im = Image.new("RGB", (1400, height), "#f7f9fc")
    d = ImageDraw.Draw(im)
    text(d, (48, 25), title, 34, bold=True)
    return im, d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    im, d = canvas("观弈 · 视觉局面提取原型数据流", 850)
    labels = [("1 连接游戏窗口", "自动检测或手动选择窗口", 60, 125),
              ("2 采集与帧检查", "客户区 / 去重 / 尺寸检查", 500, 125),
              ("3 选择游戏适配", "进程/标题选择或手选", 940, 125),
              ("6 展示与保存", "局面摘要 + JSON + 输入图", 60, 390),
              ("5 程序检查", "类型/范围/对象关联/来源", 500, 390),
              ("4 deepseek-flash", "vision-v4 + 可选公开参考图", 940, 390)]
    for title, subtitle, x, y in labels:
        d.rounded_rectangle((x, y, x+395, y+150), radius=16, fill="white", outline="#8396b3", width=2)
        text(d, (x+20, y+22), title, 29, bold=True)
        text(d, (x+20, y+85), subtitle, 21)
    for x1,y1,x2,y2 in [(455,200,500,200),(895,200,940,200),(1137,275,1137,390),(940,465,895,465),(500,465,455,465)]:
        d.line((x1,y1,x2,y2),fill="#315d96",width=5)
        if x2>x1:d.polygon([(x2,y2),(x2-13,y2-8),(x2-13,y2+8)], fill="#315d96")
        elif x2<x1:d.polygon([(x2,y2),(x2+13,y2-8),(x2+13,y2+8)], fill="#315d96")
        else:d.polygon([(x2,y2),(x2-8,y2-13),(x2+8,y2-13)], fill="#315d96")
    text(d,(60,600),"失败分支：窗口关闭/最小化、黑屏、调用超时、格式错误 → 提示与日志",25)
    text(d,(60,665),"桌面与 CLI 共用采集/识别服务；连续模式串行运行，固定图片用于回归评测",24)
    text(d,(60,730),"配置：vision/config.py + prompts.py；密钥只从环境/.env读取",23)
    im.save(OUT/"图2-原型数据流.png")

    im,d=canvas("固定评测集 E01—E10（8张合成/边界图 + 2张真实图）",1090)
    names=["清晰战斗","零能量/低血量","X费用","多段攻击","HUD遮挡","仅HUD区域","非战斗设置页","黑屏拒绝","真实三敌战斗","真实悬停详情"]
    for i in range(10):
        x=45+(i%2)*690;y=100+(i//2)*190
        d.rounded_rectangle((x,y,x+645,y+172),radius=10,fill="white",outline="#bac6d5")
        with Image.open(EVAL/("inputs/E%02d.png"%(i+1))) as source:
            thumb=source.convert("RGB");thumb.thumbnail((260,145))
            im.paste(thumb,(x+8,y+8))
        text(d,(x+280,y+20),"E%02d %s"%(i+1,names[i]),24,bold=True)
        text(d,(x+280,y+75),"真实截图" if i>=8 else "合成/边界输入",22)
        text(d,(x+280,y+114),"固定输入与模型外标签",19,fill="#66758c")
    im.save(OUT/"图1-十例固定评测集.png")

    # Two samples per figure at full content width, rather than ten tiny thumbnails.
    descriptions = [
        "E01 基础战斗：HP 68/80、能量3/3、格挡5、攻击10×1",
        "E02 重画玩家栏：HP 10/80、能量0/3、格挡0",
        "E03 重画第一张手牌：WHIRLWIND，费用X",
        "E04 重画敌人意图：ATTACK 2 x 3，单次2点、3次",
        "E05 遮住玩家栏，血量/能量/回合不可见",
        "E06 仅裁出玩家栏，敌人和手牌区域均不在图内",
        "E07 绘制设置页，不包含战斗数值",
        "E08 生成纯黑图片，预期在本地拒绝",
    ]
    for pair in range(4):
        blocks = []
        for index in (pair*2, pair*2+1):
            with Image.open(EVAL/("inputs/E%02d.png" % (index+1))) as source:
                picture = source.convert("RGB")
                picture.thumbnail((1280, 850))
                blocks.append((picture, descriptions[index]))
        height = 105 + sum(p.height + 100 for p, _ in blocks)
        sheet, sd = canvas("合成输入原图 · E%02d / E%02d" % (pair*2+1, pair*2+2), height)
        y = 100
        for picture, description in blocks:
            text(sd, (50, y), description, 29, bold=True)
            sheet.paste(picture, (50, y+55))
            y += picture.height+100
        sheet.save(OUT/("图1-%d-E%02d-E%02d.png" % (pair+1, pair*2+1, pair*2+2)))

    summary=json.loads((EVAL/"results/summary.json").read_text(encoding="utf-8"))
    im,d=canvas("同一测试集对比（单次运行，非泛化准确率）",700)
    for i,(name,label,color) in enumerate([("baseline","首版重建基线", "#bf7c55"),("revised","当前修订版", "#317d91")]):
        s=summary[name];y=130+i*210;ratio=s["field_pass"]/s["fields"]
        text(d,(55,y),label,29,bold=True)
        d.rounded_rectangle((330,y,1300,y+58),radius=8,fill="#e3e9f1")
        d.rounded_rectangle((330,y,330+970*ratio,y+58),radius=8,fill=color)
        text(d,(350,y+10),"%d/%d 检查点（%.1f%%）"%(s["field_pass"],s["fields"],ratio*100),26,fill="white",bold=True)
        text(d,(330,y+80),"全项通过 %d/10；耗时中位数 %.2fs；估算费用 %.5f元"%(s["case_pass"],s["median_ms"]/1000,s["estimated_yuan"]),24)
    text(d,(55,570),"修订版真实图耗时：E09 7.32s / E10 8.91s，仍未达到5s目标。",25)
    text(d,(55,625),"标签：合成图按生成值；真实图按截图可见内容设置检查点。",23)
    im.save(OUT/"图4-基线与修订评测.png")

    im,d=canvas("E10 游戏截图、悬停文字与识别结果",1100)
    with Image.open(EVAL/"inputs/E10.png") as source:
        image=source.convert("RGB");image.thumbnail((850,520));im.paste(image,(35,100))
        crop=source.crop((710,560,1075,835)).resize((548,412))
        im.paste(crop,(35,640))
    d.rounded_rectangle((910,100,1360,1050),radius=12,fill="white",outline="#a8b6ca",width=2)
    rows=["实际结果：修订版 E10","玩家 HP 107/107","能量 2/3，格挡0","笨拙：不可打出、虚无","左敌：18/24，攻击1×3","中敌：26/26，攻击8×1","右敌：25/25，增益意图","三敌均识别：难以杀灭9","悬停归属：左侧敌人","攻势：伤害1点，3次","难以杀灭：伤害不超9点","耗时8.91s；26/26检查点","右侧增益的具体效果未显示"]
    for i,row in enumerate(rows):text(d,(930,125+i*66),row,23,bold=i==0)
    text(d,(610,680),"悬停原文局部",23,bold=True)
    text(d,(610,745),"数字9表示\n伤害上限，\n不是9层。",25)
    im.save(OUT/"图3-悬停原文与输出证据.png")
    print("8 figures generated")


if __name__=="__main__":
    main()
