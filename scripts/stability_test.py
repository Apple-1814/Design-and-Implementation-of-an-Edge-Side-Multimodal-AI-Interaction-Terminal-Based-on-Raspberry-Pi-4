#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""30-minute stability test for the edge AI terminal.

Runs on the Raspberry Pi; calls the FastAPI endpoints over localhost.
Records hardware commands, LLM chat, VLM image Q&A, memory and temperature.
"""
import argparse
import datetime
import json
import os
import subprocess
import time
import urllib.error
import urllib.request


def log(line):
    print(line, flush=True)


def http_json(base, path, method="GET", payload=None, timeout=90):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def mem_free_mb():
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return -1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--duration", type=int, default=1800)
    parser.add_argument("--image", default="/home/apple/ai-terminal/test.png")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--summary", default="/home/apple/ai-terminal/logs/stability_summary.json")
    args = parser.parse_args()

    started = time.time()
    loops = 0
    failures = 0
    checks = 0
    max_temp = -1.0
    min_free = 10 ** 9
    log(f"START {datetime.datetime.now().isoformat(timespec='seconds')} duration={args.duration}s")

    while time.time() - started < args.duration:
        loops += 1
        cycle_start = time.time()
        tasks = [
            ("ping", "/api/device/ping", "GET", None),
            ("led_on", "/api/device/led", "POST", {"id": 1, "on": True}),
            ("led_off", "/api/device/led", "POST", {"id": 1, "on": False}),
            ("adc", "/api/device/adc", "GET", None),
            ("pwm", "/api/device/pwm", "POST", {"ch": 1, "duty": (loops * 10) % 101}),
        ]
        for name, path, method, payload in tasks:
            checks += 1
            try:
                status, body = http_json(args.base, path, method, payload, timeout=30)
                ok = status == 200 and '"ok":true' in body.replace(" ", "")
                if not ok:
                    failures += 1
                log(f"HW {name} status={status} ok={ok} body={body[:120]}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log(f"HW {name} ERROR {type(exc).__name__}: {exc}")

        if loops % 6 == 0:
            checks += 1
            try:
                payload = {"messages": [{"role": "user", "content": "用一句话介绍你自己"}],
                           "max_tokens": 32}
                status, body = http_json(args.base, "/api/chat", "POST", payload, timeout=90)
                ok = status == 200 and "choices" in body
                if not ok:
                    failures += 1
                log(f"LLM status={status} ok={ok} body={body[:160]}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log(f"LLM ERROR {type(exc).__name__}: {exc}")

        if loops % 60 == 0 and os.path.isfile(args.image):
            checks += 1
            try:
                result = subprocess.run(
                    [
                        "curl", "-sS", "--max-time", "120",
                        "-F", f"file=@{args.image}",
                        "-F", "prompt=请描述这张图片",
                        args.base + "/api/vision",
                    ],
                    capture_output=True, text=True, timeout=130,
                )
                body = result.stdout.strip()
                ok = result.returncode == 0 and '"ok":true' in body.replace(" ", "")
                if not ok:
                    failures += 1
                log(f"VLM rc={result.returncode} ok={ok} body={body[:200]}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log(f"VLM ERROR {type(exc).__name__}: {exc}")

        free_mb = mem_free_mb()
        tc = temp_c()
        max_temp = max(max_temp, tc)
        min_free = min(min_free, free_mb)
        log(f"MEM free={free_mb}MB TEMP={tc:.1f}C")

        elapsed = time.time() - cycle_start
        sleep_for = args.interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    summary = {
        "started": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "duration_s": round(time.time() - started, 1),
        "loops": loops,
        "checks": checks,
        "failures": failures,
        "max_temp_c": round(max_temp, 1),
        "min_free_mb": min_free,
    }
    os.makedirs(os.path.dirname(args.summary), exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log("SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
