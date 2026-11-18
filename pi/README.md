# pi —— 树莓派后端（M2）

计划使用 **FastAPI + pyserial**，保持一个常开的串口句柄，把已验证的文本命令封装成 HTTP 接口。

## 计划接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/device/ping` | GET | 发送 `PING`，返回 `OK PONG` |
| `/api/device/led` | POST | `{id, on}` → `LED <id> <0\|1>` |
| `/api/device/lcd` | POST | `{line, text}` → `LCD <line> <text>` |
| `/api/device/lcd/clear` | POST | `LCDCLR` |
| `/api/device/status` | GET | 串口状态、最近响应 |
| `/api/chat` | POST | SSE 流式对话（M3） |
| `/api/scripts` | GET/POST | 脚本选择与参数（M3/M4） |
| `/api/flash` | POST | pyOCD 烧录（P2，白名单） |

## 串口约束

- `/dev/ttyACM0`，9600 8N1，**单次持久打开**。
- 烧录后若写阻塞，重新枚举 USB：

```bash
sudo sh -c 'echo 0 > /sys/bus/usb/devices/1-1.1/authorized; sleep 1; echo 1 > /sys/bus/usb/devices/1-1.1/authorized'
```

- 不要使用 `stty 115200`（会阻塞）。

## 运行环境

- Ubuntu 20.04，Python 3.8
- 建议 venv + 固定版本：FastAPI 0.110.x、uvicorn 0.27.x、pydantic 2.6.x、pyserial 3.5
- 启动：`uvicorn app.main:app --host 0.0.0.0 --port 8000`

## 状态

M2 未开始。先实现串口服务与 `/api/device/*`，再接 LLM。
