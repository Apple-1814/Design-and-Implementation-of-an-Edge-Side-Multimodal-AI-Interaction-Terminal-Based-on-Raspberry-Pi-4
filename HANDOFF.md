# HANDOFF — 当前状态

> 覆盖式维护，≤200 行。详细方案见 `计划书.md`。
> 更新时间：2026-11-19 20:45

## 当前阶段

实测评估完成；**M1–M10 全部验证**；**M8 蓝桥杯知识库已上线**：1610 片段 / 464 来源，板卡/源码/课件直答约 0.04s，开放问题才调用 Qwen2.5-0.5B；前端为“蓝桥杯 AI 助教”，附资料来源与快捷问题。**M9 板卡控制增强**：8 LED 下拉选择 + 全亮/全灭，ADC1+ADC2、PWM1+PWM2 双通道，固件 v0.3.0 已烧录。**M10**：LCD 横幅只在首次打开串口时发送，重连不再覆盖队友显示内容。**M11**：前端默认浅蓝+白，顶栏可切换浅蓝白/薄荷青/暖白橙/浅紫/深色 5 套主题，选择记忆在浏览器。**M12**：上下文扩到最近 4 条/总 1500 字、RAG 700 字/3 来源、输出 160 tokens；历史会话保存在 localStorage，支持单条删除/清空全部。**M13**：212 道问答回归全部通过，修复记忆/定义误路由、跨模块代码串味、板卡事实被源码压过等问题。

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
- **M2 后端完成**：FastAPI + pyserial 持久句柄；`/api/device/status|ping|led|lcd|lcd/clear|adc|pwm` 全部通过；静态 `/`、`/app.js`、`/style.css` 200。
- **M4 基础前端完成**：`web/index.html` + `style.css` + `app.js`，流式聊天、会话列表、设备面板、图片占位；待浏览器视觉验收。
- **自然语言硬件路由**：`/api/chat` 先走中文规则路由，`让 LED1 亮起来`、`LCD 显示 Hello`、`读取 ADC`、`PWM 50` 均执行并返回 ACK；未命中再交给 LLM。
- **M3 完成**：ModelScope Qwen2.5-0.5B Q4_K_M（469MB）；llama.cpp master 构建成功（CMake 3.16 UI 兼容问题通过 `LLAMA_BUILD_UI=OFF` + `ui.h` 空实现 + 移除 `llama-ui` 链接绕过）；38 tokens/7.04s，**7.26 tok/s**，prompt 19.09 tok/s；`/api/chat` SSE 正常。
- **M5 完成（基础）**：SmolVLM-500M Q8 + mmproj 加载；320×240 测试图 34.11s 返回 `HELLO`；`/api/vision` 可用，前端图片上传已接入。
- **M7 完成（初版）**：`paper/课程设计报告.docx`（封面 + 7 表 + 9 图）、`paper/答辩PPT.pptx`（10 页）、`paper/figures/*.png`（系统框图/电源树/接线/流程图/UART/PWM/UI 示意）；脚本 `make_figures.py`、`make_ui_mock.py`、`build_report_docx.py`、`build_ppt.py`。
- **M6 稳定性通过**：1801.4s / 180 轮 / **933 次检查 / 0 失败**；最高 47.2°C；最低空闲 6251MB；VLM 2 次单图检查 OK。数据在 `paper/stability_summary.json`。
- **开机自启完成**：`llama.service`、`vlm.service`、`ai-terminal.service` 均 enabled/active；重启验证 API **22s** 上线；eth0 固定 `192.168.49.50`；LCD 显示 IP/READY；新增 `pi/systemd/`、`scripts/install_services.sh`、`docs/课堂演示网络配置.md`。
- **M8 知识库完成**：
  - PC 侧 `scripts/build_knowledge.py` 提取 37 份 PPT（OLE 文本原子）、3 份 PDF、3 份 DOCX、3 份 XLSX、51 个源码压缩包（仅 `.c/.h/.ioc`，过滤 HAL/CMSIS/构建产物），并加入 `docs/board_facts.md` 与本机固件。
  - 生成 `knowledge/chunks.jsonl`（1610 片段 / 2.62MB 文本）+ `manifest.json`；`knowledge/` 已 gitignore，不上传。
  - `pi/app/knowledge.py`：中文 bigram + ASCII 标识符 + 同义词 BM25；板卡事实卡/本机固件加权；`/api/knowledge/status|search|reload`。
  - `/api/chat`：硬件规则路由 → 知识库直答（板卡/本机固件/官方 BSP/课件摘录）→ 0.5B RAG 回退 → 0.5B 通用回答（天气/日期有安全约束）；SSE 先发 `sources`，前端显示“知识库直答/RAG 生成”和可展开来源。
  - 前端：品牌改为“蓝桥杯 AI 助教”、CT117E-M4 副标题、8 个快捷问题、知识库片段数、来源卡片；硬件控制面板保留。
  - 实测：LED/USART/I2C/PWM/LCD/入门/真题/竞赛简介/NVIC/输入捕获均 **0.04–0.05s 直答**；硬件命令“让 LED1 亮起来”仍执行 `OK LED 1 1`。
  - 身份/问候修复：`你是谁/你能做什么` → `mode=meta`，`你好/谢谢` → `mode=greeting`；普通无资料问题交 Qwen；树莓派运行环境已加入事实卡第 12 节。
