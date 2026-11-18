# pi —— 树莓派后端（M2）

FastAPI + pyserial，保持一个常开的串口句柄，把 M1 的文本命令封装为 HTTP 接口。

## 运行

```bash
cd pi
bash run.sh
# 或
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://<树莓派IP>:8000/` 查看服务状态。

## 接口

| 接口 | 方法 | 命令 |
|---|---|---|
| `/api/info` | GET | 服务与串口状态 |
| `/api/device/status` | GET | 串口状态 |
| `/api/device/reconnect` | POST | 重新打开串口 |
| `/api/device/ping` | GET | `PING` |
| `/api/device/led` | POST | `LED <id> <0\|1>` |
| `/api/device/lcd` | POST | `LCD <line> <text>` |
| `/api/device/lcd/clear` | POST | `LCDCLR` |
| `/api/device/adc` | GET | `ADC?` |
| `/api/device/pwm` | POST | `PWM <ch> <duty>` |
| `/api/chat` | POST | SSE 聊天；先走中文硬件规则，未命中转发 llama-server |
| `/api/scripts` | GET | 预设脚本列表 |

请求示例：

```bash
curl http://127.0.0.1:8000/api/device/ping
curl -X POST http://127.0.0.1:8000/api/device/led \
  -H 'Content-Type: application/json' -d '{"id":1,"on":true}'
curl -X POST http://127.0.0.1:8000/api/device/lcd \
  -H 'Content-Type: application/json' -d '{"line":1,"text":"Hello"}'
curl http://127.0.0.1:8000/api/device/adc
curl -X POST http://127.0.0.1:8000/api/device/pwm \
  -H 'Content-Type: application/json' -d '{"ch":1,"duty":50}'
```

## 串口约束

- `/dev/ttyACM0`，9600 8N1，**单次持久打开**。
- 烧录/复位后 VCP 可能写阻塞：物理拔插 USB 一次，或重新枚举后重启服务。
- 不要使用 `stty 115200`（会阻塞）。

## 自然语言控制

`POST /api/chat` 先走 `tool_router.py` 的中文规则（LED/LCD/ADC/PWM/PING）；未命中才转发 `llama-server`。这样小模型不稳定时，硬件闭环仍可演示。

## 状态

M2 已验证；M4 基础前端已接入；M3 llama.cpp 构建中；M5 待做。
