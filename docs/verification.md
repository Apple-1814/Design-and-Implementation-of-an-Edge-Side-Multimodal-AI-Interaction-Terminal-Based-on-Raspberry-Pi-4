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
| 模型下载 | ModelScope `Qwen2.5-0.5B-Instruct-GGUF` q4_k_m | 469MB，已完成（初版） |
| 模型升级 | ModelScope `Qwen2.5-1.5B-Instruct-GGUF` q4_k_m | 1.07GB，SHA256 校验一致 |
| llama.cpp 源码 | GitHub master tarball（38MB） | 已解压 |
| CMake 兼容 | Pi CMake 3.16.3；UI 脚本要求 ≥3.18 | `LLAMA_BUILD_UI=OFF` + `ui.h` 空实现 + 移除 `llama-ui` 链接 |
| llama-server 构建 | `cmake --build ... --target llama-server -j4` | **成功** |
| 模型加载 | `llama-server -m qwen... --port 8080` | `model loaded`，`/health` OK |
| 推理基准 | “用三句话介绍树莓派”，max_tokens=128 | 0.5B：38 tokens / 7.04s，**7.26 tok/s**；prompt 19.09 tok/s |
| 1.5B 基准 | 傅里叶/ISR/天空三问，max_tokens=120–160 | **3.02 tok/s**；prompt 6.9 tok/s；答完 40–60s |
| FastAPI 流式 | `POST /api/chat` | SSE 逐 token 返回，中文正常 |

### M4 前端（基础版）

| 项 | 操作 | 结果 |
|---|---|---|
| 首页 | `GET /` | 返回 `index.html` |
| 静态资源 | `GET /app.js`、`/style.css` | 200 |
| 功能 | 流式聊天、会话列表、设备面板、图片上传 | 已实现 |
| 视觉验收 | 浏览器 DOM + 截图 | DOM 通过（快捷问题/来源卡片/硬件命令）；截图 API 超时，视觉截图待补 |

### M5 VLM（基础验证）

| 项 | 操作 | 结果 |
|---|---|---|
| 模型下载 | SmolVLM-500M-Instruct Q8 + mmproj Q8 | 417MB + 104MB |
| 服务启动 | `llama-server --mmproj ... --port 8081` | `loaded multimodal model`，`/health` OK |
| 测试图 | 320×240 白底红圆 + `HELLO` | — |
| 直接推理 | “请描述这张图片”，max_tokens=64 | **34.11s**，返回 ` HELLO` |
| FastAPI | `POST /api/vision` | `{"ok": true, "response": " HELLO"}` |
| 前端 | 图片上传 → `/api/vision` | 已接入，待浏览器验收 |

### M6 整机稳定性（已验证）

| 项 | 结果 |
|---|---|
| 时长 | 1801.4 s（30 分钟） |
| 轮次 / 检查次数 | 180 轮 / **933 次检查** |
| 失败 | **0** |
| 最高温度 | 47.2°C |
| 最低空闲内存 | 6251 MB |
| VLM 单图检查 | 2 次均 `ok=True`，返回 `HELLO` |
| 覆盖 | 硬件命令（PING/LED/ADC/PWM）+ LLM 对话 + VLM 单图 |

### M7 报告与交付

| 项 | 产物 | 结果 |
|---|---|---|
| Word 报告 | `paper/课程设计报告.docx` | 478KB，封面 + 7 表 + 9 图 |
| 答辩 PPT | `paper/答辩PPT.pptx` | 11 页 |
| 插图 | `paper/figures/*.png` | 系统框图/电源树/接线/3 张流程/UART/PWM/UI 示意 |
| 30 分钟稳定性 | `scripts/stability_test.py` | 进行中（硬件/LLM 已连续通过） |
| 最终交付包 | 源码、固件、报告、PPT、复现说明 | 待最终提交 |