- **M9 板卡控制增强**：
  - 固件 v0.3.0：ADC2（PB15/ADC2_IN15）、PWM2（PA3/TIM15_CH2），PWM1/2 均 1kHz、0–100%；新增 `ADC2?`/`PWM2?`，`PWM <ch>` 支持 ch=1/2。
  - 后端：`/api/device/adc?ch=1|2`、`/api/device/pwm2`、`/api/device/leds`、`/api/device/ledall`；单灯命令返回完整位图。
  - 前端：LED 改为下拉框选 LD1–LD8 + 开/关 + 全亮/全灭/回读；ADC1/ADC2 独立读取与电压；PWM1/PWM2 双滑杆 + 应用两路 + 回读；请求序号防止旧回包覆盖。
  - 实测：ADC1=369、ADC2=1414；PWM1 20%/PWM2 40% 设置与回读一致；LD3 单灯、全亮 FF、全灭 00；前端数值/位图同步。
- **M10 LCD 覆盖修复**：串口服务原来每次 open/重连都发 `LCDCLR` + IP + `READY`，会覆盖队友显示内容；改为仅在开机后 180s 内首次打开时发横幅，重连/服务重启跳过。新增 `open_count/banner_count/last_open_at` 状态和 `~/ai-terminal/logs/serial.log`；重连与 6 并发 LCD 测试通过。
- **M11 前端配色**：默认浅蓝+白；顶栏“配色”下拉可切换浅蓝白/薄荷青/暖白橙/浅紫/深色；颜色变量覆盖聊天气泡、代码块、来源卡片、控制面板；选择存 `localStorage`。静态资源使用 `?v=0.8.1` 避免旧缓存。
- **M12 上下文与历史**：后端最多 4 条历史（每条 ≤600 字、总 ≤1500 字），RAG 3 来源/700 字，输出 ≤160 tokens；前端会话历史继续存 `localStorage`，每条带删除按钮，另有“清空全部历史”。实测 4 轮历史 prompt_n=674（cache_n=256），未超 2048；3 轮数字记忆测试回答 7319。
- **M13 高强度问答**：`scripts/qa_mass.py` 186 道事实题（31 组×6 问法）+ 19 道深度题 + 6 组多轮 + 12 并发 = **212/212 通过**；新增命令速查/ST-Link/ADC 滤波/RTC 板卡事实；修复记忆问题被直答误判、定义题拼接历史、LED→PWM 代码串模块、源码压过板卡事实、跨模块只答一个等问题。报告见 `docs/qa_stress_report.md`。
- **局域网/跨网访问**：
  - 局域网：Pi `wlan0=192.168.1.165`（OpenWrt），其他电脑同一 Wi-Fi 打开 `http://192.168.1.165:8000/`；`eth0=192.168.49.50` 仅直连维护。面板/LCD 自动显示当前 Wi-Fi IP。
  - 跨网：Cloudflare quick tunnel 已运行；当前 `https://consensus-unlimited-sword-poly.trycloudflare.com`；公网请求需 Basic 密码（`~/.ai_terminal_access`，不入 Git），局域网访问免密。
  - 脚本：`scripts/start_tunnel.sh` / `scripts/stop_tunnel.sh`；临时 URL 重启后会变化，以日志为准。

## 待办

| # | 事项 | 影响 | 下一步 |
|---|---|---|---|
| 1 | 最终提交 + tag `v0.8.2` | 交付 | **已完成**（commit `c804e72`，tag 已推送） |
| 2 | PWM 物理波形/ADC 电位器变化 | HIL 证据 | PA2/PA3 与 PB12/PB15 万用表/示波器复测 |
| 3 | 组内分工 | 报告分工 | 用户确认 8–10 人角色 |
| 4 | 指导老师要求 | 仿真/焊接/PCB | 用户确认 |
| 5 | 摄像头 | 可选扩展 | 当前无摄像头 |
| 6 | 实物照片/UI 截图/封面信息 | 报告完整性 | 组员补拍/填写 |
| 7 | 图片型真题 OCR | 真题题面覆盖 | 可选；当前真题汇编/OneNote 仅目录 |

## 下一步（按顺序）

