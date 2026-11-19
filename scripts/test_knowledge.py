#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test the knowledge retriever / direct-answer policy.

Run on the PC after `python scripts/build_knowledge.py`:
    python scripts/test_knowledge.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pi"))

from app.knowledge import kb  # noqa: E402

CASES = [
    ("LED怎么点亮？", "board"),
    ("USART1串口怎么配置？", "board"),
    ("I2C读写AT24C02怎么写？", "board"),
    ("PWM怎么输出1kHz 50%占空比？", "board"),
    ("LCD怎么显示字符串？", "board"),
    ("CT117E-M4怎么快速入门？", "board"),
    ("省赛真题一般考哪些模块？", "board"),
    ("NVIC中断优先级怎么配置？", "ppt"),
    ("定时器输入捕获怎么测频率？", "code"),
    ("树莓派是什么？", "board"),
]

NEGATIVE = ["今天天气怎么样？"]


def main() -> int:
    if not kb.load(force=True):
        print("FAIL: knowledge not loaded:", kb.load_error)
        return 1
    print(f"loaded: {len(kb.docs)} chunks / {len({d.get('source') for d in kb.docs})} sources")
    failed = 0
    for query, expected_kind in CASES:
        result = kb.fast_answer(query)
        if not result:
            print(f"FAIL {query}: no direct answer")
            failed += 1
            continue
        answer, used = result
        kinds = [h.get("kind") for h in used]
        ok = expected_kind in kinds
        print(("PASS " if ok else "FAIL ") + query + f" | {kinds} | {len(answer)} chars")
        if not ok:
            failed += 1
    for query in NEGATIVE:
        result = kb.fast_answer(query)
        ok = result is None
        print(("PASS " if ok else "FAIL ") + query + " | out of scope")
        if not ok:
            failed += 1
    print("RESULT:", "PASS" if failed == 0 else f"{failed} FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