### M8 蓝桥杯知识库（2026-11-19）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| 构建 | `python scripts/build_knowledge.py` | 1610 片段 / 464 来源 / 2,628,717 chars |
| 覆盖 | PPT/PDF/DOCX/XLSX/源码压缩包 | 37 PPT、3 PDF、3 DOCX、3 XLSX、51 个源码包；过滤 HAL/CMSIS/构建产物 |
| 索引 | `knowledge/chunks.jsonl` + `manifest.json` | 3.5MB JSONL；sha256 见 manifest |
| 加载 | `GET /api/knowledge/status` | loaded=true；kinds: board 21 / code 921 / ioc 138 / ppt 66 / pdf 447 / docx 3 / xlsx 14 |
| 检索 | `GET /api/knowledge/search?q=LED怎么点亮` | 约 3ms；板卡事实卡 3.1 + 本机 `bsp_led.c` |
| 冒烟测试 | `python scripts/test_knowledge.py` | 10 个问答 PASS + 负例 PASS |
| 直答 | `POST /api/chat` LED/I2C/PWM/USART/LCD | **0.04s**；`mode=knowledge`；2 条来源 |
| 课件直答 | `POST /api/chat` NVIC/输入捕获 | **0.05s**；PPT 摘录 / 代码+PPT |
| 通用回答 | `POST /api/chat` “天气怎么样/代码是什么” | 14s/3.5s；`mode=llm`；天气不编造、代码给定义 |
| 日期时间 | `POST /api/chat` “今天几号” | **0.03s**；`mode=time`，用树莓派系统时间 |
| 身份路由 | `POST /api/chat` “你是谁/你好” | **0.04s**；`mode=meta/greeting`，正确介绍 Qwen2.5-1.5B 与知识库 |
| 树莓派事实 | `POST /api/chat` “树莓派是什么” | 0.04s；板卡事实卡第 12 节，说明 Pi 与 STM32 分工 |
| 硬件分流 | 前端“让 LED1 亮起来” | `OK LED 1 1`；随后“LED1 关”恢复 |
| 前端 DOM | 浏览器打开 `/`、快捷问题、来源卡片 | 通过；截图 API 30s 超时，未取得视觉截图 |
| 知识库排除 | `git status` / `.gitignore` | `knowledge/` 已忽略，不入库 |

### M9 双通道板卡控制（2026-11-19）

| 项 | 命令/操作 | 结果 |
|---|---|---|
| Keil 编译 | `UV4 -b firmware/MDK-ARM/HAL_01_LED_TEST.uvprojx` | **0 error / 0 warning** |
| 固件烧录 | `pyocd flash ... command_firmware.hex` | 擦 16 扇区 / 写 32 页；v0.3.0 |
| ADC1 | `GET /api/device/adc?ch=1` | `OK ADC 369`；0.297 V；PB12/ADC1_IN11 |
| ADC2 | `GET /api/device/adc?ch=2` | `OK ADC2 1414`；1.139 V；PB15/ADC2_IN15 |
| PWM1/2 设置 | `POST /api/device/pwm` ch=1/2 | `OK PWM 1 20` / `OK PWM 2 40` |
| PWM1/2 回读 | `GET /api/device/pwm` + `/pwm2` | 20% / 40%，与设置一致 |
| LED 单灯 | 前端下拉选 LD3 → 开 | `mask=04`，LD3 ● |
| LED 全控 | `/api/device/ledall` FF/00 | FF 全亮 / 00 全灭 |
| 前端面板 | 浏览器 DOM/数值检查 | 下拉选灯、ADC1/2、PWM1/2 同步；请求序号防乱序 |

### M10 LCD 被 READY 覆盖修复（2026-11-19）

| 项 | 操作 | 结果 |
|---|---|---|
| 根因 | 串口服务每次打开/重连都发送 `LCDCLR` + IP + `READY` 横幅 | 队友显示内容被覆盖 |
| 修复 | 横幅只在开机后 180s 内首次打开时发送；重连/服务重启不再覆盖 LCD | `banner_count=0`（晚启动时） |
| 重连测试 | LCD TEST1 → `/api/device/reconnect` → LCD TEST2 | 日志 `skip LCD banner`；TEST2 保留 |
| 并发测试 | 6 个客户端同时 POST `/api/device/lcd` | 6/6 `OK LCD`；`open_count` 不变 |
| 队友实测 | 日志 `LCD 1 stupid xyp` → `OK LCD`；随后服务重启 | `uptime=12178s`，日志 `skip LCD banner`，不再覆盖 |
| 诊断字段 | `/api/device/status` | `open_count`、`banner_count`、`last_open_at` |
| 串口日志 | `~/ai-terminal/logs/serial.log` | 记录 OPEN/命令/响应/横幅 |

### M11 前端主题（2026-11-22）

| 项 | 操作 | 结果 |
|---|---|---|
| 主题 | 顶栏“配色”下拉 | 浅蓝白 / 薄荷青 / 暖白橙 / 浅紫 / 深色 |
| 变量 | `html[data-theme]` CSS 变量 | 背景、气泡、代码块、来源卡片、控制面板同步切换 |
| 记忆 | 切换后刷新页面 | `localStorage` 恢复上次主题 |
| 视觉 | 浏览器截图 | 浅蓝白、薄荷青、深色通过；文字/控件对比度正常 |
| 缓存 | `style.css?v=0.8.1` / `app.js?v=0.8.1` | 避免旧主题缓存 |

### M12 上下文与历史对话（2026-11-22）

