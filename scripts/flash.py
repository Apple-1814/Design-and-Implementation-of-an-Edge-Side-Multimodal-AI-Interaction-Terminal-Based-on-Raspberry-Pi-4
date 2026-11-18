#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flash a whitelisted firmware from firmware/release/manifest.json via pyOCD.

Run on the Raspberry Pi:
    python3 scripts/flash.py --firmware command_firmware --yes
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "firmware" / "release" / "manifest.json"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", default="command_firmware")
    parser.add_argument("--pack", default=str(Path.home() / "Keil.STM32G4xx_DFP.1.6.0.pack"))
    parser.add_argument("--target", default="STM32G431RBTx")
    parser.add_argument("--frequency", default="100k")
    parser.add_argument("--yes", action="store_true", help="skip confirmation")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"manifest not found: {MANIFEST}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next((x for x in manifest.get("firmwares", []) if x.get("id") == args.firmware), None)
    if entry is None:
        print(f"firmware {args.firmware!r} not in manifest", file=sys.stderr)
        return 2
    if entry.get("status") != "ready" or not entry.get("bin"):
        print(f"firmware {args.firmware!r} is not ready", file=sys.stderr)
        return 2

    bin_path = ROOT / "firmware" / "release" / entry["bin"]
    if not bin_path.is_file():
        print(f"binary not found: {bin_path}", file=sys.stderr)
        return 2
    digest = sha256(bin_path)
    expected = entry.get("sha256")
    if expected and digest != expected:
        print(f"sha256 mismatch: {digest} != {expected}", file=sys.stderr)
        return 2

    print(f"firmware : {entry['name']} ({bin_path.name})")
    print(f"sha256   : {digest}")
    print(f"target   : {args.target}  pack: {args.pack}")
    if not args.yes:
        answer = input("Type 'yes' to flash: ").strip().lower()
        if answer != "yes":
            print("cancelled")
            return 1

    flash_cmd = [
        "pyocd", "flash", "--pack", args.pack, "-t", args.target,
        "-f", args.frequency, str(bin_path),
    ]
    reset_cmd = ["pyocd", "reset", "--pack", args.pack, "-t", args.target]
    print("+", " ".join(flash_cmd))
    subprocess.run(flash_cmd, check=True)
    print("+", " ".join(reset_cmd))
    subprocess.run(reset_cmd, check=True)
    print("flash OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
