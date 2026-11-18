# scripts —— 烧录与串口测试脚本

## 计划

| 脚本 | 功能 |
|---|---|
| `flash.py` | 读取 `firmware/release/manifest.json`，校验 sha256，pyOCD 烧录 + 复位 + 重新枚举 USB |
| `uart_test.py` | 常开 `/dev/ttyACM0`，逐条发送协议命令并打印 ACK |
| `deploy_pi.sh` | 安装 Python 依赖、部署 FastAPI、配置 systemd（M2） |

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