| 项 | 操作 | 结果 |
|---|---|---|
| 上下文 | 4 轮历史 + 当前问题 | `prompt_n=674`、`cache_n=256`，未超 `-c 2048` |
| 记忆 | 3 轮“记住 7319” | 回答 `7319`；`prompt_n=146` |
| 历史预算 | 后端最近 4 条，每条 ≤600 字，总 ≤1500 字 | 已生效 |
| RAG 预算 | 3 个来源 / 700 字 | 已生效 |
| 输出长度 | `max_tokens` 上限 160 | 已生效 |
| 历史保存 | 浏览器 `localStorage` | 刷新/重开保留 |
| 单条删除 | 会话列表 × + confirm | 列表和 localStorage 同步减少 |
| 清空全部 | “清空全部历史” + confirm | 保留一个空白新会话 |

### M13 高强度问答测试（2026-11-22）

| 组别 | 数量 | 结果 |
|---|---:|---|
| 快速事实（31 组×6 问法） | 186 | **186/186**，0.02–0.05s |
| 深度/概念问题 | 25 | **25/25**，含 ADC 滤波、LCD+RTC、边沿/PWM/I2C 定义 |
| 定义问法（40 术语×5） | 200 | **200/200**，含“什么叫/含义/解释一下” |
| 对比/FAQ/板卡/引脚/事实/开放 | 31 | **31/31**，6 对比 + 5 FAQ + 5 板卡 + 6 引脚 + 10 事实 + 4 开放 |
| 回答质量合计 | 236 | **236/236**，无复读、无提示词泄漏、无无来源引用、引脚/事实不贴代码 |
| 多轮 | 6 | **6/6**，7319 记忆 0.01s、PWM/USART 追问 0.04s |
| 并发 | 12 请求 | **1/1**，0.30s，最大 0.22s |
| **合计** | **454** | **454/454** |

修复：记忆问题被直答误判、定义题拼接历史、LED→PWM 代码串模块、源码压过板卡事实、跨模块只答一个、“下降沿”复读/概念错误、未收录术语拒绝回答、提示词泄漏、G431 污染记忆数字、“定时器引脚”贴代码/PPT、事实题返回整节资料。LLM 已升级 Qwen2.5-1.5B（3.02 tok/s）。报告见 `docs/qa_stress_report.md`。

### M14 代码讲解页（2026-11-23）

| 项 | 操作 | 结果 |
|---|---|---|
| 页面切换 | 点击“AI 对话 / 代码讲解” | 两视图正常切换，聊天记录保留 |
| LED 操作 | 全亮、单灯关 | 自动打开 LED 讲解，摘要含本次命令 |
| LED 动态 | LD3 开（FB→FF）、LD3 关（FF→FB） | 操作片段自动生成 `mask |=` / `mask &= ~`、前后位图与 `LED_Disp()` 参数 |
| LCD 操作 | 显示 Hello2 | 自动打开 LCD 讲解，代码含实际字符串 `"Hello2"` |
| ADC 操作 | 读取 ADC2 | 自动打开 ADC 讲解，代码含 `getADC2()` 与 1421/1.145V |
| PWM 操作 | 应用 20%/40% | 自动打开 PWM 讲解，代码含 `PWM_SetDuty(20)` / `SetDuty2(40)` |
| 内容 | 四套指南 | 时钟→引脚→外设→main 完整代码 + 文字流程；本次操作卡片置顶 |
| 复制 | 复制按钮 | 显示“已复制” |
| 视觉 | 1280×720 截图 | 双栏布局正常，操作卡片自动换行、完整代码可滚动 |

### M15 输入框历史提问（2026-11-23）

| 项 | 操作 | 结果 |
|---|---|---|
| 单会话切换 | 草稿 `draft-test`，↑↑↓↓ | 依次召回 `让 LED1 亮起来` → `I2C 读写 AT24C02 怎么写？` → 回到 `让 LED1 亮起来` → 恢复草稿 |
| 发送后更新 | 发送“LED 怎么点亮？”后按 ↑ | 立即召回该问题 |
| 多行保护 | `line1\nline2` 中按 ↑/↓ | 仅移动光标，输入内容不变 |
| 会话隔离 | 切换会话后按 ↑ | 只读取当前会话的用户提问 |
| 范围 | 当前会话 | 新建/清空/发送后重置历史游标 |

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
| M3 | llama.cpp + Qwen2.5-1.5B benchmark | **已验证**：1.5B 3.02 tok/s（0.5B 初版 7.26 tok/s） |
| M4 | 前端聊天 UI | DOM 验证通过；视觉截图待补 |
| M5 | SmolVLM 上传图片问答 | **基础验证**：单图 34.11s，返回 `HELLO` |
| M6 | 整机联调 30 分钟稳定性 | **已验证**：933 次检查 / 0 失败；最高 47.2°C |
| M7 | 报告、图表、演示、PPT | **Word/PPT/图表/稳定性数据已完成** |
| M8 | 蓝桥杯知识库/RAG/助教前端 | **已验证**：1610 片段；直答 0.04s；模型回退 20–60s |
| M9 | 8 LED / ADC×2 / PWM×2 | **已验证**：ADC1/2、PWM1/2、LED 全控；物理波形待 HIL |
