# HANDOFF — 当前状态

> 覆盖式维护，≤200 行。详细方案见 `计划书.md`。
> 更新时间：2026-11-18 12:35

## 当前阶段

实测评估完成；CMSIS-DAP 烧录、9600 UART、**M1a 命令协议（PING/LED/LCD/LCDCLR）** 均已验证。下一步 M1b（ADC/PWM）与 M2（FastAPI 后端）。

## 已完成

- 读取并解读《嵌入式系统综合设计》任务书：2 周、8–10 人一组、报告需电路图 + 仿真 + 流程图 + 作品照片。
- 导入 26 个相关技能到 `.agents/skills/`，附索引。
- 找到 Pi：`192.168.49.50`（eth0 直连 PC），SSH 登录成功（用户 `apple`）。
- 实测 Pi：Raspberry Pi 4B Rev 1.5，**8GB RAM**，Ubuntu 20.04.6 LTS，kernel 5.4，4×Cortex-A72 1.8GHz，29GB SD（剩 15GB），Python 3.8.10。
- 实测外设：`/dev/ttyACM0`（CMSIS-DAP CDC），`apple` 在 `dialout/video/i2c/spi/gpio/plugdev/sudo`；无摄像头。
- 实测调试器：**Keil CMSIS-DAP（VID:PID `c251:f001`）**，不是 ST-Link；`pyocd list` 可识别。
- 安装 pyOCD 0.36.0（用户级），添加 `/etc/udev/rules.d/99-cmsis-dap.rules`，`/dev/hidraw0` 权限 0666。
- 确认 pyOCD 目标名 `STM32G431RBTx` 可用；上传 `HAL_01_LED_TEST.hex` 与 97MB Keil STM32G4 DFP 包。
- **换官方电源后**：无 Under-voltage；备份 128KB（sha256 `8dcdda9c...`）；烧 LED 例程成功（擦 3 扇区/写 5 页/2.82 kB/s），LED 正常闪烁。
- **UART 双向验证通过（9600）**：
  - 原始 USART 例程把 USART1 TX 配成 `GPIO_MODE_AF_OD`，Pi 侧读不到数据；
  - 复制例程到 `.tmp/HAL_05_USART_TEST_PP`，改为 `GPIO_MODE_AF_PP` + `GPIO_PULLUP`，Keil 命令行重编译（0 error/0 warning）；
  - 烧录后串口读到 `0000:Hello,world.`、`0001:Hello,world.`……；
  - Pi→板子发 5 字节，板子 8 个 LED 闪 5 下，接收链路正常。
  - **板载 VCP 可用，无需 USB-TTL。**
- **115200 尝试失败**：`stty -F /dev/ttyACM0 115200` 阻塞（多个进程卡住），VCP 不响应线码设置；已回退 9600 AF_PP 固件，串口恢复输出 `0000:Hello,world.`。命令链路保持 9600。
- 检查蓝桥杯例程：STM32G431RBT6 / LQFP64 / CubeMX + Keil MDK V5 / HAL；BSP 含 LED/KEY/LCD/USART/IIC/ADC/PWM/RTC；PC 已装 Keil。
- 输出 `计划书.md`（实测修正版）。
- **M1a 命令协议完成**：Keil 0 error / 0 warning；烧录 26 页；`PING`→`OK PONG`、`LED 1 1/0`、`LEDALL FF/00`、`LCDCLR`+`LCD 1 Hello`、`BAD`→`ERR UNKNOWN` 均通过；LED 亮/灭、全亮/全灭、LCD 清屏后仅显示 `Hello` 物理验证通过。
- 修复主循环移除 `Key_Proc()`/`LCD_Proc()`，避免原 `i num` 覆盖 LCD；固件归档 `firmware/release/command_firmware.hex`，sha256 `782335e7119029e61077abe0c0dec167b948660417a201ce43c33823b7e48058`。

## 待办

| # | 事项 | 影响 | 下一步 |
|---|---|---|---|
| 1 | M1b：ADC/PWM 命令 | 完成 P0 硬件控制范围 | 从 `HAL_07_ADC1_TEST`、`HAL_10_1_Channel_PWM_Frq_TEST` 移植 BSP，扩展命令 |
| 2 | M2：Pi 后端 | 串口/HTTP 联调 | FastAPI + 持久串口 + `/api/device` |
| 3 | 组内分工 | 任务拆分与报告分工 | 用户确认 8–10 人角色 |
| 4 | 指导老师要求 | 是否强制 Proteus/焊接/PCB | 用户确认 |
| 5 | 前端方案 | Vue 构建版 vs 无构建 HTML | 推荐 PC 构建 Vue，Pi 静态托管 |
| 6 | 模型组合 | 0.5B 路由 + 1.5B 对话 vs 只用 0.5B | benchmark 后定 |
| 7 | 摄像头 | VLM 拍照问答 | 当前无摄像头；先做上传图片，摄像头可选 |

## 下一步（按顺序）

1. M1b：补 ADC/PWM 命令，重编译/烧录/实测。
2. 提交并推送当前工程到 GitHub（排除 `.agents/`、指导书、个人作业）。
3. M2：Pi venv + FastAPI + 持久串口 + `/api/device`。
4. M3：下载 Qwen2.5-0.5B/1.5B，llama.cpp benchmark。
5. M4：前端骨架（PC 构建 Vue，Pi 静态托管）。

## 重要决策