1. **已完成**：commit `c804e72` + tag `v0.8.2`（含 212 题问答回归、路由修复、上下文/主题/历史、知识库 1610 片段）。
2. 组员补拍实物照片、替换 UI 示意图、填写封面信息；按 `docs/课堂演示网络配置.md` 彩排。
3. 可选：PWM/ADC 物理复测；图片型真题 OCR。

## 重要决策

| 决策 | 结论 | 原因 |
|---|---|---|
| 调试/烧录 | CMSIS-DAP + pyOCD（Keil G4 pack）+ PC Keil 兜底 | 板载是 Keil CMSIS-DAP，`st-flash` 不适用；已实测通过 |
| 串口 | 板载 CMSIS-DAP VCP，`/dev/ttyACM0` | 已双向验证；固件必须用 `GPIO_MODE_AF_PP`，禁用 `AF_OD` |
| 主链路 | UART 命令模式 + 本地知识库 RAG；Pi 烧录为 P1/P2 演示 | 命令/RAG 已具备条件；烧录已验证 |
| VLM 输入 | 网页上传图片，不做 Pi 摄像头 | 当前无摄像头；上传图片足够课程演示 |
| 模型分工 | 规则路由硬件命令；RAG 直答板卡/源码；0.5B 只处理开放问题 | Pi 4B 算力有限；0.5B 长上下文约 19 tok/s，直答可避免 30–80s 延迟 |
| LLM 边界 | 硬件动作只走白名单规则；LLM 不直接操作硬件 | 防止幻觉直接控制板子 |
| 知识库 | PC 构建 JSONL → Pi 纯 Python BM25；直答优先 | 无需向量库/额外服务；1610 片段查询 3ms |
| 前端 | 无构建 HTML/CSS/JS，Pi 静态托管 | Pi 没装 Node；浏览器已验证 |
| 烧录安全 | 只烧 manifest 内固件；烧录前备份 | 已实际备份 128KB，可作为回滚依据 |

## 已知问题

