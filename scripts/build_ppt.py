#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build paper/答辩PPT.pptx with python-pptx."""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "paper" / "figures"
OUT = ROOT / "paper" / "答辩PPT.pptx"

BG = RGBColor(11, 13, 18)
TEXT = RGBColor(231, 234, 240)
MUTED = RGBColor(150, 160, 180)
ACCENT = RGBColor(79, 140, 255)
GREEN = RGBColor(61, 220, 151)
ORANGE = RGBColor(245, 158, 11)


def set_font(run, size=20, bold=False, color=TEXT, font="Microsoft YaHei"):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = OxmlElement("a:ea")
        rPr.append(ea)
    ea.set("typeface", font)


def textbox(slide, left, top, width, height, text, size=20, bold=False,
            color=TEXT, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=8):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing)
        run = p.add_run()
        run.text = line
        set_font(run, size, bold, color)


def bullets(slide, left, top, width, height, items, size=20, color=TEXT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(12)
        run = p.add_run()
        run.text = "•  " + item
        set_font(run, size, False, color)


def bg(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG


def title_bar(slide, title, idx=None):
    bg(slide)
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    textbox(slide, 0.7, 0.35, 11.5, 0.8, title, 30, True)
    if idx is not None:
        textbox(slide, 12.2, 7.0, 0.8, 0.3, str(idx), 12, False, MUTED, PP_ALIGN.RIGHT)


def picture(slide, filename, left, top, max_w, max_h):
    path = FIG / filename
    if not path.is_file():
        textbox(slide, left, top, max_w, 0.5, f"缺图：{filename}", 14, False, MUTED)
        return
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    slide.shapes.add_picture(str(path), Inches(left), Inches(top),
                             width=Inches(w * scale), height=Inches(h * scale))


def main():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 1 cover
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg(s)
    textbox(s, 0.8, 1.7, 11.8, 0.6, "《嵌入式系统综合设计》课程设计", 26, True, ACCENT)
    textbox(s, 0.8, 2.4, 11.8, 2.0,
            "基于树莓派 4B 与 STM32G431 的\n端侧多模态 AI 交互终端\n——蓝桥杯 CT117E-M4 专用 AI 助教",
            30, True, TEXT)
    textbox(s, 0.8, 4.7, 11.8, 0.5,
            "本地 LLM / VLM · 蓝桥杯知识库 RAG · Web 聊天 · UART 硬件控制", 20, False, MUTED)
    textbox(s, 0.8, 5.9, 11.8, 0.5,
            "答辩人：________    组员：________    指导教师：________    2026 年 11 月",
            14, False, MUTED)

    # 2 background
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "项目背景与目标", 2)
    bullets(s, 0.8, 1.5, 11.8, 5.2, [
        "云端 LLM/VLM 依赖网络，存在隐私、延迟与成本问题",
        "边缘设备算力提升：量化推理让小模型在 ARM CPU 上可运行",
        "目标：在树莓派 4B 上离线运行 Qwen2.5-0.5B 与 SmolVLM-500M",
        "通过 Web 聊天界面把自然语言转成 STM32 的硬件动作",
        "形成「语言 → 命令 → 执行 → 回读」的端到端闭环",
        "扩展为蓝桥杯 CT117E-M4 专用 AI 助教：板卡/外设/代码/真题",
    ])

    # 3 architecture
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "系统总体架构", 3)
    picture(s, "block.png", 0.7, 1.25, 12.0, 5.8)
    textbox(s, 0.8, 7.05, 11.8, 0.3,
            "浏览器 ⇄ FastAPI ⇄ llama.cpp / 持久串口 ⇄ STM32G431", 12, False, MUTED, PP_ALIGN.CENTER)

    # 4 hardware
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "硬件设计与接线", 4)
    bullets(s, 0.7, 1.4, 5.2, 5.4, [
        "树莓派 4B Rev 1.5，8GB，Ubuntu 20.04",
        "蓝桥杯 CT117E-M4，STM32G431RBT6",
        "板载 CMSIS-DAP：烧录 + 9600 VCP",
        "USART1 PA9/PA10（AF_PP 推挽）",
        "LED PC8–PC15；ADC PB12；PWM PA2",
        "官方 27W 电源，避免欠压与 VCP 重枚举",
    ], 16)
    picture(s, "wiring.png", 6.1, 1.35, 6.6, 5.5)

    # 5 firmware/protocol
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "固件与 UART 命令协议", 5)
    bullets(s, 0.7, 1.4, 5.4, 5.3, [
        "Keil MDK V5，HAL + BSP，0 error / 0 warning",
        "命令：PING / LED / LEDALL / LCD / LCDCLR / ADC? / PWM / PWM?",
        "中断只入环形缓冲，主循环解析并执行",
        "ACK / ERR 返回；9600 8N1 持久会话",
        "归档固件：command_firmware.hex（sha256）",
    ], 18)
    picture(s, "sim-uart.png", 6.2, 1.6, 6.5, 4.6)

    # 6 LLM/VLM performance
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "边缘推理性能", 6)
    textbox(s, 0.8, 1.5, 5.6, 0.5, "LLM：Qwen2.5-0.5B-Instruct Q4_K_M", 22, True, ACCENT)
    bullets(s, 0.8, 2.1, 5.6, 4.2, [
        "38 completion tokens / 7.04 s",
        "解码 7.26 tok/s；prompt 19.09 tok/s",
        "中文回答正常；FastAPI SSE 流式",
        "内存占用约 0.4GB；温度 35°C",
    ], 17)
    textbox(s, 6.6, 1.5, 5.9, 0.5, "VLM：SmolVLM-500M-Instruct Q8", 22, True, GREEN)
    bullets(s, 6.6, 2.1, 5.9, 4.2, [
        "mmproj 多模态，单图 155 prompt tokens",
        "测试图（红圆 + HELLO）34.11 s",
        "返回「HELLO」；适合单张上传图片",
        "CPU 推理，暂不做实时摄像头",
    ], 17)
    textbox(s, 0.8, 6.5, 11.8, 0.4,
            "结论：0.5B 对话可用，VLM 适合低频单图；1.5B/3B 需权衡速度与内存",
            14, False, MUTED, PP_ALIGN.CENTER)

    # 7 web + NL
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "Web 前端与自然语言控制", 7)
    picture(s, "ui-chat.png", 0.55, 1.25, 8.6, 5.9)
    bullets(s, 9.35, 1.5, 3.6, 5.3, [
        "类 DeepSeek 深色聊天界面",
        "SSE 流式输出、会话历史",
        "设备面板：LED/LCD/ADC/PWM",
        "图片上传 → /api/vision",
        "规则路由优先：中文指令直接执行",
        "知识库直答 + 资料来源卡片",
        "开放问题再交给本地 LLM",
    ], 14)

    # 8 knowledge base
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "蓝桥杯知识库 RAG", 8)
    textbox(s, 0.8, 1.35, 11.8, 0.6, "1606 个片段 · 464 个来源 · 2.62MB 文本", 26, True, GREEN)
    bullets(s, 0.8, 2.2, 5.7, 4.4, [
        "资料：章节 PPT、产品手册、实训指导书",
        "真题汇编目录、考点统计、官方/历年源码",
        "本机验证固件 + CT117E-M4 板卡事实卡",
        "中文 bigram + ASCII 标识符 + 同义词 BM25",
        "板卡/本机固件加权，旧平台内容降权",
    ], 16)
    bullets(s, 6.7, 2.2, 5.8, 4.4, [
        "硬件命令 → 规则路由（不经 LLM）",
        "板卡/源码/课件 → 直答 0.04s + 来源",
        "开放技术问题 → 0.5B RAG（20–35s）",
        "完全未命中 → 0.03s 范围提示",
        "前端显示“知识库直答/RAG 生成”",
    ], 16)
    textbox(s, 0.8, 6.6, 11.8, 0.4,
            "结论：高频板卡问题毫秒级回答；小模型只处理开放问题，避免长上下文拖慢演示",
            14, False, MUTED, PP_ALIGN.CENTER)

    # 9 verification
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "验证结果", 9)
    bullets(s, 0.8, 1.4, 11.8, 5.4, [
        "CMSIS-DAP 烧录 + 原固件备份成功；Keil 0 error / 0 warning",
        "UART 9600 双向：PING → OK PONG；LED 闪 5 下",
        "LED 单灯/全亮/全灭正确；LCD 清屏后仅显示 Hello",
        "ADC 读回 1759；PWM 0/50/100% 回读一致",
        "自然语言：「让 LED1 亮起来」「LCD 显示 Hello」「读取 ADC」「PWM 50」均执行",
        "LLM 7.26 tok/s；VLM 单图 34.11 s；30 分钟稳定性 933 次检查 / 0 失败（最高 47.2°C）",
        "知识库：1606 片段；LED/I2C/PWM/USART/LCD 直答 0.04s，附来源",
        "systemd 开机自启：上电后约 22 秒 API 上线（LCD 显示 IP/READY）",
    ], 17)

    # 10 shortcomings
    s = prs.slides.add_slide(prs.slide_layouts[6])
    title_bar(s, "不足与改进", 10)
    bullets(s, 0.8, 1.4, 11.8, 5.4, [
        "板载 VCP 仅 9600，且烧录后可能写阻塞 → USB-TTL/GPIO UART",
        "小模型能力有限 → 1.5B/3B、RAG、端云协同",
        "VLM 单图 34s → 更强 VLM、NPU 加速、图片预处理",
        "无摄像头 → Camera Module 3 / USB 摄像头",
        "规则路由优先 → 结构化 function calling / GBNF",
        "知识库真题截图未 OCR → 后续 OCR/人工整理题面",
        "Proteus 无法仿真 Pi/LLM → 实测波形 + 明确边界",
    ], 16)

    # 11 summary
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg(s)
    textbox(s, 0.8, 2.0, 11.8, 0.8, "总结", 38, True, ACCENT)
    textbox(s, 0.8, 3.0, 11.8, 2.4,
            "完成端侧多模态 AI 交互终端的全链路实现：\n"
            "本地 LLM/VLM + 蓝桥杯知识库 RAG + Web 聊天 + STM32 硬件控制。",
            24, False, TEXT)
    textbox(s, 0.8, 5.8, 11.8, 0.6, "谢谢！请各位老师批评指正", 26, True, GREEN)

    prs.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
