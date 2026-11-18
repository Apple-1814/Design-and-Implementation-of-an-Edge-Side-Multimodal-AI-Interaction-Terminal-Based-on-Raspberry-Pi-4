# scripts —— 烧录与串口测试脚本

## 计划

| 脚本 | 功能 |
|---|---|
| `flash.py` | 读取 `firmware/release/manifest.json`，校验 sha256，pyOCD 烧录 + 复位 |
| `uart_test.py` | 常开 `/dev/ttyACM0`，逐条发送协议命令并打印 ACK |
| `start_all.sh` | 后台启动 LLM(8080) + VLM(8081) + FastAPI(8000) |
| `run_llama.sh` | 启动 Qwen2.5-0.5B `llama-server`（127.0.0.1:8080） |
| `run_vlm.sh` | 启动 SmolVLM-500M 多模态 `llama-server`（127.0.0.1:8081） |
| `bench_llm.py` | 调用 `/v1/chat/completions`，输出耗时/tok/s/内容 |
| `stability_test.py` | 30 分钟稳定性测试（硬件/LLM/VLM/内存/温度） |
| `make_figures.py` / `make_ui_mock.py` | 生成报告插图与界面布局示意 |
| `build_report_docx.py` / `build_ppt.py` | 生成 Word 报告与答辩 PPT |

## 模型运行

```bash
# LLM（8080）
bash scripts/run_llama.sh

# VLM（8081，需 llama-server 支持 mtmd）
bash scripts/run_vlm.sh

# 基准
python3 scripts/bench_llm.py --url http://127.0.0.1:8080 \
  --prompt "用三句话介绍树莓派" --max-tokens 128
```

## 设备、稳定性与一键启动

```bash
# 白名单烧录（校验 sha256）
python3 scripts/flash.py --firmware command_firmware --yes

# 串口命令逐条测试（持久会话）
python3 scripts/uart_test.py --port /dev/ttyACM0 --baud 9600

# 30 分钟稳定性（硬件 + LLM + VLM + 内存/温度）
python3 scripts/stability_test.py --duration 1800

# 一键启动 LLM + VLM + FastAPI
ROOT=$HOME/ai-terminal bash scripts/start_all.sh
```

## 当前手动命令

```bash
# 烧录
pyocd flash --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack \
  -t STM32G431RBTx -f 100k firmware/release/command_firmware.hex
pyocd reset --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack -t STM32G431RBTx

# VCP 写阻塞时重新枚举
sudo sh -c 'echo 0 > /sys/bus/usb/devices/1-1.1/authorized; sleep 1; echo 1 > /sys/bus/usb/devices/1-1.1/authorized'

# 串口
python3 -c "import serial; s=serial.Serial('/dev/ttyACM0',9600,timeout=1); s.write(b'PING\\n'); print(s.read(64))"
```

## 约束

- 串口必须单次持久打开，禁止每条命令重新 open。
- 烧录只允许 `firmware/release/manifest.json` 中的 `status=ready` 固件。
- 不把密码、token 写入脚本或日志。
