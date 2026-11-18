# 验证记录

> 每个里程碑必须留下可复现的命令与结果；未执行项标“未验证”。

## M0 环境与链路（2026-11-18）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| Pi 型号/内存 | `cat /proc/device-tree/model` / `free -h` | Raspberry Pi 4B Rev 1.5 / 8GB |
| 系统 | `cat /etc/os-release` | Ubuntu 20.04.6 LTS，kernel 5.4，aarch64 |
| 调试器 | `lsusb` / `udevadm info` | CMSIS-DAP `c251:f001`，`/dev/ttyACM0` |
| pyOCD | `pip3 install --user pyocd==0.36.0` | 0.36.0 |
| 探针识别 | `pyocd list` | `CMSIS-DAP-PL 1001A0000000` |
| 原固件备份 | `pyocd commander ... savemem 0x08000000 0x20000` | 131072B，sha256 `8dcdda9cfc78e7502bc045120405c201515c619f1cb420ecd285c88a8576eb8c` |
| LED 例程烧录 | `pyocd flash ... HAL_01_LED_TEST.hex` | 擦 3 扇区/写 5 页/2.82 kB/s，LED 闪烁 |
| UART 9600 | 烧 AF_PP 版 USART 例程后读 `/dev/ttyACM0` | 收到 `0000:Hello,world.`；发 5 字节 LED 闪 5 下 |

## M1 命令协议（2026-11-18）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| Keil 编译 | `UV4.exe -b firmware/MDK-ARM/HAL_01_LED_TEST.uvprojx` | **0 error / 0 warning** |
| 固件烧录 | `pyocd flash ... command_firmware.hex` | 擦 26 页/写 26 页/4.32 kB/s |
| `PING` | 持久串口会话发送 | `OK PONG` |
| `LED 1 1` / `LED 1 0` | 持久串口会话，停留 3 秒 | `OK LED 1 1` / `OK LED 1 0`；LED1 亮/灭正确 |
| `LEDALL FF` / `LEDALL 00` | 持久串口会话，停留 3 秒 | 全亮/全灭正确 |
| `LCDCLR` + `LCD 1 Hello` | 持久串口会话 | `OK LCDCLR` / `OK LCD`；LCD 清屏后仅第 1 行 `Hello` |
| `BAD` | 持久串口会话 | `ERR UNKNOWN` |
| `ADC?`（M1a） | 持久串口会话 | `ERR UNSUPPORTED ADC`（M1b 已补齐） |

### M1b ADC/PWM（2026-11-18）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| Keil 编译 | `UV4.exe -b ...` | **0 error / 0 warning** |
| 固件烧录 | `pyocd flash ...` | 擦 32 页/写 32 页/4.38 kB/s |
| 启动诊断 | LED 进度标记 | 4 颗 LED 全亮，初始化全部完成 |
| `ADC?` | 持久串口会话 | `OK ADC 1759`（12 位原始值） |
| `PWM 1 0/50/100` | 持久串口会话 | `OK PWM 1 0/50/100` |
| `PWM?` | 持久串口会话 | `OK PWM 1 0/50/100`，回读一致 |
| PWM 物理波形 | 万用表/示波器测 PA2 | **待 HIL 复测**（0%≈0V、50%≈1.65V、100%≈3.3V） |
| ADC 电位器变化 | 转动 PB12 电位器后复测 | **待 HIL 复测** |

### M2 后端（2026-11-18）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| FastAPI 启动 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | 启动成功 |
| 串口状态 | `GET /api/device/status` | `open: true`，9600 |
| PING | `GET /api/device/ping` | `{"ok": true, "response": "OK PONG"}` |
| LED | `POST /api/device/led` | `OK LED 1 1` / `OK LED 1 0` |
| LCD | `POST /api/device/lcd/clear` + `/lcd` | `OK LCDCLR` / `OK LCD` |
| ADC | `GET /api/device/adc` | `OK ADC 1759`，raw=1759 |
| PWM | `POST /api/device/pwm` | `OK PWM 1 50` |
| 静态前端 | `GET /`、`/app.js`、`/style.css` | 200 |
| 自然语言硬件 | `POST /api/chat`：让 LED1 亮起来 / LCD 显示 Hello / 读取 ADC / PWM 50 | 分别执行 `LED 1 1`、`LCD 1 Hello`、`ADC?`、`PWM 1 50` 并返回 ACK |

