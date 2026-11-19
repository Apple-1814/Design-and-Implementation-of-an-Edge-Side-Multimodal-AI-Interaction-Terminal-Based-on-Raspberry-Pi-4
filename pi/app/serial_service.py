"""Persistent serial service for the STM32 command protocol.

The board's CMSIS-DAP VCP only tolerates a single long-lived open; do not
open/close the port per request. Opening is done in a background thread so a
blocked VCP cannot block FastAPI startup. Device endpoints return 503 while
the port is still opening; use /api/device/reconnect after a replug.
"""
import os
import subprocess
import threading
import time
from typing import Optional

import serial


def _wifi_ip() -> Optional[str]:
    """Return the current wlan0 IPv4 address, if the Pi is on Wi-Fi."""
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "wlan0"],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        )
        for token in out.split():
            if "/" in token and token[0].isdigit():
                return token.split("/", 1)[0]
    except Exception:
        pass
    return None


class SerialService:
    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 9600) -> None:
        self.port = port
        self.baud = baud
        # Prefer the Wi-Fi address so other classroom PCs can reach the UI;
        # fall back to the fixed Ethernet demo address.
        self.demo_ip = _wifi_ip() or os.environ.get("DEMO_IP", "192.168.49.50")
        self._lock = threading.RLock()
        self._ser: Optional[serial.Serial] = None
        self._opening = False
        self.last_error: str = ""
        self.last_response: str = ""
        self._start_open()

    def _start_open(self) -> None:
        with self._lock:
            if self._ser is not None or self._opening:
                return
            self._opening = True
        threading.Thread(target=self._open_worker, daemon=True).start()

    def _open_worker(self) -> None:
        try:
            while True:
                if self._open():
                    # Show the fixed demo IP on the board LCD for classroom use.
                    try:
                        self.command("LCDCLR", wait=1.2)
                        self.command(f"LCD 1 {self.demo_ip}", wait=0.8)
                        self.command("LCD 2 READY", wait=0.8)
                    except Exception:
                        pass
                    break
                time.sleep(2.0)
        finally:
            with self._lock:
                self._opening = False

    def _open(self) -> bool:
        try:
            ser = serial.Serial(
                self.port,
                self.baud,
                timeout=0.2,
                write_timeout=1.0,
            )
            time.sleep(0.2)
            ser.reset_input_buffer()
            with self._lock:
                self._ser = ser
                self.last_error = ""
            return True
        except Exception as exc:  # noqa: BLE001 - report the real cause
            with self._lock:
                self._ser = None
                self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def reconnect(self) -> bool:
        with self._lock:
            self._close_locked()
        self._start_open()
        return True

    def _close_locked(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def command(self, command: str, wait: float = 0.8) -> str:
        """Send one line and collect the response for ``wait`` seconds."""
        with self._lock:
            if not self.is_open():
                if not self._opening:
                    self._start_open()
                raise RuntimeError("serial not ready (opening or blocked)")
            try:
                self._ser.reset_input_buffer()
                self._ser.write((command.strip() + "\n").encode("ascii"))
                self._ser.flush()
                deadline = time.time() + wait
                data = b""
                while time.time() < deadline:
                    chunk = self._ser.read(256)
                    if chunk:
                        data += chunk
                text = data.decode("utf-8", errors="replace").strip()
                self.last_response = text
                return text
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._close_locked()
                raise

    def status(self) -> dict:
        return {
            "port": self.port,
            "baud": self.baud,
            "open": self.is_open(),
            "opening": self._opening,
            "last_error": self.last_error,
            "last_response": self.last_response,
            "demo_ip": self.demo_ip,
            "access_url": f"http://{self.demo_ip}:8000/",
        }
