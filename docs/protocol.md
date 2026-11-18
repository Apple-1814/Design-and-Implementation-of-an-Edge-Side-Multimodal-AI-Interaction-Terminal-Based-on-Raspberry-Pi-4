# UART 命令协议 v0.1

## 物理层

| 项 | 值 |
|---|---|
| 设备 | `/dev/ttyACM0`（板载 CMSIS-DAP VCP） |
| 波特率 | **9600 8N1**（VCP 不支持 115200；不要用 `stty` 强改） |
| 流控 | 无 |
| 会话 | **单次持久打开**，不要每条命令 open/close |
| 编码 | ASCII/UTF-8，行尾 `\n`，`\r` 忽略 |
| 最大行 | 127 字符，超出返回 `ERR OVERFLOW` |

烧录后若 VCP 写阻塞，先重新枚举 USB：

```bash
sudo sh -c 'echo 0 > /sys/bus/usb/devices/1-1.1/authorized; sleep 1; echo 1 > /sys/bus/usb/devices/1-1.1/authorized'
```

## 命令

| 命令 | 响应 | 说明 |
|---|---|---|
| `PING` | `OK PONG` | 连通性测试 |
| `LED?` | `OK LED <hex>` | 查询当前 LED 位图 |
| `LED <id> <0\|1>` | `OK LED <id> <0\|1>` | id 1–8，置位/清零对应 LED |
| `LEDALL <hex>` | `OK LEDALL <hex>` | 直接设置 8 位 LED 位图 |
| `LCD <line> <text>` | `OK LCD` | line 0–9，写入对应行 |
| `LCDCLR` | `OK LCDCLR` | 清屏（白底） |
| `ADC?` | `ERR UNSUPPORTED ADC` | M1b 实现 |
| `PWM <ch> <duty>` | `ERR UNSUPPORTED PWM` | M1b 实现 |
| 其它 | `ERR UNKNOWN` | 未知命令 |

错误码：

| 响应 | 含义 |
|---|---|
| `ERR LED_ID` | LED id 不在 1–8 |
| `ERR LCD_LINE` | LCD 行号不在 0–9 |
| `ERR OVERFLOW` | 一行超过 127 字符 |
| `ERR UNSUPPORTED ...` | 功能尚未实现 |

## 示例

```text
PING                 -> OK PONG
LED 1 1              -> OK LED 1 1
LED 1 0              -> OK LED 1 0
LEDALL FF            -> OK LEDALL FF
LCDCLR               -> OK LCDCLR
LCD 1 Hello          -> OK LCD
ADC?                 -> ERR UNSUPPORTED ADC
BAD                  -> ERR UNKNOWN
```

## 设计说明

- 串口保持文本行协议，便于调试；后端 FastAPI 对 LLM 暴露 JSON，由后端负责 JSON ↔ 文本命令转换。
- 命令解析在 `firmware/Src/bsp/command/bsp_command.c`；中断只做字节入环形缓冲，解析在主循环 `CMD_Proc()`。
- `LED`/`LEDALL` 维护一个 8 位状态，调用 `LED_Disp()` 锁存输出；`LCDCLR` 调用 `LCD_Clear(White)`。
- M1 不实现 ADC/PWM；M1b 从 `HAL_07_ADC1_TEST`、`HAL_10_1_Channel_PWM_Frq_TEST` 移植对应 BSP 后补上。
