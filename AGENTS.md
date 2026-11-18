# AGENTS.md

本文件是本工程的**项目上下文与工作准则**。任何 AI 接手本项目，先读本文件，再读 `HANDOFF.md`。状态只认文件，不认对话记忆。

## 项目定位

- **课程**：《嵌入式系统综合设计》课程设计，2 周，8–10 人一组。
- **题目方向**：基于树莓派 4B + STM32G431 的边缘多模态 AI 交互终端。
- **目标**：浏览器里的类 DeepSeek 聊天界面 → 树莓派本地 LLM/VLM 推理 → 通过 UART 命令或 ST-Link 烧录控制 STM32G431 开发板。
- **课程报告要求**：概述与背景、进度与分工、主要电子元件及个数、电路图与仿真结果、程序流程图、作品演示、不足与改进、实验总结、参考文献；第四、六点必须附图。

## 行为准则

- **一律中文回复**；保留必要英文术语与命令。
- **写入限制**：未经用户确认，只修改/新增项目文件夹内的文件；读取不限。
- **破坏性操作先确认**：删除、覆盖、格式化、烧录/擦除开发板等，先说明影响并取得确认。
- **不伪造验证**：没跑过的命令标“未验证”；HIL 没上板不得声称“通过”；静态检查不能冒充运行验证。
- **密钥红线**：真实令牌、密码、API Key 不写入任何文件、不拼进命令、不回显；一律通过环境变量提供。
- **硬件安全**：STM32 为 3.3V 逻辑，禁止把 5V 直接接 GPIO；外设大电流独立供电并与 Pi 共地；Pi 使用官方 5V/3A 电源。
- **烧录安全**：只允许烧录项目内固件白名单（manifest）中的 `.hex/.bin`；网页端不得上传任意固件；烧录前必须备份并二次确认。

## 已确认的技术方案

### 硬件

| 部件 | 型号/规格 | 状态 |
|---|---|---|
| 边缘计算 | 树莓派 4B Rev 1.5，8GB，Ubuntu 20.04 | 已实测 |
| 实时控制 | 蓝桥杯 CT117E-M4（STM32G431RBT6，LQFP64） | 已确认 |
| 调试/烧录 | **Keil CMSIS-DAP（VID:PID `c251:f001`）**，USB 接 Pi，`/dev/ttyACM0` | 探针已识别；SWD 待电源修复后复测 |
| 视觉 | 当前无摄像头；VLM 用网页上传图片 | 已确认 |
| 人机交互 | 5 寸 HDMI 触摸屏（可选）、USB 麦克风/喇叭（选做） | 待确认 |
| 传感器/执行器 | DHT11、BH1750、LED、风扇/继电器 | 待确认 |

### 软件

| 层 | 选型 | 状态 |
|---|---|---|
| 固件 | C + STM32CubeG4 HAL，Keil MDK 5（例程为 `MDK-ARM V5`） | 已确认 |
| 烧录 | 树莓派上 **pyOCD + Keil STM32G4 DFP**，经 CMSIS-DAP SWD；PC Keil 兜底 | 探针已识别，SWD 待复测 |
| 推理 | llama.cpp（GGUF Q4），Qwen2.5-0.5B/1.5B，SmolVLM-500M | 待 benchmark |
| 后端 | Python 3.8 + FastAPI + uvicorn + pyserial + SQLite | 已定方向；需固定兼容 3.8 的版本 |
| 前端 | PC 构建 Vue 3 + Vite + Tailwind，Pi 静态托管；无构建 HTML 兜底 | 推荐 |
| 通信 | 浏览器 ⇄ Pi：HTTP/SSE；Pi ⇄ STM32：UART 115200，换行 JSON 或带 CRC 帧 | 已定方向 |

### 双模式控制

1. **命令模式（主）**：STM32 常驻通用固件，Pi 发送 JSON 命令（LED/LCD/PWM/ADC/蜂鸣器/传感器读取），毫秒级、不复位。
2. **固件模式（演示）**：每个功能预编译 `.bin`，Pi 用 `st-flash` 烧录，板子复位后脱机运行；用于“拔掉树莓派也能跑”的演示。

