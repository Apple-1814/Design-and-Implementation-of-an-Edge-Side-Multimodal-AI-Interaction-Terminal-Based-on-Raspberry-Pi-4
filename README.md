# 基于树莓派 4B 与 STM32G431 的端侧多模态 AI 交互终端

《嵌入式系统综合设计》课程设计项目。树莓派本地运行小参数 LLM/VLM，浏览器提供类 DeepSeek 聊天界面，通过 UART 控制 STM32G431 开发板的 LED、LCD、ADC、PWM。

## 1. 系统架构

```text
浏览器（PC / 平板）
   │ HTTP + SSE
   ▼
树莓派 4B：FastAPI
   ├─ llama.cpp：Qwen2.5-0.5B/1.5B、SmolVLM-500M
   ├─ 脚本引擎：自然语言 → 结构化命令
   ├─ 串口服务：/dev/ttyACM0 @ 9600
   └─ 烧录服务：pyOCD + CMSIS-DAP（P1/P2）
   │ USB（CMSIS-DAP VCP）
   ▼
STM32G431（蓝桥杯 CT117E-M4）
   通用固件：命令解析 + LED/LCD/ADC/PWM
```

## 2. 当前状态

| 里程碑 | 状态 |
|---|---|
| M0 环境与链路 | ✅ Pi 4B 8GB、Ubuntu 20.04、CMSIS-DAP 烧录、9600 UART 双向、原固件备份 |
| M1 固件命令协议 | ✅ M1a/M1b 已验证：PING/LED/LCD/LCDCLR/ADC/PWM（串口）；PWM 物理波形待 HIL |
| M2 Pi 后端 | ✅ 已实现：`/api/device/*` + 持久串口 |
| M3 LLM 部署 | ✅ Qwen2.5-0.5B，7.26 tok/s |
| M4 前端 | ✅ 基础版：聊天 + 设备面板；视觉验收待做 |
| M5 VLM | ✅ 基础版：SmolVLM-500M，单图 34s |
| M6 整机联调 | 🚧 自然语言/LLM/VLM 已通；30 分钟稳定性待做 |
| M7 报告与交付 | 🚧 报告初稿已写；图表/Word/PPT 待做 |

## 3. 目录

```text
firmware/        STM32G431 Keil 工程（HAL + BSP + 命令解析）
pi/              树莓派后端：FastAPI、llama.cpp、串口服务
web/             前端聊天界面
hardware/        BOM、接线图、原理图、仿真
docs/            协议、验证记录、报告大纲
scripts/         烧录、串口测试、部署辅助脚本
计划书.md         全流程计划书
HANDOFF.md       当前状态与下一步
```

## 4. 构建与烧录

### 固件

```bash
# 用 Keil MDK 打开
firmware/MDK-ARM/HAL_01_LED_TEST.uvprojx
# 编译后生成
firmware/MDK-ARM/HAL_01_LED_TEST/HAL_01_LED_TEST.hex
```

树莓派侧烧录（CMSIS-DAP + pyOCD）：

```bash
pyocd flash --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack \
  -t STM32G431RBTx -f 100k firmware/MDK-ARM/HAL_01_LED_TEST/HAL_01_LED_TEST.hex
pyocd reset --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack -t STM32G431RBTx
```

### 串口

```bash
# 板载 CMSIS-DAP VCP
stty -F /dev/ttyACM0 9600
cat /dev/ttyACM0
```

## 5. 验证方式

每个里程碑按 `计划书.md` 的验收标准实测；记录写入 `HANDOFF.md` 与 `docs/verification.md`。未验证项不得写成“已完成”。

## 6. 关键约束

- 板载 VCP 仅支持 9600；115200 会阻塞，需 USB-TTL。
- USART1 TX 必须使用 `GPIO_MODE_AF_PP`，不能用 `AF_OD`。
- 网页端不得上传任意固件；烧录只允许 `firmware/release/manifest.json` 白名单。
- 本地模型推理优先，不依赖云端 API。
