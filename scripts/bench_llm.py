#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark llama-server /v1/chat/completions.

Usage:
    python3 scripts/bench_llm.py --url http://127.0.0.1:8080 \
        --prompt "用三句话介绍树莓派" --max-tokens 128
"""
import argparse
import json
import time
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--prompt", default="用三句话介绍树莓派。")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    payload = {
        "model": "qwen",
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 0.7,
        "stream": False,
    }
    req = urllib.request.Request(
        args.url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    with urllib.request.urlopen(req, timeout=args.timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - started

    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass

    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens") or 0
    tok_s = completion_tokens / elapsed if completion_tokens else None
    timings = data.get("timings") or {}

    result = {
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tok_s_total": round(tok_s, 2) if tok_s else None,
        "predicted_per_second": timings.get("predicted_per_second"),
        "prompt_per_second": timings.get("prompt_per_second"),
        "content": content[:500],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
