# firmware —— STM32G431 固件

目标板：蓝桥杯 CT117E-M4，STM32G431RBT6（128KB Flash / 32KB RAM），板载 CMSIS-DAP。

## 工程

- Keil MDK V5 工程：`MDK-ARM/HAL_01_LED_TEST.uvprojx`
- CubeMX 配置：`HAL_01_LED_TEST.ioc`（STM32Cube FW_G4 V1.6.1）
- 外设：USART1 PA9/PA10（9600 8N1）、LED PC8–PC15 + PD2 锁存、LCD、按键
- 命令解析：`Src/bsp/command/bsp_command.c`，头文件 `Inc/bsp_command.h`

## 编译

```bash
# Windows + Keil
UV4.exe -b firmware/MDK-ARM/HAL_01_LED_TEST.uvprojx -j0 -o build.log
```

当前基线：0 error / 0 warning。

## 烧录

```bash
# 树莓派，CMSIS-DAP + pyOCD
pyocd flash --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack \
  -t STM32G431RBTx -f 100k firmware/release/command_firmware.hex
pyocd reset --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack -t STM32G431RBTx
```

已验证固件与 sha256 见 `release/manifest.json`。

## 串口

- 设备：`/dev/ttyACM0`
- 波特率：**9600 8N1**（板载 VCP 不支持 115200，`stty` 会阻塞）
- 必须保持**单次持久会话**，不要每条命令重新 open/close
- 烧录后若 VCP 写阻塞，重新枚举 USB：

```bash
sudo sh -c 'echo 0 > /sys/bus/usb/devices/1-1.1/authorized; sleep 1; echo 1 > /sys/bus/usb/devices/1-1.1/authorized'
```

## 关键修正

- `Src/bsp/usart/bsp_usart.c` 的 USART1 引脚必须用 `GPIO_MODE_AF_PP`（推挽），原例程的 `AF_OD` 会导致 TX 无法被 VCP 读取。
- 主循环只保留 `CMD_Proc()`；原 `LCD_Proc()` 会持续写 `i num`，与命令控制冲突。

## 已实现命令

见 `docs/protocol.md`。M1 支持 `PING`、`LED`、`LEDALL`、`LED?`、`LCD`、`LCDCLR`；`ADC?` 与 `PWM` 暂返回 `ERR UNSUPPORTED`，待 M1b。
