#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""High-intensity QA smoke/stress test for the local assistant.

Run on the Raspberry Pi:
    python3 scripts/qa_stress.py --group fast
    python3 scripts/qa_stress.py --group slow
    python3 scripts/qa_stress.py --group multi
    python3 scripts/qa_stress.py --group concurrency

Results are printed and written to ~/ai-terminal/logs/qa_stress_*.json.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def chat(messages, timeout=120, max_tokens=160, fast_only=False):
    body = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "use_knowledge": True,
    }
    if fast_only:
        body["fast_only"] = True
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    content = ""
    sources = []
    mode = None
    timings = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if "sources" in obj:
                sources = obj.get("sources") or []
                mode = obj.get("mode")
            content += (obj.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
            if obj.get("timings"):
                timings = obj["timings"]
    return {
        "content": content,
        "sources": sources,
        "mode": mode,
        "timings": timings,
        "latency": round(time.time() - started, 2),
    }


def check(result, must=(), must_not=(), mode=None):
    text = result["content"]
    lower = text.lower()
    failures = []
    if mode and result["mode"] != mode:
        failures.append(f"mode={result['mode']} expected={mode}")
    for word in must:
        if word.lower() not in lower:
            failures.append(f"missing:{word}")
    for word in must_not:
        if word.lower() in lower:
            failures.append(f"forbidden:{word}")
    if not text.strip():
        failures.append("empty answer")
    return failures


FAST = [
    {
        "id": "led_pin",
        "messages": [{"role": "user", "content": "LED 怎么点亮？PC8–PC15 和 PD2 怎么配置？"}],
        "mode": "knowledge",
        "must": ["PC8", "PD2"],
        "must_not": ["回答不了"],
    },
    {
        "id": "usart",
        "messages": [{"role": "user", "content": "USART1 串口怎么配置？为什么收不到数据？"}],
        "mode": "knowledge",
        "must": ["PA9", "PA10", "AF_PP"],
    },
    {
        "id": "i2c",
        "messages": [{"role": "user", "content": "I2C 读写 AT24C02 怎么写？"}],
        "mode": "knowledge",
        "must": ["PB6", "PB7", "24C02"],
    },
    {
        "id": "adc_pins",
        "messages": [{"role": "user", "content": "ADC1 和 ADC2 分别是什么引脚？"}],
        "mode": "knowledge",
        "must": ["PB12", "PB15"],
    },
    {
        "id": "pwm_pins",
        "messages": [{"role": "user", "content": "PWM1 和 PWM2 是哪些引脚？频率多少？"}],
        "mode": "knowledge",
        "must": ["PA2", "PA3", "1kHz"],
    },
    {
        "id": "lcd",
        "messages": [{"role": "user", "content": "LCD 怎么显示字符串？"}],
        "mode": "knowledge",
        "must": ["LCD_Clear"],
    },
    {
        "id": "key",
        "messages": [{"role": "user", "content": "按键消抖和松手检测怎么写？"}],
        "mode": "knowledge",
        "must": ["Key_Scan"],
    },
    {
        "id": "intro",
        "messages": [{"role": "user", "content": "CT117E-M4 怎么快速入门？"}],
        "mode": "knowledge",
        "must": ["Keil", "CubeMX"],
    },
    {
        "id": "exam",
        "messages": [{"role": "user", "content": "省赛真题一般考哪些模块？"}],
        "mode": "knowledge",
        "must": ["LED", "LCD", "按键"],
    },
    {
        "id": "pi",
        "messages": [{"role": "user", "content": "树莓派是什么？"}],
        "mode": "knowledge",
        "must": ["Raspberry"],
        "must_not": ["回答不了"],
    },
    {
        "id": "date",
        "messages": [{"role": "user", "content": "今天几号？"}],
        "mode": "time",
        "must": ["2026"],
    },
    {
        "id": "who",
        "messages": [{"role": "user", "content": "你是谁？"}],
        "mode": "meta",
        "must": ["Qwen"],
    },
    {
        "id": "greet",
        "messages": [{"role": "user", "content": "你好"}],
        "mode": "greeting",
        "must": ["蓝桥杯"],
    },
    {
        "id": "tool_ping",
        "messages": [{"role": "user", "content": "测试串口"}],
        "must": ["OK PONG"],
    },
    {
        "id": "tool_adc",
        "messages": [{"role": "user", "content": "读取 ADC"}],
        "must": ["ADC"],
    },
]

SLOW = [
    {
        "id": "code_definition",
        "messages": [{"role": "user", "content": "代码是什么？"}],
        "mode": "concept",
        "must": ["代码"],
        "must_not": ["范围"],
    },
    {
        "id": "weather",
        "messages": [{"role": "user", "content": "天气怎么样？"}],
        "mode": "weather",
        "must": ["无法获取"],
        "must_not": ["℃", "北京", "2022"],
    },
    {
        "id": "nvic",
        "messages": [{"role": "user", "content": "NVIC 中断优先级怎么配置？"}],
        "mode": "knowledge",
        "must": ["NVIC", "优先级"],
    },
    {
        "id": "capture",
        "messages": [{"role": "user", "content": "定时器输入捕获怎么测频率？"}],
        "mode": "knowledge",
        "must": ["捕获", "PWM"],
    },
]

SEQUENCES = [
    {
        "id": "memory_7319",
        "turns": ["请记住数字 7319。", "我刚才让你记住的数字是多少？只回答数字。"],
        "must": ["7319"],
    },
    {
        "id": "follow_pwm",
        "turns": ["LED 在哪个引脚？", "那 PWM 呢？"],
        "must": ["PA2", "PA3"],
        "must_not": ["LED 引脚"],
    },
    {
        "id": "follow_usart",
        "turns": ["USART1 怎么配置？", "为什么收不到数据？"],
        "must": ["PA9", "PA10"],
    },
    {
        "id": "follow_code",
        "turns": ["LED 怎么点亮？", "那代码呢？"],
        "must": ["LED_Disp"],
    },
    {
        "id": "general_after_board",
        "turns": ["LED 怎么点亮？", "代码是什么？"],
        "must": ["指令"],
        "must_not": ["STM32G431RBT6 的代码"],
    },
    {
        "id": "topic_switch",
        "turns": ["天气怎么样？", "LED 怎么点亮？"],
        "must": ["PC8"],
    },
]


def run_case(case):
    try:
        result = chat(case["messages"])
        failures = check(
            result,
            must=case.get("must", ()),
            must_not=case.get("must_not", ()),
            mode=case.get("mode"),
        )
        return {"id": case["id"], "ok": not failures, "failures": failures, **result}
    except Exception as exc:
        return {"id": case["id"], "ok": False, "failures": [f"exception: {exc}"], "content": "", "mode": None, "latency": 0}


def run_sequence(case):
    messages = []
    result = None
    try:
        for turn in case["turns"]:
            messages.append({"role": "user", "content": turn})
            result = chat(messages)
            messages.append({"role": "assistant", "content": result["content"]})
        failures = check(
            result,
            must=case.get("must", ()),
            must_not=case.get("must_not", ()),
        )
        return {
            "id": case["id"], "ok": not failures, "failures": failures,
            "content": result["content"], "mode": result["mode"],
            "latency": round(sum([result["latency"]]), 2),
        }
    except Exception as exc:
        return {"id": case["id"], "ok": False, "failures": [f"exception: {exc}"], "content": "", "mode": None, "latency": 0}


def run_concurrency():
    queries = ["LED 怎么点亮？"] * 6 + ["今天几号？"] * 3 + ["你是谁？"] * 3
    started = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda q: chat([{"role": "user", "content": q}], timeout=30), queries))
    total = round(time.time() - started, 2)
    bad = [i for i, r in enumerate(results) if not r["content"]]
    return {
        "id": "concurrency_12",
        "ok": not bad,
        "failures": [f"empty:{i}" for i in bad],
        "content": f"{len(results)} requests in {total}s; max latency {max(r['latency'] for r in results)}s",
        "mode": None,
        "latency": total,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["fast", "slow", "multi", "concurrency", "all"], default="all")
    ap.add_argument("--out", default=str(Path.home() / "ai-terminal" / "logs"))
    args = ap.parse_args()

    results = []
    if args.group in ("fast", "all"):
        for c in FAST:
            results.append(run_case(c))
    if args.group in ("slow", "all"):
        for c in SLOW:
            results.append(run_case(c))
    if args.group in ("multi", "all"):
        for c in SEQUENCES:
            results.append(run_sequence(c))
    if args.group in ("concurrency", "all"):
        results.append(run_concurrency())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qa_stress_{args.group}_{stamp}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = sum(1 for r in results if r["ok"])
    for r in results:
        flag = "PASS" if r["ok"] else "FAIL"
        failures = (" | " + ", ".join(r["failures"])) if r["failures"] else ""
        preview = (r.get("content") or "").replace("\n", " ")[:120]
        print(f"{flag} {r['id']:<22} mode={r.get('mode')} {r.get('latency')}s{failures}")
        if preview:
            print(f"     {preview}")
    print(f"\nRESULT: {passed}/{len(results)} PASS; log={out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