- **例程发送用 `sizeof(str)`**：会发 50 字节含尾零；正式固件改用 `strlen`。
- **VCP 仅 9600**：`stty -F /dev/ttyACM0 115200` 会阻塞（多个进程卡住）；高波特率需 USB-TTL。命令链路保持 9600。
- **VCP 仅接受单次持久会话**：后端必须常开串口句柄；烧录/复位后若写阻塞，重新枚举 USB（`authorized 0/1`）。
- **主循环已移除 `LCD_Proc()`**：原演示会每 500ms 写 `i num`，覆盖命令显示的 LCD 内容。
- **PWM/ADC 物理验证待补**：PA2 0/50/100% 电压、PB12 电位器变化需万用表/示波器复测；串口回读已通过。
- **板载 VCP 早期出现过写阻塞**：复测已恢复；演示前做长稳测试，必要时保留 USB-TTL 备用。
- **无摄像头**：VLM 只能上传图片。
- **Python 3.8**：FastAPI/uvicorn/pydantic 需固定兼容版本。
- **磁盘 15GB**：模型与构建产物要控制；必要时外接 U 盘。
- **报告要求**：Proteus 对 Pi/LLM 不可仿真，需在报告中说明边界，只仿真 MCU 子系统/关键电路。
- **知识库限制**：3 份真题 DOCX 与 422 页 OneNote PDF 主要是截图，未 OCR，只能检索目录/标题；题面需查原文件。旧平台（F103/STC15）内容已降权，只作原理参考。
- **0.5B 回退慢**：开放问题 RAG 约 20–60s；板卡/源码/课件类已走毫秒级直答。课堂演示优先用快捷问题。

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
| 2026-11-18 | M1b ADC/PWM | 持久串口会话 | `OK ADC 1759`；`OK PWM 1 0/50/100`；`PWM?` 回读一致 |
| 2026-11-18 | M2 后端 | uvicorn + curl | `/api/device/*` 全部通过；静态 `/`、`app.js` 200 |
| 2026-11-18 | 自然语言硬件 | `POST /api/chat` | `让 LED1 亮起来`→`OK LED 1 1`；LCD/ADC/PWM 均 OK |
| 2026-11-18 | M4 前端 | `GET /` | 返回 `index.html`；视觉验收待做 |
| 2026-11-18 | M3 LLM | `llama-server` + `/api/chat` | 38 tokens/7.04s；**7.26 tok/s**；中文正常 |
| 2026-11-18 | M5 VLM | SmolVLM-500M + `/api/vision` | **34.11s**；返回 `HELLO` |
| 2026-11-18 | 开机自启 | `sudo reboot` + `curl /api/info` | **22s API 上线**；三个服务 enabled/active；eth0 固定 192.168.49.50 |
| 2026-11-18 | M6 稳定性 | `scripts/stability_test.py --duration 1800` | 1801.4s / **933 次检查 / 0 失败**；最高 47.2°C；最低空闲 6251MB |
| 2026-11-18 | M7 Word | `python scripts/build_report_docx.py` | 478KB；7 表；9 图 |
| 2026-11-18 | M7 PPT | `python scripts/build_ppt.py` | 当前 11 页 |
| 2026-11-19 | M8 构建 | `python scripts/build_knowledge.py` | 1610 片段 / 464 来源 / 2.62MB 文本 |
| 2026-11-19 | M8 检索 | `/api/knowledge/search?q=LED` | 3ms；板卡事实卡/本机固件命中 |
| 2026-11-19 | M8 直答 | `/api/chat` LED/I2C/PWM/USART/LCD | **0.04s**；来源 2 条 |
| 2026-11-19 | M8 课件 | NVIC / 输入捕获 | 0.05s；PPT 摘录 / 代码 + PPT |
| 2026-11-19 | M8 通用 | “天气怎么样/代码是什么/今天几号” | 14s/3.5s/0.03s；天气不编造，日期用系统时间 |
| 2026-11-19 | 前端 DOM | 浏览器打开页面、快捷问题、来源卡片 | 通过；截图 API 超时，未取得视觉截图 |
| 2026-11-19 | 硬件分流 | 前端“让 LED1 亮起来” | `OK LED 1 1`；随后关闭 |
| 2026-11-19 | 提交/标签 | `git push origin main` / `v0.6.0` | commit `3152139`，tag 已推送 |
| 2026-11-19 | M9 固件 | Keil `UV4 -b` + pyOCD | 0 error/0 warning；烧录 32 页；v0.3.0 |
| 2026-11-19 | M9 ADC | `GET /api/device/adc?ch=1/2` | ADC1=369 / ADC2=1414；电压 0.297/1.139V |
| 2026-11-19 | M9 PWM | `POST /api/device/pwm` ch=1/2 | 20%/40% 设置与回读一致 |
| 2026-11-19 | M9 LED | `/leds`、`/ledall`、单灯 | LD3 单灯、FF 全亮、00 全灭 |
| 2026-11-19 | M9 前端 | 下拉选灯、双 ADC、双 PWM | 位图 04、PWM 回读 20%/40% 同步 |
| 2026-11-19 | 提交/标签 | `git push origin main` / `v0.7.0` | commit `c038f6e`，tag 已推送 |
| 2026-11-19 | 局域网访问 | `curl http://192.168.1.165:8000/` | 200；其他电脑同一 Wi-Fi 可用 |
| 2026-11-19 | 公网无密码 | `curl -I https://…trycloudflare.com/` | **401** |
| 2026-11-19 | 公网带密码 | `curl -I -u admin:… https://…/` | **200**；静态资源/SSE 正常 |
| 2026-11-19 | 公网身份头 | `/api/whoami` | `cf_connecting_ip` 可见，`remote_auth=true` |
| 2026-11-19 | M10 重连 | LCD TEST1 → reconnect → LCD TEST2 | 日志 `skip LCD banner`，TEST2 保留 |
| 2026-11-19 | M10 并发 | 6 客户端同时 LCD | 6/6 `OK LCD`；`open_count=2/banner_count=1` |
| 2026-11-19 | M10 队友 | 日志 `LCD 1 stupid xyp` → `OK LCD`；服务重启 uptime=12178s | `skip LCD banner`，不再覆盖 |
| 2026-11-22 | M11 主题 | 浏览器切换 5 套主题并刷新 | 主题生效、localStorage 记忆；浅蓝白/薄荷青截图通过 |
| 2026-11-22 | M12 上下文 | 4 轮历史 + 当前问题 | `prompt_n=674`、`cache_n=256`，未超 2048 |
| 2026-11-22 | M12 记忆 | 3 轮“记住 7319” | 回答 `7319`；`prompt_n=146` |
| 2026-11-22 | M12 历史 | 新建/删除会话、刷新 | localStorage 同步；单条删除成功 |
| 2026-11-22 | M13 快速 | 186 道事实题（fast_only） | **186/186**；0.02–0.05s |
| 2026-11-22 | M13 深度 | 19 道开放/跨模块题 | **19/19**；含 ADC 滤波、LCD+RTC |
| 2026-11-22 | M13 多轮/并发 | 6 组多轮 + 12 并发 | **6/6 + 1/1**；记忆 0.01s、并发 0.33s |
| 2026-11-22 | 提交/标签 | `git push origin main` / `v0.8.2` | commit `c804e72`，tag 已推送 |
| 2026-11-22 | Pi 部署 | `curl /api/info` | 版本 0.8.2，知识库 1610 片段，服务 active |
| — | PWM 物理波形 | PA2/PA3 万用表/示波器 | 待 HIL（0/50/100% ≈ 0/1.65/3.3V） |
