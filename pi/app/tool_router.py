"""Deterministic Chinese intent router for hardware commands.

Small local models are unreliable at strict function calling, so explicit
hardware requests are handled by rules first; everything else goes to the LLM.
"""
import re
from typing import Callable, Optional


def _send(send: Callable[[str], str], command: str, wait: float = 0.8) -> str:
    try:
        return send(command, wait=wait)
    except Exception as exc:  # noqa: BLE001
        return f"ERR serial: {type(exc).__name__}: {exc}"


def route_tool(text: str, send: Callable[..., str]) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    # LED: "LED1 开/关"、"打开 LED 2"、"关灯"
    m = re.search(r"led\s*([1-8])", low)
    if m:
        led = int(m.group(1))
        off = bool(re.search(r"关|灭|关闭|off", low))
        on = bool(re.search(r"开|亮|点亮|打开|on", low))
        if on or off:
            value = 0 if off else 1
            cmd = f"LED {led} {value}"
            return f"已执行 `{cmd}` → {_send(send, cmd, 0.5)}"
    if re.search(r"开灯|亮灯|把灯打开|打开灯", t):
        return f"已执行 `LED 1 1` → {_send(send, 'LED 1 1', 0.5)}"
    if re.search(r"关灯|灭灯|把灯关掉|关闭灯", t):
        return f"已执行 `LED 1 0` → {_send(send, 'LED 1 0', 0.5)}"

    # LCD: "在 LCD 上显示 Hello"、"屏幕显示：你好"
    m = re.search(r"(?:lcd|屏幕|显示屏|液晶).*?(?:显示|写|show)\s*[:：]?\s*(.+)$", t, re.I)
    if m:
        content = m.group(1).strip().strip("\"'“”")
        content = content[:31] or "Hello"
        _send(send, "LCDCLR", 1.5)
        cmd = f"LCD 1 {content}"
        return f"已执行 `{cmd}` → {_send(send, cmd, 1.0)}"
    if re.search(r"清屏|清除屏幕|clear", low):
        return f"已执行 `LCDCLR` → {_send(send, 'LCDCLR', 1.5)}"

    # ADC / 电位器
    if re.search(r"adc|电位器|光照|传感器|采样", low):
        return f"ADC 原始值：{_send(send, 'ADC?', 0.8)}"

    # PWM / 占空比
    m = re.search(r"(?:pwm|占空比).*?(\d{1,3})", low)
    if m:
        duty = max(0, min(100, int(m.group(1))))
        cmd = f"PWM 1 {duty}"
        return f"已执行 `{cmd}` → {_send(send, cmd, 0.5)}"

    # 连通性
    if re.search(r"ping|在吗|测试串口", low):
        return f"`PING` → {_send(send, 'PING', 1.0)}"

    return None