备注：串口在后台线程打开，服务启动可能延迟约 30 秒；启动完成后状态 `open: true`。

### M3 模型部署（已验证）

| 项 | 操作 | 结果 |
|---|---|---|
| 模型下载 | ModelScope `Qwen2.5-0.5B-Instruct-GGUF` q4_k_m | 469MB，已完成 |
| llama.cpp 源码 | GitHub master tarball（38MB） | 已解压 |
| CMake 兼容 | Pi CMake 3.16.3；UI 脚本要求 ≥3.18 | `LLAMA_BUILD_UI=OFF` + `ui.h` 空实现 + 移除 `llama-ui` 链接 |
| llama-server 构建 | `cmake --build ... --target llama-server -j4` | **成功** |
| 模型加载 | `llama-server -m qwen... --port 8080` | `model loaded`，`/health` OK |
| 推理基准 | “用三句话介绍树莓派”，max_tokens=128 | 38 completion tokens / 7.04s；**7.26 tok/s**；prompt 19.09 tok/s |
| FastAPI 流式 | `POST /api/chat` | SSE 逐 token 返回，中文正常 |

### M4 前端（基础版）

| 项 | 操作 | 结果 |
|---|---|---|
| 首页 | `GET /` | 返回 `index.html` |
| 静态资源 | `GET /app.js`、`/style.css` | 200 |
| 功能 | 流式聊天、会话列表、设备面板、图片上传 | 已实现 |
| 视觉验收 | 浏览器截图 | 待用户/浏览器验收 |

### M5 VLM（基础验证）

| 项 | 操作 | 结果 |
|---|---|---|
| 模型下载 | SmolVLM-500M-Instruct Q8 + mmproj Q8 | 417MB + 104MB |
| 服务启动 | `llama-server --mmproj ... --port 8081` | `loaded multimodal model`，`/health` OK |
| 测试图 | 320×240 白底红圆 + `HELLO` | — |
| 直接推理 | “请描述这张图片”，max_tokens=64 | **34.11s**，返回 ` HELLO` |
| FastAPI | `POST /api/vision` | `{"ok": true, "response": " HELLO"}` |
| 前端 | 图片上传 → `/api/vision` | 已接入，待浏览器验收 |

### 已知现象

- 板载 VCP 只接受**单次持久会话**；频繁 open/close 会导致写阻塞（`rc=124`）。
- 烧录/复位后 VCP 可能写阻塞，需要重新枚举 USB：

```bash
sudo sh -c 'echo 0 > /sys/bus/usb/devices/1-1.1/authorized; sleep 1; echo 1 > /sys/bus/usb/devices/1-1.1/authorized'
```

- 软件重新枚举后仍可能读到空 ACK；**物理拔插 USB 一次**最可靠（M1b 即通过物理拔插恢复）。
- 某些重新枚举后立即读取会得到空 ACK；以物理现象（LED/LCD）为准，并保持会话常开。
- 板载 VCP 不支持 115200；`stty -F /dev/ttyACM0 115200` 会阻塞。

## 待验证

| 里程碑 | 项 | 状态 |
|---|---|---|
| M1b | ADC/PWM 命令 | **已验证（串口）**；PWM 物理波形/电位器变化待 HIL |
| M2 | FastAPI 持久串口服务、`/api/device` | **已验证** |
| M3 | llama.cpp + Qwen2.5-0.5B/1.5B benchmark | **已验证**：Qwen2.5-0.5B 7.26 tok/s |
| M4 | 前端聊天 UI | 基础版已验证；视觉验收待做 |
| M5 | SmolVLM 上传图片问答 | **基础验证**：单图 34.11s，返回 `HELLO` |
| M6 | 整机联调 30 分钟稳定性 | 部分验证（自然语言硬件 + LLM 对话 + VLM 单图）；30 分钟稳定性待做 |
| M7 | 报告、图表、演示、PPT | 报告初稿已写；图表/PPT/Word 待做 |