## 技能使用

- 26 个相关技能在 `.agents/skills/`，索引见 `.agents/skills/README.md`。
- 做具体任务时调用对应技能，**不要**把技能正文里引用的 starter 路径当成当前工程已存在的文件；需要哪个目录/文件，到时按任务创建，或在项目内做等价适配。
- 技能与本文件冲突时，以本文件为准，并在交付说明里记录差异。
- 常见对应关系：
  - STM32 固件：`fw-init`、`driver-writer`、`build-flash`、`hil-test`、`toolchain-check`
  - 树莓派：`env-probe`、`sys-interface-design`、`native-build`、`runtime-verify`
  - 前端：`frontend-discovery`、`stack-advisor`、`page-composition`、`interaction-review`、`visual-acceptance`、`visual-direction`、`design-system-builder`
  - 后端/工程：`scaffold-generator`、`build-test-gate`、`code-review-checklist`、`release-iteration`
  - 硬件/报告：`solution-advisor`、`bom-selector`、`board-review-checklist`、`experiment-log`、`figure-check`、`cite-check`

## 工作流程（六阶段）

1. **需求确认**：缺前提（路径、硬件型号、验收标准、权限）时逐个提问，不替用户假设。
2. **制定计划**：背景、目标/非目标、实施步骤、验证方式、风险与回滚、涉及文件。
3. **计划确认**：逐条与用户确认后再动代码。
4. **执行**：按任务清单小步推进；遇到计划外情况先暂停。
5. **验证**：实际执行命令；区分宿主单测、静态检查、HIL 三层证据。
6. **汇报**：先结论后过程；写明做了什么、验证结果、跳过项；更新 `HANDOFF.md`。

## 启动编码时再建的目录

以下结构是建议，不是当前已存在的文件；等对应任务开始时按需创建：

```text
fw/          STM32 应用层（app/、board/、main.c）
drivers/     STM32 外设驱动（led/lcd/uart/adc/pwm）
firmware/    预编译 .bin + manifest.json（烧录白名单）
pi/          树莓派后端：FastAPI、llama.cpp、systemd
web/         Vue 3 聊天界面
hardware/    原理图、BOM、仿真、接线
docs/        课设报告、实验记录、图表、交付/迭代文档
tooling/     工具链契约、烧录/HIL 指南
```

## 待确认清单

| # | 事项 | 影响 |
|---|---|---|
| 1 | **树莓派供电（Under-voltage）** | 决定 CMSIS-DAP 烧录、LLM 高负载稳定性 | 换官方 5V/3A 电源；这是当前硬阻塞 |
| 2 | 板载 CMSIS-DAP VCP 是否接 USART1 | 决定命令模式走 `/dev/ttyACM0` 还是 USB-TTL | 烧 USART 测试固件后读串口 |
| 3 | Pi 侧烧录是否作为课程必须项 | 决定 pyOCD 烧录是 P0 还是 P1/P2 | 电源修复后复测；PC Keil 兜底 |
| 4 | 指导老师是否强制 Proteus 仿真/焊接/自制 PCB | 决定硬件工作量与报告“仿真结果”写法 | 先按“开发板 + 扩展板 + 关键电路仿真”准备 |
| 5 | 前端 Vue 构建版还是无构建 HTML | 决定前端交付方式 | 推荐 PC 构建 Vue，Pi 静态托管 |
| 6 | 最终模型组合 | 决定 Pi 内存分配与演示速度 | 先按 0.5B 路由 + 1.5B 对话 + SmolVLM-500M 选做 |
| 7 | 8–10 人组内分工 | 决定任务拆分与报告分工表 | 按硬件/固件/模型/后端/前端/测试文档拆分 |

## 编码与命名

- 文件编码 UTF-8，换行 LF；Markdown 不裁剪行尾空格；CSV 用 UTF-8 with BOM（Excel 直开）。
- Python 4 空格；JS/TS/JSON 2 空格；C 语言按 STM32 工程惯例。
- 路径、端口、串口号、模型名、烧录地址进配置，不硬编码在业务代码里。
- 串口协议字段统一小写下划线；固件 manifest 字段与脚本引擎字段保持一致。
