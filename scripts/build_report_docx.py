#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build paper/课程设计报告.docx from the Markdown report and figures."""
from pathlib import Path
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "paper" / "课程设计报告.md"
FIG = ROOT / "paper" / "figures"
OUT = ROOT / "paper" / "课程设计报告.docx"

FIGURE_MAP = {
    "### 4.1 系统框图": [("block.png", "系统总体架构")],
    "### 4.2 电源树": [("power.png", "电源树")],
    "### 4.3 引脚与接线": [("wiring.png", "系统接线与引脚分配")],
    "### 4.4 仿真方案与结果": [("sim-uart.png", "UART 帧格式"), ("sim-pwm.png", "PWM 输出")],
    "## 五、程序流程图": [
        ("flow-main.png", "系统主流程"),
        ("flow-cmd.png", "命令解析流程"),
        ("flow-chat.png", "自然语言到硬件/LLM 流程"),
    ],
    "### 6.1 演示环境": [("ui-chat.png", "Web 聊天与设备控制界面（布局示意）")],
}


def set_cn_font(run, name="宋体", size=12, bold=False, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_para(doc, text, size=12, bold=False, font="宋体", indent=True,
             align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(space_after)
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    run = p.add_run(text)
    set_cn_font(run, font, size, bold)
    return p


def shade(cell, color="D9E2F3"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def add_table(doc, rows):
    if not rows:
        return
    cols = len(rows[0])
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j in range(cols):
            cell = table.cell(i, j)
            text = row[j] if j < len(row) else ""
            text = text.replace("**", "").replace("`", "").strip()
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            set_cn_font(run, "宋体", 9, bold=(i == 0))
            if i == 0:
                shade(cell)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_figure(doc, filename, caption, number):
    path = FIG / filename
    if not path.is_file():
        add_para(doc, f"（缺图：{filename}）", size=10, indent=False,
                 align=WD_ALIGN_PARAGRAPH.CENTER)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(path), width=Cm(15.5))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(8)
    run = cap.add_run(f"图 {number}  {caption}")
    set_cn_font(run, "宋体", 10)


def is_table_line(line):
    return line.strip().startswith("|") and line.strip().endswith("|")


def parse_table(lines, start):
    rows = []
    i = start
    while i < len(lines) and is_table_line(lines[i]):
        raw = lines[i].strip().strip("|").split("|")
        cells = [c.strip() for c in raw]
        if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            rows.append(cells)
        i += 1
    return rows, i


def main():
    text = MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    doc = Document()

    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.6)
    section.right_margin = Cm(2.6)

    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(12)

    # cover
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("《嵌入式系统综合设计》")
    set_cn_font(run, "黑体", 22, True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("课程设计报告")
    set_cn_font(run, "黑体", 26, True)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("基于树莓派 4B 与 STM32G431 的\n端侧多模态 AI 交互终端设计与实现")
    set_cn_font(run, "黑体", 18, True)
    for _ in range(3):
        doc.add_paragraph()

    info = [
        ("学    院", "电子工程学院"),
        ("专    业", "电子信息科学与技术"),
        ("班    级", "________"),
        ("组    员", "________、________、________、________、________"),
        ("指导教师", "________"),
        ("日    期", "2026 年 11 月"),
    ]
    table = doc.add_table(rows=len(info), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(info):
        c0, c1 = table.cell(i, 0), table.cell(i, 1)
        c0.width = Cm(4)
        c1.width = Cm(10)
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cn_font(p0.add_run(k), "宋体", 14, True)
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_cn_font(p1.add_run(v), "宋体", 14)
    doc.add_page_break()

    # body starts at first ## heading
    start = next(i for i, l in enumerate(lines) if l.startswith("## "))
    fig_no = 0
    i = start
    first_section = True
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("## "):
            if not first_section:
                doc.add_page_break()
            first_section = False
            h = doc.add_heading(level=1)
            h.alignment = WD_ALIGN_PARAGRAPH.LEFT
            set_cn_font(h.add_run(stripped[3:].strip()), "黑体", 16, True)
            for filename, caption in FIGURE_MAP.get(stripped, []):
                fig_no += 1
                add_figure(doc, filename, caption, fig_no)
            i += 1
            continue

        if stripped.startswith("### "):
            h = doc.add_heading(level=2)
            set_cn_font(h.add_run(stripped[4:].strip()), "黑体", 14, True)
            for filename, caption in FIGURE_MAP.get(stripped, []):
                fig_no += 1
                add_figure(doc, filename, caption, fig_no)
            i += 1
            continue

        if stripped.startswith("#### "):
            h = doc.add_heading(level=3)
            set_cn_font(h.add_run(stripped[5:].strip()), "黑体", 12, True)
            i += 1
            continue

        if stripped.startswith("```"):
            # Skip ASCII/code blocks in the Word report; figures cover diagrams.
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue

        if is_table_line(line):
            rows, i = parse_table(lines, i)
            add_table(doc, rows)
            continue

        if stripped in ("---", ""):
            i += 1
            continue

        if stripped.startswith("|"):
            i += 1
            continue

        clean = stripped.replace("**", "").replace("`", "")
        if clean.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.line_spacing = 1.5
            set_cn_font(p.add_run(clean[2:]), "宋体", 12)
        elif re.match(r"^\d+\.\s", clean):
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.line_spacing = 1.5
            set_cn_font(p.add_run(re.sub(r"^\d+\.\s", "", clean)), "宋体", 12)
        else:
            add_para(doc, clean, size=12)
        i += 1

    # page number footer
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.addnext(fld)

    doc.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
