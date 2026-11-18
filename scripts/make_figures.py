#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate report/PPT figures with Pillow (no matplotlib required)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BG = (248, 250, 253)
INK = (30, 41, 59)
MUTED = (100, 116, 139)
BLUE = (59, 130, 246)
LIGHT_BLUE = (219, 234, 254)
GREEN = (16, 185, 129)
LIGHT_GREEN = (209, 250, 229)
PURPLE = (139, 92, 246)
LIGHT_PURPLE = (237, 233, 254)
ORANGE = (245, 158, 11)
LIGHT_ORANGE = (254, 243, 199)
LINE = (148, 163, 184)


def font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def canvas(w, h, title=None):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    if title:
        d.text((w // 2, 38), title, font=font(34, True), fill=INK, anchor="mm")
    return img, d


def box(d, xy, text, fill=LIGHT_BLUE, outline=BLUE, size=22, radius=16):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=3)
    lines = text.split("\n")
    total = len(lines) * (size + 8)
    cy = (y0 + y1) / 2 - total / 2 + size / 2
    for line in lines:
        d.text(((x0 + x1) / 2, cy), line, font=font(size), fill=INK, anchor="mm")
        cy += size + 8


def arrow(d, p1, p2, color=LINE, width=4):
    d.line([p1, p2], fill=color, width=width)
    import math

    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    size = 14
    for sign in (-1, 1):
        a = angle + sign * math.radians(150)
        d.line(
            [p2, (p2[0] + size * math.cos(a), p2[1] + size * math.sin(a))],
            fill=color,
            width=width,
        )


def save(img, name):
    path = OUT / name
    img.save(path, "PNG")
    print("wrote", path)


def block():
    img, d = canvas(1800, 1000, "系统总体架构")
    box(d, (60, 300, 380, 700), "浏览器\n\n聊天界面\n设备面板\n图片上传", LIGHT_BLUE, BLUE, 24)
    box(d, (520, 120, 1240, 880), "", LIGHT_PURPLE, PURPLE, 24)
    d.text((880, 165), "树莓派 4B（Ubuntu 20.04）", font=font(26, True), fill=PURPLE, anchor="mm")
    box(d, (560, 230, 930, 340), "FastAPI\n/api/chat  /api/device  /api/vision", (255, 255, 255), PURPLE, 18)
    box(d, (950, 230, 1200, 340), "规则路由\n中文指令 → 命令", (255, 255, 255), PURPLE, 18)
    box(d, (560, 380, 930, 490), "llama.cpp\nQwen2.5-0.5B 7.26 tok/s", (255, 255, 255), PURPLE, 18)
    box(d, (950, 380, 1200, 490), "llama.cpp\nSmolVLM-500M 34s/图", (255, 255, 255), PURPLE, 18)
    box(d, (560, 530, 930, 640), "持久串口服务\n/dev/ttyACM0 9600 8N1", (255, 255, 255), PURPLE, 18)
    box(d, (950, 530, 1200, 640), "pyOCD 烧录\nCMSIS-DAP（P1/P2）", (255, 255, 255), PURPLE, 18)
    box(d, (560, 690, 1200, 800), "Web 静态托管\n（web/index.html + app.js）", (255, 255, 255), PURPLE, 18)

    box(d, (1380, 240, 1740, 780), "STM32G431\n（CT117E-M4）", LIGHT_GREEN, GREEN, 24)
    box(d, (1420, 340, 1700, 440), "命令解析\nPING/LED/LCD/ADC/PWM", (255, 255, 255), GREEN, 17)
    box(d, (1420, 470, 1700, 570), "BSP 驱动\nLED/LCD/ADC/PWM", (255, 255, 255), GREEN, 17)
    box(d, (1420, 600, 1700, 700), "外设\n8 LED / LCD / 电位器", (255, 255, 255), GREEN, 17)

    arrow(d, (380, 500), (520, 500), BLUE)
    d.text((450, 470), "HTTP / SSE", font=font(17), fill=BLUE, anchor="mm")
    arrow(d, (520, 540), (380, 540), BLUE)
    arrow(d, (1240, 500), (1380, 500), GREEN)
    d.text((1310, 470), "USB CDC\n9600", font=font(17), fill=GREEN, anchor="mm")
    arrow(d, (1380, 540), (1240, 540), GREEN)
    save(img, "block.png")


def power():
    img, d = canvas(1500, 900, "电源树")
    box(d, (520, 110, 980, 220), "220V → 官方 27W USB-C\n5V / 3A", LIGHT_ORANGE, ORANGE, 24)
    box(d, (120, 360, 500, 480), "树莓派 4B\n5V（官方电源）", LIGHT_BLUE, BLUE, 22)
    box(d, (560, 360, 940, 480), "5 寸 HDMI 屏（可选）\n5V", LIGHT_PURPLE, PURPLE, 22)
    box(d, (1000, 360, 1380, 480), "开发板 USB\n5V → 板载 3.3V LDO", LIGHT_GREEN, GREEN, 22)
    box(d, (1000, 600, 1380, 720), "STM32G431 / LCD / LED\n3.3V", LIGHT_GREEN, GREEN, 22)
    arrow(d, (700, 220), (310, 360), ORANGE)
    arrow(d, (750, 220), (750, 360), ORANGE)
    arrow(d, (800, 220), (1190, 360), ORANGE)
    arrow(d, (1190, 480), (1190, 600), GREEN)
    d.text((750, 800), "注意：Pi 必须使用 5V/3A 官方电源；欠压会导致 VCP 重枚举与系统不稳定。",
           font=font(18), fill=MUTED, anchor="mm")
    save(img, "power.png")


def wiring():
    img, d = canvas(1600, 900, "系统接线与引脚分配")
    box(d, (80, 160, 520, 760), "树莓派 4B", LIGHT_BLUE, BLUE, 26)
    box(d, (1080, 160, 1520, 760), "STM32G431\n（CT117E-M4）", LIGHT_GREEN, GREEN, 26)
    rows = [
        ("USB-A", "板载 CMSIS-DAP", "烧录 + VCP"),
        ("—", "PA9 / USART1_TX", "UART TX"),
        ("—", "PA10 / USART1_RX", "UART RX"),
        ("GND", "GND", "共地"),
        ("—", "PC8–PC15 + PD2", "8 LED"),
        ("—", "PB12 / ADC1_CH11", "电位器"),
        ("—", "PA2 / TIM15_CH1", "PWM 输出"),
    ]
    y = 250
    for left, right, note in rows:
        d.text((300, y), left, font=font(20), fill=INK, anchor="mm")
        d.text((1300, y), right, font=font(20), fill=INK, anchor="mm")
        d.text((800, y), note, font=font(18), fill=MUTED, anchor="mm")
        d.line([(520, y), (1080, y)], fill=LINE, width=2)
        y += 70
    d.text((800, 820), "VCP 内部连接；若 VCP 异常，使用 USB-TTL：TX→PA10、RX←PA9、GND↔GND（不接 5V）",
           font=font(17), fill=MUTED, anchor="mm")
    save(img, "wiring.png")


def flow_main():
    img, d = canvas(1500, 1000, "系统主流程")
    box(d, (600, 100, 900, 180), "上电", LIGHT_ORANGE, ORANGE, 22)
    box(d, (520, 240, 980, 340), "初始化\nLCD/LED/按键/ADC/PWM/USART", LIGHT_BLUE, BLUE, 20)
    box(d, (600, 400, 900, 480), "发送 READY", LIGHT_BLUE, BLUE, 20)
    box(d, (520, 540, 980, 640), "主循环\n读取环形缓冲 → 按行解析", LIGHT_PURPLE, PURPLE, 20)
    box(d, (520, 700, 980, 800), "执行命令\nLED/LCD/ADC/PWM", LIGHT_GREEN, GREEN, 20)
    box(d, (600, 860, 900, 940), "返回 ACK/ERR", LIGHT_GREEN, GREEN, 20)
    arrow(d, (750, 180), (750, 240), LINE)
    arrow(d, (750, 340), (750, 400), LINE)
    arrow(d, (750, 480), (750, 540), LINE)
    arrow(d, (750, 640), (750, 700), LINE)
    arrow(d, (750, 800), (750, 860), LINE)
    d.line([(900, 900), (1250, 900), (1250, 590), (980, 590)], fill=LINE, width=3)
    arrow(d, (980, 590), (980, 590), LINE)
    save(img, "flow-main.png")


def flow_cmd():
    img, d = canvas(1600, 950, "命令解析流程")
    box(d, (100, 150, 480, 250), "USART1 接收中断", LIGHT_BLUE, BLUE, 20)
    box(d, (580, 150, 960, 250), "CMD_FeedByte()\n写入环形缓冲", LIGHT_BLUE, BLUE, 20)
    box(d, (1060, 150, 1440, 250), "主循环 CMD_Proc()\n拼行（\\n 结束）", LIGHT_PURPLE, PURPLE, 20)
    box(d, (1060, 350, 1440, 450), "命令匹配\nPING/LED/LCD/ADC/PWM", LIGHT_ORANGE, ORANGE, 20)
    box(d, (1060, 550, 1440, 650), "参数校验\n范围/通道/长度", LIGHT_ORANGE, ORANGE, 20)
    box(d, (580, 750, 960, 850), "执行 BSP 驱动", LIGHT_GREEN, GREEN, 20)
    box(d, (100, 750, 480, 850), "发送 ACK / ERR", LIGHT_GREEN, GREEN, 20)
    arrow(d, (480, 200), (580, 200), LINE)
    arrow(d, (960, 200), (1060, 200), LINE)
    arrow(d, (1250, 250), (1250, 350), LINE)
    arrow(d, (1250, 450), (1250, 550), LINE)
    arrow(d, (1250, 650), (1250, 800), LINE)
    arrow(d, (1060, 800), (960, 800), LINE)
    arrow(d, (580, 800), (480, 800), LINE)
    save(img, "flow-cmd.png")


def flow_chat():
    img, d = canvas(1600, 950, "自然语言 → 硬件 / LLM 流程")
    box(d, (100, 150, 480, 250), "用户输入", LIGHT_BLUE, BLUE, 22)
    box(d, (580, 150, 960, 250), "POST /api/chat", LIGHT_BLUE, BLUE, 22)
    box(d, (1060, 150, 1440, 250), "tool_router\n中文规则匹配", LIGHT_ORANGE, ORANGE, 22)
    box(d, (1060, 380, 1440, 480), "命中：串口命令\nLED/LCD/ADC/PWM", LIGHT_GREEN, GREEN, 20)
    box(d, (580, 380, 960, 480), "未命中：llama-server\n/v1/chat/completions", LIGHT_PURPLE, PURPLE, 20)
    box(d, (580, 620, 960, 720), "SSE 流式返回前端", LIGHT_GREEN, GREEN, 20)
    box(d, (1060, 620, 1440, 720), "返回「已执行 … → OK …」", LIGHT_GREEN, GREEN, 20)
    arrow(d, (480, 200), (580, 200), LINE)
    arrow(d, (960, 200), (1060, 200), LINE)
    arrow(d, (1250, 250), (1250, 380), LINE)
    arrow(d, (1060, 430), (960, 430), LINE)
    arrow(d, (770, 480), (770, 620), LINE)
    arrow(d, (1250, 480), (1250, 620), LINE)
    arrow(d, (1060, 670), (960, 670), LINE)
    save(img, "flow-chat.png")


def sim_uart():
    img, d = canvas(1600, 700, "UART 帧格式（9600 8N1）")
    fields = [("AA", 120), ("55", 120), ("ver", 130), ("type", 130), ("seq", 130),
              ("len_lo", 160), ("len_hi", 160), ("payload", 300), ("crc_lo", 160), ("crc_hi", 160)]
    x = 80
    y0, y1 = 220, 360
    colors = [LIGHT_ORANGE, LIGHT_ORANGE, LIGHT_BLUE, LIGHT_BLUE, LIGHT_BLUE,
              LIGHT_PURPLE, LIGHT_PURPLE, LIGHT_GREEN, LIGHT_ORANGE, LIGHT_ORANGE]
    for (name, w), color in zip(fields, colors):
        d.rectangle((x, y0, x + w, y1), fill=color, outline=INK, width=2)
        d.text((x + w / 2, (y0 + y1) / 2), name, font=font(18), fill=INK, anchor="mm")
        x += w
    d.text((800, 440), "同步字 0xAA55 · CRC-16/CCITT-FALSE（poly 0x1021, init 0xFFFF）",
           font=font(19), fill=MUTED, anchor="mm")
    d.text((800, 500), "命令示例：PING / LED 1 1 / LCD 1 Hello / ADC? / PWM 1 50",
           font=font(19), fill=MUTED, anchor="mm")
    d.text((800, 580), "实测：Pi→STM32 LED 闪 5 下；STM32→Pi 收到 OK PONG / OK ADC 1759",
           font=font(19), fill=GREEN, anchor="mm")
    save(img, "sim-uart.png")


def sim_pwm():
    img, d = canvas(1600, 800, "PWM 输出（TIM15_CH1 / PA2，1 kHz）")
    y0 = 180
    for idx, duty in enumerate((0, 50, 100)):
        y = y0 + idx * 190
        d.text((90, y + 40), f"{duty}%", font=font(24, True), fill=INK, anchor="mm")
        x = 200
        period = 400
        high = int(period * duty / 100)
        for _ in range(3):
            d.line([(x, y + 70), (x + high, y + 70)], fill=GREEN, width=5)
            d.line([(x + high, y + 70), (x + high, y + 10)], fill=GREEN, width=5)
            d.line([(x + high, y + 10), (x + period, y + 10)], fill=GREEN, width=5)
            d.line([(x + period, y + 10), (x + period, y + 70)], fill=GREEN, width=5)
            x += period
    d.text((800, 720), "占空比 0/50/100% 对应比较值 0/500/1000；万用表平均电压约 0/1.65/3.3V",
           font=font(19), fill=MUTED, anchor="mm")
    save(img, "sim-pwm.png")


def main():
    block()
    power()
    wiring()
    flow_main()
    flow_cmd()
    flow_chat()
    sim_uart()
    sim_pwm()


if __name__ == "__main__":
    main()
