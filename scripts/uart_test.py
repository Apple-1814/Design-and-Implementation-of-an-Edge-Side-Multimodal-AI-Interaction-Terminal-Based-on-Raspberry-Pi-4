#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent UART command test for the STM32G431 protocol.

Run on the Raspberry Pi:
    python3 scripts/uart_test.py --port /dev/ttyACM0 --baud 9600
"""
import argparse
import time

import serial

COMMANDS = [
    "PING",
    "LED 1 1",
    "LED 1 0",
    "LEDALL FF",
    "LEDALL 00",
    "ADC?",
    "PWM 1 50",
    "PWM?",
    "LCDCLR",
    "LCD 1 Hello",
    "BAD",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--wait", type=float, default=0.8)
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=1.0) as ser:
        ser.reset_input_buffer()
        for cmd in COMMANDS:
            ser.write((cmd + "\n").encode("ascii"))
            ser.flush()
            deadline = time.time() + args.wait
            data = b""
            while time.time() < deadline:
                chunk = ser.read(256)
                if chunk:
                    data += chunk
            print(f"{cmd:<14} -> {data.decode('utf-8', errors='replace').strip()!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
