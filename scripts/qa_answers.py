#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""High-intensity answer-quality regression for concept/board questions.

Run on the Raspberry Pi:
    python3 scripts/qa_answers.py --group all
    python3 scripts/qa_answers.py --group def
    python3 scripts/qa_answers.py --group compare
    python3 scripts/qa_answers.py --group faq
    python3 scripts/qa_answers.py --group board
    python3 scripts/qa_answers.py --group open

Every case checks required keywords, routing mode, empty answers, repeated
sentences, prompt leakage and invented [1][2] citations.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from qa_stress import chat, check

# (term, must-contain keyword)
TERMS = [
    ("中断", "ISR"),
    ("中断优先级", "抢占"),
    ("中断服务函数", "ISR"),
    ("中断嵌套", "抢占"),
    ("外部中断", "EXTI"),
    ("定时器", "计数"),
    ("输入捕获", "捕获"),
    ("PWM", "占空比"),
    ("占空比", "100%"),
    ("串口", "PA9"),
    ("波特率", "9600"),
    ("校验位", "校验"),
    ("I2C", "SCL"),
    ("SPI", "MOSI"),
    ("ADC", "4095"),
    ("分辨率", "4096"),
    ("参考电压", "VREF"),
    ("滤波", "噪声"),
    ("中值滤波", "中值"),
    ("一阶低通", "y +="),
    ("GPIO", "推挽"),
    ("推挽输出", "高电平"),
    ("开漏输出", "上拉"),
    ("上拉电阻", "高电平"),
    ("下拉电阻", "低电平"),
    ("寄存器", "数据手册"),
    ("时钟", "80MHz"),
    ("晶振", "32.768"),
    ("RTC", "GetTime"),
    ("看门狗", "复位"),
    ("DMA", "内存"),
    ("NVIC", "优先级"),
    ("野指针", "非法内存"),
    ("栈溢出", "Stack_Size"),
    ("数组越界", "下标"),
    ("状态机", "状态"),
    ("消抖", "延时"),
    ("启动文件", "向量表"),
    ("复位", "Reset_Handler"),
    ("低功耗", "Standby"),
]

VARIANTS = ["什么是{term}？", "{term}是什么？", "什么叫{term}？", "解释一下{term}", "{term}的含义"]

COMPARE = [
    ("上升沿和下降沿有什么区别？", ["上升沿", "下降沿", "0→1", "1→0"]),
    ("I2C 和 SPI 的区别是什么？", ["SCL", "SDA", "MOSI"]),
    ("中断和轮询的区别", ["ISR", "轮询"]),
    ("推挽和开漏的区别", ["推挽", "开漏"]),
    ("上拉和下拉的区别", ["上拉", "下拉"]),
    ("ADC 和 DAC 的区别", ["ADC", "DAC"]),
]

FAQ = [
    ("为什么天是蓝的？", ["瑞利散射"], "concept"),
    ("天气怎么样？", ["无法获取"], "weather"),
    ("代码是什么？", ["指令"], "concept"),
    ("程序跑飞了怎么办？", ["HardFault"], "concept"),
    ("什么是程序？", ["main"], "concept"),
]

BOARD = [
    ("什么是 USART1？", ["PA9", "PA10"], "knowledge"),
    ("LED 的数据口是什么？", ["PC8", "PD2"], "knowledge"),
    ("I2C 的地址是多少？", ["0x50"], "knowledge"),
    ("RTC 怎么配置？", ["RTC"], "knowledge"),
    ("PWM1 是哪个引脚？", ["PA2"], "knowledge"),
]

OPEN = [
    "为什么会有四季？",
    "地球为什么是圆的？",
    "给我讲一个简短的笑话。",
]


def quality_failures(result, must=(), mode=None):
    text = result.get("content") or ""
    failures = check(result, must=must, mode=mode)
    if re.search(r"300\s*字以内|代码用\s*Markdown|不要编造|回答要求", text):
        failures.append("prompt leak")
    if not result.get("sources") and re.search(r"\[\d+\]", text):
        failures.append("fake citation")
    # Ignore fenced code blocks: repeated code lines are legitimate.
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    sentences = [
        re.sub(r"\s+", "", s)
        for s in re.split(r"(?<=[。！？!?；;])", prose)
        if len(s.strip()) >= 8
    ]
    if any(sentences.count(s) >= 2 for s in sentences):
        failures.append("repeated sentence")
    return failures


def run_case(case_id, category, question, must, mode=None, timeout=180):
    try:
        result = chat([{"role": "user", "content": question}], timeout=timeout, max_tokens=160)
        failures = quality_failures(result, must=must, mode=mode)
        return {
            "id": case_id,
            "cat": category,
            "q": question,
            "ok": not failures,
            "failures": failures,
            "content": result["content"],
            "mode": result["mode"],
            "sources": len(result.get("sources") or []),
            "latency": result["latency"],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": case_id,
            "cat": category,
            "q": question,
            "ok": False,
            "failures": [f"exception: {exc}"],
            "content": "",
            "mode": None,
            "sources": 0,
            "latency": 0,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["all", "def", "compare", "faq", "board", "open"], default="all")
    ap.add_argument("--out", default=str(Path.home() / "ai-terminal" / "logs"))
    args = ap.parse_args()

    results = []
    if args.group in ("def", "all"):
        for term, must in TERMS:
            for idx, template in enumerate(VARIANTS, 1):
                q = template.format(term=term)
                results.append(run_case(f"def_{term}_{idx}", "定义", q, [must], "concept"))
    if args.group in ("compare", "all"):
        for idx, (q, must) in enumerate(COMPARE, 1):
            results.append(run_case(f"compare_{idx}", "对比", q, must, "concept"))
    if args.group in ("faq", "all"):
        for idx, (q, must, mode) in enumerate(FAQ, 1):
            results.append(run_case(f"faq_{idx}", "FAQ", q, must, mode))
    if args.group in ("board", "all"):
        for idx, (q, must, mode) in enumerate(BOARD, 1):
            results.append(run_case(f"board_{idx}", "板卡", q, must, mode))
    if args.group in ("open", "all"):
        for idx, q in enumerate(OPEN, 1):
            results.append(run_case(f"open_{idx}", "开放", q, [], None, timeout=240))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qa_answers_{args.group}_{stamp}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        if not r["ok"]:
            print(f"FAIL {r['id']:<26} {r['q']}")
            print("     " + " | ".join(r["failures"]))
            print("     " + (r["content"] or "").replace("\n", " ")[:180])

    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["cat"]][1] += 1
        if r["ok"]:
            by_cat[r["cat"]][0] += 1
    for cat, (ok, total) in sorted(by_cat.items()):
        print(f"{cat:<6} {ok}/{total}")
    passed = sum(1 for r in results if r["ok"])
    print(f"\nRESULT: {passed}/{len(results)} PASS; log={out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
