#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a UI layout mock (labelled as schematic) for the report."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "paper" / "figures" / "ui-chat.png"
W, H = 1440, 900
BG = (11, 13, 18)
PANEL = (18, 21, 29)
PANEL2 = (23, 27, 37)
PANEL3 = (30, 35, 48)
LINE = (38, 44, 58)
TEXT = (231, 234, 240)
MUTED = (139, 147, 167)
ACCENT = (79, 140, 255)
GREEN = (61, 220, 151)


def font(size, bold=False):
    for path in (r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
                 r"C:\Windows\Fonts\simhei.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(d, xy, r, fill, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# sidebar
d.rectangle((0, 0, 260, H), fill=PANEL)
d.rectangle((260, 0, 261, H), fill=LINE)
rounded(d, (16, 18, 50, 52), 10, ACCENT)
d.text((33, 35), "AI", font=font(13, True), fill=(255, 255, 255), anchor="mm")
d.text((62, 28), "Edge AI", font=font(16, True), fill=TEXT)
d.text((62, 48), "Raspberry Pi 4B · STM32G431", font=font(10), fill=MUTED)
rounded(d, (14, 78, 246, 118), 9, PANEL2, LINE)
d.text((28, 98), "＋ 新建对话", font=font(13), fill=TEXT, anchor="lm")
for idx, title in enumerate(["用一句话介绍树莓派", "LED 控制", "LCD 显示"]):
    y = 132 + idx * 38
    rounded(d, (10, y, 250, y + 32), 8, PANEL3 if idx == 0 else PANEL)
    d.text((24, y + 16), title, font=font(12), fill=TEXT if idx == 0 else MUTED, anchor="lm")
d.rectangle((0, H - 55, 260, H - 55), fill=LINE)
d.ellipse((18, H - 35, 26, H - 27), fill=GREEN)
d.text((34, H - 31), "串口已连接 · /dev/ttyACM0", font=font(10), fill=MUTED, anchor="lm")

# main topbar
d.rectangle((260, 0, W - 300, 56), fill=(15, 18, 25))
d.rectangle((260, 56, W - 300, 57), fill=LINE)
rounded(d, (282, 14, 468, 42), 14, (20, 32, 55), (50, 85, 150))
d.text((296, 28), "Qwen2.5-0.5B · 本地推理", font=font(11), fill=(140, 180, 255), anchor="lm")
rounded(d, (W - 420, 16, W - 320, 40), 8, PANEL2, LINE)
d.text((W - 370, 28), "清空当前对话", font=font(11), fill=MUTED, anchor="mm")

# chat
user_y = 110
rounded(d, (800, user_y, 1080, user_y + 46), 14, (32, 47, 82), (50, 84, 150))
d.text((820, user_y + 23), "用一句话介绍树莓派", font=font(13), fill=TEXT, anchor="lm")
d.ellipse((1092, user_y + 8, 1122, user_y + 38), fill=(70, 100, 190))
d.text((1107, user_y + 23), "你", font=font(10, True), fill=(255, 255, 255), anchor="mm")

ai_y = 180
rounded(d, (282, ai_y, 1080, ai_y + 118), 14, PANEL2, LINE)
d.ellipse((282, ai_y + 10, 312, ai_y + 40), fill=(35, 42, 58))
d.text((297, ai_y + 25), "AI", font=font(10, True), fill=(140, 180, 255), anchor="mm")
d.text((330, ai_y + 26), "树莓派（Raspberry Pi）是一款便携式电脑，由荷兰的嵌入式设计与制造公司", font=font(13), fill=TEXT, anchor="lm")
d.text((330, ai_y + 52), "Raspberry Pi 有限公司设计和制造。它可以运行 Linux，常用于嵌入式、", font=font(13), fill=TEXT, anchor="lm")
d.text((330, ai_y + 78), "教育和物联网项目。", font=font(13), fill=TEXT, anchor="lm")

# composer
rounded(d, (282, H - 140, W - 340, H - 78), 16, PANEL2, (50, 85, 150), 2)
d.text((304, H - 109), "输入问题，Enter 发送，Shift+Enter 换行", font=font(13), fill=(102, 112, 137), anchor="lm")
rounded(d, (W - 388, H - 128, W - 352, H - 92), 10, ACCENT)
d.polygon([(W - 377, H - 116), (W - 363, H - 110), (W - 377, H - 104)], fill=(255, 255, 255))
d.text((W - 416, H - 58), "本地推理 · 数据不出设备 · 可控制 LED / LCD / ADC / PWM",
       font=font(10), fill=(95, 104, 128), anchor="mm")

# device panel
px = W - 280
d.rectangle((px, 0, W, H), fill=PANEL)
d.rectangle((px, 0, px + 1, H), fill=LINE)
d.text((px + 18, 24), "设备控制", font=font(14, True), fill=TEXT, anchor="lm")
d.ellipse((px + 18, 52, px + 26, 60), fill=GREEN)
d.text((px + 34, 56), "串口已连接 · /dev/ttyACM0", font=font(10), fill=MUTED, anchor="lm")

y = 96
d.text((px + 18, y), "LED", font=font(11), fill=MUTED)
for i, label in enumerate(("LED1 开", "LED1 关")):
    x0 = px + 18 + i * 128
    rounded(d, (x0, y + 20, x0 + 118, y + 52), 8, PANEL2, LINE)
    d.text((x0 + 59, y + 36), label, font=font(11), fill=TEXT, anchor="mm")
y += 82
d.text((px + 18, y), "LCD 第 1 行", font=font(11), fill=MUTED)
rounded(d, (px + 18, y + 20, px + 262, y + 50), 8, PANEL2, LINE)
d.text((px + 30, y + 35), "Hello", font=font(11), fill=TEXT, anchor="lm")
for i, label in enumerate(("显示", "清屏")):
    x0 = px + 18 + i * 128
    rounded(d, (x0, y + 58, x0 + 118, y + 88), 8, PANEL2, LINE)
    d.text((x0 + 59, y + 73), label, font=font(11), fill=TEXT, anchor="mm")
y += 120
d.text((px + 18, y), "ADC（PB12 电位器）", font=font(11), fill=MUTED)
rounded(d, (px + 18, y + 20, px + 118, y + 50), 8, PANEL2, LINE)
d.text((px + 68, y + 35), "读取", font=font(11), fill=TEXT, anchor="mm")
d.text((px + 140, y + 35), "1759", font=font(16, True), fill=(110, 160, 255), anchor="lm")
y += 92
d.text((px + 18, y), "PWM 占空比", font=font(11), fill=MUTED)
d.text((px + 200, y), "50%", font=font(11), fill=(110, 160, 255), anchor="lm")
d.line([(px + 18, y + 28), (px + 262, y + 28)], fill=(60, 68, 88), width=5)
d.line([(px + 18, y + 28), (px + 140, y + 28)], fill=ACCENT, width=5)
d.ellipse((px + 132, y + 20, px + 148, y + 36), fill=(255, 255, 255))
rounded(d, (px + 18, y + 50, px + 262, y + 82), 8, PANEL2, LINE)
d.text((px + 140, y + 66), "应用到 PA2", font=font(11), fill=TEXT, anchor="mm")

d.text((W // 2 - 20, H - 18), "界面布局示意（实际运行截图见 http://<树莓派IP>:8000/）",
       font=font(10), fill=(90, 98, 120), anchor="mm")

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "PNG")
print("wrote", OUT)