| 决策 | 结论 | 原因 |
|---|---|---|
| 调试/烧录 | CMSIS-DAP + pyOCD（Keil G4 pack）+ PC Keil 兜底 | 板载是 Keil CMSIS-DAP，`st-flash` 不适用；已实测通过 |
| 串口 | 板载 CMSIS-DAP VCP，`/dev/ttyACM0` | 已双向验证；固件必须用 `GPIO_MODE_AF_PP`，禁用 `AF_OD` |
| 主链路 | UART 命令模式为 P0；Pi 烧录为 P1/P2 演示 | 命令模式已具备条件；烧录已验证但演示前仍需长稳测试 |
| VLM 输入 | 网页上传图片，不做 Pi 摄像头 | 当前无摄像头；上传图片足够课程演示 |
| 模型分工 | 0.5B 意图路由，1.5B 对话，SmolVLM-500M 选做 | Pi 4B 8GB 算力有限；小模型做结构化选择更稳 |
| LLM 边界 | 只输出结构化决策，后端白名单校验 | 防止幻觉直接操作硬件 |
| 前端 | PC 构建 Vue，Pi 静态托管；无构建 HTML 兜底 | Pi 没装 Node，避免在 Pi 上装整套前端工具链 |
| 烧录安全 | 只烧 manifest 内固件；烧录前备份 | 已实际备份 128KB，可作为回滚依据 |

## 已知问题

- **例程发送用 `sizeof(str)`**：会发 50 字节含尾零；正式固件改用 `strlen`。
- **VCP 仅 9600**：`stty -F /dev/ttyACM0 115200` 会阻塞（多个进程卡住）；高波特率需 USB-TTL。命令链路保持 9600。
- **VCP 仅接受单次持久会话**：后端必须常开串口句柄；烧录/复位后若写阻塞，重新枚举 USB（`authorized 0/1`）。
- **主循环已移除 `LCD_Proc()`**：原演示会每 500ms 写 `i num`，覆盖命令显示的 LCD 内容。
- **板载 VCP 早期出现过写阻塞**：复测已恢复；演示前做长稳测试，必要时保留 USB-TTL 备用。
- **无摄像头**：VLM 只能上传图片。
- **Python 3.8**：FastAPI/uvicorn/pydantic 需固定兼容版本。
- **磁盘 15GB**：模型与构建产物要控制；必要时外接 U 盘。
- **报告要求**：Proteus 对 Pi/LLM 不可仿真，需在报告中说明边界，只仿真 MCU 子系统/关键电路。

## 验证记录

| 日期 | 项目 | 命令/操作 | 结果 |
|---|---|---|---|
| 2026-11-18 | SSH 登录 | `ssh apple@192.168.49.50` | 成功 |
| 2026-11-18 | Pi 型号/内存 | `cat /proc/device-tree/model` / `free -h` | 4B Rev 1.5 / 8GB |
| 2026-11-18 | 系统 | `cat /etc/os-release` | Ubuntu 20.04.6 LTS |
| 2026-11-18 | 调试器 | `lsusb` / `udevadm info` | CMSIS-DAP `c251:f001`，`/dev/ttyACM0` |
| 2026-11-18 | pyOCD 安装 | `pip3 install --user pyocd==0.36.0` | 0.36.0 安装成功 |
| 2026-11-18 | 探针识别 | `pyocd list` | 可见 `CMSIS-DAP-PL 1001A0000000` |
| 2026-11-18 | Flash 备份 | `pyocd commander ... savemem 0x08000000 0x20000` | 通过，131072B，sha256 已记录 |
| 2026-11-18 | LED 烧录 | `pyocd flash ... HAL_01_LED_TEST.hex` | 通过，擦 3 扇区/写 5 页/2.82 kB/s |
| 2026-11-18 | USART 原始例程 | 9600 读 `/dev/ttyACM0` | 空（TX 为 `AF_OD`） |
| 2026-11-18 | 改 `AF_PP` 重编译 | Keil `UV4 -b` | 0 error/0 warning |
| 2026-11-18 | 烧录 AF_PP 版 | `pyocd flash ... HAL_05_USART_TEST_PP.hex` | 通过，擦 1 扇区/写 2 页/5.68 kB/s |
| 2026-11-18 | UART 双向 | 9600 读 + 发 5 字节 | 读到 `0000:Hello,world.`；LED 闪 5 下 |
| 2026-11-18 | 115200 尝试 | `stty -F /dev/ttyACM0 115200` | **阻塞 rc=124**，VCP 不支持 |
| 2026-11-18 | 回退 9600 | 烧 9600 AF_PP + 读串口 | 恢复 `0000:Hello,world.` |
| 2026-11-18 | 115200 验证 | `stty -F /dev/ttyACM0 115200` | **不支持**，阻塞；保持 9600 |
| 2026-11-18 | M1 编译 | Keil `UV4 -b` | 0 error / 0 warning |
| 2026-11-18 | M1 烧录 | `pyocd flash ... command_firmware.hex` | 通过，擦 26 页/写 26 页/4.32 kB/s |
| 2026-11-18 | M1 命令 | 持久串口会话 | `OK PONG`、`OK LED 1 1/0`、`OK LEDALL`、`OK LCD`、`OK LCDCLR`、`ERR UNKNOWN` |
| 2026-11-18 | M1 物理现象 | 人工观察 | LED1 亮/灭、全亮/全灭正确；LCD 清屏后仅 `Hello` |
| 2026-11-18 | ADC/PWM | 持久串口会话 | `ERR UNSUPPORTED`（M1b 待实现） |
| — | LLM benchmark | llama.cpp + 0.5B/1.5B | 未执行 |
